"""Parametric 3D building specs the frontend renders with three.js.

A spec is a small list of primitives in metres (y up, origin = hex centre at ground
level). It's data, not code, so the agent can design one safely. The frontend maps
each primitive to a three.js geometry (BoxGeometry, CylinderGeometry, ConeGeometry,
SphereGeometry half for domes, LatheGeometry for hyperboloid cooling towers).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MODELS_DIR = Path(__file__).resolve().parents[1] / "profiles" / "models"
MAX_TRIANGLES = 5000
SEGMENTS = 24  # radial segments the frontend should use

PALETTE = {
    "concrete": "#b8bcc2", "steel": "#8a94a3", "glass": "#5b7fa6", "roof": "#3d4450",
    "brick": "#9c5b46", "white": "#e8eaed", "accent": "#0064e0", "earth": "#7a6a52",
    "green": "#4f7d5a", "dark": "#2a2f37", "warning": "#e0a100",
}
Colour = Literal["concrete", "steel", "glass", "roof", "brick", "white", "accent", "earth", "green", "dark", "warning"]
Vec3 = tuple[float, float, float]


class _Part(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: Vec3 = (0.0, 0.0, 0.0)   # base centre, metres (also the rotation pivot)
    rotation_y: float = 0.0            # degrees, about the vertical axis
    rotation_z: float = 0.0            # degrees, tilt in the x–y plane (e.g. turbine blades)
    color: Colour = "concrete"


class Box(_Part):
    shape: Literal["box"]
    size: Vec3                          # width (x), height (y), depth (z)

    def triangles(self) -> int:
        return 12


class Cylinder(_Part):
    shape: Literal["cylinder"]
    radius: float = Field(gt=0, le=200)
    height: float = Field(gt=0, le=300)

    def triangles(self) -> int:
        return SEGMENTS * 4


class Cone(_Part):
    shape: Literal["cone"]
    radius: float = Field(gt=0, le=200)
    height: float = Field(gt=0, le=300)

    def triangles(self) -> int:
        return SEGMENTS * 2


class Dome(_Part):
    shape: Literal["dome"]
    radius: float = Field(gt=0, le=200)

    def triangles(self) -> int:
        return SEGMENTS * (SEGMENTS // 2) * 2


class Hyperboloid(_Part):
    """Cooling-tower shell, lathed from three radii."""

    shape: Literal["hyperboloid"]
    radius_bottom: float = Field(gt=0, le=200)
    radius_waist: float = Field(gt=0, le=200)
    radius_top: float = Field(gt=0, le=200)
    height: float = Field(gt=0, le=300)
    waist_at: float = Field(default=0.75, gt=0.1, lt=0.95)  # fraction of height

    def triangles(self) -> int:
        return SEGMENTS * 12 * 2


Part = Annotated[Box | Cylinder | Cone | Dome | Hyperboloid, Field(discriminator="shape")]


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,40}$")
    label: str
    footprint_m: tuple[float, float] = Field(description="bounding width × depth in metres")
    parts: list[Part] = Field(min_length=1, max_length=40)
    palette: dict[str, str] = Field(default_factory=lambda: dict(PALETTE))
    segments: int = SEGMENTS

    @model_validator(mode="after")
    def _budget(self) -> ModelSpec:
        tris = self.triangles()
        if tris > MAX_TRIANGLES:
            raise ValueError(f"model has ~{tris} triangles; the budget is {MAX_TRIANGLES}")
        w, d = self.footprint_m
        for p in self.parts:
            x, _, z = p.position
            if abs(x) > w or abs(z) > d:
                raise ValueError(f"part at {p.position} lies outside the {w}×{d} m footprint")
        return self

    def triangles(self) -> int:
        return sum(p.triangles() for p in self.parts)


def local_models_dir() -> Path:
    from backend.layers import _common

    return _common.LOCAL_DIR / "models3d"


def list_ids() -> list[str]:
    """Every saved spec: committed (backend/profiles/models/) and local agent-made (data/local/models3d/)."""
    ids = {p.stem for d in (MODELS_DIR, local_models_dir()) if d.exists() for p in d.glob("*.json")}
    return sorted(ids)


def save(spec: ModelSpec, directory: Path | None = None) -> Path:
    """Agent saves go to the local (gitignored) folder unless a directory is given."""
    directory = directory or local_models_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{spec.id}.json"
    payload = spec.model_dump(mode="json")
    payload["triangles"] = spec.triangles()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load(model_id: str, directory: Path | None = None) -> dict:
    """A local agent-made spec wins over a committed one with the same id."""
    dirs = [directory] if directory else [local_models_dir(), MODELS_DIR]
    for d in dirs:
        path = d / f"{model_id}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise KeyError(f"no 3D model {model_id!r}")


def cooling_tower(x: float, z: float, h: float = 120.0) -> dict:
    """Helper used by presets and examples in the agent instructions."""
    r = h * 0.4
    return {"shape": "hyperboloid", "position": [x, 0, z], "radius_bottom": r, "radius_waist": r * 0.62,
            "radius_top": r * 0.7, "height": h, "color": "white"}

