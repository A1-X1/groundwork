"""Share of the hex mapped as residential land use in OpenStreetMap."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import _osm, _synthetic
from ._common import LayerMeta
from ._geo import share_inside

META = LayerMeta(
    id="land_use_residential", label="Residential land", unit="share of hex", kind="aggregate",
    description="Fraction of the hex covered by landuse=residential (from 7 sample points per hex).",
    source="OpenStreetMap landuse=residential via Overpass API",
    depends_on=("population_density",),
    normalise="identity",
)


def fetch() -> list:
    return _osm.element_polygons(_osm.query("landuse_residential", ['nwr["landuse"="residential"]']))


def to_hex(raw: list, grid: pd.DataFrame) -> pd.Series:
    return share_inside(grid, raw)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    dens = grid["raw_population_density"].to_numpy() if "raw_population_density" in grid \
        else _synthetic.population_density(grid)
    share = 1 / (1 + np.exp(-(dens - 4500) / 1500)) + 0.12 * _synthetic.smooth_noise(grid, META.id, 150, 1200)
    return pd.Series(np.clip(share, 0, 1), index=grid.index)
