"""Mean relative humidity (%) from Open-Meteo historical weather (ERA5 family)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import _openmeteo, _synthetic
from ._common import LayerMeta

META = LayerMeta(
    id="humidity_mean", label="Mean relative humidity", unit="%", kind="raster",
    description="Mean hourly relative humidity at 2 m.",
    source=f"Open-Meteo Historical Weather API (ERA5 / ERA5-Land), {_openmeteo.YEAR}",
    depends_on=("elevation",),
)


def fetch() -> pd.DataFrame:
    return _openmeteo.weather_stats()


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    return _openmeteo.interpolate(raw, META.id, grid, lapse=False)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    uhi = _synthetic.uhi(grid)
    noise = _synthetic.smooth_noise(grid, META.id)
    return pd.Series(79.0 - 4.0 * uhi + 2.0 * np.exp(-_synthetic.dist_thames_m(grid) / 2000) + 0.6 * noise, index=grid.index)
