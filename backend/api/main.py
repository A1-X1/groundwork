"""Groundwork public API.

Run with ``make api`` (``uvicorn backend.api.main:app --reload``). Docs at /docs and /redoc.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Hashable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any, TypeVar

import h3
import httpx
from backend.api import agent_routes, areas, assistant, pois, reviewer, scoring_source
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
    Region,
    ScoreResponse,
)
from fastapi import FastAPI, File, Form, Path, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

RESOLUTION = 8
WARM_POINT = (51.5155, -0.0922)
log = logging.getLogger("groundwork.api")

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
    {"name": "assistant", "description": "Natural-language / voice commands for the UI."},
    {"name": "pois", "description": "Points of interest for map icons (power, fibre, transport)."},
    {"name": "areas", "description": "Areas users draw and name, stored in SQLite."},
    {"name": "structures", "description": "Saved structures and their requirements."},
    {"name": "agent", "description": "Planning agent: new use cases, layers and models."},
    {"name": "connections", "description": "Mistral and Azure ML connection status."},
]

ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Unknown profile, layer or location."},
    422: {"model": ErrorResponse, "description": "Invalid parameters or weights."},
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Warm ML models in the background so the first click on a model profile is fast."""

    def warm() -> None:
        for p in scoring.list_profiles():
            if p.get("has_model"):
                try:
                    scoring.score_point(p["id"], *WARM_POINT)
                except Exception as exc:  # warm-up is best effort
                    log.warning("warm-up for %s failed: %s", p["id"], exc)

    threading.Thread(target=warm, name="warm-models", daemon=True).start()
    yield


app = FastAPI(
    lifespan=lifespan,
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
    # Any local dev port (make web WEB_PORT=...), never a remote origin.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)


areas.scoring = scoring
app.include_router(areas.router, responses=ERRORS)
app.include_router(agent_routes.router, responses=ERRORS)


def _reload_after_agent() -> None:
    """The agent may add profiles, layers and models: drop cached data and scores."""
    if hasattr(scoring, "reload"):
        scoring.reload()
    score_cache.clear()


agent_routes.ON_FINISH.append(_reload_after_agent)


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
    if isinstance(exc.detail, dict) and "code" in exc.detail:  # routers that set their own code
        return _error(exc.status_code, str(exc.detail["code"]), str(exc.detail.get("message", "")))
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


def check_weight_keys(profile_id: str, weights: dict[str, float] | None) -> None:
    """Unknown layers in weights are bad input (422), whichever backend is active."""
    if not weights:
        return
    own = {layer["id"] for layer in profile_by_id(profile_id)["layers"]}
    bad = sorted(k for k, v in weights.items() if k not in own and v != 0)
    if bad:
        raise ValueError(f"layer(s) {', '.join(bad)} are not part of profile '{profile_id}'")


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


def cells_resolution(cells: list[dict[str, Any]]) -> int:
    """Finest H3 resolution among the returned cells (regions mix res 5–8); the default if none."""
    if not cells:
        return RESOLUTION
    return max(h3.get_resolution(c["h3"]) for c in cells)


def cached_score(
    profile: str, weights: dict[str, float] | None, bbox: BBox | None
) -> ScoreResponse:
    def compute() -> ScoreResponse:
        cells = scoring.score(profile, weights=weights, bbox=bbox)
        return ScoreResponse(
            profile=profile,
            resolution=cells_resolution(cells),
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


@app.get("/", include_in_schema=False)
def root() -> Response:
    """Someone opened the API port in a browser: point them at the app and the docs."""
    html = (
        "<!doctype html><meta charset=utf-8><title>Groundwork API</title>"
        "<body style='font:16px system-ui;max-width:36rem;margin:3rem auto;padding:0 1rem'>"
        "<h1>Groundwork API is running</h1>"
        "<p>This is the API, not the app. Open the app at "
        "<a href='http://localhost:5173'>http://localhost:5173</a> "
        "(start it with <code>cd frontend; npm run dev</code> if it isn't running).</p>"
        "<p>API docs: <a href='/docs'>/docs</a> · Health: <a href='/health'>/health</a></p>"
    )
    return Response(html, media_type="text/html")


@app.get("/health", response_model=Health, tags=["meta"], summary="Service status and provenance")
def health() -> Health:
    """Reports which scoring backend is active, when the data was built, and which layers are
    real versus synthetic fallbacks."""
    layers: dict[str, str] = {layer["id"]: "unknown" for layer in scoring.list_layers()}
    generated_at = None
    if hasattr(scoring, "health"):
        info = scoring.health() or {}
        generated_at = info.get("data_generated_at")
        for lid, status in (info.get("layers") or {}).items():
            layers[lid] = status if status in {"real", "synthetic"} else "unknown"
    elif hasattr(scoring, "data_status"):
        st = scoring.data_status() or {}
        generated_at = st.get("generated_at")
        for lid in st.get("real_layers") or []:
            layers[lid] = "real"
        for lid in st.get("synthetic_layers") or []:
            layers[lid] = "synthetic"
    return Health(
        status="ok",
        scoring_source=SCORING_SOURCE,
        data_generated_at=generated_at,
        layers=layers,  # type: ignore[arg-type]
        real_layers=sum(v == "real" for v in layers.values()),
        synthetic_layers=sum(v == "synthetic" for v in layers.values()),
    )


DEFAULT_PROFILES = ["data_centre", "house", "school", "solar_farm", "wind_farm"]


def default_profile_ids() -> list[str]:
    if hasattr(scoring, "default_profiles"):
        return list(scoring.default_profiles())
    return DEFAULT_PROFILES


def profile_notes(profile_id: str) -> dict[str, str]:
    """Person 1's per-layer notes (``scoring.profile_notes``) when available; never fails."""
    fn = getattr(scoring, "profile_notes", None)
    if fn is None:
        return {}
    try:
        return {str(k): str(v) for k, v in (fn(profile_id) or {}).items()}
    except Exception:
        return {}


@app.get("/profiles", response_model=list[Profile], tags=["profiles"], summary="List profiles")
def list_profiles() -> list[dict[str, Any]]:
    """Every use case Groundwork can score, with default weights and masks. Main use cases come
    first (`is_default`, in display order); the rest follow."""
    defaults = default_profile_ids()
    rank = {pid: i for i, pid in enumerate(defaults)}
    profiles = [
        {**p, "is_default": p["id"] in rank, "notes": profile_notes(p["id"])}
        for p in scoring.list_profiles()
    ]
    return sorted(profiles, key=lambda p: (rank.get(p["id"], len(rank)), p["label"]))


@app.get("/regions", response_model=list[Region], tags=["meta"], summary="Regions with data")
def list_regions() -> list[dict[str, Any]]:
    """Where detailed hexagons exist. The globe uses this to mark built regions."""
    if hasattr(scoring, "list_regions"):
        return scoring.list_regions()  # type: ignore[no-any-return]
    return []


@app.get(
    "/profiles/{profile_id}",
    response_model=Profile,
    tags=["profiles"],
    summary="Get one profile",
    responses=ERRORS,
)
def get_profile(profile_id: ProfileId) -> dict[str, Any]:
    """Layers, weights, directions and masks for one use case."""
    return {**profile_by_id(profile_id), "notes": profile_notes(profile_id)}


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
    return LayerValues(layer=layer_id, resolution=cells_resolution(cells), cells=cells)


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


WeightsQuery = Annotated[
    str | None,
    Query(
        description="Optional weight overrides: `layer:weight,layer:weight`, as the sliders send.",
        examples=["free_cooling_hours:40,dist_fibre_ix:30"],
    ),
]


def parse_weights(raw: str | None) -> dict[str, float] | None:
    if raw is None or raw.strip() == "":
        return None
    out: dict[str, float] = {}
    for part in raw.split(","):
        key, sep, val = part.partition(":")
        try:
            if not sep:
                raise ValueError
            out[key.strip()] = float(val)
        except ValueError:
            raise ValueError("weights must look like layer:weight,layer:weight") from None
    return validate_weights(out)


def shap_explanation(res: dict[str, Any], raw: dict[str, float]) -> dict[str, Any] | None:
    """Accept `shap_detail`, a structured `shap`, or a flat `{layer: value}` `shap`."""
    detail = res.get("shap_detail")
    if detail:
        return detail  # type: ignore[no-any-return]
    shap = res.get("shap")
    if not shap:
        return None
    if "positive" in shap and "negative" in shap:
        return shap  # type: ignore[no-any-return]
    labels = {layer["id"]: layer["label"] for layer in scoring.list_layers()}
    drivers = [
        {"layer": k, "label": labels.get(k, k), "value": float(v), "raw": raw.get(k)}
        for k, v in shap.items()
    ]
    return {
        "base_value": 0.0,
        "positive": sorted((d for d in drivers if d["value"] > 0), key=lambda d: -d["value"]),
        "negative": sorted((d for d in drivers if d["value"] < 0), key=lambda d: d["value"]),
    }


def point_score(
    profile_id: str, lat: float, lon: float, weights: dict[str, float] | None
) -> PointScore:
    res = scoring.score_point(profile_id, lat, lon, weights=weights)
    if "rank" in res and "rank_of" in res:
        n = int(res["rank_of"] or 0)
        rank = {"rank": res["rank"], "ranked_cells": n, "percentile": res.get("percentile")}
    else:
        rank = rank_fields(profile_id, res["h3"], weights)
    return PointScore(
        profile=profile_id,
        h3=res["h3"],
        lat=res.get("lat", lat),
        lon=res.get("lon", lon),
        score=res.get("score"),
        masked=bool(res.get("masked")),
        masks=res.get("masks") or [],
        sustainability=res.get("sustainability_score"),
        feasibility=res.get("feasibility") if res.get("model") else res.get("feasibility_score"),
        weights=res.get("weights") or {},
        breakdown=res.get("breakdown") or {},
        raw=res.get("raw") or {},
        shap=shap_explanation(res, res.get("raw") or {}),
        model=res.get("model"),
        **rank,
    )


@app.get(
    "/score/{profile_id}/point",
    response_model=PointScore,
    tags=["scores"],
    summary="Explain the score at one location",
    responses=ERRORS,
)
def score_point(
    profile_id: ProfileId, lat: Lat, lon: Lon, weights: WeightsQuery = None
) -> PointScore:
    """Score, rank among all hexagons, signed breakdown, raw layer values and (if the profile
    has a model) SHAP drivers for the hexagon containing `lat`,`lon`."""
    parsed = parse_weights(weights)
    check_weight_keys(profile_id, parsed)
    return point_score(profile_id, lat, lon, parsed)


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
    check_weight_keys(body.profile, weights)
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
        pt = point_score(pid, lat, lon, None)
        h3_id = pt.h3
        results.append(
            CompareEntry(
                profile=pid,
                label=meta["label"],
                score=pt.score,
                masked=pt.masked,
                rank=pt.rank,
                ranked_cells=pt.ranked_cells,
                percentile=pt.percentile,
            )
        )
    return CompareResponse(h3=h3_id, lat=lat, lon=lon, results=results)


@app.post(
    "/assistant/command",
    response_model=assistant.AssistantResponse,
    tags=["assistant"],
    summary="Turn a spoken or typed request into UI commands",
    responses=ERRORS,
)
def assistant_command(body: assistant.AssistantRequest) -> assistant.AssistantResponse:
    """Uses Mistral when `MISTRAL_API_KEY` is set (environment or `.env`), otherwise a rule-based
    parser. Output is always validated against the fixed command set (PAN_CITY, SET_PROFILE,
    SET_OVERLAY, SET_WEIGHT, SHOW_TOP_SITES, PLACE_SITE, EXPLAIN, …), so the model can only ask
    the frontend to do listed things. The key never leaves the server."""
    return assistant.handle(body, scoring.list_profiles(), scoring.list_layers())


@app.get(
    "/pois",
    response_model=list[pois.Poi],
    tags=["pois"],
    summary="Points of interest for map icons",
    responses=ERRORS,
)
def list_pois(
    kinds: Annotated[
        str | None,
        Query(
            description="Comma-separated kinds: station, substation, power_plant, water, port, "
            "ixp, data_centre, airport.",
            examples=["substation,ixp"],
        ),
    ] = None,
    bbox: BBoxQuery = None,
) -> list[dict[str, Any]]:
    """Stations, substations, power plants, water, ports, internet exchanges, data centres and
    airports for map icons, in every region. Ask per viewport (`bbox`): at most 4,000 points
    come back. Each item says where its location comes from. Display only: scoring uses the
    layers, not these points."""
    ks = [k.strip() for k in kinds.split(",") if k.strip()] if kinds else None
    return pois.list_pois(scoring, ks, parse_bbox(bbox))


@app.get(
    "/assistant/status",
    response_model=assistant.AssistantStatus,
    tags=["assistant"],
    summary="Whether Mistral / Voxtral are configured",
)
def assistant_status() -> assistant.AssistantStatus:
    """The frontend uses Voxtral for voice when this says `mistral: true`, otherwise the
    browser's own speech recognition. The key itself is never returned."""
    return assistant.status()


@app.post(
    "/assistant/transcribe",
    response_model=assistant.Transcript,
    tags=["assistant"],
    summary="Speech to text with Mistral Voxtral",
    responses={**ERRORS, 502: {"model": ErrorResponse, "description": "Voxtral call failed."}},
)
async def assistant_transcribe(
    file: Annotated[UploadFile, File(description="Recorded audio (webm/ogg/wav/mp3/m4a).")],
    language: Annotated[str | None, Form(description="Optional ISO language, e.g. `en`.")] = None,
) -> assistant.Transcript | JSONResponse:
    """Forwards a short recording to Voxtral using the server-side key and returns the text.
    Send the text to `POST /assistant/command` to act on it."""
    audio = await file.read()
    try:
        return assistant.transcribe(audio, file.filename or "", file.content_type or "", language)
    except httpx.HTTPError as exc:
        return _error(502, "upstream_error", f"Voxtral transcription failed: {exc}")


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    tone: assistant.Tone | None = Field(
        default=None, description="Override the tone; otherwise picked from the wording."
    )
    speaker: str | None = Field(
        default=None, description="Speaker family: en_paul (default), gb_oliver, gb_jane."
    )


@app.post(
    "/assistant/speak",
    tags=["assistant"],
    summary="Speak a reply with a Voxtral voice",
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "MP3 audio."},
        422: {"model": ErrorResponse, "description": "No key or empty text."},
        502: {"model": ErrorResponse, "description": "Voxtral call failed."},
    },
)
def assistant_speak(body: SpeakRequest) -> Response:
    """Turns a reply into speech with Mistral's Voxtral TTS (key stays server-side). The tone
    (neutral, curious, cheerful, confident, excited) follows the wording unless given; the voice
    used is returned in `X-Voice`."""
    try:
        audio, voice = assistant.speak(body.text, body.tone, body.speaker)
    except httpx.HTTPError as exc:
        return _error(502, "upstream_error", f"Voxtral speech failed: {exc}")
    return Response(content=audio, media_type="audio/mpeg", headers={"X-Voice": voice})


@app.post(
    "/assistant/review",
    response_model=reviewer.Review,
    tags=["assistant"],
    summary="Check whether a request makes sense before acting",
)
def assistant_review(body: reviewer.ReviewRequest) -> reviewer.Review:
    """A Mistral reviewer judges whether the request is physically, legally and practically
    sensible: `ok`, `warning` (possible, with a serious constraint) or `unsuitable` (e.g. a house
    in the open ocean), with a one-line reason and a workable suggestion. Obvious impossibilities
    are caught by rules without a model call."""
    return reviewer.review(body)
