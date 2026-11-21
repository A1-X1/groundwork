"""Distance (m) to the nearest motorway, trunk or primary road."""

from __future__ import annotations

import pandas as pd

from . import _osm, _synthetic
from ._common import LayerMeta
from ._geo import lines_to_points, nearest_distance

META = LayerMeta(
    id="dist_major_road", label="Distance to major road", unit="m", kind="proximity",
    description="Distance to the nearest motorway, trunk or primary road (access for heavy vehicles; also noise and pollution).",
    source="OpenStreetMap highway=motorway|trunk|primary via Overpass API",
)


def fetch() -> list[list[tuple[float, float]]]:
    return _osm.element_lines(_osm.query("major_roads", ['way["highway"~"^(motorway|trunk|primary)$"]']))


def to_hex(raw: list[list[tuple[float, float]]], grid: pd.DataFrame) -> pd.Series:
    return nearest_distance(grid, lines_to_points(raw, 50))


def synthetic(grid: pd.DataFrame) -> pd.Series:
    return to_hex(_synthetic.major_roads(), grid)
