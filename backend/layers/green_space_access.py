"""Distance (m) to the nearest public park — lower means better green-space access."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import _osm, _places, _synthetic
from ._common import LayerMeta
from ._geo import nearest_distance, points_xy, polygons_contain, to_xy

META = LayerMeta(
    id="green_space_access", label="Distance to park", unit="m", kind="proximity",
    description="Distance from the hex centre to the edge of the nearest public park (0 inside a park). Lower = better access.",
    source="OpenStreetMap leisure=park via Overpass API",
    depends_on=("population_density",),
)


def fetch() -> list:
    return _osm.element_polygons(_osm.query("parks", ['nwr["leisure"="park"]']))


def to_hex(raw: list, grid: pd.DataFrame) -> pd.Series:
    boundary = []
    for poly in raw:
        xs, ys = poly.exterior.coords.xy
        boundary.append(to_xy(np.asarray(ys), np.asarray(xs)))
    dist = nearest_distance(grid, np.vstack(boundary))
    inside = polygons_contain(raw, grid["lat"].to_numpy(), grid["lon"].to_numpy())
    return dist.where(~inside, 0.0)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    pts = _synthetic.sample_points(grid, META.id, 1100, np.ones(len(grid)), jitter_m=500)
    pts += [(lon, lat) for _, lon, lat, _ in _places.PROTECTED_SITES]
    d = nearest_distance(grid, points_xy(pts)) - 150  # parks have area; measure to the edge
    return d.clip(lower=0)
