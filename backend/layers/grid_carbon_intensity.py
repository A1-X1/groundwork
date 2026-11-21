"""Electricity grid carbon intensity (gCO₂/kWh) for the hex's DNO region."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from . import _synthetic
from ._common import DAILY, LayerMeta, cached_json, http_get

META = LayerMeta(
    id="grid_carbon_intensity", label="Grid carbon intensity", unit="gCO₂/kWh", kind="aggregate",
    description=("Mean forecast carbon intensity of electricity for the distribution region. "
                 "All of Greater London is one region (London, id 13), so this layer is uniform "
                 "here; it differentiates sites once a region spans several DNOs."),
    source="National Grid ESO Carbon Intensity API (regional)",
)
LONDON_REGION_ID = 13
URL = "https://api.carbonintensity.org.uk/regional/intensity/{start}/fw48h/regionid/{rid}"


def fetch() -> float:
    start = datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ")

    def produce() -> dict[str, float]:
        res = http_get(URL.format(start=start, rid=LONDON_REGION_ID))
        values = [p["intensity"]["forecast"] for p in res["data"]["data"]]
        return {"mean_forecast": float(np.mean(values)), "n": len(values)}

    return cached_json("carbon_intensity/london.json", produce, DAILY)["mean_forecast"]


def to_hex(raw: float, grid: pd.DataFrame) -> pd.Series:
    return pd.Series(float(raw), index=grid.index)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    # Synthetic only: a mild gradient so the layer is visibly "something" in demos.
    return pd.Series(165 + 6 * _synthetic.east_west(grid) + 2 * _synthetic.smooth_noise(grid, META.id),
                     index=grid.index)
