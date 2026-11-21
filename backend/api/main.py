"""Groundwork public API.

Run with ``make api`` (``uvicorn backend.api.main:app --reload``). Docs at /docs and /redoc.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from datetime import UTC, datetime
from typing import Annotated, Any, TypeVar

from fastapi import FastAPI, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api import scoring_source
from backend.api.models import (
    CompareEntry,
    CompareResponse,
    CustomScoreRequest,
    ErrorResponse,
    Health,
    Layer,
    LayerValues,
    PointScore,
    Profile,
    ScoreResponse,
)

RESOLUTION = 8
LONDON_POINT = {"lat": 51.5155, "lon": -0.0922}

scoring, SCORING_SOURCE = scoring_source.load()

DESCRIPTION = """
**Groundwork** answers one question for any kind of development: *where is the ideal place to
put this?*

London is divided into H3 hexagons (resolution 8, ~0.74 km² each). Every hexagon carries dozens
of environmental, infrastructure and social **layers**. A **profile** (data centre, house,
school, mine, …) picks layers, weights them and defines hard no-go **masks**.

* `score = sustainability × feasibility` — the weighted layer score, multiplied by an optional
  ML feasibility model. The model learns where things *have* been built, not where they
  *should* be; the weighted score is the normative part.
* `breakdown` gives each layer's signed contribution relative to the regional average, so you
  can see *why* a hexagon scores the way it does.
* `bbox` parameters are `min_lon,min_lat,max_lon,max_lat` (WGS84).

This is a decision-support demo, not planning advice.
"""

TAGS = [
    {"name": "meta", "description": "Service status and data provenance."},
    {"name": "profiles", "description": "Use cases: which layers matter, how much, and masks."},
    {"name": "layers", "description": "Per-hexagon data layers for map overlays."},
    {"name": "scores", "description": "Suitability for a profile, a point, or a comparison."},
]

ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Unknown profile, layer or location."},
    422: {"model": ErrorResponse, "description": "Invalid parameters or weights."},
}

app = FastAPI(
    title="Groundwork API",
    version="0.1.0",
    summary="Site suitability for any kind of development, scored per H3 hexagon.",
    description=DESCRIPTION,
    openapi_tags=TAGS,
    license_info={"name": "MIT", "identifier": "MIT"},
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- errors


def _error(status: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "detail": detail}}
    return JSONResponse(status_code=status, content=body)


@app.exception_handler(KeyError)
async def _key_error(_: Request, exc: KeyError) -> JSONResponse:
    what = exc.args[0] if exc.args else "resource"
    return _error(404, "not_found", f"Not found: {what}")


@app.exception_handler(ValueError)
async def _value_error(_: Request, exc: ValueError) -> JSONResponse:
    return _error(422, "invalid_value", str(exc))


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    errs = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in exc.errors()
    ]
    return _error(422, "validation_error", "Request parameters are invalid.", errs)


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
    return _error(exc.status_code, code, str(exc.detail))


# ---------------------------------------------------------------- cache

T = TypeVar("T")


class LRU:
    """Tiny thread-safe LRU cache for score results."""

    def __init__(self, maxsize: int = 64) -> None:
        self.maxsize = maxsize
        self._data: OrderedDict[Hashable, Any] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get_or_set(self, key: Hashable, fn: Callable[[], T]) -> T:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self.hits += 1
                return self._data[key]  # type: ignore[no-any-return]
        value = fn()
        with self._lock:
            self.misses += 1
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = self.misses = 0


score_cache = LRU(64)

BBox = tuple[float, float, float, float]


def weights_key(weights: dict[str, float] | None) -> str:
    if not weights:
        return "default"
    blob = json.dumps(sorted(weights.items()), separators=(",", ":"))
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def validate_weights(weights: dict[str, float] | None) -> dict[str, float] | None:
    if not weights:
        return None
    for k, v in weights.items():
        if not math.isfinite(v) or v < 0:
            raise ValueError(f"weight for '{k}' must be a finite, non-negative number")
    return weights


def parse_bbox(raw: str | None) -> BBox | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        parts = [float(p) for p in raw.split(",")]
    except ValueError:
        raise ValueError("bbox must be four numbers: min_lon,min_lat,max_lon,max_lat") from None
    return check_bbox(parts)


def check_bbox(parts: list[float] | tuple[float, ...] | None) -> BBox | None:
    if parts is None:
        return None
    if len(parts) != 4 or not all(math.isfinite(p) for p in parts):
        raise ValueError("bbox must be four numbers: min_lon,min_lat,max_lon,max_lat")
    min_lon, min_lat, max_lon, max_lat = parts
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise ValueError("bbox needs min_lon < max_lon and min_lat < max_lat, in WGS84 range")
    return (min_lon, min_lat, max_lon, max_lat)


def cached_score(
    profile: str, weights: dict[str, float] | None, bbox: BBox | None
) -> ScoreResponse:
    def compute() -> ScoreResponse:
        cells = scoring.score(profile, weights=weights, bbox=bbox)
        return ScoreResponse(
            profile=profile,
            resolution=RESOLUTION,
            generated_at=datetime.now(UTC).replace(microsecond=0),
            cells=cells,
        )

    return score_cache.get_or_set(("score", profile, weights_key(weights), bbox), compute)


def ranking(profile: str, weights: dict[str, float] | None) -> dict[str, int]:
    """h3 → rank (1 = best) over all unmasked cells in the region."""

    def compute() -> dict[str, int]:
        cells = cached_score(profile, weights, None).cells
        ordered = sorted((c for c in cells if c.score is not None), key=lambda c: -(c.score or 0))
        return {c.h3: i + 1 for i, c in enumerate(ordered)}

    return score_cache.get_or_set(("rank", profile, weights_key(weights)), compute)


def rank_fields(profile: str, h3_id: str, weights: dict[str, float] | None) -> dict[str, Any]:
    ranks = ranking(profile, weights)
    n = len(ranks)
    rank = ranks.get(h3_id)
    pct = None if rank is None or n <= 1 else round((n - rank) / (n - 1), 4)
    return {"rank": rank, "ranked_cells": n, "percentile": pct}


def profile_by_id(profile_id: str) -> dict[str, Any]:
    for p in scoring.list_profiles():
        if p["id"] == profile_id:
            return p
    raise KeyError(f"profile '{profile_id}'")


# ---------------------------------------------------------------- routes

ProfileId = Annotated[str, Path(description="Profile id.", examples=["data_centre"])]
BBoxQuery = Annotated[
    str | None,
    Query(
        description="Optional `min_lon,min_lat,max_lon,max_lat` filter.",
        examples=["-0.2,51.45,0.0,51.55"],
    ),
]
Lat = Annotated[float, Query(ge=-90, le=90, description="Latitude (WGS84).", examples=[51.5155])]
Lon = Annotated[float, Query(ge=-180, le=180, description="Longitude (WGS84).", examples=[-0.0922])]


@app.get("/health", response_model=Health, tags=["meta"], summary="Service status and provenance")
def health() -> Health:
    """Reports which scoring backend is active, when the data was built, and which layers are
    real versus synthetic fallbacks."""
    info: dict[str, Any] = {}
    if hasattr(scoring, "health"):
        info = scoring.health() or {}
    layers = info.get("layers") or {layer["id"]: "unknown" for layer in scoring.list_layers()}
    return Health(
        status="ok",
        scoring_source=SCORING_SOURCE,
        data_generated_at=info.get("data_generated_at"),
        layers=layers,
        real_layers=sum(v == "real" for v in layers.values()),
        synthetic_layers=sum(v == "synthetic" for v in layers.values()),
    )


@app.get("/profiles", response_model=list[Profile], tags=["profiles"], summary="List profiles")
def list_profiles() -> list[dict[str, Any]]:
    """Every use case Groundwork can score, with default weights and masks."""
    return scoring.list_profiles()


@app.get(
    "/profiles/{profile_id}",
    response_model=Profile,
    tags=["profiles"],
    summary="Get one profile",
    responses=ERRORS,
)
def get_profile(profile_id: ProfileId) -> dict[str, Any]:
    """Layers, weights, directions and masks for one use case."""
    return profile_by_id(profile_id)


@app.get("/layers", response_model=list[Layer], tags=["layers"], summary="List layers")
def list_layers() -> list[dict[str, Any]]:
    """Metadata for every data layer: unit, kind, source and raw value range."""
    return scoring.list_layers()


@app.get(
    "/layers/{layer_id}",
    response_model=LayerValues,
    tags=["layers"],
    summary="Per-hexagon values for one layer",
    responses=ERRORS,
)
def get_layer(
    layer_id: Annotated[str, Path(description="Layer id.", examples=["summer_max_temp"])],
    bbox: BBoxQuery = None,
) -> LayerValues:
    """Normalised (0–1) and raw values for every hexagon, for map overlays."""
    cells = scoring.get_layer(layer_id, bbox=parse_bbox(bbox))
    return LayerValues(layer=layer_id, resolution=RESOLUTION, cells=cells)


@app.get(
    "/score/{profile_id}",
    response_model=ScoreResponse,
    tags=["scores"],
    summary="Score every hexagon for a profile",
    responses=ERRORS,
)
def score(profile_id: ProfileId, bbox: BBoxQuery = None) -> ScoreResponse:
    """Scores with the profile's default weights. Masked hexagons have `score: null`.
    Shape is frozen in `shared/contracts/score_response.schema.json`."""
    return cached_score(profile_id, None, parse_bbox(bbox))


@app.get(
    "/score/{profile_id}/point",
    response_model=PointScore,
    tags=["scores"],
    summary="Explain the score at one location",
    responses=ERRORS,
)
def score_point(profile_id: ProfileId, lat: Lat, lon: Lon) -> PointScore:
    """Score, rank among all hexagons, signed breakdown, raw layer values and (if the profile
    has a model) SHAP drivers for the hexagon containing `lat`,`lon`."""
    res = scoring.score_point(profile_id, lat, lon)
    return PointScore(
        profile=profile_id,
        lat=lat,
        lon=lon,
        h3=res["h3"],
        score=res.get("score"),
        masked=bool(res.get("masked")),
        breakdown=res.get("breakdown") or {},
        raw=res.get("raw") or {},
        feasibility=res.get("feasibility"),
        shap=res.get("shap"),
        **rank_fields(profile_id, res["h3"], None),
    )


@app.post(
    "/score/custom",
    response_model=ScoreResponse,
    tags=["scores"],
    summary="Re-score with custom weights",
    responses=ERRORS,
)
def score_custom(body: CustomScoreRequest) -> ScoreResponse:
    """Live re-scoring for the weight sliders. Weights override the profile defaults for the
    given layers and are renormalised to sum to 1. Results are cached by profile + weights."""
    weights = validate_weights(body.weights)
    return cached_score(body.profile, weights, check_bbox(body.bbox))


@app.get(
    "/compare",
    response_model=CompareResponse,
    tags=["scores"],
    summary="Compare use cases at one location",
    responses=ERRORS,
)
def compare(
    profiles: Annotated[
        str,
        Query(description="Comma-separated profile ids.", examples=["data_centre,house,school"]),
    ],
    lat: Lat,
    lon: Lon,
) -> CompareResponse:
    """How one location scores for several use cases, with its rank in each."""
    ids = [p.strip() for p in profiles.split(",") if p.strip()]
    if not ids:
        raise ValueError("profiles must list at least one profile id")
    results: list[CompareEntry] = []
    h3_id = ""
    for pid in ids:
        meta = profile_by_id(pid)
        res = scoring.score_point(pid, lat, lon)
        h3_id = res["h3"]
        results.append(
            CompareEntry(
                profile=pid,
                label=meta["label"],
                score=res.get("score"),
                masked=bool(res.get("masked")),
                **rank_fields(pid, h3_id, None),
            )
        )
    return CompareResponse(h3=h3_id, lat=lat, lon=lon, results=results)
