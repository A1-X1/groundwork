"""Solar irradiance (kWh/m²/yr) from Open-Meteo historical weather (ERA5 family)."""

from __future__ import annotations

import pandas as pd

from . import _openmeteo, _synthetic
from ._common import LayerMeta

META = LayerMeta(
    id="solar_irradiance", label="Solar irradiance", unit="kWh/m²/yr", kind="raster",
    description="Annual global horizontal irradiance (sum of hourly shortwave radiation).",
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
    return pd.Series(1010 - 25 * _synthetic.grid_xy(grid)[:, 1] / 25000 - 12 * uhi + 4 * noise, index=grid.index)
