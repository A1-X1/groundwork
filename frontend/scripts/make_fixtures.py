"""Regenerate frontend/src/fixtures from the API's synthetic stub (run from the repo root).

    .venv/bin/python frontend/scripts/make_fixtures.py
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.api import stub_scoring as s  # noqa: E402

OUT = ROOT / "frontend" / "src" / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)
PROFILE = "data_centre"


def dump(name: str, obj: object) -> None:
    (OUT / name).write_text(json.dumps(obj, separators=(",", ":")) + "\n")
    print(f"wrote {OUT / name}")


dump("profiles.json", s.list_profiles())
dump("layers.json", s.list_layers())
dump(
    "score_response.json",
    {
        "profile": PROFILE,
        "resolution": s.RESOLUTION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "cells": [
            {**c, "breakdown": {k: round(v, 3) for k, v in c["breakdown"].items()}}
            for c in s.score(PROFILE)
        ],
    },
)
