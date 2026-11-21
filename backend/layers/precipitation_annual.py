"""Annual precipitation (mm/yr) from Open-Meteo historical daily data (ERA5), 10-year normals."""

from __future__ import annotations

import pandas as pd

from . import _openmeteo, _synthetic
from ._common import LayerMeta

META = LayerMeta(
    id="precipitation_annual", label="Annual precipitation", unit="mm/yr", kind="raster",
    description="Mean yearly rainfall total over the normals period.",
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
    return pd.Series(610 - 40 * _synthetic.east_west(grid) + 0.4 * elev + 15 * noise, index=grid.index)
