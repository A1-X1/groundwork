"""LSOA-level statistics (ONS Census 2021, IMD) mapped to hexes via population-weighted centroids.

These sources are bulk downloads, so the fetchers read files the user has placed in
``data/raw/ons/`` (see docs/data-sources.md for exact links). Column names are matched
loosely so the various ONS/MHCLG export formats all work.
"""

from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd

from ._common import require_file

PWC_HINT = ("Download 'LSOA (Dec 2021) Population Weighted Centroids' CSV from the ONS Open "
            "Geography Portal and save as data/raw/ons/lsoa_pwc.csv")
POP_HINT = ("Download Census 2021 TS001 (usual residents) by LSOA from Nomis and save as "
            "data/raw/ons/lsoa_population.csv")
IMD_HINT = ("Download English Indices of Deprivation File 7 (all ranks, scores) CSV and save "
            "as data/raw/ons/imd.csv")


def _col(df: pd.DataFrame, *patterns: str) -> str:
    for pat in patterns:
        for c in df.columns:
            if re.search(pat, str(c), flags=re.IGNORECASE):
                return c
    raise KeyError(f"none of {patterns} in columns {list(df.columns)[:12]}…")


@lru_cache(maxsize=1)
def centroids() -> pd.DataFrame:
    """LSOA code → lat/lon."""
    df = pd.read_csv(require_file("ons", "lsoa_pwc.csv", hint=PWC_HINT))
    code = _col(df, r"^LSOA\d\dCD$", r"lsoa.*code")
    try:
        lat, lon = df[_col(df, r"^lat")], df[_col(df, r"^lon")]
    except KeyError:
        from ._schools import bng_to_wgs84

        lon, lat = bng_to_wgs84(df[_col(df, r"^x$", r"easting")], df[_col(df, r"^y$", r"northing")])
    return pd.DataFrame({"lat": lat.to_numpy(), "lon": lon.to_numpy()}, index=df[code].to_numpy())


def lsoa_values(filename: str, hint: str, value_patterns: tuple[str, ...]) -> pd.DataFrame:
    """Join an LSOA table to centroids → DataFrame(lat, lon, value)."""
    df = pd.read_csv(require_file("ons", filename, hint=hint))
    code = _col(df, r"^LSOA\d\dCD$", r"lsoa.*code", r"geography code", r"mnemonic")
    val = _col(df, *value_patterns)
    vals = pd.to_numeric(df[val], errors="coerce")
    joined = centroids().join(pd.Series(vals.to_numpy(), index=df[code].to_numpy(), name="value"), how="inner")
    if joined.empty:
        raise RuntimeError(f"{filename}: no LSOA codes matched the centroid file")
    return joined.dropna()


def population() -> pd.DataFrame:
    return lsoa_values("lsoa_population.csv", POP_HINT, (r"OBS_VALUE", r"total", r"usual residents", r"observation"))


def imd() -> pd.DataFrame:
    return lsoa_values("imd.csv", IMD_HINT, (r"IMD\)? score", r"Index of Multiple Deprivation.*Score"))
