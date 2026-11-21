"""Mean wind speed (m/s) from Open-Meteo historical weather (ERA5 family)."""

from __future__ import annotations

import pandas as pd

from . import _openmeteo, _synthetic
from ._common import LayerMeta

META = LayerMeta(
    id="wind_speed_mean", label="Mean wind speed", unit="m/s", kind="raster",
    description="Mean hourly 10 m wind speed.",
    source=f"Open-Meteo Historical Weather API (ERA5 / ERA5-Land), {_openmeteo.YEAR}",
    depends_on=("elevation",),
)


def fetch() -> pd.DataFrame:
    return _openmeteo.weather_stats()


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    return _openmeteo.interpolate(raw, META.id, grid, lapse=False)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    uhi = _synthetic.uhi(grid)
    elev = grid["raw_elevation"].to_numpy() if "raw_elevation" in grid else _synthetic.elevation(grid)
    noise = _synthetic.smooth_noise(grid, META.id)
    return pd.Series(3.7 - 1.0 * uhi + 0.006 * elev + 0.15 * noise, index=grid.index)
