"""Soil moisture (m³/m³) from Open-Meteo historical daily data (ERA5), 10-year normals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import _openmeteo, _synthetic
from ._common import LayerMeta

META = LayerMeta(
    id="soil_moisture_mean", label="Soil moisture", unit="m³/m³", kind="raster",
    description="Mean volumetric soil water content in the top 7 cm over the normals period (drainage, foundations, vegetation).",
    source=f"Open-Meteo Historical Weather API (ERA5 daily), {_openmeteo.NORMALS[0]}–{_openmeteo.NORMALS[1]}",
    depends_on=("elevation",),
)


def fetch() -> pd.DataFrame:
    return _openmeteo.normals_stats()


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    return _openmeteo.interpolate(raw, META.id, grid)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    noise = _synthetic.smooth_noise(grid, META.id)
    return pd.Series(0.30 - 0.03 * _synthetic.uhi(grid) + 0.03 * np.exp(-_synthetic.dist_thames_m(grid) / 3000) + 0.01 * noise, index=grid.index)
