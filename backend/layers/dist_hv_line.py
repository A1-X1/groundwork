"""Distance (m) to the nearest overhead power line or high-voltage cable."""

from __future__ import annotations

import pandas as pd

from . import _osm, _synthetic
from ._common import LayerMeta
from ._geo import lines_to_points, nearest_distance

META = LayerMeta(
    id="dist_hv_line", label="Distance to HV line", unit="m", kind="proximity",
    description="Distance to the nearest mapped transmission line (power=line) or HV cable.",
    source="OpenStreetMap power=line, power=cable via Overpass API",
)


def fetch() -> list[list[tuple[float, float]]]:
    return _osm.element_lines(_osm.query("hv_lines", ['way["power"="line"]', 'way["power"="cable"]["voltage"]']))


def to_hex(raw: list[list[tuple[float, float]]], grid: pd.DataFrame) -> pd.Series:
    return nearest_distance(grid, lines_to_points(raw, 100))


def synthetic(grid: pd.DataFrame) -> pd.Series:
    return to_hex(_synthetic.hv_lines(), grid)
