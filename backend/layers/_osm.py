"""OpenStreetMap features via the Overpass API, cached in data/raw/osm/."""

from __future__ import annotations

from typing import Any

from ._common import MONTHLY, cached_json, http_get

# Tried in order; public instances rate-limit or refuse some networks, so fall back.
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
# Greater London bbox padded by ~3 km so edge hexes see features just outside.
BBOX = (51.26, -0.56, 51.72, 0.37)  # south, west, north, east (Overpass order)


def query(name: str, selectors: list[str], *, geometry: bool = True, timeout: int = 180) -> list[dict[str, Any]]:
    """Run an Overpass query (union of ``selectors``) and return its elements.

    ``selectors`` are Overpass statements without bbox, e.g. ``'nwr["railway"="station"]'``.
    """
    s, w, n, e = BBOX
    body = "".join(f"{sel}({s},{w},{n},{e});" for sel in selectors)
    out = "out geom;" if geometry else "out center;"
    ql = f"[out:json][timeout:{timeout}];({body});{out}"

    def produce() -> Any:
        errors = []
        for url in OVERPASS_URLS:
            try:
                return http_get(url, data={"data": ql}, timeout=timeout + 30, retries=2)["elements"]
            except Exception as exc:  # noqa: BLE001 — try the next mirror
                errors.append(f"{url}: {exc}")
        raise RuntimeError("all Overpass mirrors failed: " + " | ".join(errors))

    return cached_json(f"osm/{name}.json", produce, MONTHLY)


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
