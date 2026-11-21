"""Distance (m) to the nearest internet exchange / interconnection hub."""

from __future__ import annotations

import pandas as pd

from . import _places
from ._common import LayerMeta
from ._geo import nearest_distance, points_xy

META = LayerMeta(
    id="dist_fibre_ix", label="Distance to internet exchange", unit="m", kind="proximity",
    description="Distance to the nearest interconnection hub hosting LINX/LONAP (Docklands, City, Slough).",
    source="Seeded list of public London IXP facilities (approximate coordinates; see layers/_places.py)",
)


def fetch() -> list[tuple[float, float]]:
    return [(lon, lat) for _, lon, lat in _places.IXPS]


def to_hex(raw: list[tuple[float, float]], grid: pd.DataFrame) -> pd.Series:
    return nearest_distance(grid, points_xy(raw))


def synthetic(grid: pd.DataFrame) -> pd.Series:
    return to_hex(fetch(), grid)  # the seeded list needs no network
