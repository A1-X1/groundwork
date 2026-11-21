"""Points of interest for map icons: power, connectivity, transport, water, existing data centres.

Uses ``backend.scoring.list_pois(kinds, bbox)`` when Person 1 provides it (requested in
shared/handoff/p2-to-p1.md). Until then a small seed list of well-known London sites is served,
with approximate coordinates and ``source`` saying so. It is a display aid, not scoring input.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Fallback list when the scoring module doesn't publish its own (``scoring.pois.POI_KINDS``).
DEFAULT_KINDS: tuple[str, ...] = (
    "station", "substation", "power_plant", "water", "port", "ixp", "data_centre", "airport",
)  # fmt: skip
# Most points one response may carry (the USA alone has ~12k); the client asks per viewport.
MAX_POIS = 4000


def kinds_from(scoring: Any) -> tuple[str, ...]:
    mod = getattr(scoring, "pois", None)
    return tuple(getattr(mod, "POI_KINDS", None) or DEFAULT_KINDS)


class Poi(BaseModel):
    id: str
    kind: str = Field(description="station, substation, power_plant, water, port, ixp, …")
    name: str
    lat: float
    lon: float
    source: str = Field(description="Where the location comes from, and how exact it is.")
    region: str | None = Field(default=None, description="Region id the point belongs to.")
    detail: str | None = Field(
        default=None, description="Extra facts, e.g. a power plant's fuel and MW."
    )


SEED = "seed list (approximate location)"

# (kind, name, lat, lon). Approximate public locations, for orientation only.
_SEED: list[tuple[str, str, float, float]] = [
    ("ixp", "Telehouse North / East (Docklands)", 51.5115, -0.0010),
    ("ixp", "Equinix LD8 (Harbour Exchange)", 51.4995, -0.0160),
    ("ixp", "Telehouse West", 51.5105, 0.0030),
    ("ixp", "Global Switch London East", 51.5113, -0.0045),
    ("data_centre", "Slough Trading Estate cluster", 51.5230, -0.6210),
    ("data_centre", "Park Royal cluster", 51.5280, -0.2790),
    ("data_centre", "Docklands cluster", 51.5100, -0.0020),
    ("data_centre", "Enfield cluster", 51.6620, -0.0330),
    ("substation", "Barking 400 kV", 51.5225, 0.1060),
    ("substation", "West Ham 400 kV", 51.5245, 0.0040),
    ("substation", "Willesden 275 kV", 51.5395, -0.2440),
    ("substation", "Wimbledon 275 kV", 51.4170, -0.1910),
    ("substation", "Hurst 275 kV", 51.4380, 0.1450),
    ("substation", "Tottenham 275 kV", 51.6040, -0.0560),
    ("substation", "St John's Wood 400 kV", 51.5320, -0.1700),
    ("substation", "Beddington 275 kV", 51.3800, -0.1350),
    ("station", "King's Cross St Pancras", 51.5308, -0.1238),
    ("station", "Paddington", 51.5154, -0.1755),
    ("station", "Waterloo", 51.5031, -0.1132),
    ("station", "Liverpool Street", 51.5178, -0.0817),
    ("station", "Victoria", 51.4952, -0.1441),
    ("station", "Euston", 51.5282, -0.1337),
    ("station", "London Bridge", 51.5052, -0.0864),
    ("station", "Stratford", 51.5416, -0.0033),
    ("station", "Clapham Junction", 51.4642, -0.1703),
    ("station", "Canary Wharf (Elizabeth line)", 51.5059, -0.0179),
    ("water", "Queen Mary Reservoir", 51.4180, -0.4520),
    ("water", "King George V Reservoir", 51.6460, -0.0280),
    ("water", "William Girling Reservoir", 51.6300, -0.0390),
    ("water", "Walthamstow Reservoirs", 51.5870, -0.0510),
    ("water", "Queen Elizabeth II Reservoir", 51.3920, -0.3940),
]


def seed_pois() -> list[dict[str, Any]]:
    return [
        {"id": f"seed-{i}", "kind": k, "name": n, "lat": lat, "lon": lon, "source": SEED}
        for i, (k, n, lat, lon) in enumerate(_SEED)
    ]


def list_pois(
    scoring: Any, kinds: list[str] | None, bbox: tuple[float, float, float, float] | None
) -> list[dict[str, Any]]:
    known = kinds_from(scoring)
    wanted = set(kinds or known)
    unknown = wanted - set(known)
    if unknown:
        raise ValueError(f"unknown POI kind(s): {', '.join(sorted(unknown))}")
    seeds = seed_pois()
    items: list[dict[str, Any]] = []
    for kind in sorted(wanted):
        real = scoring.list_pois([kind], bbox) if hasattr(scoring, "list_pois") else []
        # Prefer real points; fall back to the labelled seed list for kinds with none cached.
        items.extend(real or [p for p in seeds if p["kind"] == kind])
    out = items
    if bbox:
        w, s, e, n = bbox
        out = [p for p in out if w <= p["lon"] <= e and s <= p["lat"] <= n]
    # Seeds are London-only and approximate: drop them where real points of that kind exist.
    real_kinds = {p["kind"] for p in out if p.get("source") != SEED}
    out = [p for p in out if p.get("source") != SEED or p["kind"] not in real_kinds]
    # NaN-free strings for optional fields (parquet rows can carry NaN)
    for p in out:
        for k in ("region", "detail"):
            v = p.get(k)
            if v is not None and not isinstance(v, str):
                p[k] = None if v != v else str(v)
    return cap_fairly(out, MAX_POIS)


def cap_fairly(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """At most ``limit`` points, shared round-robin across kinds so no category vanishes."""
    if len(items) <= limit:
        return items
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for p in items:
        by_kind.setdefault(p["kind"], []).append(p)
    queues = list(by_kind.values())
    out: list[dict[str, Any]] = []
    i = 0
    while len(out) < limit and queues:
        q = queues[i % len(queues)]
        out.append(q.pop(0))
        if not q:
            queues.remove(q)
        else:
            i += 1
    return out
