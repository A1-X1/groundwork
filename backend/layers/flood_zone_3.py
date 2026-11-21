"""Hard mask: hex is mostly inside Environment Agency Flood Zone 3."""

from __future__ import annotations

import pandas as pd

from . import flood_risk
from ._common import LayerMeta
from ._geo import share_inside

META = LayerMeta(
    id="flood_zone_3", label="Flood Zone 3", unit="1 = in zone", kind="raster",
    description="1 if at least half of the hex lies in EA Flood Zone 3 (≥1% annual river / 0.5% sea risk), else 0.",
    source="Environment Agency Flood Map for Planning via planning.data.gov.uk (flood-risk-zone)",
    depends_on=("flood_risk",),
    normalise="identity",
    is_mask=True,
)


def fetch() -> list:
    return flood_risk.zone_polygons()["3"]


def to_hex(raw: list, grid: pd.DataFrame) -> pd.Series:
    return (share_inside(grid, raw) >= 0.5).astype(float)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    risk = grid["raw_flood_risk"] if "raw_flood_risk" in grid else flood_risk.synthetic(grid)
    return (risk >= 0.6).astype(float)
