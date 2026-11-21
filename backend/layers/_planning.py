"""Polygons from the planning.data.gov.uk entity API (EA flood zones, Green Belt, SSSIs).

A manually downloaded GeoJSON at ``data/raw/planning/<dataset>.geojson`` (WGS84) takes
precedence over the API, so a slow or blocked API never breaks the build.
"""

from __future__ import annotations

import json
from typing import Any

from ._common import RAW_DIR, cached_json, http_get

URL = "https://www.planning.data.gov.uk/entity.geojson"
LONDON_WKT = "POLYGON((-0.56 51.26,0.37 51.26,0.37 51.72,-0.56 51.72,-0.56 51.26))"
PAGE = 500


def features(dataset: str, max_pages: int = 200) -> list[dict[str, Any]]:
    local = RAW_DIR / "planning" / f"{dataset}.geojson"
    if local.exists():
        with local.open() as fh:
            return json.load(fh)["features"]

    def produce() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for page in range(max_pages):
            res = http_get(URL, {"dataset": dataset, "geometry": LONDON_WKT,
                                 "geometry_relation": "intersects",
                                 "limit": PAGE, "offset": page * PAGE}, timeout=120)
            batch = res.get("features", [])
            out.extend(batch)
            if len(batch) < PAGE:
                break
        if not out:
            raise RuntimeError(f"planning.data.gov.uk returned no {dataset} features")
        return out

    return cached_json(f"planning/api_{dataset}.json", produce)


def polygons(feats: list[dict[str, Any]]) -> list:
    from shapely.geometry import shape

    polys = []
    for f in feats:
        try:
            g = shape(f["geometry"])
        except Exception:  # noqa: BLE001 — skip malformed geometries
            continue
        if g.is_empty:
            continue
        polys.extend(getattr(g, "geoms", [g]))
    return polys
