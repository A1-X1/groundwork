"""The agent loop: Mistral chat completions with tool calls, executed locally.

    python -m backend.agent "I'm looking for building a nuclear power plant"

``run(prompt, on_event, context=None)`` streams events as dicts (the API forwards them as
SSE). Every event has ``type`` and a short human-readable ``message``:
``tool_call {name, args}``, ``tool_result {name, result}``, ``ui {commands}``,
``action_required {action, message}`` (e.g. ``action: "connect_azure"``),
``thinking {content}`` and finally ``answer {content, steps}``. The API adds its own
``done`` event wrapping the return value ``{content, steps, ui, actions}``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import tools

INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text()
AGGREGATOR_INSTRUCTIONS = (Path(__file__).parent / "aggregator.md").read_text()
AGENTS = {"planner": INSTRUCTIONS, "aggregator": AGGREGATOR_INSTRUCTIONS}
DEFAULT_MODEL = os.environ.get("GROUNDWORK_AGENT_MODEL", "mistral-large-latest")
# Routine steps (reading results, calling the next obvious tool, map commands) go to a faster
# model; the first planning step and any step after a tool error use DEFAULT_MODEL.
# Set GROUNDWORK_AGENT_FAST_MODEL to the same value as DEFAULT_MODEL to disable routing.
FAST_MODEL = os.environ.get("GROUNDWORK_AGENT_FAST_MODEL", "mistral-medium-latest")
MAX_STEPS = 30
Event = dict[str, Any]


def _client() -> Any:
    from mistralai.client import Mistral

    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise RuntimeError("MISTRAL_API_KEY is not set (Connections → Mistral, or .env)")
    return Mistral(api_key=key)


def _trim(result: dict[str, Any], limit: int = 12000) -> str:
    text = json.dumps(result, default=str, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + '…"(truncated)"'


# Phases shown in the UI, in order, with typical seconds (used for the time estimate).
PHASES = [("understand", "Understanding the request", 4), ("data", "Choosing data", 6),
          ("build", "Building data", 45), ("profile", "Creating the scoring profile", 5),
          ("model3d", "Designing the 3D model", 8), ("train", "Training / checking Azure", 15),
          ("verify", "Checking the best sites", 6), ("map", "Updating the map", 2)]
TOOL_PHASE = {"get_catalog": "understand", "search_data_sources": "data", "add_layer": "data", "layer_stats": "data",
              "build_layers": "build", "create_profile": "profile", "design_3d_model": "model3d",
              "azure_status": "train", "train_model": "train", "request_user_action": "train",
              "preview_scores": "verify", "ui_command": "map"}

STEP_LABELS = {
    "get_catalog": "Reading Groundwork's layers and profiles", "search_data_sources": "Searching free data sources",
    "add_layer": "Adding a data layer", "build_layers": "Downloading and building layers",
    "create_profile": "Creating the scoring profile", "design_3d_model": "Designing the 3D model",
    "azure_status": "Checking Azure ML", "train_model": "Training the feasibility model",
    "preview_scores": "Checking the best sites", "ui_command": "Updating the map",
    "request_user_action": "Waiting for you", "layer_stats": "Comparing local data ranges",
}


def run(prompt: str, on_event: Callable[[Event], None] | None = None, history: list[dict] | None = None,
        model: str = DEFAULT_MODEL, client: Any = None, context: dict[str, Any] | None = None,
        return_messages: bool = False, fast_model: str | None = FAST_MODEL) -> dict[str, Any]:
    """Run the agent to completion. Returns {content, steps, ui, actions} (+ messages if asked)."""
    client = client or _client()
    agent = str((context or {}).get("agent") or "planner")
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}; known: {sorted(AGENTS)}")
    schemas = tools.schemas_for(agent)
    allowed = {sc["function"]["name"] for sc in schemas}
    messages: list[dict[str, Any]] = [{"role": "system", "content": AGENTS[agent]}]
    if context:
        messages.append({"role": "system", "content": "Current UI context (what the user is looking at): "
                         + json.dumps(_context_for_model(context), default=str)[:2000]})
    messages += [*(history or []), {"role": "user", "content": prompt}]

    import time

    started = time.monotonic()
    phase_ids = [p[0] for p in PHASES]
    state: dict[str, Any] = {"phase": 0, "since": started, "build": None}

    def timing(phase_id: str | None = None, done: int | None = None, total: int | None = None) -> dict[str, Any]:
        now = time.monotonic()
        if phase_id in phase_ids and phase_ids.index(phase_id) > state["phase"]:
            state["phase"], state["since"] = phase_ids.index(phase_id), now
        i = state["phase"]
        elapsed = now - started
        in_phase = now - state["since"]
        typical = PHASES[i][2]
        if done is not None and total:  # data builds: extrapolate from layers finished so far
            current = (in_phase / done) * (total - done) if done else typical
        else:
            current = max(typical - in_phase, 3)  # counts down; never claims 0 while working
        remaining = current + sum(p[2] for p in PHASES[i + 1:])
        return {"phase": PHASES[i][0], "phase_label": PHASES[i][1], "phase_index": i + 1,
                "phase_total": len(PHASES), "elapsed_s": round(elapsed, 1),
                "eta_s": round(remaining), "percent": round(100 * i / len(PHASES))}

    def emit(e: Event) -> None:  # every event carries elapsed time, phase and an estimate
        base(e | timing(TOOL_PHASE.get(e.get("name", "")) or e.get("phase"), e.get("done"), e.get("total")))

    base = on_event or (lambda e: None)
    tools.set_progress(lambda e: emit({**e, "message": e.get("detail", "")}))

    def finish(content: str, steps: int) -> dict[str, Any]:
        emit({"type": "answer", "content": content, "steps": steps, "message": content[:200], "phase": "map"})
        tools.set_progress(None)
        out = {"content": content, "steps": steps, "ui": ui, "actions": actions, "agent": agent,
               "models": {m: models_used.count(m) for m in dict.fromkeys(models_used)},
               "seconds": round(time.monotonic() - started, 1)}
        if return_messages:
            out["messages"] = messages
        return out

    ui: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    last_error = False
    models_used: list[str] = []
    for step in range(MAX_STEPS):
        use = model if (step == 0 or last_error or not fast_model) else fast_model
        models_used.append(use)
        resp = client.chat.complete(model=use, messages=messages, tools=schemas,
                                    tool_choice="auto", temperature=0.2)
        msg = resp.choices[0].message
        calls = msg.tool_calls or []
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.function.name, "arguments": _args_str(c)}}
                                        for c in calls] or None})
        text = _text(msg.content)
        if text and calls:
            emit({"type": "thinking", "content": text, "message": text[:200]})
        if not calls:
            return finish(text or "", step)
        last_error = False
        for c in calls:
            name, args = c.function.name, _args_dict(c)
            label = STEP_LABELS.get(name, name)
            emit({"type": "tool_call", "name": name, "args": args, "message": f"{label}…", "detail": _detail(name, args)})
            result = tools.call(name, args) if name in allowed else {"error": f"{name} is not available to the {agent} agent"}
            last_error = last_error or "error" in result
            emit({"type": "tool_result", "name": name, "result": result,
                  "message": f"{label}: {'error' if 'error' in result else 'done'}"})
            if "ui" in result:
                ui.extend(result["ui"])
                emit({"type": "ui", "commands": result["ui"], "message": "Updating the map"})
            if "action_required" in result:
                actions.append(result)
                emit({"type": "action_required", "action": result["action_required"],
                      "message": result.get("message", "")})
            messages.append({"role": "tool", "name": c.function.name, "tool_call_id": c.id,
                             "content": _trim(result)})
    return finish("Stopped: step limit reached.", MAX_STEPS)


VIEW_KEYS = ("screen", "place", "region", "profile", "overlay", "agent", "selection_place", "structure")


def _context_for_model(context: dict[str, Any]) -> dict[str, Any]:
    """Only the human-meaningful parts of the UI state. Raw coordinates and zoom stay out, so the
    model reasons (and talks) in place names; the zoom level becomes a coarse 'view' word."""
    out = {k: context[k] for k in VIEW_KEYS if context.get(k) not in (None, "", [])}
    sel = context.get("selection")
    if isinstance(sel, dict) and {"lat", "lon"} <= set(sel):  # the clicked site, for address lookups only
        out["selection"] = {"lat": sel["lat"], "lon": sel["lon"], **({"h3": sel["h3"]} if "h3" in sel else {})}
    zoom = context.get("zoom")
    if isinstance(zoom, (int, float)):
        out["view"] = "globe" if zoom < 4 else "country" if zoom < 7 else "city" if zoom < 11 else "street"
    return out


def _detail(name: str, args: dict[str, Any]) -> str:
    """A specific one-line description of what a tool call is doing, for the progress card."""
    if name == "add_layer":
        return f"Adding data: {args.get('label') or args.get('id')} ({args.get('template', '')})"
    if name == "build_layers":
        ids = args.get("layer_ids") or []
        return f"Building {len(ids)} layer(s) for {args.get('region', 'london')}: {', '.join(ids)[:120]}"
    if name == "search_data_sources":
        return f"Searching free sources for “{str(args.get('query', ''))[:80]}”"
    if name == "layer_stats":
        return f"Comparing local ranges of {len(args.get('layer_ids') or [])} layer(s)"
    if name == "create_profile":
        return f"Writing profile “{args.get('label', args.get('id', ''))}” with {len(args.get('layers') or {})} criteria"
    if name == "design_3d_model":
        spec = args.get("spec") or {}
        return f"Designing a 3D {spec.get('label', 'model')} from {len(spec.get('parts') or [])} parts"
    if name == "train_model":
        return f"Training the feasibility model ({args.get('backend', 'auto')})"
    if name == "preview_scores":
        return "Scoring every hexagon and picking the best sites"
    if name == "ui_command":
        return "Map: " + " → ".join(c.get("command", "") for c in (args.get("commands") or []))[:120]
    return STEP_LABELS.get(name, name)


def _text(content: Any) -> str:
    """Plain answer text from a string or a list of content chunks (reasoning chunks dropped)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    texts, thoughts = [], []
    for chunk in content:
        kind = getattr(chunk, "type", None) or (chunk.get("type") if isinstance(chunk, dict) else None)
        if kind == "text":
            texts.append(getattr(chunk, "text", None) or chunk.get("text", ""))
        elif kind == "thinking":
            inner = getattr(chunk, "thinking", None) or (chunk.get("thinking") if isinstance(chunk, dict) else [])
            thoughts.extend(getattr(t, "text", "") or (t.get("text", "") if isinstance(t, dict) else "") for t in inner)
    return "\n".join(t for t in texts if t).strip() or "\n".join(thoughts).strip()


def _args_dict(call: Any) -> dict[str, Any]:
    a = call.function.arguments
    if isinstance(a, dict):
        return a
    try:
        return json.loads(a or "{}")
    except json.JSONDecodeError:
        return {}


def _args_str(call: Any) -> str:
    a = call.function.arguments
    return a if isinstance(a, str) else json.dumps(a)


def main() -> None:
    import argparse
    import logging

    ap = argparse.ArgumentParser(description="Run the Groundwork planning agent")
    ap.add_argument("prompt", nargs="+")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)

    def show(e: Event) -> None:
        if e["type"] == "tool_call":
            print(f"→ {e['name']}({json.dumps(e['args'], ensure_ascii=False)[:300]})")
        elif e["type"] == "tool_result":
            print(f"  ← {_trim(e['result'], 400)}")
        elif e["type"] == "action_required":
            print(f"!! ACTION REQUIRED [{e['action']}]: {e['message']}")
        elif e["type"] == "answer":
            print("\n" + e["content"])

    run(" ".join(args.prompt), show, model=args.model)


if __name__ == "__main__":
    main()
