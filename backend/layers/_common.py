"""Shared plumbing for layer modules: metadata, caching, HTTP, offline switch.

Every layer module in this package exposes:

    META: LayerMeta
    fetch() -> Any                         # download (cached in data/raw/), may raise
    to_hex(raw, grid) -> pd.Series         # raw units, indexed by h3 like ``grid``
    synthetic(grid) -> pd.Series           # deterministic fallback, same units

``grid`` is a DataFrame indexed by H3 cell id with ``lat``/``lon`` centroid columns
and a ``raw_<layer_id>`` column for every layer already computed (see
``META.depends_on``).
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger("groundwork.layers")

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = Path(os.environ.get("GROUNDWORK_RAW_DIR", REPO_ROOT / "data" / "raw"))
# Agent-made layers, profiles and 3D models live here (gitignored) until promoted into the repo
# with `python -m backend.agent.promote <profile_id>`, so a teammate's `git pull` never collides.
LOCAL_DIR = Path(os.environ.get("GROUNDWORK_LOCAL_DIR", REPO_ROOT / "data" / "local"))

USER_AGENT = "groundwork-site-suitability/0.1 (hackathon demo)"

Kind = Literal["raster", "proximity", "aggregate"]
Normalise = Literal["rank", "identity"]


class OfflineError(RuntimeError):
    """Raised by fetchers when offline mode is on and nothing is cached."""


class SourceUnavailable(RuntimeError):
    """Raised when a source needs a manually downloaded file that is not present."""


@dataclass(frozen=True)
class LayerMeta:
    id: str
    label: str
    unit: str
    kind: Kind
    description: str
    source: str
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    # "rank": percentile rank within the region (default, robust to outliers).
    # "identity": raw value is already 0–1 (binary masks, shares).
    normalise: Normalise = "rank"
    is_mask: bool = False
    # Pure derivation of its dependencies (no source of its own): inherits their status.
    derived: bool = False

    def public(self) -> dict[str, Any]:
        """The fields exposed by ``scoring.list_layers()`` (min/max added later)."""
        return {
            "id": self.id,
            "label": self.label,
            "unit": self.unit,
            "kind": self.kind,
            "description": self.description,
            "source": self.source,
        }


# Region being built (set by the pipeline): id, kind (city|national), country, bbox (w, s, e, n).
REGION: dict = {"id": "london", "kind": "city", "country": "GBR", "bbox": (-0.56, 51.26, 0.37, 51.72)}


def set_region(attrs: dict) -> None:
    REGION.update({k: attrs[k] for k in ("region", "kind", "country", "bbox") if k in attrs})
    if "region" in attrs:
        REGION["id"] = attrs["region"]


def is_offline() -> bool:
    return os.environ.get("GROUNDWORK_OFFLINE", "").lower() in {"1", "true", "yes"}


def raw_path(*parts: str) -> Path:
    path = RAW_DIR.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# Cache lifetimes. The API never calls sources: it only reads grid.parquet, so these
# control how often `make data` re-downloads.
FOREVER: float | None = None          # fixed historical periods (climate years, normals)
DAILY = 24 * 3600.0                   # live-ish feeds (grid carbon intensity)
MONTHLY = 30 * 24 * 3600.0            # slowly changing maps (OSM, planning, crime)


def refresh_requested() -> bool:
    return os.environ.get("GROUNDWORK_REFRESH", "").lower() in {"1", "true", "yes"}


def cached_json(name: str, producer: Callable[[], Any], max_age: float | None = FOREVER) -> Any:
    """Return JSON cached at ``data/raw/<name>``; call ``producer`` on a miss.

    A cache older than ``max_age`` seconds (or any cache under ``--refresh``) is
    re-downloaded; if that download fails the stale copy is used. In offline mode a
    miss raises ``OfflineError`` and stale copies are always used.
    """
    path = raw_path(name)
    if path.exists():
        age = time.time() - path.stat().st_mtime
        fresh = (max_age is None or age <= max_age) and not refresh_requested()
        if fresh or is_offline():
            with path.open() as fh:
                return json.load(fh)
        try:
            return _store(path, producer())
        except Exception as exc:  # noqa: BLE001 — stale beats nothing
            log.warning("refresh of %s failed (%s); using cached copy", name, exc)
            with path.open() as fh:
                return json.load(fh)
    if is_offline():
        raise OfflineError(f"offline and no cache at {path}")
    return _store(path, producer())


def _store(path: Path, data: Any) -> Any:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as fh:
        json.dump(data, fh)
    tmp.replace(path)
    return data


def http_get(url: str, params: dict[str, Any] | None = None, *, timeout: float = 60,
             retries: int = 3, data: dict[str, Any] | None = None) -> Any:
    """GET (or POST when ``data`` is given) returning parsed JSON, with backoff."""
    if is_offline():
        raise OfflineError(f"offline: refusing to fetch {url}")
    import requests  # imported lazily so scoring never needs it

    headers = {"User-Agent": USER_AGENT}
    last: Exception | None = None
    for attempt in range(retries):
        try:
            if data is not None:
                resp = requests.post(url, data=data, headers=headers, timeout=timeout)
            else:
                resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code in (429, 502, 503, 504):
                raise RuntimeError(f"HTTP {resp.status_code} from {url}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 — any failure triggers retry/fallback
            last = exc
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last}") from last


def require_file(*parts: str, hint: str) -> Path:
    """Return a manually downloaded file under data/raw/, or raise with a hint."""
    path = RAW_DIR.joinpath(*parts)
    if not path.exists():
        raise SourceUnavailable(f"missing {path}. {hint}")
    return path
