"""Points of interest for map icons: real (cached OSM) or seeded lists only, never synthetic."""

from __future__ import annotations

from typing import Any

POI_KINDS = ("station", "substation", "power_plant", "water", "port", "ixp", "data_centre", "airport")
_OSM_QUERY = {"substation": "substations", "station": "stations", "data_centre": "data_centres", "water": "water"}


def _osm_pois(kind: str) -> list[dict[str, Any]]:
    from backend.layers import _osm

    out = []
    for el in _osm.cached_elements(_OSM_QUERY[kind]):
        pts = _osm.element_points([el])
        if not pts:
            continue
        tags = el.get("tags", {})
        if kind == "water" and not tags.get("name"):
            continue  # unnamed ponds would flood the map
        out.append({"id": f"osm:{el.get('type')}/{el.get('id')}", "kind": kind,
                    "name": tags.get("name") or tags.get("operator") or kind.replace("_", " "),
                    "lon": round(pts[0][0], 6), "lat": round(pts[0][1], 6), "source": "osm"})
    return out


def _seeded(kind: str) -> list[dict[str, Any]]:
    from backend.layers import _places

    rows = {"ixp": _places.IXPS, "data_centre": _places.DATA_CENTRES, "water": _places.RESERVOIRS}.get(kind, [])
    return [{"id": f"seed:{kind}/{i}", "kind": kind, "name": name, "lon": lon, "lat": lat, "source": "seeded"}
            for i, (name, lon, lat) in enumerate(rows)]


def _region_pois(kinds: set[str]) -> list[dict[str, Any]]:
    """Per-region pois.parquet files (backend/pipeline/pois.py), for every loaded region."""
    import pandas as pd

    from .data import region_dirs

    out: list[dict[str, Any]] = []
    for rid, d in region_dirs().items():
        path = d / "pois.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        df = df[df["kind"].isin(kinds)]
        df = df.assign(region=rid)
        out.extend(df.to_dict("records"))
    return out


def list_pois(kinds: list[str] | None = None, bbox: tuple[float, float, float, float] | None = None) -> list[dict]:
    kinds = list(kinds or POI_KINDS)
    unknown = sorted(set(kinds) - set(POI_KINDS))
    if unknown:
        raise KeyError(f"unknown POI kind(s) {unknown}; known: {list(POI_KINDS)}")
    out: list[dict[str, Any]] = _region_pois(set(kinds))
    have = {p["kind"] for p in out}
    for kind in kinds:  # London extras: cached OSM, then seeded lists where nothing else exists
        rows = _osm_pois(kind) if kind in _OSM_QUERY else []
        if not rows and kind not in have:
            rows = _seeded(kind)
        out.extend(rows)
    seen: set[tuple] = set()
    uniq = []
    for p in out:  # the same site can come from several sources
        key = (p["kind"], round(p["lat"], 3), round(p["lon"], 3))
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    out = uniq
    if bbox is not None:
        from .scorer import validate_bbox

        w, s, e, n = validate_bbox(bbox)
        out = [p for p in out if w <= p["lon"] <= e and s <= p["lat"] <= n]
    return out
