"""Fine particulates (PM2.5) from the Open-Meteo Air Quality API (CAMS European reanalysis)."""

from __future__ import annotations

import pandas as pd

from . import _openmeteo, _places, _synthetic
from ._common import LayerMeta

META = LayerMeta(
    id="air_quality_pm25", label="Fine particulates (PM2.5)", unit="µg/m³", kind="raster",
    description="Annual mean surface PM2.5 concentration.",
    source=f"Open-Meteo Air Quality API (CAMS Europe), {_openmeteo.YEAR}",
)


def fetch() -> pd.DataFrame:
    return _openmeteo.air_stats()


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    return _openmeteo.interpolate(raw, META.id, grid)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    uhi = _synthetic.uhi(grid)
    noise = _synthetic.smooth_noise(grid, META.id)
    return pd.Series(7.5 + 2.8 * uhi + 1.2 * _synthetic.gaussian(grid, *_places.HEATHROW, 3000) + 0.4 * noise, index=grid.index)
