"""Distance (m) to the nearest high-voltage (≥ 132 kV) electricity substation."""

from __future__ import annotations

import re

import pandas as pd

from . import _osm, _synthetic
from ._common import LayerMeta
from ._geo import nearest_distance, points_xy

META = LayerMeta(
    id="dist_substation", label="Distance to HV substation", unit="m", kind="proximity",
    description=("Distance to the nearest substation tagged ≥ 132 kV (falls back to all mapped "
                 "substations if voltages are missing). Large loads need a grid connection here."),
    source="OpenStreetMap power=substation via Overpass API",
)
MIN_VOLTAGE = 132_000


def _max_voltage(tags: dict[str, str]) -> int:
    nums = [int(v) for v in re.findall(r"\d+", tags.get("voltage", ""))]
    return max(nums) if nums else 0


def fetch() -> list[tuple[float, float]]:
    els = _osm.query("substations", ['nwr["power"="substation"]'], geometry=False)
    hv = [e for e in els if _max_voltage(e.get("tags", {})) >= MIN_VOLTAGE]
    return _osm.element_points(hv if len(hv) >= 10 else els)


def to_hex(raw: list[tuple[float, float]], grid: pd.DataFrame) -> pd.Series:
    return nearest_distance(grid, points_xy(raw))


def synthetic(grid: pd.DataFrame) -> pd.Series:
    pts = [p for line in _synthetic.hv_lines() for p in line]
    extra = _synthetic.sample_points(grid, META.id, 45, _synthetic.uhi(grid) + 0.3, jitter_m=600)
    return to_hex(pts + extra, grid)
