"""Loading the per-hex grid (grid.parquet) and layer metadata (layers.json)."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
SAMPLE_DIR = REPO_ROOT / "data" / "sample"
LONDON_SAMPLE = SAMPLE_DIR / "regions" / "london"


def _region_dirs(root: Path) -> dict[str, Path]:
    """Region grids under ``root``: ``regions/<id>/`` plus a legacy top-level grid (London)."""
    found: dict[str, Path] = {}
    if (root / "grid.parquet").exists() and (root / "layers.json").exists():
        build = root / "build.json"
        rid = json.loads(build.read_text()).get("region", "london") if build.exists() else "london"
        found[rid] = root
    for d in sorted((root / "regions").glob("*")) if (root / "regions").exists() else []:
        if (d / "grid.parquet").exists() and (d / "layers.json").exists():
            found[d.name] = d
    return found


def region_dirs() -> dict[str, Path]:
    """All available regions: ``$GROUNDWORK_DATA_DIR`` alone if set, else the committed sample
    overlaid by anything built in data/processed (processed wins per region)."""
    env = os.environ.get("GROUNDWORK_DATA_DIR")
    if env:
        return _region_dirs(Path(env))
    return {**_region_dirs(SAMPLE_DIR), **_region_dirs(PROCESSED_DIR)}


def data_dir() -> Path:
    """Directory of the London (default) grid, kept for single-region callers."""
    dirs = region_dirs()
    return dirs.get("london") or next(iter(dirs.values()), SAMPLE_DIR)


@dataclass
class GridData:
    directory: Path
    frame: pd.DataFrame                 # index h3; columns <layer_id> (0–1) and raw_<layer_id>
    layers: list[dict[str, Any]]        # list_layers() payload, in pipeline order
    build: dict[str, Any] = field(default_factory=dict)

    @property
    def layer_ids(self) -> list[str]:
        return [m["id"] for m in self.layers]

    @property
    def resolution(self) -> int:
        return int(self.build.get("resolution", 8))

    @property
    def region(self) -> str:
        return str(self.build.get("region", "london"))

    @property
    def synthetic_layers(self) -> set[str]:
        return {k for k, v in self.build.get("layers", {}).items() if v.get("status") == "synthetic"}

    def fingerprint(self) -> str:
        """Stable hash of the normalised layer values (to invalidate saved models)."""
        arr = np.ascontiguousarray(self.frame[self.layer_ids].to_numpy(dtype=np.float32))
        h = hashlib.sha1(arr.tobytes())
        h.update(",".join(self.frame.index).encode())
        return h.hexdigest()[:16]


def load(directory: Path | None = None) -> GridData:
    directory = Path(directory) if directory else data_dir()
    grid_path, meta_path = directory / "grid.parquet", directory / "layers.json"
    if not grid_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"no grid.parquet/layers.json in {directory}; run `python -m backend.pipeline.run`")
    frame = pd.read_parquet(grid_path)
    frame = frame.set_index("h3")
    for col in frame.columns:  # normalised values are stored as uint8 0–255
        if frame[col].dtype == np.uint8:
            frame[col] = frame[col].astype("float32") / 255.0
    import h3

    centres = [h3.cell_to_latlng(c) for c in frame.index]
    frame["lat"] = [c[0] for c in centres]
    frame["lon"] = [c[1] for c in centres]
    layers = json.loads(meta_path.read_text())
    missing = [m["id"] for m in layers if m["id"] not in frame or f"raw_{m['id']}" not in frame]
    if missing:
        raise ValueError(f"{grid_path} is missing columns for layers {missing}")
    build_path = directory / "build.json"
    build = json.loads(build_path.read_text()) if build_path.exists() else {}
    frame.attrs["synthetic"] = {k: v.get("status") == "synthetic" for k, v in build.get("layers", {}).items()}
    frame.attrs["region"] = build.get("region", "london")
    frame.attrs["country"] = build.get("country", "GBR")
    return GridData(directory=directory, frame=frame, layers=layers, build=build)


def load_all() -> dict[str, GridData]:
    """Every region, finest resolution first; layers missing in a region are added as
    neutral (0.5, raw NaN) so every profile can score everywhere."""
    grids = {rid: load(d) for rid, d in region_dirs().items()}
    if not grids:
        raise FileNotFoundError("no region grids found; run `python -m backend.pipeline.run`")
    all_meta: dict[str, dict[str, Any]] = {}
    for g in grids.values():
        for m in g.layers:
            all_meta.setdefault(m["id"], m)
    for g in grids.values():
        have = set(g.layer_ids)
        for lid, m in all_meta.items():
            if lid not in have:
                g.frame[lid] = np.float32(0.0 if lid in ("flood_zone_3", "protected_land") else 0.5)
                g.frame[f"raw_{lid}"] = np.nan
                g.layers.append({**m, "min": None, "max": None})
                g.build.setdefault("layers", {})[lid] = {"status": "unavailable", "reason": "not built for this region"}
    return dict(sorted(grids.items(), key=lambda kv: -kv[1].resolution))
