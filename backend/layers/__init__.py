"""Data layers: one module per layer id, plus YAML-defined layers in ``generated/``.

``LAYER_IDS`` (built-ins in dependency order, then generated layers) is computed at
import; call ``refresh()`` after adding a generated layer in the same process.
"""

from __future__ import annotations

import importlib
from types import ModuleType

from ._common import LayerMeta

BUILTIN_IDS: tuple[str, ...] = (
    "elevation",
    "slope",
    "mean_temp_annual",
    "summer_max_temp",
    "wet_bulb_p99",
    "free_cooling_hours",
    "humidity_mean",
    "wind_speed_mean",
    "solar_irradiance",
    "wind_speed_100m",
    "wind_power_density",
    "precipitation_annual",
    "soil_moisture_mean",
    "evapotranspiration_annual",
    "temp_trend_decade",
    "population_density",
    "land_use_residential",
    "crime_rate",
    "deprivation_index",
    "median_house_price",
    "flood_risk",
    "flood_zone_3",
    "air_quality_no2",
    "air_quality_pm25",
    "grid_carbon_intensity",
    "dist_station",
    "dist_substation",
    "dist_hv_line",
    "dist_fibre_ix",
    "dist_water_body",
    "green_space_access",
    "dist_major_road",
    "dist_primary_school",
    "dist_secondary_school",
    "school_quality_nearby",
    "protected_land",
)


_generated: dict[str, object] = {}
LAYER_IDS: tuple[str, ...] = BUILTIN_IDS


def refresh() -> tuple[str, ...]:
    """Re-read generated/*.yaml; returns the updated ``LAYER_IDS``."""
    global LAYER_IDS
    from . import _generic

    _generated.clear()
    for spec in _generic.load_specs():
        if spec.id in BUILTIN_IDS:
            raise ValueError(f"generated layer {spec.id!r} clashes with a built-in layer")
        _generated[spec.id] = _generic.module_for(spec)
    LAYER_IDS = BUILTIN_IDS + tuple(_generated)
    return LAYER_IDS


def load(layer_id: str) -> ModuleType:
    if layer_id in _generated:
        return _generated[layer_id]  # type: ignore[return-value]
    if layer_id not in BUILTIN_IDS:
        raise KeyError(f"unknown layer {layer_id!r}")
    return importlib.import_module(f"{__name__}.{layer_id}")


refresh()


def all_meta() -> list[LayerMeta]:
    return [load(i).META for i in LAYER_IDS]


__all__ = ["BUILTIN_IDS", "LAYER_IDS", "LayerMeta", "all_meta", "load", "refresh"]
