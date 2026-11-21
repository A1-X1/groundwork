"""Distance (m) to the nearest rail, Underground, Overground, DLR or tram station."""

from __future__ import annotations

import pandas as pd

from . import _osm, _synthetic
from ._common import LayerMeta
from ._geo import nearest_distance, points_xy

META = LayerMeta(
    id="dist_station", label="Distance to station", unit="m", kind="proximity",
    description="Straight-line distance from the hex centre to the nearest station or Underground entrance.",
    source="OpenStreetMap railway=station, railway=subway_entrance, public_transport=station",
    depends_on=("population_density",),
)


def fetch() -> list[tuple[float, float]]:
    return _osm.element_points(_osm.query("stations", [
        'nwr["railway"="station"]', 'node["railway"="subway_entrance"]',
        'nwr["public_transport"="station"]'], geometry=False))


def to_hex(raw: list[tuple[float, float]], grid: pd.DataFrame) -> pd.Series:
    return nearest_distance(grid, points_xy(raw))


def synthetic(grid: pd.DataFrame) -> pd.Series:
    w = grid["raw_population_density"].to_numpy() if "raw_population_density" in grid \
        else _synthetic.population_density(grid)
    return to_hex(_synthetic.sample_points(grid, META.id, 650, w**1.4), grid)
