"""Reference evapotranspiration (mm/yr) from Open-Meteo historical daily data (ERA5), 10-year normals."""

from __future__ import annotations

import pandas as pd

from . import _openmeteo, _synthetic
from ._common import LayerMeta

META = LayerMeta(
    id="evapotranspiration_annual", label="Reference evapotranspiration", unit="mm/yr", kind="raster",
    description="FAO-56 reference evapotranspiration per year: water demand of vegetation and evaporative cooling.",
    source=f"Open-Meteo Historical Weather API (ERA5 daily), {_openmeteo.NORMALS[0]}–{_openmeteo.NORMALS[1]}",
    depends_on=("elevation",),
)


def fetch() -> pd.DataFrame:
    return _openmeteo.normals_stats()


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    return _openmeteo.interpolate(raw, META.id, grid)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    elev = grid["raw_elevation"].to_numpy() if "raw_elevation" in grid else _synthetic.elevation(grid)
    noise = _synthetic.smooth_noise(grid, META.id)
    return pd.Series(640 + 25 * _synthetic.uhi(grid) - 0.1 * elev + 6 * noise, index=grid.index)
