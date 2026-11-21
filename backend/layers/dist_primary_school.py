"""Distance (m) to the nearest open primary school."""

from __future__ import annotations

import pandas as pd

from . import _schools, _synthetic
from ._common import LayerMeta
from ._geo import nearest_distance, points_xy

META = LayerMeta(
    id="dist_primary_school", label="Distance to primary school", unit="m", kind="proximity",
    description="Distance from the hex centre to the nearest open primary school.",
    source="DfE Get Information About Schools (GIAS); OpenStreetMap amenity=school as fallback",
    depends_on=("population_density",),
)


def fetch() -> pd.DataFrame:
    return _schools.schools()


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    sel = raw[raw["phase"] == "primary"]
    return nearest_distance(grid, points_xy(zip(sel["lon"], sel["lat"], strict=True)))


def synthetic(grid: pd.DataFrame) -> pd.Series:
    return nearest_distance(grid, points_xy(synthetic_points(grid)))


def synthetic_points(grid: pd.DataFrame) -> list[tuple[float, float]]:
    w = grid["raw_population_density"].to_numpy() if "raw_population_density" in grid \
        else _synthetic.population_density(grid)
    return _synthetic.sample_points(grid, META.id, 1800, w)
