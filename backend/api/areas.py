"""User-drawn areas and saved structures, stored in SQLite (backend/api/db.py)."""

from __future__ import annotations

import math
from typing import Any, Literal

import h3
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator

from backend.api import db

router = APIRouter()
RESOLUTION = 8
MAX_AREA_KM2 = 20_000

# Set by main.py: the active scoring module.
scoring: Any = None


class Polygon(BaseModel):
    """GeoJSON Polygon: rings of [lon, lat]; the first ring is the outline."""

    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[tuple[float, float]]]

    @field_validator("coordinates")
    @classmethod
    def _valid(cls, rings: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
        if not rings or len(rings[0]) < 3:
            raise ValueError("an area needs at least three points")
        for ring in rings:
            for lon, lat in ring:
                if not (-180 <= lon <= 180 and -90 <= lat <= 90) or not math.isfinite(lon + lat):
                    raise ValueError("coordinates must be [lon, lat] in WGS84")
            if ring[0] != ring[-1]:
                ring.append(ring[0])
        return rings


class AreaIn(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Docklands shortlist",
                "note": "Near Telehouse",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-0.03, 51.49], [0.02, 51.49], [0.02, 51.52], [-0.03, 51.52]]],
                },
            }
        }
    }

    name: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=2000)
    geometry: Polygon


class AreaPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)
    geometry: Polygon | None = None


class Area(BaseModel):
    id: str
    name: str
    note: str
    geometry: Polygon
    created_at: str
    updated_at: str


class AreaSummary(BaseModel):
    area_id: str
    profile: str
    cells: int = Field(description="H3 res-8 hexagons whose centres fall inside the area.")
    area_km2: float
    scored_cells: int = Field(description="Hexagons inside the area that have data.")
    masked_cells: int
    mean_score: float | None
    best_h3: str | None
    best_score: float | None


class StructureIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(examples=["data_centre"])
    profile: str = Field(examples=["data_centre"])
    spec: dict[str, Any] | None = Field(
        default=None, description="Requirements, e.g. GPUs, cooling, PUE (free-form JSON)."
    )
    priorities: list[str] = Field(default_factory=list)
    area_id: str | None = None


class StructurePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    spec: dict[str, Any] | None = None
    priorities: list[str] | None = None
    area_id: str | None = None


class Structure(StructureIn):
    id: str
    created_at: str
    updated_at: str


def _cells(poly: Polygon) -> list[str]:
    outer, *holes = [[(lat, lon) for lon, lat in ring] for ring in poly.coordinates]
    shape = h3.LatLngPoly(outer, *holes)
    # Guard against accidental continent-sized drawings.
    lons = [p[1] for p in outer]
    lats = [p[0] for p in outer]
    approx = (
        (max(lons) - min(lons)) * 111.32 * math.cos(math.radians(sum(lats) / len(lats)))
        * (max(lats) - min(lats)) * 110.57
    )
    if approx > MAX_AREA_KM2 * 2:
        raise ValueError(f"area is too large; keep it under about {MAX_AREA_KM2:,} km²")
    return list(h3.polygon_to_cells(shape, RESOLUTION))


# --------------------------------------------------------------------------- areas

TAGS: list[str | Any] = ["areas"]


@router.get("/areas", response_model=list[Area], tags=TAGS, summary="List saved areas")
def list_areas() -> list[dict[str, Any]]:
    """Every area users have drawn and saved, newest first."""
    return db.list_areas()


@router.post("/areas", response_model=Area, status_code=201, tags=TAGS, summary="Save an area")
def create_area(body: AreaIn) -> dict[str, Any]:
    """Store a drawn polygon with a name. Coordinates are `[lon, lat]`; the ring is closed for
    you."""
    _cells(body.geometry)  # validates size
    return db.create_area(body.name.strip(), body.geometry.model_dump(), body.note)


@router.get("/areas/{area_id}", response_model=Area, tags=TAGS, summary="Get one area")
def get_area(area_id: str) -> dict[str, Any]:
    """One saved area."""
    return db.get_area(area_id)


@router.patch("/areas/{area_id}", response_model=Area, tags=TAGS, summary="Rename or edit")
def update_area(area_id: str, body: AreaPatch) -> dict[str, Any]:
    """Change the name, note or outline of an area."""
    if body.geometry:
        _cells(body.geometry)
    return db.update_area(
        area_id,
        name=body.name.strip() if body.name else None,
        note=body.note,
        geometry=body.geometry.model_dump() if body.geometry else None,
    )


@router.delete("/areas/{area_id}", status_code=204, tags=TAGS, summary="Delete an area")
def delete_area(area_id: str) -> None:
    """Remove an area. Structures linked to it keep existing, unlinked."""
    db.delete_area(area_id)


@router.get(
    "/areas/{area_id}/summary",
    response_model=AreaSummary,
    tags=TAGS,
    summary="Score an area for a profile",
)
def area_summary(
    area_id: str,
    profile: str = Query(description="Profile id to score with.", examples=["data_centre"]),
) -> AreaSummary:
    """How many hexagons the area covers, how many are ruled out, the mean score and the best
    hexagon inside it, using the profile's default weights."""
    area = db.get_area(area_id)
    poly = Polygon(**area["geometry"])
    cells = set(_cells(poly))
    lons = [p[0] for p in poly.coordinates[0]]
    lats = [p[1] for p in poly.coordinates[0]]
    bbox = (min(lons) - 0.01, min(lats) - 0.01, max(lons) + 0.01, max(lats) + 0.01)
    scored = [c for c in scoring.score(profile, bbox=bbox) if c["h3"] in cells]
    ok = [c for c in scored if c["score"] is not None]
    best = max(ok, key=lambda c: c["score"], default=None)
    return AreaSummary(
        area_id=area_id,
        profile=profile,
        cells=len(cells),
        area_km2=round(sum(h3.cell_area(c, unit="km^2") for c in cells), 2),
        scored_cells=len(scored),
        masked_cells=sum(1 for c in scored if c["masked"]),
        mean_score=round(sum(c["score"] for c in ok) / len(ok), 4) if ok else None,
        best_h3=best["h3"] if best else None,
        best_score=best["score"] if best else None,
    )


# --------------------------------------------------------------------------- structures

STAGS: list[str | Any] = ["structures"]


@router.get("/structures", response_model=list[Structure], tags=STAGS, summary="List")
def list_structures() -> list[dict[str, Any]]:
    """Saved structures (what the user wants to build and its requirements)."""
    return db.list_structures()


@router.post("/structures", response_model=Structure, status_code=201, tags=STAGS,
             summary="Save a structure")  # fmt: skip
def create_structure(body: StructureIn) -> dict[str, Any]:
    """Store a structure: its type, scoring profile, requirements and optional area."""
    if scoring is not None:
        ids = {p["id"] for p in scoring.list_profiles()}
        if body.profile not in ids:
            raise KeyError(f"profile '{body.profile}'")
    return db.create_structure(
        body.name.strip(), body.type, body.profile, body.spec, body.priorities, body.area_id
    )


@router.patch("/structures/{sid}", response_model=Structure, tags=STAGS, summary="Edit")
def update_structure(sid: str, body: StructurePatch) -> dict[str, Any]:
    """Rename, change requirements, or link to an area."""
    return db.update_structure(
        sid,
        name=body.name.strip() if body.name else None,
        spec=body.spec,
        priorities=body.priorities,
        area_id=body.area_id,
    )


@router.delete("/structures/{sid}", status_code=204, tags=STAGS, summary="Delete")
def delete_structure(sid: str) -> None:
    """Remove a saved structure."""
    db.delete_structure(sid)
