"""Weighted sustainability score × optional feasibility, with masks and breakdowns."""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import numpy as np

from . import ml
from .data import GridData
from .profiles import Profile

MASK_THRESHOLD = 0.5
_CACHE_SIZE = 64


@dataclass(frozen=True)
class Result:
    profile_id: str
    layer_ids: tuple[str, ...]
    weights: tuple[float, ...]
    directions: tuple[str, ...]
    sustainability: np.ndarray       # (n,)
    feasibility: np.ndarray          # (n,) 1.0 when there is no model
    score: np.ndarray                # (n,) NaN where masked
    masked: np.ndarray               # (n,) bool
    mask_hits: dict[str, np.ndarray]  # mask id -> bool (n,)
    contributions: np.ndarray        # (n, k) signed, relative to regional mean
    rank: np.ndarray                 # (n,) 1 = best, 0 where masked
    n_ranked: int
    model: ml.TrainedModel | None


class Scorer:
    def __init__(self, data: GridData, profiles: dict[str, Profile]):
        self.data = data
        self.profiles = profiles
        self._lock = threading.Lock()
        self._results: OrderedDict[tuple, Result] = OrderedDict()
        self._models: dict[str, ml.TrainedModel | None] = {}
        self._feas: dict[str, np.ndarray] = {}

    # ---- inputs ----------------------------------------------------------------
    def profile(self, profile_id: str) -> Profile:
        if profile_id not in self.profiles:
            raise KeyError(f"unknown profile {profile_id!r}; known: {sorted(self.profiles)}")
        return self.profiles[profile_id]

    def resolve_weights(self, profile: Profile, overrides: dict[str, float] | None) -> dict[str, float]:
        """Profile weights with overrides applied, renormalised to sum to 1."""
        weights = {k: v.weight for k, v in profile.layers.items()}
        for layer_id, w in (overrides or {}).items():
            if layer_id not in self.data.layer_ids:
                raise ValueError(f"unknown layer {layer_id!r} in weights")
            if isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w) or w < 0:
                raise ValueError(f"weight for {layer_id!r} must be a finite number ≥ 0, got {w!r}")
            if layer_id not in weights:
                if w == 0:
                    continue
                raise ValueError(f"layer {layer_id!r} is not part of profile {profile.id!r}; "
                                 "add it to the profile YAML to give it a direction")
            weights[layer_id] = float(w)
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("at least one weight must be positive")
        return {k: v / total for k, v in weights.items()}

    # ---- model -----------------------------------------------------------------
    def model(self, profile: Profile) -> ml.TrainedModel | None:
        if profile.id not in self._models:
            try:
                self._models[profile.id] = ml.get_model(self.data, profile)
            except ValueError:  # too few positives in this region: score normatively
                self._models[profile.id] = None
            m = self._models[profile.id]
            n = len(self.data.frame)
            self._feas[profile.id] = (ml.feasibility(m, self.data, profile.model.floor)[1]
                                      if m is not None and profile.model else np.ones(n))
        return self._models[profile.id]

    # ---- scoring ---------------------------------------------------------------
    def compute(self, profile_id: str, overrides: dict[str, float] | None = None) -> Result:
        profile = self.profile(profile_id)
        weights = self.resolve_weights(profile, overrides)
        key = (profile_id, tuple(sorted((k, round(v, 9)) for k, v in weights.items())))
        with self._lock:
            if key in self._results:
                self._results.move_to_end(key)
                return self._results[key]
            model = self.model(profile)
            result = self._compute(profile, weights, model, self._feas[profile.id])
            self._results[key] = result
            if len(self._results) > _CACHE_SIZE:
                self._results.popitem(last=False)
            return result

    def _compute(self, profile: Profile, weights: dict[str, float], model: ml.TrainedModel | None,
                 feas: np.ndarray) -> Result:
        frame = self.data.frame
        ids = tuple(k for k in profile.layers if weights.get(k, 0) > 0) or tuple(profile.layers)
        w = np.array([weights[k] for k in ids])
        directions = tuple(profile.layers[k].better for k in ids)
        values = frame[list(ids)].to_numpy(dtype=float)
        directed = np.where(np.array(directions) == "higher", values, 1.0 - values)
        sustainability = directed @ w
        contributions = w * (directed - directed.mean(axis=0))

        mask_hits = {m: frame[m].to_numpy(dtype=float) >= MASK_THRESHOLD for m in profile.masks}
        masked = np.zeros(len(frame), dtype=bool)
        for hit in mask_hits.values():
            masked |= hit
        score = np.where(masked, np.nan, sustainability * feas)

        rank = np.zeros(len(frame), dtype=int)
        order = np.argsort(-np.where(masked, -np.inf, score), kind="stable")
        n_ranked = int((~masked).sum())
        rank[order[:n_ranked]] = np.arange(1, n_ranked + 1)
        return Result(profile.id, ids, tuple(w.tolist()), directions, sustainability, feas, score, masked,
                      mask_hits, contributions, rank, n_ranked, model)

    def bbox_mask(self, bbox: tuple[float, float, float, float] | None) -> np.ndarray:
        frame = self.data.frame
        if bbox is None:
            return np.ones(len(frame), dtype=bool)
        min_lon, min_lat, max_lon, max_lat = validate_bbox(bbox)
        lat, lon = frame["lat"].to_numpy(), frame["lon"].to_numpy()
        return (lon >= min_lon) & (lon <= max_lon) & (lat >= min_lat) & (lat <= max_lat)

    def cells(self, result: Result, bbox: tuple[float, float, float, float] | None,
              mask: np.ndarray | None = None) -> list[dict[str, Any]]:
        sel = np.flatnonzero(self.bbox_mask(bbox) if mask is None else mask)
        index = self.data.frame.index
        contrib = np.round(result.contributions, 4)
        out = []
        for i in sel:
            out.append({
                "h3": index[i],
                "score": None if result.masked[i] else round(float(result.score[i]), 4),
                "masked": bool(result.masked[i]),
                "breakdown": {k: float(contrib[i, j]) for j, k in enumerate(result.layer_ids)},
            })
        return out


def validate_bbox(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
    except (TypeError, ValueError) as exc:
        raise ValueError("bbox must be (min_lon, min_lat, max_lon, max_lat)") from exc
    if not all(math.isfinite(v) for v in (min_lon, min_lat, max_lon, max_lat)):
        raise ValueError("bbox values must be finite")
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise ValueError("bbox must satisfy min_lon < max_lon and min_lat < max_lat within WGS84 bounds")
    return min_lon, min_lat, max_lon, max_lat
