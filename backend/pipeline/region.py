"""Region definitions (regions.yaml): city outlines and Natural Earth countries."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from backend.layers._common import RAW_DIR

REGIONS_FILE = Path(__file__).parent / "regions.yaml"
NATURAL_EARTH = RAW_DIR / "naturalearth" / "ne_10m_admin_0_countries.zip"
NATURAL_EARTH_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"

# Simplified Greater London boundary (lon, lat), clockwise from the Colne Valley. Edges are
# within ~1-2 km of the real boundary and the area is ~10% larger (1,755 vs 1,572 km²).
# Save the official ONS/GLA boundary as data/raw/london_boundary.geojson (WGS84) to use
# the exact outline instead.
LONDON_OUTLINE: list[tuple[float, float]] = [
    (-0.510, 51.468), (-0.500, 51.540), (-0.490, 51.600), (-0.460, 51.630), (-0.400, 51.632),
    (-0.330, 51.640), (-0.280, 51.660), (-0.210, 51.664), (-0.170, 51.686), (-0.100, 51.692),
    (-0.050, 51.690), (-0.012, 51.680), (0.010, 51.640), (0.070, 51.612), (0.130, 51.628),
    (0.200, 51.630), (0.270, 51.612), (0.310, 51.580), (0.334, 51.540), (0.312, 51.500),
    (0.250, 51.478), (0.218, 51.468), (0.200, 51.450), (0.170, 51.410), (0.150, 51.390),
    (0.120, 51.350), (0.090, 51.300), (0.020, 51.290), (-0.040, 51.300), (-0.090, 51.310),
    (-0.130, 51.298), (-0.160, 51.292), (-0.190, 51.330), (-0.250, 51.350), (-0.290, 51.332),
    (-0.330, 51.330), (-0.330, 51.370), (-0.360, 51.400), (-0.420, 51.410), (-0.460, 51.430),
    (-0.490, 51.450), (-0.510, 51.468),
]


@dataclass(frozen=True)
class Region:
    id: str
    label: str
    resolution: int
    geometry: dict[str, Any] = field(hash=False)  # GeoJSON Polygon/MultiPolygon (lon, lat)
    source: str
    country: str = "GBR"
    kind: str = "city"
    order: int = 0

    @property
    def outline(self) -> list[tuple[float, float]]:
        """Exterior ring of the largest polygon (kept for older callers)."""
        polys = self.geometry["coordinates"] if self.geometry["type"] == "MultiPolygon" else [self.geometry["coordinates"]]
        return [tuple(p) for p in max(polys, key=lambda poly: len(poly[0]))[0]]


def definitions() -> list[dict[str, Any]]:
    return sorted(yaml.safe_load(REGIONS_FILE.read_text()), key=lambda r: r.get("order", 99))


def region_ids() -> list[str]:
    return [r["id"] for r in definitions()]


@lru_cache(maxsize=16)
def get(region_id: str = "london") -> Region:
    spec = next((r for r in definitions() if r["id"] == region_id), None)
    if spec is None:
        raise KeyError(f"unknown region {region_id!r}; known: {region_ids()}")
    if isinstance(spec["boundary"], dict):  # derived (e.g. urban areas of another region)
        b = spec["boundary"]
        geom, source = {"type": "Derived", **b}, (f"cells of {b['urban_of']} with population density "
                                                   f"≥ {b.get('min_density', 1000)}/km² (WorldPop)")
    elif spec["boundary"] == "london":
        geom, source = _london_geometry()
    else:
        geom, source = _country_geometry(spec["boundary"]), f"Natural Earth 10m admin-0 ({spec['boundary']})"
    return Region(spec["id"], spec["name"], int(spec["resolution"]), geom, source,
                  spec.get("country", "GBR"), spec.get("kind", "national"), int(spec.get("order", 0)))


def london(resolution: int = 8) -> Region:
    r = get("london")
    return r if r.resolution == resolution else Region(r.id, r.label, resolution, r.geometry, r.source, r.country, r.kind)


def _london_geometry() -> tuple[dict[str, Any], str]:
    path = RAW_DIR / "london_boundary.geojson"
    if path.exists():
        gj = json.loads(path.read_text())
        geom = gj["features"][0]["geometry"] if "features" in gj else gj
        return geom, f"boundary file {path.name}"
    return {"type": "Polygon", "coordinates": [[list(p) for p in LONDON_OUTLINE]]}, "simplified built-in outline"


def _country_geometry(adm0_a3: str) -> dict[str, Any]:
    if not NATURAL_EARTH.exists():
        from backend.layers._common import is_offline

        if is_offline():
            raise FileNotFoundError(f"offline and no {NATURAL_EARTH}")
        import requests

        NATURAL_EARTH.parent.mkdir(parents=True, exist_ok=True)
        NATURAL_EARTH.write_bytes(requests.get(NATURAL_EARTH_URL, timeout=120).content)
    import shapefile

    reader = shapefile.Reader(str(NATURAL_EARTH))
    names = [f[0] for f in reader.fields[1:]]
    idx = names.index("ADM0_A3")
    for sr in reader.iterShapeRecords():
        if sr.record[idx] == adm0_a3:
            return sr.shape.__geo_interface__
    raise KeyError(f"country {adm0_a3!r} not in Natural Earth")
