"""Median residential sale price (£) from HM Land Registry Price Paid data."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import _synthetic
from ._common import RAW_DIR, LayerMeta, SourceUnavailable
from ._geo import fill_gaps

META = LayerMeta(
    id="median_house_price", label="Median house price", unit="£", kind="aggregate",
    description="Median sale price of residential transactions in the hex over the last 12 months (gaps filled from neighbours).",
    source="HM Land Registry Price Paid Data + ONS Postcode Directory (postcode centroids)",
)
PP_COLS = ["id", "price", "date", "postcode", "type", "new", "tenure", "paon", "saon",
           "street", "locality", "town", "district", "county", "ppd_cat", "status"]
HINT = ("Save Price Paid CSVs (no header, e.g. pp-2025.csv) in data/raw/landreg/ and a postcode "
        "lookup with columns pcds,lat,long (from the ONS Postcode Directory) as "
        "data/raw/onspd/postcodes.csv")


def fetch() -> pd.DataFrame:
    pp_files = sorted((RAW_DIR / "landreg").glob("pp-*.csv")) if (RAW_DIR / "landreg").exists() else []
    lookup = RAW_DIR / "onspd" / "postcodes.csv"
    if not pp_files or not lookup.exists():
        raise SourceUnavailable(HINT)
    pp = pd.concat(pd.read_csv(p, header=None, names=PP_COLS, usecols=["price", "date", "postcode", "type", "ppd_cat"])
                   for p in pp_files)
    pp["date"] = pd.to_datetime(pp["date"])
    pp = pp[(pp["date"] >= pp["date"].max() - pd.DateOffset(months=12)) & (pp["ppd_cat"] == "A")
            & (pp["type"] != "O")]
    pc = pd.read_csv(lookup, usecols=["pcds", "lat", "long"]).rename(columns={"pcds": "postcode", "long": "lon"})
    return pp.merge(pc, on="postcode", how="inner")[["price", "lat", "lon"]]


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    import h3

    cells = [h3.latlng_to_cell(a, b, 8) for a, b in zip(raw["lat"], raw["lon"], strict=True)]
    med = pd.Series(raw["price"].to_numpy(), index=cells).groupby(level=0).median()
    return fill_gaps(grid, med.reindex(grid.index))


def synthetic(grid: pd.DataFrame) -> pd.Series:
    d = _synthetic.dist_centre_m(grid) / 1000
    west = -_synthetic.east_west(grid)
    price = 520_000 * np.exp(-d / 14) * (1 + 0.35 * west) + 330_000
    price *= np.exp(0.6 * np.exp(-(((d - 3) / 3.5) ** 2)) * (west > -0.1))  # Kensington/Chelsea premium
    price *= np.exp(0.12 * _synthetic.smooth_noise(grid, META.id, 150, 1500))
    return pd.Series(np.round(price, -3), index=grid.index)
