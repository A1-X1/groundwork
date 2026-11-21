"""Share of schools within 2 km rated Good or Outstanding by Ofsted."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import _schools, _synthetic
from ._common import LayerMeta
from ._geo import grid_xy, points_xy

META = LayerMeta(
    id="school_quality_nearby", label="Good schools nearby", unit="%", kind="proximity",
    description="Percentage of Ofsted-rated schools within 2 km of the hex centre rated Good or Outstanding.",
    source="DfE Get Information About Schools (GIAS) with latest Ofsted overall effectiveness",
    depends_on=("deprivation_index",),
)
RADIUS_M = 2000


def fetch() -> pd.DataFrame:
    df = _schools.schools()
    rated = df[df["rating"].isin(_schools.RATED)]
    if len(rated) < 50:
        raise RuntimeError("no Ofsted ratings available (OSM fallback has none)")
    return rated


def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
    from scipy.spatial import cKDTree

    tree = cKDTree(points_xy(zip(raw["lon"], raw["lat"], strict=True)))
    good = raw["rating"].isin(_schools.GOOD).to_numpy()
    out = []
    for idx in tree.query_ball_point(grid_xy(grid), RADIUS_M):
        out.append(100 * good[idx].mean() if idx else np.nan)
    from ._geo import fill_gaps

    return fill_gaps(grid, pd.Series(out, index=grid.index))


def synthetic(grid: pd.DataFrame) -> pd.Series:
    dep = grid["raw_deprivation_index"].to_numpy() if "raw_deprivation_index" in grid else 20.0
    share = 92 - 0.25 * (dep - 20) + 4 * _synthetic.smooth_noise(grid, META.id, 120, 1800)
    return pd.Series(np.clip(share, 40, 100), index=grid.index)
