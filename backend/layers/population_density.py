"""Residents per km² from ONS Census 2021 (TS001) at LSOA level."""

from __future__ import annotations

import h3
import pandas as pd

from . import _ons, _synthetic
from ._common import LayerMeta
from ._geo import count_in_hex, fill_gaps, smooth_neighbours

META = LayerMeta(
    id="population_density", label="Population density", unit="residents/km²", kind="aggregate",
    description="Usual residents per km², LSOA populations assigned to hexes by population-weighted centroid.",
    source="ONS Census 2021 TS001 (LSOA) + ONS LSOA 2021 population-weighted centroids",
)


def fetch() -> pd.DataFrame:
    return _ons.population()


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    people = count_in_hex(grid, raw["lat"], raw["lon"], weights=raw["value"])
    area = pd.Series([h3.cell_area(c, unit="km^2") for c in grid.index], index=grid.index)
    # LSOAs are often bigger than a hex, so spread over the 1-ring to avoid empty holes.
    density = smooth_neighbours(grid, people / area, rings=1)
    return fill_gaps(grid, density)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    return pd.Series(_synthetic.population_density(grid), index=grid.index)
