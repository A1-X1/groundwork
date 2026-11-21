"""Chooses the scoring implementation the API talks to.

``GROUNDWORK_SCORING`` selects it:

- ``auto`` (default): Person 1's ``backend.scoring`` if it imports, otherwise the stub.
- ``real``: ``backend.scoring`` only; fail at startup if it is missing.
- ``stub``: ``backend.api.stub_scoring`` (synthetic data, no pipeline needed).
"""

from __future__ import annotations

import importlib
import logging
import os
from types import ModuleType

log = logging.getLogger("groundwork.api")

REQUIRED = ("list_profiles", "list_layers", "get_layer", "score", "score_point")


def load() -> tuple[ModuleType, str]:
    mode = os.environ.get("GROUNDWORK_SCORING", "auto").lower()
    if mode not in {"auto", "real", "stub"}:
        raise RuntimeError(f"GROUNDWORK_SCORING must be auto, real or stub (got {mode!r})")
    if mode in {"auto", "real"}:
        try:
            mod = importlib.import_module("backend.scoring")
            missing = [f for f in REQUIRED if not hasattr(mod, f)]
            if missing:
                raise ImportError(f"backend.scoring is missing {', '.join(missing)}")
            log.info("Using real scoring module backend.scoring")
            return mod, "real"
        except Exception as exc:  # any failure to load real scoring falls back in auto mode
            if mode == "real":
                raise
            log.warning("backend.scoring unavailable (%s); using synthetic stub", exc)
    from backend.api import stub_scoring

    return stub_scoring, "stub"
