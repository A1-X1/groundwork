"""Warming trend (°C/decade) from Open-Meteo historical daily data (ERA5), 10-year normals."""

from __future__ import annotations

import pandas as pd

from . import _openmeteo, _synthetic
from ._common import LayerMeta

META = LayerMeta(
    id="temp_trend_decade", label="Warming trend", unit="°C/decade", kind="raster",
    description="Linear trend of annual mean temperature over the normals period (historical warming rate).",
    source=f"Open-Meteo Historical Weather API (ERA5 daily), {_openmeteo.NORMALS[0]}–{_openmeteo.NORMALS[1]}",
    depends_on=("elevation",),
)


def fetch() -> pd.DataFrame:
    return _openmeteo.normals_stats()


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    return _openmeteo.interpolate(raw, META.id, grid)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    noise = _synthetic.smooth_noise(grid, META.id)
    return pd.Series(0.45 + 0.05 * _synthetic.uhi(grid) + 0.02 * noise, index=grid.index)
