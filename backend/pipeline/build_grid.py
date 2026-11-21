"""Region boundary → H3 cells → centroids."""

from __future__ import annotations

from functools import lru_cache

import h3
import pandas as pd

from .region import Region, get


def cells_for(region: Region) -> list[str]:
    return sorted(h3.geo_to_cells(region.geometry, region.resolution))


@lru_cache(maxsize=8)
def build_grid(resolution: int | None = None, region_id: str = "london") -> pd.DataFrame:
    """DataFrame indexed by H3 id (``h3``) with ``lat``/``lon`` centroid columns.

    ``attrs`` carries the region id, kind (city|national), country, resolution and bbox.
    """
    region = get(region_id)
    res = resolution or region.resolution
    if res != region.resolution:
        region = Region(region.id, region.label, res, region.geometry, region.source, region.country, region.kind)
    cells = cells_for(region)
    lat, lon = zip(*(h3.cell_to_latlng(c) for c in cells), strict=True)
    grid = pd.DataFrame({"lat": lat, "lon": lon}, index=pd.Index(cells, name="h3"))
    pad = h3.average_hexagon_edge_length(res, unit="km") / 111.0
    grid.attrs.update(region=region.id, resolution=res, boundary=region.source, kind=region.kind,
                      country=region.country, label=region.label,
                      bbox=(min(lon) - pad, min(lat) - pad, max(lon) + pad, max(lat) + pad))
    return grid


if __name__ == "__main__":
    import sys

    for rid in sys.argv[1:] or ["london"]:
        g = build_grid(region_id=rid)
        print(f"{rid}: {len(g)} cells at res {g.attrs['resolution']} ({g.attrs['boundary']})")
