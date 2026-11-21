"""Recorded street-level crime per 1,000 residents per year (data.police.uk)."""

from __future__ import annotations

import time
from pathlib import Path

import h3
import numpy as np
import pandas as pd

from . import _synthetic
from ._common import RAW_DIR, LayerMeta, cached_json, http_get, is_offline

META = LayerMeta(
    id="crime_rate", label="Crime rate", unit="crimes/1,000 residents/yr", kind="aggregate",
    description=("Street-level crimes recorded in the hex over 12 months per 1,000 residents. "
                 "Centres with high footfall and few residents (e.g. the West End) score high."),
    source="data.police.uk street-level crime (Metropolitan + City of London police)",
    depends_on=("population_density",),
)
API = "https://data.police.uk/api"
MIN_RESIDENTS = 500  # floor so near-empty hexes don't produce absurd rates


def _bulk_csvs() -> list[Path]:
    """Bulk downloads unzipped into data/raw/police/ (YYYY-MM/<force>-street.csv)."""
    root = RAW_DIR / "police"
    return sorted(root.glob("**/*-street.csv")) if root.exists() else []


def _api_points() -> tuple[list[tuple[float, float]], int]:
    """One month of crime points via the API, splitting busy hexes until under the cap."""
    month = http_get(f"{API}/crime-last-updated")["date"][:7]
    from backend.pipeline.build_grid import build_grid

    parents = sorted({h3.cell_to_parent(c, 6) for c in build_grid().index})
    points: list[tuple[float, float]] = []

    def fetch_cell(cell: str) -> list[list[float]]:
        poly = ":".join(f"{lat:.5f},{lon:.5f}" for lat, lon in h3.cell_to_boundary(cell))
        try:
            res = http_get(f"{API}/crimes-street/all-crime", {"poly": poly, "date": month}, retries=1)
        except RuntimeError:  # 503 = over 10k crimes: split into children
            if h3.get_resolution(cell) >= 8:
                return []
            return [p for child in h3.cell_to_children(cell) for p in fetch_cell(child)]
        time.sleep(0.08)  # stay under the 15 req/s rate limit
        return [[float(c["location"]["longitude"]), float(c["location"]["latitude"])] for c in res]

    for cell in parents:
        pts = cached_json(f"police/api/{month}/{cell}.json", lambda cell=cell: fetch_cell(cell))
        points.extend((p[0], p[1]) for p in pts)
    return points, 1


def fetch() -> tuple[list[tuple[float, float]], int]:
    """(lon, lat) crime points and the number of months they cover."""
    csvs = _bulk_csvs()
    if csvs:
        frames = [pd.read_csv(p, usecols=["Month", "Longitude", "Latitude"]).dropna() for p in csvs]
        df = pd.concat(frames)
        months = sorted(df["Month"].unique())[-12:]
        df = df[df["Month"].isin(months)]
        return list(zip(df["Longitude"], df["Latitude"], strict=True)), len(months)
    if is_offline() and not (RAW_DIR / "police" / "api").exists():
        from ._common import OfflineError

        raise OfflineError("no cached police data")
    return _api_points()


def to_hex(raw: tuple[list[tuple[float, float]], int], grid: pd.DataFrame) -> pd.Series:
    points, months = raw
    counts = pd.Series([h3.latlng_to_cell(lat, lon, 8) for lon, lat in points]).value_counts()
    counts = counts.reindex(grid.index).fillna(0.0) * (12 / max(months, 1))
    area = np.array([h3.cell_area(c, unit="km^2") for c in grid.index])
    residents = np.maximum(grid["raw_population_density"].to_numpy() * area, MIN_RESIDENTS)
    return counts / residents * 1000


def synthetic(grid: pd.DataFrame) -> pd.Series:
    d = _synthetic.dist_centre_m(grid)
    rate = 55 + 260 * np.exp(-((d / 3000) ** 2)) + 25 * _synthetic.east_west(grid)
    rate *= np.exp(0.25 * _synthetic.smooth_noise(grid, META.id, 120, 1500))
    return pd.Series(np.maximum(rate, 8), index=grid.index)
