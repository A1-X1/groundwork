"""Planning agent stream and external connections (Mistral, Azure ML).

``POST /agent/run`` streams Person 1's ``backend.agent.run(prompt, on_event)`` as server-sent
events. Until that module exists it answers 503 with a clear message.

Connections are stored in the SQLite ``settings`` table (backend/api/db.py) so the agent can
read them: ``db.get_setting("azure_ml")``. Azure sign-in uses the device-code flow from
``azure-identity`` when installed; secrets are never stored, only workspace coordinates and the
signed-in account name.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import queue
import re
import threading
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.api import assistant, db

log = logging.getLogger("groundwork.agent")
router = APIRouter()
AZURE_SCOPE = "https://management.azure.com/.default"
STREAM_TIMEOUT_S = 600

# Called after every agent run (main.py registers a reload of scoring + the score cache, so new
# profiles and layers show up without restarting the API).
ON_FINISH: list[Any] = []

# In-memory Azure login state for this API process (the token stays in azure-identity's cache).
_azure: dict[str, Any] = {"status": "signed_out", "message": None, "account": None}
_azure_lock = threading.Lock()


# --------------------------------------------------------------------------- models


class AgentRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {"prompt": "I'm looking at building a nuclear power plant"}
        }
    }

    prompt: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict, description="UI context (profile, view).")


class AzureConfig(BaseModel):
    subscription_id: str = Field(min_length=1, max_length=64)
    resource_group: str = Field(min_length=1, max_length=90)
    workspace: str = Field(min_length=1, max_length=64)


class MistralKey(BaseModel):
    api_key: str = Field(min_length=8, max_length=200, description="Stored server-side only.")


class MistralStatus(BaseModel):
    configured: bool
    chat_model: str | None
    voxtral_model: str | None


class AzureStatus(BaseModel):
    configured: bool
    config: AzureConfig | None
    status: str = Field(description="signed_out | pending | signed_in | error | unavailable")
    message: str | None = Field(description="Sign-in instructions or the last error.")
    account: str | None
    verification_uri: str | None = None
    user_code: str | None = None


class Connections(BaseModel):
    mistral: MistralStatus
    azure_ml: AzureStatus


# --------------------------------------------------------------------------- agent


def _agent_module() -> Any | None:
    try:
        mod = importlib.import_module("backend.agent")
    except ImportError:
        return None
    return mod if hasattr(mod, "run") else None


_UESC = re.compile(r"\\u([0-9a-fA-F]{4})")
_TEXT_CHUNK = re.compile(r"""^text=(['"])(.*?)\1(?: type='text')?$""", re.S)


def _clean_content(content: Any) -> Any:
    """Reasoning models return content as chunk lists (or their repr). Keep only the answer
    text and drop the model's private thinking."""
    items: Any = content
    if isinstance(content, str) and content.startswith('["thinking='):
        try:
            items = json.loads(content)
        except json.JSONDecodeError:
            return content
    if not isinstance(items, list):
        return content
    parts: list[str] = []
    for it in items:
        if isinstance(it, dict):
            if it.get("type") == "text":
                parts.append(str(it.get("text", "")))
            continue
        text = str(it)
        if text.startswith("thinking="):
            continue
        m = _TEXT_CHUNK.match(text.strip())
        raw = m.group(2) if m else text
        parts.append(_UESC.sub(lambda m: chr(int(m.group(1), 16)), raw))
    return "\n".join(p for p in parts if p).strip()


def _tidy(event: dict[str, Any]) -> dict[str, Any] | None:
    if "content" in event:
        event = {**event, "content": _clean_content(event["content"])}
        if event["type"] == "message" and not event["content"]:
            return None  # thinking only: nothing to show
    return event


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event.get('type', 'step')}\ndata: {json.dumps(event, default=str)}\n\n"


@router.post(
    "/agent/run",
    tags=["agent"],
    summary="Run the planning agent (server-sent events)",
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "Stream of step events."},
        503: {"description": "The agent is not installed yet."},
    },
)
def run_agent(body: AgentRequest) -> Any:
    """Streams the planning agent's events: `tool_call`, `tool_result`, `ui` (map commands),
    `action_required` (e.g. `connect_azure`), `message`, `done`, then a compact `end` summary.
    Steps (identify use case → pick layers → add data sources →
    write profile → model spec → build layers → train) as `text/event-stream`. Each event is
    JSON with a `type`. If the agent needs Azure it emits `{"action": "connect_azure"}`; the UI
    then opens Connections and re-runs."""
    mod = _agent_module()
    if mod is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "agent_unavailable",
                    "message": "The planning agent isn't installed yet (backend.agent).",
                    "detail": None,
                }
            },
        )

    events: queue.Queue[dict[str, Any] | None] = queue.Queue()
    # The agent's Mistral client reads MISTRAL_API_KEY from the environment; the API may have it
    # only in .env.
    key = assistant.mistral_key()
    if key and not os.environ.get("MISTRAL_API_KEY"):
        os.environ["MISTRAL_API_KEY"] = key

    def worker() -> None:
        try:
            kwargs = {"context": body.context} if body.context else {}
            result = mod.run(body.prompt, events.put, **kwargs) or {}
            # The agent ends with an "answer" event; this route sends the single final "done".
            events.put(
                {
                    "type": "done",
                    "content": result.get("content"),
                    "ui": result.get("ui", []),
                    "actions": result.get("actions", []),
                    "steps": result.get("steps"),
                }
            )
        except Exception as exc:  # surfaced to the UI as an error event
            log.exception("agent run failed")
            events.put({"type": "error", "message": str(exc)})
        finally:
            for hook in ON_FINISH:
                try:
                    hook()
                except Exception:
                    log.exception("agent finish hook failed")
            events.put(None)

    threading.Thread(target=worker, name="agent-run", daemon=True).start()

    def stream() -> Iterator[str]:
        while True:
            try:
                ev = events.get(timeout=STREAM_TIMEOUT_S)
            except queue.Empty:
                yield _sse({"type": "error", "message": "agent timed out"})
                return
            if ev is None:
                return
            tidy = _tidy(ev) if isinstance(ev, dict) else {"type": "step", "data": ev}
            if tidy is not None:
                yield _sse(tidy)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------- connections


def _azure_status() -> AzureStatus:
    cfg = db.get_setting("azure_ml")
    with _azure_lock:
        state = dict(_azure)
    try:
        importlib.import_module("azure.identity")
        available = True
    except ImportError:
        available = False
    return AzureStatus(
        configured=bool(cfg),
        config=AzureConfig(**cfg) if cfg else None,
        status=state["status"] if available else "unavailable",
        message=state["message"] if available else "Install azure-identity to sign in to Azure ML.",
        account=state["account"],
        verification_uri=state.get("verification_uri"),
        user_code=state.get("user_code"),
    )


@router.get(
    "/connections",
    response_model=Connections,
    tags=["connections"],
    summary="Status of Mistral and Azure ML",
)
def connections() -> Connections:
    """Whether a Mistral key is configured (never returned) and the Azure ML workspace and
    sign-in state."""
    st = assistant.status()
    return Connections(
        mistral=MistralStatus(
            configured=st.mistral, chat_model=st.chat_model, voxtral_model=st.voxtral_model
        ),
        azure_ml=_azure_status(),
    )


@router.put(
    "/connections/mistral",
    response_model=MistralStatus,
    tags=["connections"],
    summary="Save a Mistral API key",
)
def save_mistral(body: MistralKey) -> MistralStatus:
    """Checks the key with Mistral, then stores it in the server's gitignored `.env`. The key is
    never returned by any endpoint. If Mistral can't be reached the key is stored unchecked."""
    key = body.api_key.strip()
    if assistant.check_mistral_key(key) is False:
        raise ValueError("Mistral rejected that API key")
    assistant.save_mistral_key(key)
    st = assistant.status()
    return MistralStatus(
        configured=st.mistral, chat_model=st.chat_model, voxtral_model=st.voxtral_model
    )


@router.delete(
    "/connections/mistral",
    response_model=MistralStatus,
    tags=["connections"],
    summary="Remove the Mistral API key",
)
def forget_mistral() -> MistralStatus:
    """Deletes the key from `.env` and the running server."""
    assistant.save_mistral_key(None)
    st = assistant.status()
    return MistralStatus(
        configured=st.mistral, chat_model=st.chat_model, voxtral_model=st.voxtral_model
    )


@router.put(
    "/connections/azure",
    response_model=AzureStatus,
    tags=["connections"],
    summary="Save the Azure ML workspace",
)
def save_azure(body: AzureConfig) -> AzureStatus:
    """Stores subscription, resource group and workspace (no secrets) for the agent's training
    step."""
    db.set_setting("azure_ml", body.model_dump())
    return _azure_status()


@router.delete(
    "/connections/azure",
    response_model=AzureStatus,
    tags=["connections"],
    summary="Forget the Azure ML workspace",
)
def forget_azure() -> AzureStatus:
    """Removes the stored workspace and resets the sign-in state."""
    db.set_setting("azure_ml", None)
    with _azure_lock:
        _azure.update(
            status="signed_out", message=None, account=None, verification_uri=None, user_code=None
        )
    return _azure_status()


@router.post(
    "/connections/azure/login",
    response_model=AzureStatus,
    tags=["connections"],
    summary="Start Azure device-code sign-in",
)
def azure_login() -> AzureStatus | JSONResponse:
    """Starts the device-code flow: the response carries a URL and a code for the user to enter
    in their browser. Poll `GET /connections` until `azure_ml.status` is `signed_in`."""
    if not db.get_setting("azure_ml"):
        raise ValueError("Save the Azure ML workspace first")
    try:
        identity = importlib.import_module("azure.identity")
    except ImportError:
        raise ValueError("azure-identity is not installed on the API server") from None

    started = threading.Event()

    def prompt(verification_uri: str, user_code: str, expires_on: Any) -> None:
        with _azure_lock:
            _azure.update(
                status="pending",
                verification_uri=verification_uri,
                user_code=user_code,
                message=f"Open {verification_uri} and enter code {user_code}.",
            )
        started.set()

    def worker() -> None:
        try:
            cred = identity.DeviceCodeCredential(prompt_callback=prompt)
            record = cred.authenticate(scopes=[AZURE_SCOPE])
            try:  # hand the signed-in credential to the agent's Azure ML training
                azure_ml = importlib.import_module("backend.agent.azure_ml")
                if hasattr(azure_ml, "set_credential"):
                    azure_ml.set_credential(cred)
            except ImportError:
                pass
            with _azure_lock:
                _azure.update(
                    status="signed_in",
                    account=getattr(record, "username", None),
                    message=None,
                    verification_uri=None,
                    user_code=None,
                )
        except Exception as exc:
            with _azure_lock:
                _azure.update(status="error", message=f"Azure sign-in failed: {exc}")
        finally:
            started.set()

    with _azure_lock:
        _azure.update(status="pending", message="Contacting Azure…")
    threading.Thread(target=worker, name="azure-login", daemon=True).start()
    started.wait(timeout=20)
    return _azure_status()


# --------------------------------------------------------------------------- 3D model specs


def _models3d() -> Any | None:
    try:
        return importlib.import_module("backend.agent.models3d")
    except ImportError:
        return None


@router.get("/models3d", tags=["agent"], summary="List parametric 3D building specs")
def list_models3d() -> list[str]:
    """Ids of building specs the agent (or a person) has saved in `backend/profiles/models/`."""
    mod = _models3d()
    if mod is None or not mod.MODELS_DIR.exists():
        return []
    return sorted(p.stem for p in mod.MODELS_DIR.glob("*.json"))


@router.get("/models3d/{model_id}", tags=["agent"], summary="One parametric 3D building spec")
def get_model3d(model_id: str) -> dict[str, Any]:
    """Primitives in metres (box, cylinder, cone, dome, hyperboloid; y up, origin at the hex
    centre) with a palette. The frontend builds the three.js mesh from it."""
    mod = _models3d()
    if mod is None:
        raise KeyError(f"3D model '{model_id}'")
    return mod.load(model_id)  # type: ignore[no-any-return]
