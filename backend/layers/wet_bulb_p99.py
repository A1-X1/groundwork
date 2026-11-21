"""Wet-bulb temperature (99th percentile) (°C) from Open-Meteo historical weather (ERA5 family)."""

from __future__ import annotations

import pandas as pd

from . import _openmeteo, _synthetic
from ._common import LayerMeta

META = LayerMeta(
    id="wet_bulb_p99", label="Wet-bulb temperature (99th percentile)", unit="°C", kind="raster",
    description="99th percentile of hourly wet-bulb temperature (Stull 2011): the design point for evaporative cooling.",
    source=f"Open-Meteo Historical Weather API (ERA5 / ERA5-Land), {_openmeteo.YEAR}",
    depends_on=("elevation",),
)


def fetch() -> pd.DataFrame:
    return _openmeteo.weather_stats()


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    return _openmeteo.interpolate(raw, META.id, grid, lapse=True)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    uhi = _synthetic.uhi(grid)
    elev = grid["raw_elevation"].to_numpy() if "raw_elevation" in grid else _synthetic.elevation(grid)
    noise = _synthetic.smooth_noise(grid, META.id)
    return pd.Series(19.1 + 0.8 * uhi - 0.004 * elev + 0.1 * noise, index=grid.index)
