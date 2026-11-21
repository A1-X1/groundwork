"""Fluvial/tidal flood risk: share of the hex in EA Flood Zone 3 (×1.0) or Zone 2 (×0.5)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import _planning, _synthetic
from ._common import LayerMeta
from ._geo import share_inside

META = LayerMeta(
    id="flood_risk", label="Flood risk", unit="index 0–1", kind="raster",
    description=("Weighted share of the hex in Environment Agency Flood Zone 3 (1.0) or Zone 2 "
                 "(0.5). Zones ignore defences such as the Thames Barrier."),
    source="Environment Agency Flood Map for Planning via planning.data.gov.uk (flood-risk-zone)",
    depends_on=("elevation",),
    normalise="identity",
)


def zone_polygons() -> dict[str, list]:
    feats = _planning.features("flood-risk-zone")
    zones: dict[str, list] = {"2": [], "3": []}
    for f in feats:
        props = f.get("properties", {})
        level = str(props.get("flood-risk-level") or props.get("flood_zone") or props.get("name") or "")
        key = "3" if "3" in level else ("2" if "2" in level else None)
        if key:
            zones[key].extend(_planning.polygons([f]))
    if not zones["3"]:
        raise RuntimeError("no Flood Zone 3 polygons found")
    return zones


def fetch() -> dict[str, list]:
    return zone_polygons()


def to_hex(raw: dict[str, list], grid: pd.DataFrame) -> pd.Series:
    z3 = share_inside(grid, raw["3"])
    z2 = share_inside(grid, raw["2"]) if raw["2"] else 0.0
    return (z3 + 0.5 * np.clip(z2 - z3, 0, None)).clip(0, 1)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    elev = grid["raw_elevation"].to_numpy() if "raw_elevation" in grid else _synthetic.elevation(grid)
    near = np.exp(-_synthetic.dist_thames_m(grid) / 2500)
    risk = np.clip((22 - elev) / 12, 0, 1) * (0.25 + 0.75 * near)
    return pd.Series(np.clip(risk, 0, 1), index=grid.index)
