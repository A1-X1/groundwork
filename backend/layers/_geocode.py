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
