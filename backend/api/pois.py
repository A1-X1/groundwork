"""Points of interest for map icons: power, connectivity, transport, water, existing data centres.

Uses ``backend.scoring.list_pois(kinds, bbox)`` when Person 1 provides it (requested in
shared/handoff/p2-to-p1.md). Until then a small seed list of well-known London sites is served,
with approximate coordinates and ``source`` saying so. It is a display aid, not scoring input.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PoiKind = Literal["substation", "ixp", "data_centre", "station", "water"]
KINDS: tuple[str, ...] = ("substation", "ixp", "data_centre", "station", "water")


class Poi(BaseModel):
    id: str
    kind: PoiKind
    name: str
    lat: float
    lon: float
    source: str = Field(description="Where the location comes from, and how exact it is.")


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
    wanted = set(kinds or KINDS)
    unknown = wanted - set(KINDS)
    if unknown:
        raise ValueError(f"unknown POI kind(s): {', '.join(sorted(unknown))}")
    if hasattr(scoring, "list_pois"):
        items = scoring.list_pois(sorted(wanted), bbox)
    else:
        items = seed_pois()
    out = [p for p in items if p["kind"] in wanted]
    if bbox:
        w, s, e, n = bbox
        out = [p for p in out if w <= p["lon"] <= e and s <= p["lat"] <= n]
    return out
