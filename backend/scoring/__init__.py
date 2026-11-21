"""Groundwork scoring library — the public interface the API calls (shared/contracts §5.1).

    list_profiles()  list_layers()  get_layer()  score()  score_point()

Unknown profile/layer ids raise ``KeyError`` (API → 404); bad weights, bboxes or
coordinates raise ``ValueError`` (API → 422).

Additions beyond the contract (safe to ignore): ``data_status()`` for ``/health`` and
``reload()`` to pick up a rebuilt grid without restarting.
"""

from __future__ import annotations

import math
import threading
from datetime import UTC, datetime
from typing import Any

from . import data as _data
from .profiles import ProfileError, load_profiles
from .scorer import Scorer, validate_bbox

__all__ = ["ProfileError", "data_status", "default_profiles", "get_layer", "health", "list_pois", "list_regions", "list_layers", "list_profiles",
           "reload", "score", "score_point"]

BBox = tuple[float, float, float, float]
_lock = threading.Lock()
_scorer: Scorer | None = None
TOP_DRIVERS = 5
MODEL_NOTE = ("The feasibility model learns where similar sites have been built, not where "
              "they should be; it scales the normative weighted score, it does not replace it.")


def _engine() -> Scorer:
    global _scorer
    if _scorer is None:
        with _lock:
            if _scorer is None:
                grid = _data.load()
                _scorer = Scorer(grid, load_profiles(set(grid.layer_ids)))
    return _scorer


def reload() -> None:
    """Drop cached data, profiles and models; the next call reloads from disk."""
    global _scorer
    with _lock:
        _scorer = None


def list_profiles() -> list[dict]:
    return [p.public() for p in _engine().profiles.values()]


def list_layers() -> list[dict]:
    return [dict(m) for m in _engine().data.layers]


def get_layer(layer_id: str, bbox: BBox | None = None) -> list[dict]:
    eng = _engine()
    if layer_id not in eng.data.layer_ids:
        raise KeyError(f"unknown layer {layer_id!r}")
    sel = eng.bbox_mask(bbox)
    frame = eng.data.frame.loc[sel]
    return [{"h3": h, "value": round(float(v), 4), "raw": round(float(r), 4)}
            for h, v, r in zip(frame.index, frame[layer_id], frame[f"raw_{layer_id}"], strict=True)]


def score(profile_id: str, weights: dict[str, float] | None = None, bbox: BBox | None = None) -> list[dict]:
    """Cells shaped as ``score_response.cells``: h3, score (None if masked), masked, breakdown."""
    eng = _engine()
    if bbox is not None:
        validate_bbox(bbox)
    return eng.cells(eng.compute(profile_id, weights), bbox)


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

    eng = _engine()
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError) as exc:
        raise ValueError("lat and lon must be numbers") from exc
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("lat must be in [-90, 90] and lon in [-180, 180]")
    result = eng.compute(profile_id, weights)
    frame = eng.data.frame
    cell = h3.latlng_to_cell(lat, lon, eng.data.resolution)
    if cell not in frame.index:
        raise KeyError(f"({lat}, {lon}) is outside the {eng.data.build.get('region', 'study')} region")
    i = frame.index.get_loc(cell)
    row = frame.iloc[i]
    meta = {m["id"]: m for m in eng.data.layers}
    masked = bool(result.masked[i])

    layers = []
    for j, lid in enumerate(result.layer_ids):
        layers.append({
            "id": lid, "label": meta[lid]["label"], "unit": meta[lid]["unit"],
            "value": round(float(row[lid]), 4), "raw": round(float(row[f"raw_{lid}"]), 4),
            "weight": round(result.weights[j], 6), "better": result.directions[j],
            "contribution": round(float(result.contributions[i, j]), 4),
        })

    shap = shap_flat = model_info = None
    if result.model is not None:
        contrib = result.model.contributions(frame.iloc[[i]])[0]
        pairs = [{"layer": f, "label": meta[f]["label"], "value": round(float(c), 4),
                  "raw": round(float(row[f"raw_{f}"]), 4)} for f, c in zip(result.model.features, contrib[:-1], strict=True)]
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
        "raw": {lid: round(float(row[f"raw_{lid}"]), 4) for lid in eng.data.layer_ids},
        "values": {lid: round(float(row[lid]), 4) for lid in eng.data.layer_ids},
        "shap": shap,
        "shap_flat": shap_flat,
        "model": model_info,
    }


DEFAULT_PROFILES = ("data_centre", "house", "school", "solar_farm", "wind_farm")


def default_profiles() -> list[str]:
    """Profile ids for the home screen, in display order (others go under "More")."""
    available = {p for p in _engine().profiles}
    return [p for p in DEFAULT_PROFILES if p in available]


def list_pois(kinds: list[str] | None = None, bbox: BBox | None = None) -> list[dict]:
    """Map icons: [{id, kind, name, lat, lon, source: osm|seeded}]. Kinds: substation, ixp,
    data_centre, station, water. Only real (cached OSM) or seeded locations, never synthetic."""
    from .pois import list_pois as _list

    return _list(kinds, bbox)


def list_regions() -> list[dict[str, Any]]:
    """Regions with detailed hexes: [{id, name, bbox, resolution, cells, is_sample, generated_at}]."""
    eng = _engine()
    f = eng.data.frame
    pad = 0.01
    names = {"london": "Greater London"}
    region = eng.data.build.get("region", "london")
    return [{
        "id": region, "name": names.get(region, region.replace("_", " ").title()),
        "bbox": [round(float(f["lon"].min()) - pad, 4), round(float(f["lat"].min()) - pad, 4),
                 round(float(f["lon"].max()) + pad, 4), round(float(f["lat"].max()) + pad, 4)],
        "resolution": eng.data.resolution, "cells": int(len(f)),
        "is_sample": eng.data.directory.resolve() == _data.SAMPLE_DIR.resolve(),
        "generated_at": eng.data.build.get("generated_at"),
    }]


def health() -> dict[str, Any]:
    """Optional extension used by ``GET /health`` (shared/handoff/p2-to-p1.md)."""
    eng = _engine()
    statuses = {k: v.get("status", "unknown") for k, v in eng.data.build.get("layers", {}).items()}
    return {"data_generated_at": eng.data.build.get("generated_at"),
            "layers": {lid: statuses.get(lid, "unknown") for lid in eng.data.layer_ids}}


def data_status() -> dict[str, Any]:
    """For ``/health``: where data came from and which layers are real vs synthetic."""
    eng = _engine()
    build = eng.data.build
    layers = build.get("layers", {})
    return {
        "data_dir": str(eng.data.directory),
        "is_sample": eng.data.directory.resolve() == _data.SAMPLE_DIR.resolve(),
        "generated_at": build.get("generated_at"),
        "checked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "region": build.get("region", "london"),
        "resolution": eng.data.resolution,
        "cells": int(len(eng.data.frame)),
        "real_layers": sorted(k for k, v in layers.items() if v.get("status") == "real"),
        "synthetic_layers": sorted(k for k, v in layers.items() if v.get("status") == "synthetic"),
        "profiles": sorted(eng.profiles),
    }


