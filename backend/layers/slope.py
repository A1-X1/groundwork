"""Terrain slope (%) derived from hex elevations (steepest drop to a neighbouring hex)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._common import LayerMeta

META = LayerMeta(
    id="slope", label="Slope", unit="%", kind="raster",
    description="Steepest gradient from this hex to any neighbouring hex.",
    source="Derived from the elevation layer",
    depends_on=("elevation",),
    derived=True,
)


def fetch() -> None:
    return None  # derived; nothing to download


def to_hex(raw: None, grid: pd.DataFrame) -> pd.Series:
    import h3

    elev = grid["raw_elevation"]
    out = {}
    for cell in grid.index:
        lat, lon = h3.cell_to_latlng(cell)
        best = 0.0
        for nb in h3.grid_ring(cell, 1):
            if nb in elev.index:
                d = h3.great_circle_distance((lat, lon), h3.cell_to_latlng(nb), unit="m")
                best = max(best, abs(elev[cell] - elev[nb]) / d * 100)
        out[cell] = best
    return pd.Series(out).reindex(grid.index)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    if "raw_elevation" not in grid:
        raise RuntimeError("slope needs raw_elevation")
    return to_hex(None, grid).fillna(0.0).clip(lower=0).pipe(lambda s: s.where(np.isfinite(s), 0.0))
