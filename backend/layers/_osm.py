"""OpenStreetMap features via the Overpass API, cached in data/raw/osm/."""

from __future__ import annotations

from typing import Any

import numpy as np

from ._common import MONTHLY, cached_json, http_get

# Tried in order; public instances rate-limit or refuse some networks, so fall back.
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
MAX_TILES = 400  # refuse continent-sized Overpass crawls (USA would be ~3,000 tiles per query)
# Greater London bbox padded by ~3 km so edge hexes see features just outside.
BBOX = (51.26, -0.56, 51.72, 0.37)  # south, west, north, east (Overpass order)


_down_reason: str | None = None  # circuit breaker: once every mirror fails, stop trying this run


DOWN_TTL_S = 600  # after every mirror fails, skip Overpass for 10 minutes (across runs)


def _down_file():
    from ._common import RAW_DIR

    return RAW_DIR / "osm" / "_down.json"


def _recently_down() -> str | None:
    import json
    import time

    f = _down_file()
    if f.exists():
        d = json.loads(f.read_text())
        if time.time() - d.get("at", 0) < DOWN_TTL_S:
            return d.get("reason", "recently unreachable")
    return None


def _run(ql: str, timeout: int) -> list[dict[str, Any]]:
    import json
    import time

    global _down_reason
    _down_reason = _down_reason or _recently_down()
    if _down_reason:
        raise RuntimeError(f"Overpass unavailable (checked in the last 10 min): {_down_reason[:200]}")
    errors = []
    for url in OVERPASS_URLS:
        try:
            return http_get(url, data={"data": ql}, timeout=min(timeout, 45), retries=1)["elements"]
        except Exception as exc:  # noqa: BLE001 — try the next mirror
            errors.append(f"{url.split('/')[2]}: {str(exc)[:120]}")
    _down_reason = " | ".join(errors)
    f = _down_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"at": time.time(), "reason": _down_reason}))
    raise RuntimeError("all Overpass mirrors failed: " + _down_reason)


def query(name: str, selectors: list[str], *, geometry: bool = True, timeout: int = 120,
          tiles: int = 3) -> list[dict[str, Any]]:
    """Run an Overpass query (union of ``selectors``) and return its elements.

    ``selectors`` are Overpass statements without bbox, e.g. ``'nwr["railway"="station"]'``.
    The bbox is split into ``tiles``×``tiles`` sub-queries (each cached) so heavy
    geometry requests stay under public-server limits; elements are de-duplicated.
    """
    from ._common import REGION

    s, w, n, e = BBOX
    if REGION.get("id") != "london":
        w, s, e, n = REGION["bbox"]
        tiles = max(tiles, int(np.ceil(max(e - w, n - s))))  # ~1° tiles for big regions
        if tiles * tiles > MAX_TILES:
            raise RuntimeError(f"region too large for Overpass ({tiles * tiles} tiles > {MAX_TILES}); "
                               "use a Geofabrik extract for this region")
        name = f"{REGION['id']}/{name}"
    out = "out geom;" if geometry else "out center;"
    lats = [s + (n - s) * i / tiles for i in range(tiles + 1)]
    lons = [w + (e - w) * j / tiles for j in range(tiles + 1)]
    seen: dict[tuple[str, int], dict[str, Any]] = {}
    for i in range(tiles):
        for j in range(tiles):
            bb = f"{lats[i]:.4f},{lons[j]:.4f},{lats[i + 1]:.4f},{lons[j + 1]:.4f}"
            body = "".join(f"{sel}({bb});" for sel in selectors)
            ql = f"[out:json][timeout:{timeout}];({body});{out}"
            part = cached_json(f"osm/{name}/{i}_{j}.json", lambda ql=ql: _run(ql, timeout), MONTHLY)
            for el in part:
                seen[(el.get("type", ""), el.get("id", 0))] = el
    return list(seen.values())


def cached_elements(name: str) -> list[dict[str, Any]]:
    """Elements from whatever tiles of query ``name`` are already cached (never downloads)."""
    import json

    from ._common import RAW_DIR

    seen: dict[tuple[str, int], dict[str, Any]] = {}
    for path in sorted((RAW_DIR / "osm" / name).glob("*.json")):
        for el in json.loads(path.read_text()):
            seen[(el.get("type", ""), el.get("id", 0))] = el
    return list(seen.values())


def element_points(elements: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """One representative (lon, lat) per element (node position or way/relation centroid)."""
    pts: list[tuple[float, float]] = []
    for el in elements:
        if el.get("type") == "node":
            pts.append((el["lon"], el["lat"]))
        elif "center" in el:
            pts.append((el["center"]["lon"], el["center"]["lat"]))
        elif "geometry" in el:
            g = el["geometry"]
            pts.append((sum(p["lon"] for p in g) / len(g), sum(p["lat"] for p in g) / len(g)))
        elif "members" in el:
            coords = [p for m in el["members"] for p in m.get("geometry", [])]
            if coords:
                pts.append((sum(p["lon"] for p in coords) / len(coords),
                            sum(p["lat"] for p in coords) / len(coords)))
    return pts


def element_lines(elements: list[dict[str, Any]]) -> list[list[tuple[float, float]]]:
    """Every way (and relation member way) as a (lon, lat) polyline; nodes as 1-point lines."""
    lines: list[list[tuple[float, float]]] = []
    for el in elements:
        if el.get("type") == "node":
            lines.append([(el["lon"], el["lat"])])
        elif "geometry" in el:
            lines.append([(p["lon"], p["lat"]) for p in el["geometry"] if p])
        for m in el.get("members", []):
            if m.get("geometry"):
                lines.append([(p["lon"], p["lat"]) for p in m["geometry"] if p])
    return [ln for ln in lines if ln]


def element_polygons(elements: list[dict[str, Any]]) -> list:
    """Closed ways and multipolygon relations as shapely polygons (lon/lat)."""
    from shapely.geometry import Polygon
    from shapely.ops import polygonize, unary_union

    polys = []
    for el in elements:
        if el.get("type") == "way" and "geometry" in el:
            ring = [(p["lon"], p["lat"]) for p in el["geometry"]]
            if len(ring) >= 4 and ring[0] == ring[-1]:
                poly = Polygon(ring)
                if poly.is_valid and poly.area > 0:
                    polys.append(poly)
        elif el.get("type") == "relation":
            outers = [[(p["lon"], p["lat"]) for p in m["geometry"]]
                      for m in el.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
            if outers:
                from shapely.geometry import LineString

                merged = unary_union([LineString(o) for o in outers if len(o) >= 2])
                polys.extend(p for p in polygonize(merged) if p.area > 0)
    return polys
