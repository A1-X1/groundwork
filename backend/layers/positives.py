"""ML positive sets: ``source`` strings from profile YAML → hexes with existing examples.

Each resolver returns ``(cells, is_synthetic)``. Real sources fall back to seeded or
synthetic examples so training always works offline.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import h3
import pandas as pd

from . import _osm, _places, _schools

log = logging.getLogger("groundwork.layers")
Resolver = Callable[[pd.DataFrame], tuple[set[str], bool]]


@contextmanager
def _network(allowed: bool) -> Iterator[None]:
    """Temporarily force offline mode (cache-only) unless network use is allowed."""
    old = os.environ.get("GROUNDWORK_OFFLINE")
    if not allowed:
        os.environ["GROUNDWORK_OFFLINE"] = "1"
    try:
        yield
    finally:
        if not allowed:
            if old is None:
                os.environ.pop("GROUNDWORK_OFFLINE", None)
            else:
                os.environ["GROUNDWORK_OFFLINE"] = old


def _cells(points: list[tuple[float, float]], grid: pd.DataFrame, res: int) -> set[str]:
    return {c for lon, lat in points if (c := h3.latlng_to_cell(lat, lon, res)) in grid.index}


def data_centres(grid: pd.DataFrame, res: int = 8) -> tuple[set[str], bool]:
    try:
        pts = _osm.element_points(_osm.query("data_centres", [
            'nwr["telecom"="data_center"]', 'nwr["building"="data_center"]'], geometry=False))
        if len(pts) >= 10:
            return _cells(pts, grid, res), False
        raise RuntimeError("too few OSM data centres")
    except Exception as exc:  # noqa: BLE001
        log.info("data_centre positives: using seeded cluster list (%s)", exc)
        return _cells([(lon, lat) for _, lon, lat in _places.DATA_CENTRES], grid, res), True


def residential(grid: pd.DataFrame, res: int = 8) -> tuple[set[str], bool]:
    col = "raw_land_use_residential"
    if col not in grid:
        raise KeyError("grid has no land_use_residential column")
    return set(grid.index[grid[col] >= 0.5]), bool(grid.attrs.get("synthetic", {}).get("land_use_residential", True))


def schools(grid: pd.DataFrame, res: int = 8) -> tuple[set[str], bool]:
    try:
        df = _schools.schools()
        return _cells(list(zip(df["lon"], df["lat"], strict=True)), grid, res), False
    except Exception as exc:  # noqa: BLE001
        log.info("school positives: using synthetic school points (%s)", exc)
        from . import dist_primary_school, dist_secondary_school

        pts = dist_primary_school.synthetic_points(grid) + dist_secondary_school.synthetic_points(grid)
        return _cells(pts, grid, res), True


RESOLVERS: dict[str, Resolver] = {
    "osm:telecom=data_center": data_centres,
    "osm:landuse=residential": residential,
    "gias:schools": schools,
}


def resolve(source: str, grid: pd.DataFrame, allow_network: bool = False) -> tuple[set[str], bool]:
    """Positive hexes for ``source``. Without ``allow_network`` only cached downloads are used,
    so scoring at API request time never blocks on the internet."""
    if source not in RESOLVERS:
        raise KeyError(f"unknown positives source {source!r}; known: {sorted(RESOLVERS)}")
    with _network(allow_network):
        return RESOLVERS[source](grid)
