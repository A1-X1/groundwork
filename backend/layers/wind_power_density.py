"""Wind power density (W/m²) from Open-Meteo historical hourly weather (ERA5)."""

from __future__ import annotations

import pandas as pd

from . import _openmeteo, _synthetic
from ._common import LayerMeta

META = LayerMeta(
    id="wind_power_density", label="Wind power density", unit="W/m²", kind="raster",
    description="Mean available wind power per m² of rotor at 100 m (0.5·ρ·v³): what a turbine can actually harvest.",
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
    return pd.Series(330 - 120 * uhi + 0.9 * elev + 20 * noise, index=grid.index)
