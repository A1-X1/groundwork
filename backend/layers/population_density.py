"""Residents per km² from ONS Census 2021 (TS001) at LSOA level."""

from __future__ import annotations

import h3
import pandas as pd

from . import _ons, _synthetic, _worldpop
from ._common import LayerMeta, SourceUnavailable
from ._geo import count_in_hex, fill_gaps, smooth_neighbours

META = LayerMeta(
    id="population_density", label="Population density", unit="residents/km²", kind="aggregate",
    description="Residents per km² from the WorldPop 100 m constrained grid (or ONS Census 2021 LSOAs when those files are present).",
    source="WorldPop 2020 constrained 100 m (CC BY 4.0); optional ONS Census 2021 TS001 by LSOA",
)


def fetch() -> pd.DataFrame | str:
    """ONS LSOA files if the user downloaded them (most precise in the UK), else WorldPop."""
    try:
        return _ons.population()
    except SourceUnavailable:
        return _worldpop.download("GBR")


def to_hex(raw: pd.DataFrame | str, grid: pd.DataFrame) -> pd.Series:
    if isinstance(raw, str):
        return fill_gaps(grid, _worldpop.density(raw, grid))
    people = count_in_hex(grid, raw["lat"], raw["lon"], weights=raw["value"])
    area = pd.Series([h3.cell_area(c, unit="km^2") for c in grid.index], index=grid.index)
    # LSOAs are often bigger than a hex, so spread over the 1-ring to avoid empty holes.
    density = smooth_neighbours(grid, people / area, rings=1)
    return fill_gaps(grid, density)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    return pd.Series(_synthetic.population_density(grid), index=grid.index)
