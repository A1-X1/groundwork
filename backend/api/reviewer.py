"""Suitability reviewer: a Mistral agent that sanity-checks a request before Groundwork acts on it.

"Build a house in the ocean" → unsuitable (open water; suggest a coastal plot or a floating home).
"Put a nuclear plant in central London" → warning (exclusion zones, population). Ordinary requests
pass straight through. Without a Mistral key a small rule set catches the obvious cases.
"""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from backend.api import assistant

log = logging.getLogger("groundwork.reviewer")
Verdict = Literal["ok", "warning", "unsuitable"]


class ReviewRequest(BaseModel):
    model_config = {
        "json_schema_extra": {"example": {"text": "can you build a house in the ocean"}}
    }

    text: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] = Field(
        default_factory=dict, description="UI context (profile, place)."
    )


class Review(BaseModel):
    verdict: Verdict
    reason: str = Field(description="One sentence: why, in plain words.")
    suggestion: str | None = Field(default=None, description="A workable alternative, if any.")
    source: Literal["mistral", "rules"]


SYSTEM = (
    "You review requests made to Groundwork, a site-suitability tool that finds good places to "
    "build things (homes, schools, data centres, farms, power plants, any structure) on land. "
    "Requests to move or change the map (fly to a place, zoom, show a view or layer) are always "
    "ok. Return JSON: "
    '{"verdict": "ok"|"warning"|"unsuitable", "reason": "<one sentence>", '
    '"suggestion": "<a workable alternative or null>"}. '
    "unsuitable ONLY when the structure physically cannot work there or the request is absurd: "
    "a house in the open ocean, a data centre on the Moon, a school inside a volcano, a ski "
    "resort in the Sahara. "
    "warning when it is physically possible but faces serious legal, safety or planning "
    "constraints: a nuclear plant in a dense city, building on a protected nature reserve, a "
    "wind farm next to an airport, homes on a flood plain. "
    "ok for everything else; most requests are ok. Never moralise. Be brief and friendly, and "
    "suggest the closest sensible option."
)

# Offline fallback: obvious impossible locations for buildings. Words match fuzzily so typos
# ("ocnea") and transcription slips still count.
_BUILD_WORDS = {
    "build", "building", "put", "place", "site", "construct", "house", "home", "school",
    "datacentre", "datacenter", "data", "farm", "plant", "factory", "office", "hospital",
    "mine", "tower", "warehouse",
}  # fmt: skip
_IMPOSSIBLE: list[tuple[set[str], str, str]] = [
    (
        {"ocean", "underwater", "seabed", "atlantic", "pacific"},
        "That's open water, so there's no ground to build on.",
        "Try a coastal site, or ask about offshore options if it's a wind farm.",
    ),
    (
        {"moon", "mars", "orbit", "planet"},
        "Groundwork only covers sites on Earth.",
        "Pick a country or city and I'll find the best spots there.",
    ),
    (
        {"volcano", "crater", "lava"},
        "Active volcanic ground is far too hazardous to build on.",
        "Look nearby but well outside the hazard zone.",
    ),
    (
        {"antarctica", "glacier", "iceberg", "icesheet"},
        "Ice sheets and polar sites aren't buildable for this kind of structure.",
        "Choose a region with stable ground and access.",
    ),
]


def _fuzzy_hit(words: list[str], vocab: set[str]) -> bool:
    for w in words:
        for v in vocab:
            if w == v or (
                len(w) >= 4 and len(v) >= 4 and SequenceMatcher(None, w, v).ratio() >= 0.8
            ):
                return True
    return False


_IN_THE_SEA = re.compile(r"\b(in|into|under|on|middle of) the (sea|open sea)\b")


def rules_review(text: str) -> Review:
    t = text.lower()
    words = re.findall(r"[a-z]+", t)
    if _fuzzy_hit(words, _BUILD_WORDS):
        # Building words never count as places ("plant" is not "planet").
        place_words = [w for w in words if w not in _BUILD_WORDS]
        if _IN_THE_SEA.search(t):
            place_words.append("ocean")
        for vocab, reason, suggestion in _IMPOSSIBLE:
            if _fuzzy_hit(place_words, vocab):
                return Review(
                    verdict="unsuitable", reason=reason, suggestion=suggestion, source="rules"
                )
    return Review(
        verdict="ok", reason="Looks like a sensible request.", suggestion=None, source="rules"
    )


def mistral_review(text: str, context: dict[str, Any], key: str) -> Review:
    body = {
        "model": assistant.MISTRAL_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps({"request": text, "context": context})},
        ],
    }
    r = httpx.post(assistant.MISTRAL_URL, json=body, timeout=15.0,
                   headers={"Authorization": f"Bearer {key}"})  # fmt: skip
    r.raise_for_status()
    data = json.loads(r.json()["choices"][0]["message"]["content"])
    verdict = data.get("verdict")
    if verdict not in ("ok", "warning", "unsuitable"):
        verdict = "ok"
    return Review(
        verdict=verdict,
        reason=str(data.get("reason") or "")[:300] or "Looks fine.",
        suggestion=(str(data["suggestion"])[:300] if data.get("suggestion") else None),
        source="mistral",
    )


def review(req: ReviewRequest) -> Review:
    # Obvious impossibilities never need a model call.
    quick = rules_review(req.text)
    if quick.verdict == "unsuitable":
        return quick
    # Nothing to build (navigation, views, questions): nothing to judge.
    if not _fuzzy_hit(re.findall(r"[a-z]+", req.text.lower()), _BUILD_WORDS):
        return quick
    key = assistant.mistral_key()
    if key:
        try:
            return mistral_review(req.text, req.context, key)
        except Exception as exc:  # network, quota, bad JSON: the rules answer stands
            log.warning("review via Mistral failed (%s); using rules", exc)
    return quick
