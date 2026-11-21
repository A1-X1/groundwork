"""Open-Meteo historical weather and air-quality samples on a coarse lattice over London.

ERA5 / CAMS are coarse (9–28 km), so a 6×5 lattice captures all the real variation;
values are IDW-interpolated to hexes and temperatures are lapse-rate corrected with
the hex elevation.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from ._common import cached_json, http_get
from ._geo import idw

YEAR = 2025
LATS = np.linspace(51.29, 51.69, 5)
LONS = np.linspace(-0.50, 0.32, 6)
LAPSE_RATE = 0.0065  # °C per metre

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def lattice() -> list[tuple[float, float]]:
    return [(float(la), float(lo)) for la in LATS for lo in LONS]


def _batched(url: str, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    pts = lattice()
    out: list[dict[str, Any]] = []
    for i in range(0, len(pts), 6):
        chunk = pts[i:i + 6]
        q = dict(params, latitude=",".join(f"{a:.4f}" for a, _ in chunk),
                 longitude=",".join(f"{b:.4f}" for _, b in chunk))

        def produce(q: dict[str, Any] = q) -> Any:
            res = http_get(url, q, timeout=120)
            return res if isinstance(res, list) else [res]

        out.extend(cached_json(f"open_meteo/{name}_{YEAR}_{i:02d}.json", produce))
    return out


def wet_bulb_stull(t: np.ndarray, rh: np.ndarray) -> np.ndarray:
    """Stull (2011) wet-bulb temperature, °C, from dry bulb °C and RH %."""
    return (t * np.arctan(0.151977 * np.sqrt(rh + 8.313659)) + np.arctan(t + rh)
            - np.arctan(rh - 1.676331) + 0.00391838 * rh**1.5 * np.arctan(0.023101 * rh) - 4.686035)


@lru_cache(maxsize=1)
def weather_stats() -> pd.DataFrame:
    """Per-lattice-point climate statistics for ``YEAR``."""
    raw = _batched(ARCHIVE_URL, "weather", {
        "start_date": f"{YEAR}-01-01", "end_date": f"{YEAR}-12-31",
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation",
        "wind_speed_unit": "ms", "timezone": "UTC",
    })
    rows = []
    for loc in raw:
        h = loc["hourly"]
        time = pd.to_datetime(h["time"])
        t = np.asarray(h["temperature_2m"], dtype=float)
        rh = np.asarray(h["relative_humidity_2m"], dtype=float)
        summer = time.month.isin([6, 7, 8])
        daily_max = pd.Series(t[summer], index=time[summer]).resample("D").max()
        rows.append({
            "lat": loc["latitude"], "lon": loc["longitude"], "elevation": loc.get("elevation", 0.0),
            "mean_temp_annual": np.nanmean(t),
            "summer_max_temp": float(daily_max.mean()),
            "wet_bulb_p99": float(np.nanpercentile(wet_bulb_stull(t, rh), 99)),
            "free_cooling_hours": float(np.sum(t < 18.0)),
            "humidity_mean": np.nanmean(rh),
            "wind_speed_mean": np.nanmean(np.asarray(h["wind_speed_10m"], dtype=float)),
            "solar_irradiance": np.nansum(np.asarray(h["shortwave_radiation"], dtype=float)) / 1000.0,
        })
    return pd.DataFrame(rows)


@lru_cache(maxsize=1)
def air_stats() -> pd.DataFrame:
    raw = _batched(AIR_URL, "air", {
        "start_date": f"{YEAR}-01-01", "end_date": f"{YEAR}-12-31",
        "hourly": "nitrogen_dioxide,pm2_5", "timezone": "UTC",
    })
    return pd.DataFrame([{
        "lat": loc["latitude"], "lon": loc["longitude"],
        "air_quality_no2": np.nanmean(np.asarray(loc["hourly"]["nitrogen_dioxide"], dtype=float)),
        "air_quality_pm25": np.nanmean(np.asarray(loc["hourly"]["pm2_5"], dtype=float)),
    } for loc in raw])


def interpolate(stats: pd.DataFrame, column: str, grid: pd.DataFrame, *, lapse: bool = False) -> pd.Series:
    values = idw(grid, stats["lat"], stats["lon"], stats[column])
    if lapse and "raw_elevation" in grid:
        lattice_elev = idw(grid, stats["lat"], stats["lon"], stats["elevation"])
        values = values - LAPSE_RATE * (grid["raw_elevation"] - lattice_elev)
    return values
