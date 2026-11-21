"""Lightweight geometry helpers (no GDAL): local projection, nearest distance, IDW."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd

# Charing Cross — the conventional centre of London.
CENTRE_LAT, CENTRE_LON = 51.5074, -0.1278
_M_PER_DEG_LAT = 111_320.0
_M_PER_DEG_LON = 111_320.0 * np.cos(np.radians(CENTRE_LAT))

# Approximate centreline of the tidal Thames through Greater London, west → east (lon, lat).
THAMES: list[tuple[float, float]] = [
    (-0.510, 51.430), (-0.440, 51.405), (-0.370, 51.408), (-0.330, 51.405),
    (-0.306, 51.413), (-0.310, 51.440), (-0.302, 51.462), (-0.285, 51.478),
    (-0.255, 51.487), (-0.230, 51.490), (-0.215, 51.470), (-0.190, 51.468),
    (-0.165, 51.482), (-0.140, 51.486), (-0.122, 51.495), (-0.118, 51.508),
    (-0.095, 51.509), (-0.075, 51.506), (-0.050, 51.502), (-0.030, 51.507),
    (-0.010, 51.505), (0.000, 51.495), (-0.012, 51.485), (0.005, 51.483),
    (0.030, 51.497), (0.070, 51.496), (0.120, 51.507), (0.160, 51.500),
    (0.190, 51.482), (0.230, 51.468), (0.260, 51.462),
]


def to_xy(lat: np.ndarray | Sequence[float], lon: np.ndarray | Sequence[float]) -> np.ndarray:
    """Equirectangular projection around central London, metres. Fine at city scale."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    return np.column_stack(((lon - CENTRE_LON) * _M_PER_DEG_LON, (lat - CENTRE_LAT) * _M_PER_DEG_LAT))


def grid_xy(grid: pd.DataFrame) -> np.ndarray:
    return to_xy(grid["lat"].to_numpy(), grid["lon"].to_numpy())


def densify(line: Sequence[tuple[float, float]], step_m: float = 50.0) -> np.ndarray:
    """Points every ``step_m`` metres along a (lon, lat) polyline, as projected xy."""
    pts = to_xy([p[1] for p in line], [p[0] for p in line])
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:], strict=True):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step_m)))
        t = np.linspace(0, 1, n + 1)[1:, None]
        out.extend(a + (b - a) * t)
    return np.asarray(out)


def lines_to_points(lines: Iterable[Sequence[tuple[float, float]]], step_m: float = 50.0) -> np.ndarray:
    chunks = [densify(line, step_m) for line in lines if len(line) > 0]
    return np.vstack(chunks) if chunks else np.empty((0, 2))


def nearest_distance(grid: pd.DataFrame, feature_xy: np.ndarray) -> pd.Series:
    """Metres from each hex centroid to the nearest feature point."""
    if len(feature_xy) == 0:
        raise ValueError("no features to measure distance to")
    from scipy.spatial import cKDTree

    dist, _ = cKDTree(feature_xy).query(grid_xy(grid))
    return pd.Series(dist, index=grid.index)


def points_xy(points: Iterable[tuple[float, float]]) -> np.ndarray:
    """(lon, lat) points → projected xy array."""
    pts = list(points)
    if not pts:
        return np.empty((0, 2))
    return to_xy([p[1] for p in pts], [p[0] for p in pts])


def idw(grid: pd.DataFrame, sample_lat: Sequence[float], sample_lon: Sequence[float],
        values: Sequence[float], power: float = 2.0) -> pd.Series:
    """Inverse-distance-weighted interpolation of lattice samples onto hex centroids."""
    src = to_xy(sample_lat, sample_lon)
    dst = grid_xy(grid)
    vals = np.asarray(values, dtype=float)
    d = np.linalg.norm(dst[:, None, :] - src[None, :, :], axis=2)
    d = np.maximum(d, 1.0)
    w = 1.0 / d**power
    return pd.Series((w * vals).sum(axis=1) / w.sum(axis=1), index=grid.index)


def count_in_hex(grid: pd.DataFrame, lat: Sequence[float], lon: Sequence[float],
                 resolution: int = 8, weights: Sequence[float] | None = None) -> pd.Series:
    """Count (or sum ``weights``) of points falling in each hex of ``grid``."""
    import h3

    cells = [h3.latlng_to_cell(float(a), float(b), resolution) for a, b in zip(lat, lon, strict=True)]
    w = np.ones(len(cells)) if weights is None else np.asarray(weights, dtype=float)
    sums = pd.Series(w, index=cells).groupby(level=0).sum()
    return sums.reindex(grid.index).fillna(0.0)


def hex_sample_points(grid: pd.DataFrame) -> pd.DataFrame:
    """Seven sample points per hex (the centroids of its res-9 children)."""
    import h3

    rows = []
    for cell in grid.index:
        res = h3.get_resolution(cell)
        for child in h3.cell_to_children(cell, res + 1):
            lat, lon = h3.cell_to_latlng(child)
            rows.append((cell, lat, lon))
    return pd.DataFrame(rows, columns=["h3", "lat", "lon"])


def smooth_neighbours(grid: pd.DataFrame, values: pd.Series, rings: int = 1) -> pd.Series:
    """Mean over each hex's k-ring; used to fill gaps and to de-speckle aggregates."""
    import h3

    out = {}
    for cell in grid.index:
        nb = [c for c in h3.grid_disk(cell, rings) if c in values.index]
        vals = values.loc[nb].dropna()
        out[cell] = float(vals.mean()) if len(vals) else np.nan
    return pd.Series(out).reindex(grid.index)


def fill_gaps(grid: pd.DataFrame, values: pd.Series) -> pd.Series:
    """Fill NaNs from neighbours (growing rings), then the regional median."""
    values = values.reindex(grid.index).astype(float)
    for rings in (1, 2, 3):
        if not values.isna().any():
            break
        smoothed = smooth_neighbours(grid, values, rings)
        values = values.fillna(smoothed)
    return values.fillna(values.median() if values.notna().any() else 0.0)


def polygons_contain(polygons: list, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Boolean array: is each (lat, lon) inside any shapely polygon (lon/lat coords)?"""
    from shapely import STRtree, points

    if not polygons:
        return np.zeros(len(lat), dtype=bool)
    tree = STRtree(polygons)
    pts = points(np.asarray(lon), np.asarray(lat))
    hits = tree.query(pts, predicate="intersects")
    inside = np.zeros(len(lat), dtype=bool)
    inside[np.unique(hits[0])] = True
    return inside


def share_inside(grid: pd.DataFrame, polygons: list) -> pd.Series:
    """Fraction (0–1) of each hex covered by the polygons, from 7 sample points."""
    samples = hex_sample_points(grid)
    inside = polygons_contain(polygons, samples["lat"].to_numpy(), samples["lon"].to_numpy())
    return pd.Series(inside.astype(float)).groupby(samples["h3"]).mean().reindex(grid.index).fillna(0.0)
