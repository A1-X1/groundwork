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


def data_dir() -> Path:
    """``$GROUNDWORK_DATA_DIR``, else data/processed if built, else the committed sample."""
    env = os.environ.get("GROUNDWORK_DATA_DIR")
    if env:
        return Path(env)
    if (PROCESSED_DIR / "grid.parquet").exists() and (PROCESSED_DIR / "layers.json").exists():
        return PROCESSED_DIR
    return SAMPLE_DIR


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
    return GridData(directory=directory, frame=frame, layers=layers, build=build)
