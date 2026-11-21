"""English Index of Multiple Deprivation score (higher = more deprived)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import _ons, _synthetic
from ._common import LayerMeta
from ._geo import fill_gaps, smooth_neighbours

META = LayerMeta(
    id="deprivation_index", label="Deprivation", unit="IMD score", kind="aggregate",
    description="Index of Multiple Deprivation score of the LSOAs in and around the hex (higher = more deprived).",
    source="MHCLG English Indices of Deprivation (File 7, LSOA) + ONS LSOA centroids",
)


def fetch() -> pd.DataFrame:
    return _ons.imd()


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    import h3

    cells = [h3.latlng_to_cell(a, b, 8) for a, b in zip(raw["lat"], raw["lon"], strict=True)]
    mean = pd.Series(raw["value"].to_numpy(), index=cells).groupby(level=0).mean()
    return fill_gaps(grid, smooth_neighbours(grid, mean.reindex(grid.index), rings=1))


def synthetic(grid: pd.DataFrame) -> pd.Series:
    d = _synthetic.dist_centre_m(grid) / 1000
    score = 22 + 9 * _synthetic.east_west(grid) + 6 * np.exp(-(((d - 5) / 5) ** 2)) - 0.35 * d
    score += 5 * _synthetic.smooth_noise(grid, META.id, 150, 1500)
    return pd.Series(np.clip(score, 2, 65), index=grid.index)
