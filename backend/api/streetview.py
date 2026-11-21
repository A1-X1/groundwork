"""Street-level imagery for a hexagon: a preview image (proxied, so server keys stay here) and
what the browser needs to open a full-screen viewer.

Provider order: Google Street View when ``GOOGLE_MAPS_API_KEY`` is set, else Mapillary when
``MAPILLARY_TOKEN`` is set. Both are read from the environment or the repo's gitignored ``.env``
and can be saved from Connections (``PUT /streetview/keys/{provider}``).

- Google: the Street View metadata endpoint checks for imagery within RADIUS_M first; the preview is
  the Street View Static API. The viewer uses the Maps JavaScript API with a browser key
  (``GOOGLE_MAPS_BROWSER_KEY``, referrer-restricted; falls back to the server key).
- Mapillary: the Graph API's nearest image within ~RADIUS_M; its 1024 px thumbnail is the preview
  and its image id opens MapillaryJS (the token is a client token by design).
"""

from __future__ import annotations

import contextlib
import os
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from . import assistant

router = APIRouter()
TAGS = ["streetview"]
TIMEOUT_S = 8.0
# How far from the hexagon centre to look for street imagery (user request: wider than 200 m).
RADIUS_M = int(os.environ.get("STREETVIEW_RADIUS_M", "1000"))
# The search box half-size in degrees of latitude; longitude is scaled by cos(lat) below.
_DEG = RADIUS_M / 111_000


def _within() -> str:
    return f"{RADIUS_M / 1000:g} km" if RADIUS_M >= 1000 else f"{RADIUS_M} m"


Provider = Literal["google", "mapillary"]
ENV = {"google": "GOOGLE_MAPS_API_KEY", "mapillary": "MAPILLARY_TOKEN"}
# ASCII only: these also go out as HTTP headers.
CREDIT = {
    "google": "Imagery (c) Google",
    "mapillary": "Imagery (c) Mapillary contributors, CC BY-SA",
}


def key_for(provider: Provider) -> str | None:
    name = ENV[provider]
    return os.environ.get(name) or assistant._read_dotenv().get(name) or None


def provider() -> Provider | None:
    if key_for("google"):
        return "google"
    if key_for("mapillary"):
        return "mapillary"
    return None


def save_key(name: str, value: str | None) -> None:
    """Write (or remove) one variable in the gitignored .env and this process's env."""
    path = assistant._dotenv_path()
    lines = path.read_text().splitlines() if path.is_file() else []
    lines = [ln for ln in lines if not ln.strip().startswith(f"{name}=")]
    if value:
        lines.append(f"{name}={value}")
        os.environ[name] = value
    else:
        os.environ.pop(name, None)
    path.write_text("\n".join(lines) + ("\n" if lines else ""))
    with contextlib.suppress(OSError):
        path.chmod(0o600)


class StreetViewConfig(BaseModel):
    provider: Provider | None = Field(description="google, mapillary, or null when no key is set.")
    browser_key: str | None = Field(
        default=None,
        description="What the browser needs for the viewer: a referrer-restricted Google key, or "
        "a Mapillary client token. Null without a provider.",
    )
    credit: str | None = None


class KeyBody(BaseModel):
    key: str = Field(min_length=8, max_length=400)


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get(
    "/streetview/config", response_model=StreetViewConfig, tags=TAGS, summary="Viewer setup"
)
def config() -> StreetViewConfig:
    """Which provider is configured and the key the browser needs for the full-screen viewer."""
    p = provider()
    if p is None:
        return StreetViewConfig(provider=None)
    browser = (
        os.environ.get("GOOGLE_MAPS_BROWSER_KEY")
        or assistant._read_dotenv().get("GOOGLE_MAPS_BROWSER_KEY")
        or key_for("google")
        if p == "google"
        else key_for("mapillary")
    )
    return StreetViewConfig(provider=p, browser_key=browser, credit=CREDIT[p])


def _google_preview(lat: float, lon: float, key: str) -> tuple[bytes, dict[str, str]]:
    loc = f"{lat},{lon}"
    meta = httpx.get(
        "https://maps.googleapis.com/maps/api/streetview/metadata",
        params={"location": loc, "radius": RADIUS_M, "source": "outdoor", "key": key},
        timeout=TIMEOUT_S,
    ).json()
    status = meta.get("status")
    if status in ("ZERO_RESULTS", "NOT_FOUND"):
        raise _err(404, "no_imagery", f"No street imagery within {_within()} of this hexagon.")
    if status != "OK":
        # REQUEST_DENIED / OVER_QUERY_LIMIT / INVALID_REQUEST: a key or project problem, not an
        # empty area. Say so, with Google's own message, instead of "no imagery here".
        why = meta.get("error_message") or ""
        hint = (
            " Enable the Street View Static API (and billing) for this key in Google Cloud."
            if status == "REQUEST_DENIED"
            else ""
        )
        raise _err(502, "provider_error", f"Google Street View said {status}. {why}{hint}".strip())
    img = httpx.get(
        "https://maps.googleapis.com/maps/api/streetview",
        params={
            "size": "640x360",
            "location": loc,
            "radius": RADIUS_M,
            "source": "outdoor",
            "key": key,
        },
        timeout=TIMEOUT_S,
    )
    img.raise_for_status()
    pano = meta.get("location") or {}
    headers = {"X-Pano-Lat": str(pano.get("lat", lat)), "X-Pano-Lon": str(pano.get("lng", lon))}
    if meta.get("pano_id"):
        headers["X-Pano-Id"] = str(meta["pano_id"])
    return img.content, headers


def _mapillary_preview(lat: float, lon: float, token: str) -> tuple[bytes, dict[str, str]]:
    import math

    dlon = _DEG / max(0.2, math.cos(math.radians(lat)))
    bbox = f"{lon - dlon},{lat - _DEG},{lon + dlon},{lat + _DEG}"
    found = httpx.get(
        "https://graph.mapillary.com/images",
        params={
            "access_token": token,
            "fields": "id,thumb_1024_url,computed_geometry",
            "bbox": bbox,
            "limit": 100,
        },
        timeout=TIMEOUT_S,
    ).json()
    rows = [r for r in (found.get("data") or []) if r.get("thumb_1024_url")]
    if not rows:
        raise _err(404, "no_imagery", f"No street imagery within {_within()} of this hexagon.")

    def dist2(r: dict[str, Any]) -> float:
        coords = (r.get("computed_geometry") or {}).get("coordinates") or [lon, lat]
        return ((coords[0] - lon) * math.cos(math.radians(lat))) ** 2 + (coords[1] - lat) ** 2

    best = min(rows, key=dist2)  # the closest image, not just the first one listed
    img = httpx.get(best["thumb_1024_url"], timeout=TIMEOUT_S)
    img.raise_for_status()
    return img.content, {"X-Pano-Id": str(best["id"])}


@router.get(
    "/streetview/preview",
    tags=TAGS,
    summary="Street-level preview image near a point",
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "JPEG preview."},
        404: {"description": "No imagery within the search radius (STREETVIEW_RADIUS_M, 1 km)."},
        503: {"description": "No Street View provider configured."},
    },
)
def preview(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)) -> Response:
    """A 640×360 street-level image near the point (the hexagon centre). Headers carry the
    provider, its credit, and the panorama/image id for the viewer."""
    p = provider()
    if p is None:
        raise _err(
            503, "not_configured", "Add a Google Maps key or a Mapillary token in Connections."
        )
    key = key_for(p) or ""
    try:
        body, extra = (
            _google_preview(lat, lon, key) if p == "google" else _mapillary_preview(lat, lon, key)
        )
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as e:
        raise _err(502, "provider_error", f"{p} didn't return an image: {e}") from None
    headers = {
        "X-Streetview-Provider": p,
        "X-Streetview-Credit": CREDIT[p],
        "Cache-Control": "max-age=86400",
        **extra,
    }
    return Response(content=body, media_type="image/jpeg", headers=headers)


@router.put(
    "/streetview/keys/{name}", response_model=StreetViewConfig, tags=TAGS, summary="Save a key"
)
def put_key(name: Provider, body: KeyBody) -> StreetViewConfig:
    """Store a Google Maps API key or a Mapillary token in the gitignored .env."""
    save_key(ENV[name], body.key.strip())
    return config()


@router.delete(
    "/streetview/keys/{name}", response_model=StreetViewConfig, tags=TAGS, summary="Remove a key"
)
def delete_key(name: Provider) -> StreetViewConfig:
    save_key(ENV[name], None)
    return config()
