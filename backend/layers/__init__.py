"""Data layers: one module per layer id. ``LAYER_IDS`` is in dependency order."""

from __future__ import annotations

import importlib
from types import ModuleType

from ._common import LayerMeta

LAYER_IDS: tuple[str, ...] = (
    "elevation",
    "slope",
    "mean_temp_annual",
    "summer_max_temp",
    "wet_bulb_p99",
    "free_cooling_hours",
    "humidity_mean",
    "wind_speed_mean",
    "solar_irradiance",
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


def load(layer_id: str) -> ModuleType:
    if layer_id not in LAYER_IDS:
        raise KeyError(f"unknown layer {layer_id!r}")
    return importlib.import_module(f"{__name__}.{layer_id}")


def all_meta() -> list[LayerMeta]:
    return [load(i).META for i in LAYER_IDS]


__all__ = ["LAYER_IDS", "LayerMeta", "all_meta", "load"]
