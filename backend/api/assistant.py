"""Natural-language and voice commands → a validated list of UI commands.

`POST /assistant/command` sends the text to Mistral when ``MISTRAL_API_KEY`` is set (in the
environment or the repo's ``.env``) and otherwise uses a small rule-based parser, so the
feature works offline. Either way the output is validated against ``COMMANDS``: the LLM can
only ask the frontend to do things on this list.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

log = logging.getLogger("groundwork.assistant")

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
# Voxtral speech-to-text. Endpoint and model id follow Mistral's audio transcription API;
# both can be overridden in .env if Mistral renames them.
VOXTRAL_URL = os.environ.get("VOXTRAL_URL", "https://api.mistral.ai/v1/audio/transcriptions")
VOXTRAL_MODEL = os.environ.get("VOXTRAL_MODEL", "voxtral-mini-latest")
MAX_AUDIO_BYTES = 10 * 1024 * 1024

# Voxtral text-to-speech. Speakers come in tone variants (`<speaker>_<tone>` voice slugs);
# replies pick a tone from their wording. Default speaker: Paul (en_paul, chosen by the user);
# GROUNDWORK_VOICE switches speaker (gb_oliver, gb_jane).
SPEECH_URL = os.environ.get("VOXTRAL_SPEECH_URL", "https://api.mistral.ai/v1/audio/speech")
TTS_MODEL = os.environ.get("VOXTRAL_TTS_MODEL", "voxtral-mini-tts-latest")
SPEAKER = os.environ.get("GROUNDWORK_VOICE", "en_paul")
SPEAKER_TONES: dict[str, set[str]] = {
    "gb_oliver": {"neutral", "curious", "cheerful", "confident", "excited", "sad", "angry"},
    "gb_jane": {"neutral", "curious", "confident", "sad", "frustrated", "confused", "sarcasm"},
    "en_paul": {"neutral", "happy", "cheerful", "confident", "excited", "sad", "frustrated"},
}
Tone = Literal["neutral", "curious", "cheerful", "confident", "excited"]
TIMEOUT_S = 12.0

# Command set agreed with Person 1 (shared/handoff/p1-to-p2.md): name → argument names.
COMMANDS: dict[str, list[str]] = {
    "PAN_COUNTRY": ["name"],
    "PAN_CITY": ["name", "country"],
    "PAN_REGION": ["bbox", "name"],
    "ZOOM": ["direction", "levels"],
    "RESET_VIEW": [],
    "ROTATE_GLOBE": ["state"],
    "SET_PROFILE": ["id"],
    "SET_OVERLAY": ["layer"],
    "SET_WEIGHT": ["layer", "weight"],
    "RESET_WEIGHTS": [],
    "SHOW_TOP_SITES": ["n", "profile"],
    "SELECT_PLACE": ["name", "lat", "lon"],
    "PLACE_SITE": ["profile", "name", "lat", "lon"],
    "REMOVE_SITE": ["id"],
    "RENAME_SITE": ["id", "name"],
    "COMPARE_SITES": ["ids"],
    "COMPARE_USE_CASES": ["profiles", "name", "lat", "lon"],
    "EXPLAIN": ["name", "lat", "lon"],
    "TOGGLE_MASKS": ["state"],
    "TOGGLE_TERRAIN": ["state"],
    "HELP": [],
    # creation flow (home screen; Person 1's agent emits these too)
    "OPEN_CREATE": [],
    "CREATE_STRUCTURE": ["profile", "name"],
    "OPEN_STRUCTURE": ["name"],
    "SHOW_MODEL": ["profile"],
    "SHOW_PROGRESS": ["title", "step"],
    "GO_HOME": [],
}

CommandType = Literal[
    "PAN_COUNTRY", "PAN_CITY", "PAN_REGION", "ZOOM", "RESET_VIEW", "ROTATE_GLOBE",
    "SET_PROFILE", "SET_OVERLAY", "SET_WEIGHT", "RESET_WEIGHTS", "SHOW_TOP_SITES",
    "SELECT_PLACE", "PLACE_SITE", "REMOVE_SITE", "RENAME_SITE", "COMPARE_SITES",
    "COMPARE_USE_CASES", "EXPLAIN", "TOGGLE_MASKS", "TOGGLE_TERRAIN", "HELP",
    "OPEN_CREATE", "CREATE_STRUCTURE", "OPEN_STRUCTURE", "SHOW_MODEL", "SHOW_PROGRESS", "GO_HOME",
]  # fmt: skip

OVERLAY_VIEWS = ["suitability", "thermal", "height", "flood", "crime", "air"]


class Command(BaseModel):
    type: CommandType
    args: dict[str, Any] = Field(default_factory=dict)


class AssistantContext(BaseModel):
    profile: str | None = Field(default=None, description="Current profile id.")
    overlay: str | None = Field(default=None, description="Current overlay id.")
    selected_h3: str | None = None
    site_ids: list[str] = Field(default_factory=list, description="Ids of placed sites.")


class AssistantRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "text": "Show me the best data centre sites in London with the thermal view",
                "context": {"profile": "house", "overlay": "suitability"},
            }
        }
    }

    text: str = Field(min_length=1, max_length=2000, description="What the user said or typed.")
    context: AssistantContext = Field(default_factory=AssistantContext)


class AssistantResponse(BaseModel):
    commands: list[Command]
    reply: str = Field(description="One short sentence to show or speak back.")
    source: Literal["mistral", "rules"]


# --------------------------------------------------------------------------- key


def _read_dotenv() -> dict[str, str]:
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("'\"")
    return out


def _dotenv_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def save_mistral_key(key: str | None) -> None:
    """Write (or remove) MISTRAL_API_KEY in the repo's gitignored .env and this process's env."""
    path = _dotenv_path()
    lines = path.read_text().splitlines() if path.is_file() else []
    lines = [ln for ln in lines if not ln.strip().startswith("MISTRAL_API_KEY=")]
    if key:
        lines.append(f"MISTRAL_API_KEY={key}")
        os.environ["MISTRAL_API_KEY"] = key
    else:
        os.environ.pop("MISTRAL_API_KEY", None)
    path.write_text("\n".join(lines) + ("\n" if lines else ""))
    with contextlib.suppress(OSError):
        path.chmod(0o600)


def check_mistral_key(key: str) -> bool | None:
    """True if Mistral accepts the key, False if it rejects it, None if Mistral is unreachable."""
    try:
        r = httpx.get(
            "https://api.mistral.ai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10.0,
        )
    except httpx.HTTPError:
        return None
    if r.status_code in (401, 403):
        return False
    return r.is_success or None


def mistral_key() -> str | None:
    return os.environ.get("MISTRAL_API_KEY") or _read_dotenv().get("MISTRAL_API_KEY") or None


# --------------------------------------------------------------------------- validation


def clean(raw: Any, profiles: list[str], layers: list[str]) -> list[Command]:
    """Keep only well-formed commands from the list; drop unknown types and args."""
    items = raw.get("commands", raw) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    out: list[Command] = []
    for item in items[:12]:
        if not isinstance(item, dict) or item.get("type") not in COMMANDS:
            continue
        args = item.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        args = {k: v for k, v in args.items() if k in COMMANDS[item["type"]]}
        t = item["type"]
        if t == "SET_PROFILE" and args.get("id") not in profiles:
            continue
        if t == "SET_OVERLAY":
            lay = str(args.get("layer", ""))
            if lay not in OVERLAY_VIEWS and lay not in layers:
                continue
        if t == "SET_WEIGHT":
            if args.get("layer") not in layers:
                continue
            try:
                args["weight"] = max(0.0, min(100.0, float(args.get("weight", 0))))
            except (TypeError, ValueError):
                continue
        out.append(Command(type=t, args=args))
    return out


# --------------------------------------------------------------------------- mistral


def _system_prompt(profiles: list[dict], layers: list[dict]) -> str:
    cmds = "\n".join(f"- {k}({', '.join(v)})" for k, v in COMMANDS.items())
    profs = ", ".join(f"{p['id']} ({p['label']})" for p in profiles)
    lays = ", ".join(f"{layer['id']} ({layer['label']})" for layer in layers)
    return (
        "You control Groundwork, a 3D globe + hex map that scores places for a use case. "
        "Turn the user's request into JSON: "
        '{"reply": "<one short sentence>", "commands": [{"type": "...", "args": {...}}]}. '
        "Use only these commands and argument names:\n"
        f"{cmds}\n"
        f"Profile ids: {profs}.\n"
        f"Overlay views: {', '.join(OVERLAY_VIEWS)}; or any layer id: {lays}.\n"
        "Weights are 0-100. state is 'on' or 'off'. direction is 'in' or 'out'. "
        "If the request is unclear or impossible, return no commands and say why in reply. "
        "Return JSON only."
    )


def ask_mistral(
    text: str, ctx: AssistantContext, profiles: list[dict], layers: list[dict], key: str
) -> tuple[list[Command], str]:
    body = {
        "model": MISTRAL_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _system_prompt(profiles, layers)},
            {"role": "user", "content": json.dumps({"context": ctx.model_dump(), "text": text})},
        ],
    }
    r = httpx.post(
        MISTRAL_URL, json=body, timeout=TIMEOUT_S, headers={"Authorization": f"Bearer {key}"}
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    cmds = clean(parsed, [p["id"] for p in profiles], [layer["id"] for layer in layers])
    reply = str(parsed.get("reply") or "") if isinstance(parsed, dict) else ""
    return cmds, reply or ("Done." if cmds else "Sorry, I couldn't turn that into an action.")


# --------------------------------------------------------------------------- rules


_NUM = r"(\d+(?:\.\d+)?)"
_RESET_VIEW = r"\b(reset|whole|entire) (view|globe|world)\b|\bshow (me )?the (globe|world)\b"
_PLACE = (
    r"\b(?:go to|fly to|pan to|take me to|show me|zoom to|in|near)\s+"
    r"([a-z][a-z .'-]{1,40}?)(?:[,.!?]| with| for| and|$| please)"
)
_SYNONYMS = {
    "data_centre": ["data centre", "data center", "datacentre", "datacenter", "server farm"],
    "house": ["house", "home", "housing", "live"],
    "school": ["school"],
    "mine": ["mine", "mining", "quarry"],
}
_OVERLAY_WORDS = {
    "thermal": ["thermal", "heat", "temperature", "hot"],
    "height": ["height", "elevation", "terrain map", "relief"],
    "flood": ["flood"],
    "crime": ["crime"],
    "air": ["air quality", "pollution", "air"],
    "suitability": ["suitability", "score"],
}


def _find_profile(t: str, profiles: list[dict]) -> str | None:
    ids = {p["id"] for p in profiles}
    for pid, words in _SYNONYMS.items():
        if pid in ids and any(w in t for w in words):
            return pid
    for p in profiles:
        if p["label"].lower() in t or p["id"].replace("_", " ") in t:
            return str(p["id"])
    return None


def _find_layer(t: str, layers: list[dict]) -> str | None:
    best = None
    for layer in layers:
        for name in (layer["label"].lower(), layer["id"].replace("_", " ")):
            if name in t and (best is None or len(name) > best[1]):
                best = (layer["id"], len(name))
    return best[0] if best else None


def rules(text: str, profiles: list[dict], layers: list[dict]) -> tuple[list[Command], str]:
    t = " " + re.sub(r"\s+", " ", text.lower()).strip() + " "
    raw: list[dict[str, Any]] = []
    on_off = "off" if re.search(r"\b(off|hide|disable|stop|without)\b", t) else "on"

    if re.search(r"\b(help|what can you do)\b", t):
        raw.append({"type": "HELP"})
    if re.search(_RESET_VIEW, t):
        raw.append({"type": "RESET_VIEW"})
    if re.search(r"\breset (the )?weights?\b|\bdefault weights?\b", t):
        raw.append({"type": "RESET_WEIGHTS"})
    if re.search(r"\bzoom (in|out)\b", t):
        raw.append({"type": "ZOOM", "args": {"direction": re.search(r"zoom (in|out)", t)[1]}})  # type: ignore[index]
    if re.search(r"\b(spin|rotat)", t):
        raw.append({"type": "ROTATE_GLOBE", "args": {"state": on_off}})
    if re.search(r"\b(mask|no-go|no go)", t):
        raw.append({"type": "TOGGLE_MASKS", "args": {"state": on_off}})
    if re.search(r"\b3d terrain\b|\bterrain (on|off)\b", t):
        raw.append({"type": "TOGGLE_TERRAIN", "args": {"state": on_off}})

    pid = _find_profile(t, profiles)
    if pid:
        raw.append({"type": "SET_PROFILE", "args": {"id": pid}})

    m = re.search(rf"\b(?:set|weight|make)\b(.+?)\b(?:to|=|at)\s*{_NUM}", t)
    if m and (lid := _find_layer(m[1], layers)):
        raw.append({"type": "SET_WEIGHT", "args": {"layer": lid, "weight": float(m[2])}})
    else:
        for ov, words in _OVERLAY_WORDS.items():
            if any(re.search(rf"\b{re.escape(w)}\b", t) for w in words) and ov != "suitability":
                raw.append({"type": "SET_OVERLAY", "args": {"layer": ov}})
                break
        else:
            if re.search(r"\b(overlay|layer|show)\b", t) and (lid := _find_layer(t, layers)):
                raw.append({"type": "SET_OVERLAY", "args": {"layer": lid}})

    if re.search(r"\b(best|top)\b", t):
        n = re.search(r"\b(?:top|best)\s+(\d+)\b", t)
        raw.append({"type": "SHOW_TOP_SITES", "args": {"n": int(n[1]) if n else 10}})
    if re.search(r"\b(why|explain)\b", t):
        raw.append({"type": "EXPLAIN"})
    if re.search(r"\bcompare\b", t):
        raw.append({"type": "COMPARE_USE_CASES", "args": {"profiles": [p["id"] for p in profiles]}})

    place = re.search(_PLACE, t)
    if place:
        name = place[1].strip()
        skip = {"the", "data", "the globe", "the world", "suitability", "thermal", "view"}
        if name not in skip and not any(name.startswith(w) for w in ("the best", "best", "top")):
            raw.append({"type": "PAN_CITY", "args": {"name": name.title()}})
    coords = re.search(rf"(-?{_NUM})\s*,\s*(-?{_NUM})", t)
    if coords and re.search(r"\b(place|build|put|drop)\b", t):
        lat, lon = float(coords[1]), float(coords[3])
        raw.append({"type": "PLACE_SITE", "args": {"lat": lat, "lon": lon}})
    elif re.search(r"\b(place|build|put|drop)\b", t):
        raw.append({"type": "PLACE_SITE", "args": {}})

    cmds = clean(raw, [p["id"] for p in profiles], [layer["id"] for layer in layers])
    if not cmds:
        return [], "I didn't catch an action. Try “show the best data centre sites” or “help”."
    return cmds, "OK: " + ", ".join(c.type.replace("_", " ").lower() for c in cmds) + "."


def handle(req: AssistantRequest, profiles: list[dict], layers: list[dict]) -> AssistantResponse:
    key = mistral_key()
    if key:
        try:
            cmds, reply = ask_mistral(req.text, req.context, profiles, layers, key)
            return AssistantResponse(commands=cmds, reply=reply, source="mistral")
        except Exception as exc:  # network, quota, bad JSON: fall back to the offline parser
            log.warning("Mistral call failed (%s); using rule-based parser", exc)
    cmds, reply = rules(req.text, profiles, layers)
    return AssistantResponse(commands=cmds, reply=reply, source="rules")


# --------------------------------------------------------------------------- voxtral


class AssistantStatus(BaseModel):
    mistral: bool = Field(description="A Mistral key is configured on the server.")
    voxtral_model: str | None = Field(description="Speech-to-text model used, if any.")
    chat_model: str | None


class Transcript(BaseModel):
    text: str
    model: str


def status() -> AssistantStatus:
    ok = mistral_key() is not None
    return AssistantStatus(
        mistral=ok,
        voxtral_model=VOXTRAL_MODEL if ok else None,
        chat_model=MISTRAL_MODEL if ok else None,
    )


def transcribe(audio: bytes, filename: str, content_type: str, language: str | None) -> Transcript:
    """Send recorded audio to Voxtral and return the text. Raises ValueError without a key."""
    key = mistral_key()
    if not key:
        raise ValueError("Voice transcription needs MISTRAL_API_KEY in the server's .env")
    if not audio:
        raise ValueError("No audio received")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ValueError("Audio is too long; keep voice commands under about a minute")
    data = {"model": VOXTRAL_MODEL}
    if language:
        data["language"] = language
    r = httpx.post(
        VOXTRAL_URL,
        headers={"Authorization": f"Bearer {key}"},
        data=data,
        files={"file": (filename or "speech.webm", audio, content_type or "audio/webm")},
        timeout=30.0,
    )
    r.raise_for_status()
    body = r.json()
    return Transcript(text=str(body.get("text", "")).strip(), model=VOXTRAL_MODEL)


# --------------------------------------------------------------------------- text-to-speech


def pick_tone(text: str) -> str:
    """A light heuristic so replies sound like they mean it."""
    t = text.lower()
    if re.search(r"\b(sorry|couldn.t|can.t|failed|no data|not available|blocked)\b", t):
        return "neutral"
    if text.rstrip().endswith("?") or re.search(r"\b(want me to|shall i|would you like)\b", t):
        return "curious"
    if re.search(r"\b(found|done|ready|great|good news|best|created|built|placed)\b", t):
        return "cheerful"
    if re.search(r"\b(recommend|should|i.d suggest|strongest|clear winner)\b", t):
        return "confident"
    return "neutral"


# Nearest available tone when a speaker lacks the one asked for (e.g. Paul has no "curious").
TONE_FALLBACKS: dict[str, list[str]] = {
    "curious": ["curious", "happy", "neutral"],
    "cheerful": ["cheerful", "happy", "neutral"],
    "excited": ["excited", "cheerful", "happy", "neutral"],
    "confident": ["confident", "neutral"],
    "neutral": ["neutral"],
}


def voice_for(tone: str, speaker: str | None = None) -> str:
    sp = speaker if speaker in SPEAKER_TONES else SPEAKER
    tones = SPEAKER_TONES.get(sp, {"neutral"})
    chosen = next((t for t in TONE_FALLBACKS.get(tone, [tone]) if t in tones), "neutral")
    return f"{sp}_{chosen}"


def speak(text: str, tone: str | None = None, speaker: str | None = None) -> tuple[bytes, str]:
    """Synthesise `text` with Voxtral. Returns (mp3 bytes, voice slug). ValueError without a key."""
    key = mistral_key()
    if not key:
        raise ValueError("Spoken replies need MISTRAL_API_KEY on the server")
    text = text.strip()[:1500]
    if not text:
        raise ValueError("Nothing to say")
    voice = voice_for(tone or pick_tone(text), speaker)
    r = httpx.post(
        SPEECH_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={"model": TTS_MODEL, "input": text, "voice_id": voice, "response_format": "mp3"},
        timeout=60.0,
    )
    r.raise_for_status()
    import base64

    return base64.b64decode(r.json()["audio_data"]), voice
