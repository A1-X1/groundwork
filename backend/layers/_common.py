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


def is_offline() -> bool:
    return os.environ.get("GROUNDWORK_OFFLINE", "").lower() in {"1", "true", "yes"}


def raw_path(*parts: str) -> Path:
    path = RAW_DIR.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def cached_json(name: str, producer: Callable[[], Any]) -> Any:
    """Return JSON cached at ``data/raw/<name>``; call ``producer`` on a miss.

    In offline mode a cache miss raises ``OfflineError`` instead of downloading.
    """
    path = raw_path(name)
    if path.exists():
        with path.open() as fh:
            return json.load(fh)
    if is_offline():
        raise OfflineError(f"offline and no cache at {path}")
    data = producer()
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
