"""Region definitions. Only Greater London for now; see README "Future plans"."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.layers._common import RAW_DIR

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
    outline: list[tuple[float, float]]  # (lon, lat) exterior ring
    source: str


def london(resolution: int = 8) -> Region:
    path = RAW_DIR / "london_boundary.geojson"
    if path.exists():
        with path.open() as fh:
            gj = json.load(fh)
        geom = gj["features"][0]["geometry"] if "features" in gj else gj
        coords = geom["coordinates"]
        if geom["type"] == "MultiPolygon":  # take the largest part
            coords = max(coords, key=lambda poly: len(poly[0]))
        ring = [(float(x), float(y)) for x, y in coords[0]]
        return Region("london", "Greater London", resolution, ring, f"boundary file {Path(path).name}")
    return Region("london", "Greater London", resolution, LONDON_OUTLINE, "simplified built-in outline")
