"""Polygons from the planning.data.gov.uk entity API (EA flood zones, Green Belt, SSSIs).

A manually downloaded GeoJSON at ``data/raw/planning/<dataset>.geojson`` (WGS84) takes
precedence over the API, so a slow or blocked API never breaks the build.
"""

from __future__ import annotations

import json
from typing import Any

from ._common import MONTHLY, RAW_DIR, cached_json, http_get

URL = "https://www.planning.data.gov.uk/entity.geojson"
LONDON_BBOX = (-0.56, 51.26, 0.37, 51.72)  # w, s, e, n
PAGE = 500


def _wkt(w: float, so: float, e: float, n: float) -> str:
    return f"POLYGON(({w} {so},{e} {so},{e} {n},{w} {n},{w} {so}))"


def _query_tile(dataset: str, bbox: tuple[float, float, float, float], depth: int = 0) -> list[dict[str, Any]]:
    """All features intersecting bbox. Searches over 10,000 results can't page, so split."""
    out: list[dict[str, Any]] = []
    for page in range(30):
        try:
            res = http_get(URL, {"dataset": dataset, "geometry": _wkt(*bbox), "geometry_relation": "intersects",
                                 "limit": PAGE, "offset": page * PAGE}, timeout=120, retries=2)
        except RuntimeError as exc:
            if "400" not in str(exc) or depth >= 5:
                raise
            res = None
        if res is None or (page == 0 and res.get("count_is_capped")):
            w, so, e, n = bbox
            mx, my = (w + e) / 2, (so + n) / 2
            return [f for q in ((w, so, mx, my), (mx, so, e, my), (w, my, mx, n), (mx, my, e, n))
                    for f in _query_tile(dataset, q, depth + 1)]
        batch = res.get("features", [])
        out.extend(batch)
        if len(batch) < PAGE:
            break
    return out


def features(dataset: str) -> list[dict[str, Any]]:
    local = RAW_DIR / "planning" / f"{dataset}.geojson"
    if local.exists():
        with local.open() as fh:
            return json.load(fh)["features"]

    def produce() -> list[dict[str, Any]]:
        seen: dict[Any, dict[str, Any]] = {}
        for f in _query_tile(dataset, LONDON_BBOX):
            seen[f.get("properties", {}).get("entity") or id(f)] = f
        if not seen:
            raise RuntimeError(f"planning.data.gov.uk returned no {dataset} features")
        return list(seen.values())

    return cached_json(f"planning/api_{dataset}.json", produce, MONTHLY)


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
