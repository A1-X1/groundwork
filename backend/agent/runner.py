"""The agent loop: Mistral chat completions with tool calls, executed locally.

    python -m backend.agent "I'm looking for building a nuclear power plant"

``run(prompt, on_event)`` streams events as dicts so the API can forward them (SSE):
``{"type": "tool_call", "name", "args"}``, ``{"type": "tool_result", "name", "result"}``,
``{"type": "ui", "commands"}``, ``{"type": "action_required", "action", "message"}``,
``{"type": "message", "content"}`` and finally ``{"type": "done", "content", "steps"}``.
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


def run(prompt: str, on_event: Callable[[Event], None] | None = None, history: list[dict] | None = None,
        model: str = DEFAULT_MODEL, client: Any = None) -> dict[str, Any]:
    """Run the agent to completion. Returns {content, steps, messages, ui, actions}."""
    emit = on_event or (lambda e: None)
    client = client or _client()
    messages: list[dict[str, Any]] = [{"role": "system", "content": INSTRUCTIONS}, *(history or []),
                                      {"role": "user", "content": prompt}]
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
        if msg.content and calls:
            emit({"type": "message", "content": msg.content})
        if not calls:
            content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content, default=str)
            emit({"type": "done", "content": content, "steps": step})
            return {"content": content, "steps": step, "messages": messages, "ui": ui, "actions": actions}
        for c in calls:
            args = _args_dict(c)
            emit({"type": "tool_call", "name": c.function.name, "args": args})
            result = tools.call(c.function.name, args)
            emit({"type": "tool_result", "name": c.function.name, "result": result})
            if "ui" in result:
                ui.extend(result["ui"])
                emit({"type": "ui", "commands": result["ui"]})
            if "action_required" in result:
                actions.append(result)
                emit({"type": "action_required", "action": result["action_required"],
                      "message": result.get("message", "")})
            messages.append({"role": "tool", "name": c.function.name, "tool_call_id": c.id,
                             "content": _trim(result)})
    emit({"type": "done", "content": "Stopped: step limit reached.", "steps": MAX_STEPS})
    return {"content": "Stopped: step limit reached.", "steps": MAX_STEPS, "messages": messages,
            "ui": ui, "actions": actions}


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
        elif e["type"] == "done":
            print("\n" + e["content"])

    run(" ".join(args.prompt), show, model=args.model)


if __name__ == "__main__":
    main()
