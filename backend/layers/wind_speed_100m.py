"""Wind speed at 100 m (m/s) from Open-Meteo historical hourly weather (ERA5)."""

from __future__ import annotations

import pandas as pd

from . import _openmeteo, _synthetic
from ._common import LayerMeta

META = LayerMeta(
    id="wind_speed_100m", label="Wind speed at 100 m", unit="m/s", kind="raster",
    description="Mean hourly wind speed at a typical turbine hub height (100 m).",
    source=f"Open-Meteo Historical Weather API (ERA5 hourly), {_openmeteo.YEAR}",
    depends_on=("elevation",),
)


def fetch() -> pd.DataFrame:
    return _openmeteo.wind100_stats()


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    return _openmeteo.interpolate(raw, META.id, grid)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    uhi = _synthetic.uhi(grid)
    elev = grid["raw_elevation"].to_numpy() if "raw_elevation" in grid else _synthetic.elevation(grid)
    noise = _synthetic.smooth_noise(grid, META.id)
    return pd.Series(6.2 - 1.2 * uhi + 0.008 * elev + 0.2 * noise, index=grid.index)
