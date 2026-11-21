"""Hard mask: Green Belt, SSSIs and nature reserves."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import _osm, _places, _planning, _synthetic
from ._common import LayerMeta, OfflineError
from ._geo import share_inside

META = LayerMeta(
    id="protected_land", label="Protected land", unit="1 = protected", kind="raster",
    description="1 if at least half of the hex is Green Belt, an SSSI or a nature reserve, else 0.",
    source=("planning.data.gov.uk (green-belt, site-of-special-scientific-interest) + "
            "OpenStreetMap leisure=nature_reserve / boundary=protected_area"),
    depends_on=("population_density",),
    normalise="identity",
    is_mask=True,
)


def fetch() -> list:
    polys: list = []
    errors: list[str] = []
    offline_only = True
    for dataset in ("green-belt", "site-of-special-scientific-interest"):
        try:
            polys.extend(_planning.polygons(_planning.features(dataset)))
        except Exception as exc:  # noqa: BLE001 — try every source, fail only if all fail
            offline_only &= isinstance(exc, OfflineError)
            errors.append(f"{dataset}: {exc}")
    try:
        polys.extend(_osm.element_polygons(_osm.query(
            "protected", ['nwr["leisure"="nature_reserve"]', 'nwr["boundary"="protected_area"]'])))
    except Exception as exc:  # noqa: BLE001
        offline_only &= isinstance(exc, OfflineError)
        errors.append(f"osm: {exc}")
    if not polys:
        if offline_only:
            raise OfflineError("offline and no cached protected-land sources")
        raise RuntimeError("; ".join(errors))
    return polys


def to_hex(raw: list, grid: pd.DataFrame) -> pd.Series:
    return (share_inside(grid, raw) >= 0.5).astype(float)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    dens = grid["raw_population_density"].to_numpy() if "raw_population_density" in grid \
        else _synthetic.population_density(grid)
    d_km = _synthetic.dist_centre_m(grid) / 1000
    green_belt = (d_km > 15) & (dens < 1200)
    sites = np.zeros(len(grid), dtype=bool)
    for _, lon, lat, r in _places.PROTECTED_SITES:
        sites |= _synthetic.gaussian(grid, lon, lat, r) > 0.45
    return pd.Series((green_belt | sites).astype(float), index=grid.index)
