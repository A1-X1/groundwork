"""Many regions at once: per-region scorers, overlap handling and bbox / point routing."""

from __future__ import annotations

from typing import Any

import h3
import numpy as np

from .data import GridData
from .profiles import Profile
from .scorer import Scorer, validate_bbox

DEFAULT_REGION = "london"


def non_wrapping_bbox(lon: np.ndarray, lat: np.ndarray) -> list[float]:
    """[w, s, e, n] that never spans the globe: if cells straddle the antimeridian (e.g. the
    Aleutians), shift the eastern-hemisphere side west and clamp at -180."""
    lon = np.asarray(lon, dtype=float)
    if lon.max() - lon.min() > 180:
        lon = np.where(lon > 0, lon - 360, lon)
    return [max(float(lon.min()), -180.0), float(np.min(lat)), min(float(lon.max()), 180.0), float(np.max(lat))]


class World:
    def __init__(self, grids: dict[str, GridData], profiles: dict[str, Profile]):
        self.grids = grids  # finest first
        self.profiles = profiles
        self.scorers = {rid: Scorer(g, profiles) for rid, g in grids.items()}
        self.default = DEFAULT_REGION if DEFAULT_REGION in grids else next(iter(grids))
        self.visible = self._visibility()
        self._shapes: dict[str, tuple[int, list[str]]] = {}

    def _visibility(self) -> dict[str, np.ndarray]:
        """Hide coarse cells that a finer region covers (London's res-8 hexes replace UK res-7)."""
        out = {}
        items = list(self.grids.items())
        for i, (rid, g) in enumerate(items):
            covered: set[str] = set()
            for _, finer in items[:i]:
                if finer.resolution > g.resolution:
                    covered |= {h3.cell_to_parent(c, g.resolution) for c in finer.frame.index}
            out[rid] = ~g.frame.index.isin(list(covered)) if covered else np.ones(len(g.frame), dtype=bool)
        return out

    @property
    def primary(self) -> Scorer:
        return self.scorers[self.default]

    def profile(self, profile_id: str) -> Profile:
        return self.primary.profile(profile_id)

    def in_bbox(self, bbox: tuple[float, float, float, float] | None) -> list[tuple[str, np.ndarray]]:
        """(region, mask) pairs for a bbox; no bbox → the default region only."""
        if bbox is None:
            return [(self.default, self.visible[self.default] | True)]
        validate_bbox(bbox)
        out = []
        for rid, sc in self.scorers.items():
            m = sc.bbox_mask(bbox) & self.visible[rid]
            if m.any():
                out.append((rid, m))
        return out

    def locate(self, lat: float, lon: float) -> tuple[str, str]:
        """(region, cell) of the finest region containing the point."""
        for rid, g in self.grids.items():
            cell = h3.latlng_to_cell(lat, lon, g.resolution)
            if cell in g.frame.index:
                return rid, cell
        raise KeyError(f"({lat}, {lon}) is outside every built region ({', '.join(self.grids)})")

    MARKER_RES = 4  # one shared outline resolution (~1,770 km² per hex) so outlines never overlap

    def _markers(self) -> dict[str, tuple[int, list[str], str | None]]:
        """Outline cells for the globe, computed once for all regions together:
        - one shared resolution, so neighbouring regions can't overlap;
        - a coarse hex is included only if most of the land under it belongs to the region
          (≥ 50% of its descendants at the region's resolution), so outlines hug the coast;
        - each coarse hex goes to exactly one region (the one covering most of it);
        - regions nested inside a coarser one (London, uk_urban inside uk) get no outline of
          their own (`nested_in` names the parent).
        """
        if self._shapes:
            return self._shapes
        r = self.MARKER_RES
        coverage: dict[str, dict[str, float]] = {}
        nested: dict[str, str | None] = {}
        for rid, g in self.grids.items():
            per_child = 7 ** max(g.resolution - r, 0)
            counts: dict[str, int] = {}
            for c in g.frame.index:
                p = h3.cell_to_parent(c, r) if g.resolution > r else c
                counts[p] = counts.get(p, 0) + 1
            coverage[rid] = {p: n / per_child for p, n in counts.items()}
        for rid, g in self.grids.items():
            parent = None
            for other, og in self.grids.items():
                if other != rid and og.resolution < g.resolution:
                    shared = set(coverage[rid]) & set(coverage[other])
                    if len(shared) >= 0.9 * len(coverage[rid]):
                        parent = other
                        break
            nested[rid] = parent
        owner: dict[str, tuple[str, float]] = {}
        for rid, cov in coverage.items():
            if nested[rid]:
                continue
            for p, frac in cov.items():
                if frac >= 0.5 and frac > owner.get(p, ("", 0.0))[1]:
                    owner[p] = (rid, frac)
        for rid in self.grids:
            cells = sorted(p for p, (o, _) in owner.items() if o == rid)
            self._shapes[rid] = (r, cells, nested[rid])
        return self._shapes

    def shape(self, rid: str) -> tuple[int, list[str]]:
        res, cells, _ = self._markers()[rid]
        return res, cells

    def regions(self) -> list[dict[str, Any]]:
        out = []
        for rid, g in self.grids.items():
            f, b = g.frame, g.build
            bbox = non_wrapping_bbox(f["lon"].to_numpy(), f["lat"].to_numpy())
            statuses = [v.get("status") for v in b.get("layers", {}).values()]
            out.append({
                "id": rid, "name": b.get("label") or {"london": "Greater London"}.get(rid, rid.title()),
                "bbox": [round(float(v), 4) for v in bbox], "resolution": g.resolution, "cells": int(len(f)),
                "kind": b.get("kind", "city"), "country": b.get("country"),
                "real_layers": statuses.count("real"), "unavailable_layers": statuses.count("unavailable"),
                "generated_at": b.get("generated_at"), "directory": str(g.directory),
                "marker_resolution": self._markers()[rid][0], "marker_cells": self._markers()[rid][1],
                "nested_in": self._markers()[rid][2],
            })
        return out
