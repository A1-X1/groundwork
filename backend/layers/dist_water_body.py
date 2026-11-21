"""Distance (m) to the nearest river, canal or open water."""

from __future__ import annotations

import pandas as pd

from . import _osm, _synthetic
from ._common import LayerMeta
from ._geo import lines_to_points, nearest_distance

META = LayerMeta(
    id="dist_water_body", label="Distance to water", unit="m", kind="proximity",
    description="Distance to the nearest river, canal, reservoir or lake (cooling / process water access).",
    source="OpenStreetMap natural=water, waterway=river|canal via Overpass API",
)


def fetch() -> list[list[tuple[float, float]]]:
    return _osm.element_lines(_osm.query("water", [
        'way["natural"="water"]', 'relation["natural"="water"]', 'way["waterway"~"^(river|canal)$"]']))


def to_hex(raw: list[list[tuple[float, float]]], grid: pd.DataFrame) -> pd.Series:
    return nearest_distance(grid, lines_to_points(raw, 60))


def synthetic(grid: pd.DataFrame) -> pd.Series:
    return nearest_distance(grid, _synthetic.water_points(grid))
