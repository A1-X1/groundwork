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
DEFAULT_MODEL = os.environ.get("GROUNDWORK_AGENT_MODEL", "mistral-large-latest")
MAX_STEPS = 30
Event = dict[str, Any]


def _client() -> Any:
    from mistralai.client import Mistral

    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise RuntimeError("MISTRAL_API_KEY is not set (Connections → Mistral, or .env)")
    return Mistral(api_key=key)


def _trim(result: dict[str, Any], limit: int = 6000) -> str:
    text = json.dumps(result, default=str, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + '…"(truncated)"'


STEP_LABELS = {
    "get_catalog": "Reading Groundwork's layers and profiles", "search_data_sources": "Searching free data sources",
    "add_layer": "Adding a data layer", "build_layers": "Downloading and building layers",
    "create_profile": "Creating the scoring profile", "design_3d_model": "Designing the 3D model",
    "azure_status": "Checking Azure ML", "train_model": "Training the feasibility model",
    "preview_scores": "Checking the best sites", "ui_command": "Updating the map",
    "request_user_action": "Waiting for you",
}


def run(prompt: str, on_event: Callable[[Event], None] | None = None, history: list[dict] | None = None,
        model: str = DEFAULT_MODEL, client: Any = None, context: dict[str, Any] | None = None,
        return_messages: bool = False) -> dict[str, Any]:
    """Run the agent to completion. Returns {content, steps, ui, actions} (+ messages if asked)."""
    emit = on_event or (lambda e: None)
    client = client or _client()
    messages: list[dict[str, Any]] = [{"role": "system", "content": INSTRUCTIONS}]
    if context:
        messages.append({"role": "system", "content": "Current UI context (what the user is looking at): "
                         + json.dumps(context, default=str)[:2000]})
    messages += [*(history or []), {"role": "user", "content": prompt}]

    def finish(content: str, steps: int) -> dict[str, Any]:
        emit({"type": "answer", "content": content, "steps": steps, "message": content[:200]})
        out = {"content": content, "steps": steps, "ui": ui, "actions": actions}
        if return_messages:
            out["messages"] = messages
        return out

    ui: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for step in range(MAX_STEPS):
        resp = client.chat.complete(model=model, messages=messages, tools=tools.SCHEMAS,
                                    tool_choice="auto", temperature=0.2)
        msg = resp.choices[0].message
        calls = msg.tool_calls or []
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.function.name, "arguments": _args_str(c)}}
                                        for c in calls] or None})
        text = msg.content if isinstance(msg.content, str) else json.dumps(msg.content, default=str)
        if text and calls:
            emit({"type": "thinking", "content": text, "message": text[:200]})
        if not calls:
            return finish(text or "", step)
        for c in calls:
            name, args = c.function.name, _args_dict(c)
            label = STEP_LABELS.get(name, name)
            emit({"type": "tool_call", "name": name, "args": args, "message": f"{label}…"})
            result = tools.call(name, args)
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
