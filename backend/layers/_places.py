"""Seeded, publicly known London locations (approximate coordinates, lon/lat).

These are used directly by ``dist_fibre_ix`` (a real, if approximate, layer) and as
fallbacks for synthetic layers and ML positives. Coordinates are rounded to ~100 m
and are good enough for res-8 hexes (~0.5 km across); they are not survey grade.
"""

from __future__ import annotations

# Internet exchange / interconnection hubs hosting LINX or LONAP points of presence.
IXPS: list[tuple[str, float, float]] = [
    ("Telehouse North, Docklands", 0.0005, 51.5113),
    ("Telehouse East, Docklands", 0.0020, 51.5105),
    ("Telehouse West, Docklands", -0.0008, 51.5101),
    ("Equinix LD8, Harbour Exchange", -0.0153, 51.4994),
    ("Global Switch London East, Docklands", 0.0110, 51.5089),
    ("Digital Realty LON1, Brick Lane", -0.0717, 51.5215),
    ("Equinix Slough campus (LD4-LD6)", -0.6240, 51.5220),
]

# Approximate centres of London's known data-centre clusters. Fallback ML positives
# for ``data_centre`` when OSM (telecom=data_center) cannot be fetched.
DATA_CENTRES: list[tuple[str, float, float]] = [
    *IXPS,
    ("Docklands cluster (Isle of Dogs)", -0.0157, 51.5012),
    ("Docklands cluster (Blackwall)", 0.0050, 51.5080),
    ("Park Royal cluster", -0.2720, 51.5280),
    ("Hayes / Stockley Park cluster", -0.4300, 51.5100),
    ("Brimsdown / Enfield cluster", -0.0350, 51.6500),
    ("Stratford cluster", -0.0040, 51.5420),
    ("Dagenham cluster", 0.1450, 51.5310),
    ("Wembley cluster", -0.2880, 51.5590),
    ("Croydon cluster", -0.1000, 51.3780),
    ("Heathrow perimeter cluster", -0.4700, 51.4900),
]

RESERVOIRS: list[tuple[str, float, float]] = [
    ("King George V Reservoir", -0.0300, 51.6400),
    ("William Girling Reservoir", -0.0350, 51.6250),
    ("Walthamstow Reservoirs", -0.0500, 51.5850),
    ("Brent Reservoir", -0.2420, 51.5740),
    ("Queen Mary Reservoir", -0.4590, 51.4150),
    ("Staines Reservoirs", -0.4970, 51.4500),
    ("Ruislip Lido", -0.4280, 51.5930),
]

# Large designated / protected open land (name, lon, lat, radius metres).
PROTECTED_SITES: list[tuple[str, float, float, float]] = [
    ("Richmond Park", -0.2750, 51.4420, 1500),
    ("Bushy Park", -0.3380, 51.4100, 900),
    ("Wimbledon Common", -0.2350, 51.4330, 900),
    ("Hampstead Heath", -0.1650, 51.5610, 700),
    ("Epping Forest (London part)", 0.0100, 51.6300, 1600),
    ("Rainham Marshes", 0.2000, 51.4980, 1000),
    ("Ruislip Woods", -0.4350, 51.6000, 900),
    ("Lee Valley Regional Park", -0.0300, 51.6300, 1200),
    ("Hainault Forest", 0.1300, 51.6150, 900),
    ("Farthing Downs", -0.1350, 51.3050, 900),
    ("Crystal Palace Park", -0.0700, 51.4220, 400),
    ("Walthamstow Marshes", -0.0500, 51.5700, 600),
]

HEATHROW = (-0.4543, 51.4700)
CITY_OF_LONDON = (-0.0920, 51.5155)
