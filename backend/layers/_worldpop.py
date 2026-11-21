"""WorldPop 100 m constrained population grids (global, CC BY 4.0), sampled onto hexes."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._common import OfflineError, is_offline, raw_path

URL = "https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/{iso}/{iso_l}_ppp_2020_constrained.tif"


def download(iso3: str = "GBR") -> str:
    path = raw_path("worldpop", f"{iso3.lower()}_ppp_2020_constrained.tif")
    if path.exists() and path.stat().st_size > 1_000_000:
        return str(path)
    if is_offline():
        raise OfflineError(f"offline and no WorldPop raster at {path}")
    import requests

    tmp = path.with_suffix(".part")
    with requests.get(URL.format(iso=iso3.upper(), iso_l=iso3.lower()), stream=True, timeout=120) as r:
        r.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    tmp.replace(path)
    return str(path)


def density(path: str, grid: pd.DataFrame) -> pd.Series:
    """Residents per km²: mean of 49 sample points per hex (res+2 children) / pixel area."""
    import h3
    import rasterio

    rows = []
    for cell in grid.index:
        for child in h3.cell_to_children(cell, h3.get_resolution(cell) + 2):
            lat, lon = h3.cell_to_latlng(child)
            rows.append((cell, lon, lat))
    df = pd.DataFrame(rows, columns=["h3", "lon", "lat"])
    with rasterio.open(path) as src:
        vals = np.array([v[0] for v in src.sample(zip(df["lon"], df["lat"], strict=True))], dtype=float)
        nodata = src.nodata
        res_x, res_y = src.res
    if nodata is not None:
        vals[vals == nodata] = 0.0
    vals[~np.isfinite(vals) | (vals < 0)] = 0.0
    df["pop"] = vals
    mean_pixel = df.groupby("h3")["pop"].mean().reindex(grid.index)
    lat = grid["lat"].to_numpy()
    pixel_km2 = (res_y * 111.32) * (res_x * 111.32 * np.cos(np.radians(lat)))
    return mean_pixel / pixel_km2
