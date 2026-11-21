"""Region boundary → H3 cells → centroids."""

from __future__ import annotations

from functools import lru_cache

import h3
import pandas as pd

from .region import Region, get


def cells_for(region: Region) -> list[str]:
    if region.geometry.get("type") == "Derived":
        return _urban_cells(region)
    return sorted(h3.geo_to_cells(region.geometry, region.resolution))


def _urban_cells(region: Region) -> list[str]:
    """Children of the parent region's dense cells, minus cells other regions already cover."""
    import pandas as pd

    from backend.scoring.data import region_dirs

    spec = region.geometry
    dirs = region_dirs()
    parent = spec["urban_of"]
    if parent not in dirs:
        raise FileNotFoundError(f"build region {parent!r} first (python -m backend.pipeline.run --region {parent})")
    pg = pd.read_parquet(dirs[parent] / "grid.parquet", columns=["h3", "raw_population_density"])
    dense = pg.loc[pg["raw_population_density"] >= float(spec.get("min_density", 1000)), "h3"]
    cells = {c for p in dense for c in h3.cell_to_children(p, region.resolution)}
    for other in spec.get("exclude", []):
        if other in dirs:
            og = pd.read_parquet(dirs[other] / "grid.parquet", columns=["h3"])["h3"]
            covered = {h3.cell_to_parent(c, region.resolution) if h3.get_resolution(c) > region.resolution else c
                       for c in og}
            covered |= {k for c in og if h3.get_resolution(c) < region.resolution
                        for k in h3.cell_to_children(c, region.resolution)}
            cells -= covered
    return sorted(cells)


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
    from backend.scoring.world import non_wrapping_bbox
    grid = pd.DataFrame({"lat": lat, "lon": lon}, index=pd.Index(cells, name="h3"))
    pad = h3.average_hexagon_edge_length(res, unit="km") / 111.0
    grid.attrs.update(region=region.id, resolution=res, boundary=region.source, kind=region.kind,
                      country=region.country, label=region.label,
                      bbox=tuple(v + d for v, d in zip(non_wrapping_bbox(lon, lat), (-pad, -pad, pad, pad), strict=True)))
    return grid


if __name__ == "__main__":
    import sys

    for rid in sys.argv[1:] or ["london"]:
        g = build_grid(region_id=rid)
        print(f"{rid}: {len(g)} cells at res {g.attrs['resolution']} ({g.attrs['boundary']})")
