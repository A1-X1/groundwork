"""Reverse geocoding (Nominatim, OSM) for naming recommended sites. Cached forever, ≤1 req/s."""

from __future__ import annotations

import time

from ._common import cached_json, http_get

URL = "https://nominatim.openstreetmap.org/reverse"
_last_call = 0.0


def area_name(lat: float, lon: float) -> str | None:
    """Neighbourhood-level name, e.g. "Feltham, London Borough of Hounslow"; None if unavailable."""
    key = f"geocode/{lat:.3f}_{lon:.3f}.json"

    def produce() -> dict:
        global _last_call
        wait = 1.05 - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)  # Nominatim usage policy: at most 1 request per second
        _last_call = time.time()
        return http_get(URL, {"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "format": "jsonv2", "zoom": 14},
                        timeout=20, retries=1)

    try:
        res = cached_json(key, produce)
    except Exception:  # noqa: BLE001 — offline or rate-limited: no name
        return None
    addr = res.get("address", {})
    local = addr.get("suburb") or addr.get("neighbourhood") or addr.get("quarter") or addr.get("town") \
        or addr.get("village") or res.get("name")
    district = addr.get("city_district") or addr.get("borough") or addr.get("city")
    parts = [p for p in (local, district) if p]
    return ", ".join(dict.fromkeys(parts)) or None


SEARCH_URL = "https://nominatim.openstreetmap.org/search"


def _throttled_get(url: str, params: dict) -> object:
    global _last_call
    wait = 1.05 - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()
    return http_get(url, params, timeout=20, retries=1)


def lookup(query: str) -> dict | None:
    """Forward geocode an address or place → {address, lat, lon, kind}; None if nothing found."""
    import hashlib

    q = " ".join(query.split())[:200]
    if not q:
        return None
    key = f"geocode/search_{hashlib.sha1(q.lower().encode()).hexdigest()[:16]}.json"
    res = cached_json(key, lambda: _throttled_get(SEARCH_URL, {"q": q, "format": "jsonv2", "limit": 1}))
    if not res:
        return None
    r = res[0]
    return {"address": r.get("display_name"), "lat": round(float(r["lat"]), 6), "lon": round(float(r["lon"]), 6),
            "kind": r.get("type") or r.get("category")}


def address_at(lat: float, lon: float) -> str | None:
    """Full street address at a point (reverse geocode, zoom 18)."""
    key = f"geocode/addr_{lat:.5f}_{lon:.5f}.json"
    try:
        res = cached_json(key, lambda: _throttled_get(URL, {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}",
                                                            "format": "jsonv2", "zoom": 18}))
    except Exception:  # noqa: BLE001
        return None
    return res.get("display_name")
