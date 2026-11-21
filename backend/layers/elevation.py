"""Ground elevation (m) from the Copernicus DEM via the Open-Meteo elevation API."""

from __future__ import annotations

import pandas as pd

from . import _synthetic
from ._common import LayerMeta, cached_json, http_get

META = LayerMeta(
    id="elevation", label="Elevation", unit="m", kind="raster",
    description="Ground height above sea level at the hex centre.",
    source="Copernicus GLO-90 DEM via Open-Meteo Elevation API",
)
URL = "https://api.open-meteo.com/v1/elevation"


def fetch() -> dict[str, float]:
    from backend.pipeline.build_grid import build_grid

    grid = build_grid()

    def produce() -> dict[str, float]:
        out: dict[str, float] = {}
        cells = list(grid.index)
        for i in range(0, len(cells), 100):
            chunk = grid.iloc[i:i + 100]
            res = http_get(URL, {"latitude": ",".join(f"{v:.5f}" for v in chunk["lat"]),
                                 "longitude": ",".join(f"{v:.5f}" for v in chunk["lon"])})
            out.update(zip(chunk.index, res["elevation"], strict=True))
        return out

    return cached_json(f"elevation/open_meteo_res{grid.attrs.get('resolution', 8)}.json", produce)


def to_hex(raw: dict[str, float], grid: pd.DataFrame) -> pd.Series:
    return pd.Series(raw).reindex(grid.index).astype(float)


def synthetic(grid: pd.DataFrame) -> pd.Series:
    return pd.Series(_synthetic.elevation(grid), index=grid.index)
