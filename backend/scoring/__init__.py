"""Groundwork scoring library — the public interface the API calls (shared/contracts §5.1).

    list_profiles()  list_layers()  get_layer()  score()  score_point()

Unknown profile/layer ids raise ``KeyError`` (API → 404); bad weights, bboxes or
coordinates raise ``ValueError`` (API → 422).

Multi-region: every grid in data/sample + data/processed (regions/<id>/) is loaded. Calls
with a ``bbox`` return cells from every region in view (finer regions hide the coarser
cells they cover). Calls without a bbox use the default region (London). Layers that a
region lacks are *unavailable* there: value 0.5 (neutral), ``raw`` = None.

Additions beyond the contract (safe to ignore): ``data_status()``, ``health()``,
``list_regions()``, ``list_pois()``, ``default_profiles()`` and ``reload()``.
"""

from __future__ import annotations

import math
import threading
from datetime import UTC, datetime
from typing import Any

from . import data as _data
from .profiles import ProfileError, load_profiles
from .scorer import validate_bbox  # noqa: F401  (re-exported)
from .world import World

__all__ = ["ProfileError", "data_status", "default_profiles", "get_layer", "health", "list_pois", "list_regions", "list_layers", "list_profiles",
           "reload", "score", "score_point"]

BBox = tuple[float, float, float, float]
_lock = threading.Lock()
_scorer: World | None = None
TOP_DRIVERS = 5
MODEL_NOTE = ("The feasibility model learns where similar sites have been built, not where "
              "they should be; it scales the normative weighted score, it does not replace it.")


def _world() -> World:
    global _scorer
    if _scorer is None:
        with _lock:
            if _scorer is None:
                grids = _data.load_all()
                known = set().union(*(g.layer_ids for g in grids.values()))
                _scorer = World(grids, load_profiles(known))
    return _scorer


def _engine():
    """The default region's scorer (single-region callers)."""
    return _world().primary


def _num(v: Any, nd: int = 4) -> float | None:
    """JSON-safe number: NaN (unavailable) → None."""
    f = float(v)
    return None if math.isnan(f) else round(f, nd)


def reload() -> None:
    """Drop cached data, profiles and models; the next call reloads from disk."""
    global _scorer
    with _lock:
        _scorer = None


def list_profiles() -> list[dict]:
    return [p.public() for p in _world().profiles.values()]


def list_layers() -> list[dict]:
    return [dict(m) for m in _engine().data.layers]


def get_layer(layer_id: str, bbox: BBox | None = None) -> list[dict]:
    world = _world()
    if layer_id not in world.primary.data.layer_ids:
        raise KeyError(f"unknown layer {layer_id!r}")
    out: list[dict] = []
    for rid, mask in world.in_bbox(bbox):
        frame = world.grids[rid].frame.loc[mask]
        out.extend({"h3": h, "value": round(float(v), 4), "raw": _num(r)}
                   for h, v, r in zip(frame.index, frame[layer_id], frame[f"raw_{layer_id}"], strict=True))
    return out


def score(profile_id: str, weights: dict[str, float] | None = None, bbox: BBox | None = None) -> list[dict]:
    """Cells shaped as ``score_response.cells``: h3, score (None if masked), masked, breakdown."""
    world = _world()
    world.profile(profile_id)  # KeyError before any work
    out: list[dict] = []
    for rid, mask in world.in_bbox(bbox):
        sc = world.scorers[rid]
        out.extend(sc.cells(sc.compute(profile_id, weights), None, mask))
    return out


def score_point(profile_id: str, lat: float, lon: float, weights: dict[str, float] | None = None) -> dict:
    """Everything about the hex containing (lat, lon) for one profile.

    Keys: profile, h3, lat, lon (hex centre), score, masked, masks (ids hit),
    sustainability_score, feasibility_score, rank (1 = best, None if masked), rank_of,
    percentile, weights, breakdown, layers (per profile layer: id, label, unit, value,
    raw, weight, better, contribution), raw and values (every layer), feasibility (None
    without a model), shap (None or {base_value, positive[≤5], negative[≤5]} of
    {layer, label, value, raw}), shap_flat (None or {layer: signed TreeSHAP value}),
    model (None or metadata). Matches the proposed clarification in
    shared/contracts/scoring_interface.md and adds fields.
    """
    import h3

    world = _world()
    world.profile(profile_id)
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError) as exc:
        raise ValueError("lat and lon must be numbers") from exc
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("lat must be in [-90, 90] and lon in [-180, 180]")
    region, cell = world.locate(lat, lon)
    eng = world.scorers[region]
    result = eng.compute(profile_id, weights)
    frame = eng.data.frame
    i = frame.index.get_loc(cell)
    row = frame.iloc[i]
    meta = {m["id"]: m for m in eng.data.layers}
    masked = bool(result.masked[i])

    layers = []
    for j, lid in enumerate(result.layer_ids):
        layers.append({
            "id": lid, "label": meta[lid]["label"], "unit": meta[lid]["unit"],
            "value": round(float(row[lid]), 4), "raw": _num(row[f"raw_{lid}"]),
            "weight": round(result.weights[j], 6), "better": result.directions[j],
            "contribution": round(float(result.contributions[i, j]), 4),
        })

    shap = shap_flat = model_info = None
    if result.model is not None:
        contrib = result.model.contributions(frame.iloc[[i]])[0]
        pairs = [{"layer": f, "label": meta[f]["label"], "value": round(float(c), 4),
                  "raw": _num(row[f"raw_{f}"])} for f, c in zip(result.model.features, contrib[:-1], strict=True)]
        pos = sorted((p for p in pairs if p["value"] > 0), key=lambda p: -p["value"])[:TOP_DRIVERS]
        neg = sorted((p for p in pairs if p["value"] < 0), key=lambda p: p["value"])[:TOP_DRIVERS]
        shap = {"base_value": round(float(contrib[-1]), 4), "positive": pos, "negative": neg}
        shap_flat = {d["layer"]: d["value"] for d in pos + neg}
        m = result.model.metrics
        model_info = {"type": "presence", "positives": m.get("positives"),
                      "auc_spatial_cv": m.get("auc_spatial_cv"), "n_positives": m.get("n_positives"),
                      "positives_synthetic": m.get("positives_synthetic"), "note": MODEL_NOTE}

    centre = h3.cell_to_latlng(cell)
    n_ranked = result.n_ranked
    rank = None if masked else int(result.rank[i])
    return {
        "profile": profile_id,
        "region": region,
        "h3": cell,
        "lat": round(centre[0], 6),
        "lon": round(centre[1], 6),
        "score": None if masked else round(float(result.score[i]), 4),
        "masked": masked,
        "masks": [m for m, hit in result.mask_hits.items() if hit[i]],
        "sustainability_score": round(float(result.sustainability[i]), 4),
        "feasibility_score": round(float(result.feasibility[i]), 4),
        "feasibility": round(float(result.feasibility[i]), 4) if result.model is not None else None,
        "rank": rank,
        "rank_of": n_ranked,
        "percentile": None if rank is None else round(1 - (rank - 1) / max(n_ranked - 1, 1), 4),
        "weights": dict(zip(result.layer_ids, (round(w, 6) for w in result.weights), strict=True)),
        "breakdown": {lid: round(float(result.contributions[i, j]), 4) for j, lid in enumerate(result.layer_ids)},
        "layers": layers,
        "raw": {lid: _num(row[f"raw_{lid}"]) for lid in eng.data.layer_ids},
        "unavailable": [lid for lid in eng.data.layer_ids if math.isnan(float(row[f"raw_{lid}"]))],
        "values": {lid: round(float(row[lid]), 4) for lid in eng.data.layer_ids},
        "shap": shap,
        "shap_flat": shap_flat,
        "model": model_info,
    }


DEFAULT_PROFILES = ("data_centre", "house", "school", "solar_farm", "wind_farm")


def default_profiles() -> list[str]:
    """Profile ids for the home screen, in display order (others go under "More")."""
    available = set(_world().profiles)
    return [p for p in DEFAULT_PROFILES if p in available]


def list_pois(kinds: list[str] | None = None, bbox: BBox | None = None) -> list[dict]:
    """Map icons: [{id, kind, name, lat, lon, source: osm|seeded}]. Kinds: substation, ixp,
    data_centre, station, water. Only real (cached OSM) or seeded locations, never synthetic."""
    from .pois import list_pois as _list

    return _list(kinds, bbox)


def list_regions() -> list[dict[str, Any]]:
    """Regions with hexes: [{id, name, bbox:[w,s,e,n], resolution, cells, kind, country,
    real_layers, unavailable_layers, generated_at, directory}], finest first."""
    return _world().regions()


def health() -> dict[str, Any]:
    """Optional extension used by ``GET /health``: default-region layer status + per region."""
    world = _world()
    eng = world.primary
    statuses = {k: v.get("status", "unknown") for k, v in eng.data.build.get("layers", {}).items()}
    return {"data_generated_at": eng.data.build.get("generated_at"),
            "layers": {lid: statuses.get(lid, "unknown") for lid in eng.data.layer_ids},
            "regions": {rid: {k: v.get("status") for k, v in g.build.get("layers", {}).items()}
                        for rid, g in world.grids.items()}}


def data_status() -> dict[str, Any]:
    """For ``/health``: where data came from and which layers are real vs synthetic."""
    eng = _world().primary
    build = eng.data.build
    layers = build.get("layers", {})
    return {
        "data_dir": str(eng.data.directory),
        "is_sample": _data.SAMPLE_DIR.resolve() in [eng.data.directory.resolve(), *eng.data.directory.resolve().parents],
        "generated_at": build.get("generated_at"),
        "checked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "region": build.get("region", "london"),
        "resolution": eng.data.resolution,
        "cells": int(len(eng.data.frame)),
        "real_layers": sorted(k for k, v in layers.items() if v.get("status") == "real"),
        "synthetic_layers": sorted(k for k, v in layers.items() if v.get("status") == "synthetic"),
        "profiles": sorted(eng.profiles),
        "regions": [{k: r[k] for k in ("id", "resolution", "cells", "real_layers")} for r in _world().regions()],
    }


