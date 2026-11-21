"""Global sources for national regions (everything outside the London detail grid).

One download covers the world, and rasters are read in place (straight from the zip,
windowed to the region), so nothing is extracted or duplicated on disk:
- WorldClim 2.1 monthly normals 1970–2000, 5 arc-min (~9 km): temperature, precipitation,
  solar radiation, wind, vapour pressure; 2.5 arc-min elevation. CC BY 4.0.
- WorldPop 2020 1 km population, per country. CC BY 4.0.
- Our World in Data electricity carbon intensity, per country. CC BY 4.0.

Layers with no global source are *unavailable* in national regions (neutral in scores),
never synthetic.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

import numpy as np
import pandas as pd

from ._common import RAW_DIR, OfflineError, is_offline, raw_path

WORLDCLIM_URL = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_{res}_{var}.zip"
WORLDPOP_URL = ("https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2020/{iso}/"
                "{iso_l}_ppp_2020_1km_Aggregated.tif")
OWID_URL = "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv"
DAYS = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


def _download(url: str, path) -> str:
    if path.exists() and path.stat().st_size > 10_000:
        return str(path)
    if is_offline():
        raise OfflineError(f"offline and no {path}")
    import requests

    tmp = path.with_suffix(path.suffix + ".part")
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    tmp.replace(path)
    return str(path)


def worldclim_zip(var: str, res: str = "5m") -> str:
    return _download(WORLDCLIM_URL.format(res=res, var=var), raw_path("worldclim", f"wc2.1_{res}_{var}.zip"))


def sample(src_path: str, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Values of a raster at points: one windowed read of the region's bbox."""
    import rasterio
    from rasterio.windows import from_bounds

    with rasterio.open(src_path) as src:
        pad = max(src.res) * 2
        win = from_bounds(lon.min() - pad, lat.min() - pad, lon.max() + pad, lat.max() + pad, src.transform)
        win = win.round_offsets().round_lengths()
        arr = src.read(1, window=win, boundless=True, fill_value=np.nan).astype("float32")
        t = src.window_transform(win)
        nodata = src.nodata
    cols = np.floor((lon - t.c) / t.a).astype(int)
    rows = np.floor((lat - t.f) / t.e).astype(int)
    ok = (rows >= 0) & (rows < arr.shape[0]) & (cols >= 0) & (cols < arr.shape[1])
    out = np.full(len(lon), np.nan, dtype="float32")
    out[ok] = arr[rows[ok], cols[ok]]
    if nodata is not None:
        out[out == nodata] = np.nan
    out[out < -1e30] = np.nan
    return out


_MONTHLY_CACHE: dict[tuple[str, str, int], np.ndarray] = {}


def monthly(var: str, grid: pd.DataFrame) -> np.ndarray:
    """(12, n) WorldClim monthly normals at hex centroids (cached per region for the run)."""
    key = (var, str(grid.attrs.get("region")), len(grid))
    if key not in _MONTHLY_CACHE:
        _MONTHLY_CACHE[key] = _monthly(var, grid)
    return _MONTHLY_CACHE[key]


def _monthly(var: str, grid: pd.DataFrame) -> np.ndarray:
    z = worldclim_zip(var)
    lon, lat = grid["lon"].to_numpy(), grid["lat"].to_numpy()
    return np.vstack([sample(f"zip://{z}!wc2.1_5m_{var}_{m:02d}.tif", lon, lat) for m in range(1, 13)])


def _summer(m: np.ndarray, grid: pd.DataFrame) -> np.ndarray:
    """Mean of the three summer months (JJA north of the equator, DJF south)."""
    north = grid["lat"].to_numpy() >= 0
    return np.where(north, m[[5, 6, 7]].mean(axis=0), m[[11, 0, 1]].mean(axis=0))


def _es(t: np.ndarray) -> np.ndarray:
    """Saturation vapour pressure (kPa), Tetens."""
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def _stull(t: np.ndarray, rh: np.ndarray) -> np.ndarray:
    from ._openmeteo import wet_bulb_stull

    return wet_bulb_stull(t, np.clip(rh, 1, 100))


# ---- layer functions (grid → raw values) --------------------------------------
def elevation(grid: pd.DataFrame) -> np.ndarray:
    z = worldclim_zip("elev", "2.5m")
    return sample(f"zip://{z}!wc2.1_2.5m_elev.tif", grid["lon"].to_numpy(), grid["lat"].to_numpy())


def mean_temp_annual(grid):
    return monthly("tavg", grid).mean(axis=0)


def summer_max_temp(grid):
    return _summer(monthly("tmax", grid), grid)


def humidity_mean(grid):
    rh = monthly("vapr", grid) / _es(monthly("tavg", grid)) * 100
    return np.clip(rh, 0, 100).mean(axis=0)


def wet_bulb_p99(grid):
    """Design-day proxy: wet bulb at the warmest month's mean max temperature and its RH."""
    tmax, vapr = monthly("tmax", grid), monthly("vapr", grid)
    i = np.nanargmax(np.nan_to_num(tmax, nan=-99), axis=0)
    cols = np.arange(tmax.shape[1])
    t, e = tmax[i, cols], vapr[i, cols]
    return _stull(t, e / _es(t) * 100)


def free_cooling_hours(grid):
    """Hours/yr below 18 °C, assuming a sinusoidal daily cycle between monthly tmin and tmax."""
    tmin, tmax = monthly("tmin", grid), monthly("tmax", grid)
    phase = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    mean, amp = (tmax + tmin) / 2, (tmax - tmin) / 2
    temps = mean[None] + amp[None] * np.sin(phase)[:, None, None]          # (24, 12, n)
    frac = (temps < 18.0).mean(axis=0)                                      # (12, n)
    hours = (frac * DAYS[:, None] * 24).sum(axis=0)
    return np.where(np.isnan(tmin).any(axis=0) | np.isnan(tmax).any(axis=0), np.nan, hours)


def wind_speed_mean(grid):
    return monthly("wind", grid).mean(axis=0)


def wind_speed_100m(grid):
    """10 m → 100 m with the 1/7 power law (open terrain)."""
    return wind_speed_mean(grid) * 10 ** (1 / 7)


def wind_power_density(grid):
    """0.5·ρ·<v³>, Rayleigh-distributed wind: <v³> = (6/π)·v̄³."""
    v = wind_speed_100m(grid)
    return 0.5 * 1.225 * (6 / np.pi) * v**3


def solar_irradiance(grid):
    """kJ/m²/day monthly → kWh/m²/yr."""
    return (monthly("srad", grid) * DAYS[:, None]).sum(axis=0) / 3600


def precipitation_annual(grid):
    return monthly("prec", grid).sum(axis=0)


def evapotranspiration_annual(grid):
    """Hargreaves–Samani with measured radiation: 0.0135·(T+17.8)·Rs (mm/day)."""
    t, rs = monthly("tavg", grid), monthly("srad", grid) / 1000 / 2.45  # MJ → mm/day equivalent
    return (0.0135 * (t + 17.8) * rs * DAYS[:, None]).clip(min=0).sum(axis=0)


def population_density(grid):
    iso = grid.attrs.get("country", "GBR")
    path = _download(WORLDPOP_URL.format(iso=iso.upper(), iso_l=iso.lower()),
                     raw_path("worldpop", f"{iso.lower()}_ppp_2020_1km_Aggregated.tif"))
    import h3

    rows = [(c, *h3.cell_to_latlng(k)) for c in grid.index
            for k in h3.cell_to_children(c, h3.get_resolution(c) + 1)]
    df = pd.DataFrame(rows, columns=["h3", "lat", "lon"])
    df["pop"] = np.nan_to_num(sample(path, df["lon"].to_numpy(), df["lat"].to_numpy()), nan=0.0).clip(min=0)
    mean_px = df.groupby("h3")["pop"].mean().reindex(grid.index).to_numpy()
    lat = grid["lat"].to_numpy()
    px_km2 = (30 / 3600 * 111.32) ** 2 * np.cos(np.radians(lat))  # 30 arc-second pixels
    return mean_px / px_km2


@lru_cache(maxsize=1)
def _owid() -> pd.DataFrame:
    path = _download(OWID_URL, raw_path("owid", "owid-energy-data.csv"))
    return pd.read_csv(path, usecols=["iso_code", "year", "carbon_intensity_elec"])


def grid_carbon_intensity(grid):
    iso = grid.attrs.get("country", "GBR")
    df = _owid()
    rows = df[(df["iso_code"] == iso) & df["carbon_intensity_elec"].notna()]
    if rows.empty:
        raise LookupError(f"no OWID carbon intensity for {iso}")
    latest = rows.sort_values("year").iloc[-1]
    return np.full(len(grid), float(latest["carbon_intensity_elec"]))


SOURCES: dict[str, tuple[Callable[[pd.DataFrame], np.ndarray], str]] = {
    "elevation": (elevation, "WorldClim 2.1 elevation (2.5′, from SRTM)"),
    "mean_temp_annual": (mean_temp_annual, "WorldClim 2.1 monthly normals 1970–2000 (5′)"),
    "summer_max_temp": (summer_max_temp, "WorldClim 2.1 monthly normals 1970–2000 (5′)"),
    "humidity_mean": (humidity_mean, "WorldClim 2.1 vapour pressure + temperature (5′)"),
    "wet_bulb_p99": (wet_bulb_p99, "WorldClim 2.1 warmest-month design point, Stull (2011)"),
    "free_cooling_hours": (free_cooling_hours, "WorldClim 2.1 tmin/tmax, sinusoidal daily cycle"),
    "wind_speed_mean": (wind_speed_mean, "WorldClim 2.1 wind speed (5′)"),
    "wind_speed_100m": (wind_speed_100m, "WorldClim 2.1 wind, 1/7 power law to 100 m"),
    "wind_power_density": (wind_power_density, "WorldClim 2.1 wind, Rayleigh ½ρ⟨v³⟩ at 100 m"),
    "solar_irradiance": (solar_irradiance, "WorldClim 2.1 solar radiation (5′)"),
    "precipitation_annual": (precipitation_annual, "WorldClim 2.1 precipitation (5′)"),
    "evapotranspiration_annual": (evapotranspiration_annual, "WorldClim 2.1, Hargreaves–Samani"),
    "population_density": (population_density, "WorldPop 2020 1 km (per country)"),
    "grid_carbon_intensity": (grid_carbon_intensity, "Our World in Data electricity carbon intensity (country)"),
}


def available() -> set[str]:
    return set(SOURCES)


def compute(layer_id: str, grid: pd.DataFrame) -> pd.Series:
    fn, _ = SOURCES[layer_id]
    return pd.Series(np.asarray(fn(grid), dtype="float64"), index=grid.index)


def raw_dir_size_mb() -> float:
    return sum(p.stat().st_size for p in RAW_DIR.rglob("*") if p.is_file()) / 1e6
