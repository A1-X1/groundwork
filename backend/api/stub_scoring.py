"""Stand-in for ``backend.scoring`` used until Person 1's real module lands.

Implements the frozen interface in ``shared/contracts/scoring_interface.md`` over the
real H3 res-8 cells of a rough Greater London outline. Every value is synthetic but
deterministic and spatially smooth (plausible gradients: urban heat island, Thames
flood plain, house prices falling eastwards...), so the map looks like a map.

Nothing here is real data. ``health()`` says so.
"""

from __future__ import annotations

import itertools
import math
from functools import cache
from typing import Any

import h3

RESOLUTION = 8
CENTRE = (51.495, -0.11)  # lat, lon of roughly Charing Cross

# Rough line of the Thames through London, (lon, lat).
THAMES: list[tuple[float, float]] = [
    (-0.50, 51.43), (-0.42, 51.43), (-0.33, 51.45), (-0.28, 51.48), (-0.22, 51.485),
    (-0.18, 51.47), (-0.12, 51.505), (-0.08, 51.508), (-0.03, 51.50), (0.00, 51.49),
    (0.05, 51.50), (0.12, 51.50), (0.20, 51.47), (0.33, 51.46),
]
# Green-belt-ish / designated blobs: (lon, lat, radius_km).
PROTECTED = [
    (-0.27, 51.44, 2.2), (-0.17, 51.57, 1.2), (0.03, 51.65, 3.0), (-0.45, 51.62, 3.5),
    (0.20, 51.33, 4.0), (-0.47, 51.36, 3.0), (-0.32, 51.44, 1.2),
]
STATIONS = [
    (-0.1236, 51.5308), (-0.1426, 51.5154), (-0.0886, 51.5050), (-0.1631, 51.4952),
    (-0.0755, 51.5178), (-0.1278, 51.4950), (-0.2250, 51.5100), (0.0170, 51.5430),
    (-0.0750, 51.4500), (-0.1900, 51.4200), (-0.3000, 51.5600), (0.0700, 51.4000),
    (-0.0200, 51.6000), (-0.3700, 51.4600), (0.1600, 51.5600), (-0.2100, 51.6100),
]
SUBSTATIONS = [
    (-0.20, 51.49), (0.01, 51.51), (-0.33, 51.54), (0.12, 51.47), (-0.05, 51.60),
    (-0.15, 51.40), (0.25, 51.53), (-0.42, 51.48),
]
FIBRE_IX = [(-0.0735, 51.5215), (0.0055, 51.5113), (-0.0207, 51.5089), (-0.4280, 51.5100)]

LAYER_META: list[tuple[str, str, str, str, str, str]] = [
    # id, label, unit, kind, description, source
    ("elevation", "Elevation", "m", "raster", "Ground height above sea level.", "Copernicus GLO-30 DEM"),
    ("slope", "Slope", "°", "raster", "Mean terrain slope.", "Derived from elevation"),
    ("mean_temp_annual", "Mean annual temperature", "°C", "raster", "Average 2 m air temperature.", "Open-Meteo (ERA5)"),
    ("summer_max_temp", "Summer max temperature", "°C", "raster", "Mean daily maximum, June–August.", "Open-Meteo (ERA5)"),
    ("wet_bulb_p99", "Wet-bulb 99th percentile", "°C", "raster", "Hourly wet-bulb temperature exceeded 1% of the year.", "Open-Meteo (ERA5)"),
    ("free_cooling_hours", "Free cooling hours", "h/yr", "raster", "Hours per year below 18 °C dry bulb.", "Derived from Open-Meteo hourly"),
    ("humidity_mean", "Mean relative humidity", "%", "raster", "Average relative humidity.", "Open-Meteo (ERA5)"),
    ("wind_speed_mean", "Mean wind speed", "m/s", "raster", "Average 10 m wind speed.", "Open-Meteo (ERA5)"),
    ("solar_irradiance", "Solar irradiance", "kWh/m²/yr", "raster", "Annual global horizontal irradiance.", "Open-Meteo (ERA5)"),
    ("flood_zone_3", "Flood zone 3", "flag", "raster", "Inside EA Flood Zone 3 (1% river / 0.5% sea annual chance).", "Environment Agency Flood Map for Planning"),
    ("flood_risk", "Flood risk", "index", "raster", "Relative flood likelihood.", "Environment Agency"),
    ("air_quality_no2", "NO₂", "µg/m³", "raster", "Annual mean nitrogen dioxide.", "Open-Meteo Air Quality"),
    ("air_quality_pm25", "PM2.5", "µg/m³", "raster", "Annual mean fine particulates.", "Open-Meteo Air Quality"),
    ("grid_carbon_intensity", "Grid carbon intensity", "gCO₂/kWh", "aggregate", "Regional average grid carbon intensity.", "National Grid ESO Carbon Intensity API"),
    ("crime_rate", "Crime rate", "per 1,000", "aggregate", "Street-level crimes per 1,000 residents, last 12 months.", "data.police.uk"),
    ("population_density", "Population density", "people/km²", "aggregate", "Usual residents per km².", "ONS Census 2021"),
    ("deprivation_index", "Deprivation", "IMD score", "aggregate", "Index of Multiple Deprivation score.", "English Indices of Deprivation 2019"),
    ("median_house_price", "Median house price", "£", "aggregate", "Median sale price, last 12 months.", "HM Land Registry Price Paid"),
    ("dist_primary_school", "Distance to primary school", "m", "proximity", "To nearest open primary school.", "GIAS"),
    ("dist_secondary_school", "Distance to secondary school", "m", "proximity", "To nearest open secondary school.", "GIAS"),
    ("school_quality_nearby", "School quality nearby", "share", "proximity", "Share of nearby schools rated Good or Outstanding.", "GIAS + Ofsted"),
    ("dist_station", "Distance to station", "m", "proximity", "To nearest rail, Tube or DLR station.", "OpenStreetMap"),
    ("dist_substation", "Distance to substation", "m", "proximity", "To nearest electrical substation.", "OpenStreetMap"),
    ("dist_hv_line", "Distance to HV line", "m", "proximity", "To nearest high-voltage power line.", "OpenStreetMap"),
    ("dist_fibre_ix", "Distance to internet exchange", "m", "proximity", "To nearest London IXP site.", "OpenStreetMap / seeded list"),
    ("dist_water_body", "Distance to water", "m", "proximity", "To nearest river or water body.", "OpenStreetMap"),
    ("green_space_access", "Distance to park", "m", "proximity", "To nearest public park.", "OpenStreetMap"),
    ("dist_major_road", "Distance to major road", "m", "proximity", "To nearest motorway, trunk or primary road.", "OpenStreetMap"),
    ("protected_land", "Protected land", "flag", "raster", "Designated site or Green Belt.", "Natural England / WDPA"),
    ("land_use_residential", "Residential land use", "share", "aggregate", "Share of hex with residential land use.", "OpenStreetMap"),
]

PROFILES: list[dict[str, Any]] = [
    {
        "id": "data_centre",
        "label": "Data centre",
        "description": "Low cooling demand, clean grid power, connectivity, low hazard.",
        "layers": {
            "free_cooling_hours": (0.20, "higher"), "wet_bulb_p99": (0.15, "lower"),
            "grid_carbon_intensity": (0.15, "lower"), "dist_substation": (0.15, "lower"),
            "dist_fibre_ix": (0.15, "lower"), "slope": (0.10, "lower"),
            "population_density": (0.10, "lower"),
        },
        "masks": ["flood_zone_3", "protected_land"],
        "has_model": True,
    },
    {
        "id": "house",
        "label": "House",
        "description": "Safe, connected, green and affordable places to live.",
        "layers": {
            "crime_rate": (0.20, "lower"), "dist_station": (0.15, "lower"),
            "green_space_access": (0.15, "lower"), "median_house_price": (0.15, "lower"),
            "school_quality_nearby": (0.10, "higher"), "air_quality_no2": (0.10, "lower"),
            "flood_risk": (0.10, "lower"), "dist_primary_school": (0.05, "lower"),
        },
        "masks": ["flood_zone_3", "protected_land"],
        "has_model": True,
    },
    {
        "id": "school",
        "label": "School",
        "description": "Where children live, clean air, safe streets and walkable access.",
        "layers": {
            "population_density": (0.25, "higher"), "air_quality_no2": (0.20, "lower"),
            "crime_rate": (0.15, "lower"), "dist_secondary_school": (0.15, "higher"),
            "dist_station": (0.10, "lower"), "dist_major_road": (0.10, "higher"),
            "green_space_access": (0.05, "lower"),
        },
        "masks": ["flood_zone_3", "protected_land"],
        "has_model": False,
    },
    {
        "id": "mine",
        "label": "Mine",
        "description": (
            "Water access, distance from people, road access and flat ground. London is a "
            "demo region; mineral deposit layers are future work."
        ),
        "layers": {
            "dist_water_body": (0.20, "lower"), "population_density": (0.30, "lower"),
            "dist_major_road": (0.20, "lower"), "slope": (0.15, "lower"),
            "dist_hv_line": (0.15, "lower"),
        },
        "masks": ["protected_land"],
        "has_model": False,
    },
]

DEFAULT_TOP_N = 5


# --------------------------------------------------------------------------- geometry


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dx = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat2 - lat1) * 110.57
    return math.hypot(dx, dy)


def _dist_to_points(lat: float, lon: float, pts: list[tuple[float, float]]) -> float:
    return min(_km(lat, lon, p[1], p[0]) for p in pts)


def _dist_to_polyline(lat: float, lon: float, line: list[tuple[float, float]]) -> float:
    best = math.inf
    kx = 111.32 * math.cos(math.radians(lat))
    ky = 110.57
    px, py = lon * kx, lat * ky
    for (x1, y1), (x2, y2) in itertools.pairwise(line):
        ax, ay, bx, by = x1 * kx, y1 * ky, x2 * kx, y2 * ky
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


def _noise(lat: float, lon: float, seed: int, scale: float = 1.0) -> float:
    """Smooth deterministic pseudo-noise in roughly [-1, 1]."""
    s = seed * 1.618
    x, y = lon * 30 * scale, lat * 45 * scale
    return (
        math.sin(x + s) * math.cos(y * 1.3 - s)
        + 0.5 * math.sin(2.1 * x - 1.7 * y + 2 * s)
        + 0.25 * math.cos(3.7 * y + 4.1 * x - 3 * s)
    ) / 1.75


def _london_outline() -> h3.LatLngPoly:
    clat, clon = CENTRE
    pts = []
    for i in range(72):
        a = 2 * math.pi * i / 72
        wobble = 1 + 0.07 * math.sin(3 * a + 0.4) + 0.05 * math.cos(5 * a)
        pts.append((clat + 0.185 * wobble * math.sin(a), clon + 0.37 * wobble * math.cos(a)))
    return h3.LatLngPoly(pts)


# --------------------------------------------------------------------------- grid


@cache
def _grid() -> dict[str, Any]:
    cells = sorted(h3.polygon_to_cells(_london_outline(), RESOLUTION))
    clat, clon = CENTRE
    raw: dict[str, list[float]] = {m[0]: [] for m in LAYER_META}
    centroids: list[tuple[float, float]] = []
    for c in cells:
        lat, lon = h3.cell_to_latlng(c)
        centroids.append((lat, lon))
        r = _km(lat, lon, clat, clon)
        thames = _dist_to_polyline(lat, lon, THAMES)
        urban = math.exp(-r / 11)
        n = lambda seed, k=1.0, la=lat, lo=lon: _noise(la, lo, seed, k)  # noqa: E731

        elev = 5 + 9 * thames + 8 * max(0.0, lat - 51.55) * 100 / 10 + 6 * n(1) + (
            25 if lat < 51.38 else 0
        )
        elev = max(1.0, elev)
        raw["elevation"].append(elev)
        raw["slope"].append(max(0.1, 1.5 + 1.2 * n(2, 2.5) + 0.04 * elev))
        raw["mean_temp_annual"].append(11.0 + 1.6 * urban - 0.006 * elev + 0.15 * n(3))
        raw["summer_max_temp"].append(22.5 + 2.2 * urban - 0.008 * elev + 0.3 * n(4))
        raw["wet_bulb_p99"].append(19.0 + 1.1 * urban + 0.25 * n(5))
        raw["free_cooling_hours"].append(7600 - 650 * urban + 4 * elev + 60 * n(6))
        raw["humidity_mean"].append(78 - 3 * urban + 2 * math.exp(-thames / 3) + n(7))
        raw["wind_speed_mean"].append(4.2 - 1.1 * urban + 0.02 * elev + 0.3 * n(8))
        raw["solar_irradiance"].append(1010 + 15 * n(9) - 8 * urban)
        fz3 = 1.0 if thames < 1.1 + 0.5 * n(10, 3) and elev < 18 else 0.0
        raw["flood_zone_3"].append(fz3)
        raw["flood_risk"].append(max(0.0, min(1.0, math.exp(-thames / 2.0) + 0.1 * n(11))))
        raw["air_quality_no2"].append(18 + 28 * urban + 4 * n(12, 2))
        raw["air_quality_pm25"].append(8 + 4 * urban + 0.8 * n(13, 2))
        raw["grid_carbon_intensity"].append(150 + 25 * (lon + 0.1) + 6 * n(14, 0.3))
        raw["crime_rate"].append(max(20.0, 55 + 170 * urban**1.5 + 25 * n(15, 2)))
        raw["population_density"].append(max(500.0, 2500 + 11000 * urban + 2500 * n(16, 2)))
        raw["deprivation_index"].append(max(3.0, 22 + 10 * (lon + 0.1) * 3 + 9 * n(17, 1.5)))
        raw["median_house_price"].append(
            max(250_000.0, 520_000 + 900_000 * urban - 350_000 * (lon + 0.1) + 90_000 * n(18, 2))
        )
        raw["dist_primary_school"].append(max(80.0, 450 + 300 * (1 - urban) + 200 * n(19, 5)))
        raw["dist_secondary_school"].append(max(150.0, 1100 + 700 * (1 - urban) + 400 * n(20, 4)))
        raw["school_quality_nearby"].append(max(0.2, min(1.0, 0.78 + 0.15 * n(21, 2))))
        raw["dist_station"].append(
            1000 * _dist_to_points(lat, lon, STATIONS) * 0.45 + 350 + 200 * n(22, 4)
        )
        raw["dist_substation"].append(1000 * _dist_to_points(lat, lon, SUBSTATIONS))
        raw["dist_hv_line"].append(max(50.0, 1000 * (0.6 + 1.8 * (1 + n(23, 1.3)))))
        raw["dist_fibre_ix"].append(1000 * _dist_to_points(lat, lon, FIBRE_IX))
        raw["dist_water_body"].append(max(30.0, 1000 * min(thames, 1.5 + 1.5 * (1 + n(24, 2)))))
        raw["green_space_access"].append(max(50.0, 600 + 450 * n(25, 4) - 150 * (1 - urban)))
        raw["dist_major_road"].append(max(30.0, 700 + 500 * n(26, 4)))
        prot = any(_km(lat, lon, p[1], p[0]) < p[2] for p in PROTECTED) or r > 23.5
        raw["protected_land"].append(1.0 if prot else 0.0)
        raw["land_use_residential"].append(max(0.0, min(1.0, 0.45 + 0.3 * urban + 0.2 * n(27))))

    norm = {k: _percentile_rank(v) for k, v in raw.items()}
    return {"cells": cells, "centroids": centroids, "raw": raw, "norm": norm,
            "index": {c: i for i, c in enumerate(cells)}}


def _percentile_rank(values: list[float]) -> list[float]:
    """Percentile rank in [0, 1]; ties share the mean rank. Binary flags stay 0/1."""
    if set(values) <= {0.0, 1.0}:
        return list(values)
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    n = len(values)
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        r = (i + j) / 2 / (n - 1) if n > 1 else 0.5
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return ranks


def _in_bbox(i: int, bbox: tuple[float, float, float, float] | None) -> bool:
    if bbox is None:
        return True
    lat, lon = _grid()["centroids"][i]
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def _check_bbox(bbox: tuple[float, float, float, float] | None) -> None:
    if bbox is None:
        return
    if len(bbox) != 4 or bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        raise ValueError("bbox must be (min_lon, min_lat, max_lon, max_lat) with min < max")


# --------------------------------------------------------------------------- interface


def list_layers() -> list[dict]:
    g = _grid()
    out = []
    for lid, label, unit, kind, desc, source in LAYER_META:
        vals = g["raw"][lid]
        out.append({
            "id": lid, "label": label, "unit": unit, "kind": kind, "description": desc,
            "source": f"{source} (synthetic stand-in)", "min": float(min(vals)),
            "max": float(max(vals)),
        })
    return out


def list_profiles() -> list[dict]:
    return [
        {
            "id": p["id"], "label": p["label"], "description": p["description"],
            "layers": [
                {"id": lid, "weight": w, "better": b} for lid, (w, b) in p["layers"].items()
            ],
            "masks": list(p["masks"]), "has_model": p["has_model"],
        }
        for p in PROFILES
    ]


def get_layer(layer_id: str, bbox: tuple[float, float, float, float] | None = None) -> list[dict]:
    g = _grid()
    if layer_id not in g["raw"]:
        raise KeyError(layer_id)
    _check_bbox(bbox)
    raw, norm = g["raw"][layer_id], g["norm"][layer_id]
    return [
        {"h3": c, "value": round(norm[i], 4), "raw": round(raw[i], 3)}
        for i, c in enumerate(g["cells"])
        if _in_bbox(i, bbox)
    ]


def _profile(profile_id: str) -> dict[str, Any]:
    for p in PROFILES:
        if p["id"] == profile_id:
            return p
    raise KeyError(profile_id)


def _effective_weights(
    p: dict[str, Any], weights: dict[str, float] | None
) -> dict[str, tuple[float, str]]:
    layers: dict[str, tuple[float, str]] = dict(p["layers"])
    if weights:
        for lid, w in weights.items():
            if lid not in layers:
                raise ValueError(f"layer '{lid}' is not part of profile '{p['id']}'")
            if not isinstance(w, int | float) or math.isnan(w) or w < 0:
                raise ValueError(f"weight for '{lid}' must be a non-negative number")
            layers[lid] = (float(w), layers[lid][1])
    total = sum(w for w, _ in layers.values())
    if total <= 0:
        raise ValueError("at least one weight must be greater than zero")
    return {lid: (w / total, b) for lid, (w, b) in layers.items()}


@cache
def _feasibility(profile_id: str) -> list[float]:
    g = _grid()
    seed = sum(map(ord, profile_id))
    return [
        0.55 + 0.45 * (0.5 + 0.5 * _noise(lat, lon, seed, 1.7))
        for lat, lon in g["centroids"]
    ]


def _score_all(profile_id: str, weights: dict[str, float] | None) -> list[dict]:
    p = _profile(profile_id)
    eff = _effective_weights(p, weights)
    g = _grid()
    n = len(g["cells"])
    directed = {
        lid: (g["norm"][lid] if b == "higher" else [1 - v for v in g["norm"][lid]])
        for lid, (_, b) in eff.items()
    }
    means = {lid: sum(v) / n for lid, v in directed.items()}
    feas = _feasibility(profile_id) if p["has_model"] else None
    out = []
    for i, c in enumerate(g["cells"]):
        masked = any(g["raw"][m][i] >= 0.5 for m in p["masks"])
        sust = sum(w * directed[lid][i] for lid, (w, _) in eff.items())
        s = sust * (feas[i] if feas else 1.0)
        out.append({
            "h3": c,
            "score": None if masked else round(max(0.0, min(1.0, s)), 4),
            "masked": masked,
            "breakdown": {} if masked else {
                lid: round(w * (directed[lid][i] - means[lid]), 4) for lid, (w, _) in eff.items()
            },
        })
    return out


def score(
    profile_id: str,
    weights: dict[str, float] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> list[dict]:
    _check_bbox(bbox)
    cells = _score_all(profile_id, weights)
    return [c for i, c in enumerate(cells) if _in_bbox(i, bbox)]


def score_point(
    profile_id: str, lat: float, lon: float, weights: dict[str, float] | None = None
) -> dict:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("lat/lon out of range")
    p = _profile(profile_id)
    g = _grid()
    cell = h3.latlng_to_cell(lat, lon, RESOLUTION)
    if cell not in g["index"]:
        raise KeyError(f"no data for location ({lat}, {lon}); outside the region")
    i = g["index"][cell]
    result = dict(_score_all(profile_id, weights)[i])
    labels = {m[0]: m[1] for m in LAYER_META}
    result["raw"] = {lid: round(g["raw"][lid][i], 3) for lid in g["raw"]}
    result["masks"] = [m for m in p["masks"] if g["raw"][m][i] >= 0.5]
    result["weights"] = {lid: w for lid, (w, _) in _effective_weights(p, weights).items()}
    feas = _feasibility(profile_id)[i] if p["has_model"] else 1.0
    result["feasibility_score"] = round(feas, 4)
    if result["score"] is not None:
        result["sustainability_score"] = round(result["score"] / feas, 4)
    if p["has_model"]:
        drivers = [
            {"layer": lid, "label": labels[lid], "value": round(0.8 * _noise(lat, lon, 100 + k, 2.0), 4),
             "raw": result["raw"][lid]}
            for k, lid in enumerate(g["raw"])
            if lid not in p["masks"]
        ]
        pos = sorted((d for d in drivers if d["value"] > 0), key=lambda d: -d["value"])
        neg = sorted((d for d in drivers if d["value"] < 0), key=lambda d: d["value"])
        result["shap"] = {"base_value": -2.0, "positive": pos[:DEFAULT_TOP_N],
                          "negative": neg[:DEFAULT_TOP_N]}
        result["model"] = {"type": "presence", "positives": "synthetic stub", "note": (
            "Stub model. The feasibility model learns where similar sites have been built, "
            "not where they should be.")}
    else:
        result["shap"] = None
        result["model"] = None
    return result


def data_status() -> dict:
    """Same shape as Person 1's ``backend.scoring.data_status``."""
    return {"is_sample": True, "generated_at": None, "cells": len(_grid()["cells"]),
            "real_layers": [], "synthetic_layers": [m[0] for m in LAYER_META]}
