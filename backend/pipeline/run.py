"""Run all (or some) layers over a region's grid and write grid.parquet + layers.json.

    python -m backend.pipeline.run                          # London detail grid
    python -m backend.pipeline.run --region uk              # UK (res 7) from global sources
    python -m backend.pipeline.run --region all             # every region in regions.yaml, in order
    python -m backend.pipeline.run --layers crime_rate,dist_station
    python -m backend.pipeline.run --offline                # never download
    python -m backend.pipeline.run --region uk --prune-raw  # delete raw downloads afterwards

Output: data/processed/regions/<region>/ (or --out). London may use synthetic London-shaped
fallbacks; national regions use real global sources or mark a layer *unavailable*
(neutral 0.5, raw = null). Normalised values are stored as uint8 (0–255) and raw values
as float32, zstd-compressed, so even the USA grid stays in the tens of megabytes.
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
from backend.layers import _global
from backend.layers._common import RAW_DIR, REPO_ROOT, OfflineError, SourceUnavailable, set_region
from backend.layers._geo import fill_gaps

from .build_grid import build_grid
from .normalise import normalise

log = logging.getLogger("groundwork.pipeline")
PROCESSED = REPO_ROOT / "data" / "processed"
DEFAULT_OUT = PROCESSED  # base; each region writes to <base>/regions/<id>/


def region_dir(region: str, base: Path = PROCESSED) -> Path:
    return base / "regions" / region


def run_layer_national(layer_id: str, grid: pd.DataFrame,
                       statuses: dict[str, Any]) -> tuple[pd.Series, dict[str, Any]]:
    """National regions: a real global source, a derivation, a region-aware template, or unavailable."""
    mod = layers.load(layer_id)
    started = time.perf_counter()
    try:
        if layer_id in _global.SOURCES:
            raw = _global.compute(layer_id, grid)
            status: dict[str, Any] = {"status": "real", "source": _global.SOURCES[layer_id][1]}
        elif mod.META.derived and all(statuses.get(d, {}).get("status") == "real" for d in mod.META.depends_on):
            raw = mod.to_hex(mod.fetch(), grid)
            status = {"status": "real"}
        elif getattr(mod.META, "source", "").startswith(("USGS", "OpenStreetMap")) and not mod.META.is_mask:
            raw = mod.to_hex(mod.fetch(), grid)  # region-aware templates (USGS, OSM ≤ MAX_TILES)
            status = {"status": "real"}
        else:
            raise SourceUnavailable(f"no global source for {layer_id} (available in London only)")
        if raw.isna().all():
            raise RuntimeError("source produced no values")
        nan_share = float(raw.isna().mean())
        values = fill_gaps(grid, raw) if nan_share < 0.5 else raw
        if nan_share:
            status["gap_filled_share"] = round(nan_share, 4)
    except Exception as exc:  # noqa: BLE001 — never fabricate outside London
        reason = str(exc).replace(str(REPO_ROOT) + os.sep, "")[:300]
        status = {"status": "unavailable", "reason": reason}
        values = pd.Series(np.nan, index=grid.index)
    status["seconds"] = round(time.perf_counter() - started, 2)
    log.info("%-24s %-11s %6.1fs", layer_id, status["status"], status["seconds"])
    return values, status


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
    if "reason" in status:  # keep build.json portable: no absolute machine paths
        status["reason"] = status["reason"].replace(str(REPO_ROOT) + os.sep, "")
    status["seconds"] = round(time.perf_counter() - started, 2)
    log.info("%-24s %-9s %6.1fs", layer_id, status["status"], status["seconds"])
    return values, status


def run(layer_ids: list[str] | None = None, out: Path | None = None, offline: bool = False,
        region: str = "london", progress: Any = None) -> pd.DataFrame:
    """``progress(done, total, layer_id, status)`` is called after each layer is built."""
    if offline:
        os.environ["GROUNDWORK_OFFLINE"] = "1"
    out = out or region_dir(region)
    out.mkdir(parents=True, exist_ok=True)
    grid = build_grid(region_id=region).copy()
    set_region(grid.attrs)
    national = grid.attrs.get("kind") == "national"
    log.info("region %s: %d cells at res %d", region, len(grid), grid.attrs["resolution"])
    selected = set(layer_ids or layers.LAYER_IDS)
    unknown = selected - set(layers.LAYER_IDS)
    if unknown:
        raise SystemExit(f"unknown layers: {sorted(unknown)}")

    todo = [lid for lid in layers.LAYER_IDS if lid in selected]
    done = 0
    previous = _read_previous(out)
    statuses: dict[str, Any] = previous.get("layers", {}) if layer_ids else {}
    for layer_id in layers.LAYER_IDS:  # dependency order
        col = f"raw_{layer_id}"
        if layer_id not in selected and previous.get("grid") is not None and col in previous["grid"]:
            grid[col] = previous["grid"][col].reindex(grid.index)
            continue
        if layer_id not in selected and not _needed_by(layer_id, selected):
            continue
        grid[col], statuses[layer_id] = (run_layer_national(layer_id, grid, statuses) if national
                                         else run_layer(layer_id, grid, statuses))
        if progress and layer_id in selected:
            done += 1
            progress(done, len(todo), layer_id, statuses[layer_id])

    return _write(grid, statuses, out)


def _needed_by(layer_id: str, selected: set[str]) -> bool:
    return any(layer_id in layers.load(s).META.depends_on for s in selected)


def _read_previous(out: Path) -> dict[str, Any]:
    prev: dict[str, Any] = {}
    if (out / "grid.parquet").exists():
        prev["grid"] = pd.read_parquet(out / "grid.parquet").set_index("h3")
    if (out / "build.json").exists():
        prev["layers"] = json.loads((out / "build.json").read_text(encoding="utf-8"))["layers"]
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
        # unavailable → neutral 0.5, except masks: unknown means "not excluded" (0)
        norm = normalise(raw, m.normalise).fillna(0.0 if m.is_mask else 0.5)
        table[layer_id] = np.round(norm.to_numpy() * 255).astype("uint8")  # 1 byte per value
        ok = raw.notna().any()
        meta.append({**m.public(), "min": float(raw.min()) if ok else None, "max": float(raw.max()) if ok else None})
    for layer_id in layers.LAYER_IDS:
        col = f"raw_{layer_id}"
        if col in grid:
            table[col] = grid[col].astype("float32")
    table = table.reset_index().rename(columns={"index": "h3"})
    table.to_parquet(out / "grid.parquet", index=False, compression="zstd", compression_level=9)
    (out / "layers.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    build = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "region": grid.attrs.get("region", "london"),
        "resolution": grid.attrs.get("resolution", 8),
        "boundary": grid.attrs.get("boundary"),
        "label": grid.attrs.get("label"),
        "kind": grid.attrs.get("kind", "city"),
        "country": grid.attrs.get("country"),
        "bbox": [round(v, 4) for v in grid.attrs.get("bbox", ())],
        "normalised_dtype": "uint8",
        "cells": len(table),
        "layers": {k: statuses[k] for k in layers.LAYER_IDS if k in statuses},
    }
    (out / "build.json").write_text(json.dumps(build, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    real = sorted(k for k, v in build["layers"].items() if v["status"] == "real")
    synth = sorted(k for k, v in build["layers"].items() if v["status"] == "synthetic")
    unav = sorted(k for k, v in build["layers"].items() if v["status"] == "unavailable")
    size = (out / "grid.parquet").stat().st_size / 1e6
    log.info("wrote %s (%d cells, %d layers, %.1f MB)", out / "grid.parquet", len(table), len(meta), size)
    if unav:
        log.info("UNAVAILABLE (%d): %s", len(unav), ", ".join(unav))
    log.info("REAL (%d): %s", len(real), ", ".join(real) or "-")
    log.info("SYNTHETIC (%d): %s", len(synth), ", ".join(synth) or "-")
    return table


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layers", help="comma-separated layer ids to (re)build; others are kept")
    ap.add_argument("--offline", action="store_true", help="never download; synthetic where not cached")
    ap.add_argument("--refresh", action="store_true", help="re-download every cached source now")
    ap.add_argument("--region", default="london", help="region id from regions.yaml, or 'all'")
    ap.add_argument("--out", type=Path, default=None, help="output directory (default data/processed/regions/<id>)")
    ap.add_argument("--prune-raw", action="store_true", help="delete data/raw downloads after building")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    if args.refresh:
        os.environ["GROUNDWORK_REFRESH"] = "1"
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    from .region import region_ids

    regions = region_ids() if args.region == "all" else [args.region]
    for rid in regions:
        run([s.strip() for s in args.layers.split(",")] if args.layers else None,
            args.out if len(regions) == 1 else None, args.offline, rid)
    if args.prune_raw:
        import shutil

        mb = _global.raw_dir_size_mb()
        shutil.rmtree(RAW_DIR, ignore_errors=True)
        log.info("pruned %.0f MB of raw downloads from %s", mb, RAW_DIR)


if __name__ == "__main__":
    main()
