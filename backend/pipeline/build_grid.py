"""Region boundary → H3 cells → centroids."""

from __future__ import annotations

from functools import lru_cache

import h3
import pandas as pd

from .region import Region, london


def cells_for(region: Region) -> list[str]:
    poly = h3.LatLngPoly([(lat, lon) for lon, lat in region.outline])
    return sorted(h3.polygon_to_cells(poly, region.resolution))


@lru_cache(maxsize=4)
def build_grid(resolution: int = 8) -> pd.DataFrame:
    """DataFrame indexed by H3 id (``h3``) with ``lat``/``lon`` centroid columns."""
    region = london(resolution)
    cells = cells_for(region)
    lat, lon = zip(*(h3.cell_to_latlng(c) for c in cells), strict=True)
    grid = pd.DataFrame({"lat": lat, "lon": lon}, index=pd.Index(cells, name="h3"))
    grid.attrs.update(region=region.id, resolution=resolution, boundary=region.source)
    return grid


if __name__ == "__main__":
    g = build_grid()
    print(f"{len(g)} cells at res {g.attrs['resolution']} ({g.attrs['boundary']})")
