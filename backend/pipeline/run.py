"""Run all (or some) layers over the grid and write grid.parquet + layers.json.

    python -m backend.pipeline.run                    # everything, real sources where possible
    python -m backend.pipeline.run --layers crime_rate,dist_station
    python -m backend.pipeline.run --offline          # synthetic for anything not cached
    python -m backend.pipeline.run --offline --out data/sample   # regenerate the demo sample
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend import layers
from backend.layers._common import REPO_ROOT, OfflineError, SourceUnavailable
from backend.layers._geo import fill_gaps

from .build_grid import build_grid
from .normalise import normalise

log = logging.getLogger("groundwork.pipeline")
DEFAULT_OUT = REPO_ROOT / "data" / "processed"


def run_layer(layer_id: str, grid: pd.DataFrame,
              statuses: dict[str, Any] | None = None) -> tuple[pd.Series, dict[str, Any]]:
    """Compute one layer's raw values; fall back to synthetic on any failure."""
    mod = layers.load(layer_id)
    synthetic_deps = [d for d in mod.META.depends_on
                      if (statuses or {}).get(d, {}).get("status") == "synthetic"]
    started = time.perf_counter()
    status: dict[str, Any] = {"status": "real"}
    try:
        raw = mod.to_hex(mod.fetch(), grid)
        if raw.isna().all():
            raise RuntimeError("source produced no values")
        values = fill_gaps(grid, raw)
        nan_share = float(raw.isna().mean())
        if nan_share:
            status["gap_filled_share"] = round(nan_share, 4)
    except (OfflineError, SourceUnavailable) as exc:
        status = {"status": "synthetic", "reason": str(exc)}
        values = mod.synthetic(grid)
    except Exception as exc:  # noqa: BLE001 — the demo must never break on a bad source
        log.warning("%s: real source failed (%s: %s) — using synthetic", layer_id, type(exc).__name__, exc)
        status = {"status": "synthetic", "reason": f"{type(exc).__name__}: {exc}"}
        values = mod.synthetic(grid)
    if synthetic_deps and status["status"] == "real":
        if mod.META.derived:
            status = {"status": "synthetic", "reason": f"derived from synthetic {', '.join(synthetic_deps)}"}
        else:
            status["uses_synthetic"] = synthetic_deps
    values = values.reindex(grid.index).astype(float)
    if not np.isfinite(values).all():
        values = fill_gaps(grid, values.where(np.isfinite(values)))
    status["seconds"] = round(time.perf_counter() - started, 2)
    log.info("%-24s %-9s %6.1fs", layer_id, status["status"], status["seconds"])
    return values, status


def run(layer_ids: list[str] | None = None, out: Path = DEFAULT_OUT, offline: bool = False) -> pd.DataFrame:
    if offline:
        os.environ["GROUNDWORK_OFFLINE"] = "1"
    out.mkdir(parents=True, exist_ok=True)
    grid = build_grid().copy()
    selected = set(layer_ids or layers.LAYER_IDS)
    unknown = selected - set(layers.LAYER_IDS)
    if unknown:
        raise SystemExit(f"unknown layers: {sorted(unknown)}")

    previous = _read_previous(out)
    statuses: dict[str, Any] = previous.get("layers", {}) if layer_ids else {}
    for layer_id in layers.LAYER_IDS:  # dependency order
        col = f"raw_{layer_id}"
        if layer_id not in selected and previous.get("grid") is not None and col in previous["grid"]:
            grid[col] = previous["grid"][col].reindex(grid.index)
            continue
        if layer_id not in selected and not _needed_by(layer_id, selected):
            continue
        grid[col], statuses[layer_id] = run_layer(layer_id, grid, statuses)

    return _write(grid, statuses, out)


def _needed_by(layer_id: str, selected: set[str]) -> bool:
    return any(layer_id in layers.load(s).META.depends_on for s in selected)


def _read_previous(out: Path) -> dict[str, Any]:
    prev: dict[str, Any] = {}
    if (out / "grid.parquet").exists():
        prev["grid"] = pd.read_parquet(out / "grid.parquet").set_index("h3")
    if (out / "build.json").exists():
        prev["layers"] = json.loads((out / "build.json").read_text())["layers"]
    return prev


def _write(grid: pd.DataFrame, statuses: dict[str, Any], out: Path) -> pd.DataFrame:
    table = pd.DataFrame(index=grid.index)
    meta = []
    for layer_id in layers.LAYER_IDS:
        col = f"raw_{layer_id}"
        if col not in grid:
            continue
        m = layers.load(layer_id).META
        raw = grid[col].astype(float)
        table[layer_id] = normalise(raw, m.normalise).round(6)
        meta.append({**m.public(), "min": float(raw.min()), "max": float(raw.max())})
    for layer_id in layers.LAYER_IDS:
        col = f"raw_{layer_id}"
        if col in grid:
            table[col] = grid[col].astype(float).round(4)
    table = table.reset_index().rename(columns={"index": "h3"})
    table.to_parquet(out / "grid.parquet", index=False, compression="zstd")
    (out / "layers.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    build = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "region": grid.attrs.get("region", "london"),
        "resolution": grid.attrs.get("resolution", 8),
        "boundary": grid.attrs.get("boundary"),
        "cells": len(table),
        "layers": {k: statuses[k] for k in layers.LAYER_IDS if k in statuses},
    }
    (out / "build.json").write_text(json.dumps(build, indent=2, ensure_ascii=False) + "\n")
    real = sorted(k for k, v in build["layers"].items() if v["status"] == "real")
    synth = sorted(k for k, v in build["layers"].items() if v["status"] == "synthetic")
    log.info("wrote %s (%d cells, %d layers)", out / "grid.parquet", len(table), len(meta))
    log.info("REAL (%d): %s", len(real), ", ".join(real) or "-")
    log.info("SYNTHETIC (%d): %s", len(synth), ", ".join(synth) or "-")
    return table


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layers", help="comma-separated layer ids to (re)build; others are kept")
    ap.add_argument("--offline", action="store_true", help="never download; synthetic where not cached")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (default data/processed)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    run([s.strip() for s in args.layers.split(",")] if args.layers else None, args.out, args.offline)


if __name__ == "__main__":
    main()
