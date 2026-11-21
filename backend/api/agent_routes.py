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
import queue
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
    """Streams the planning agent's steps (identify use case → pick layers → add data sources →
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

    def worker() -> None:
        try:
            extra = {"context": body.context} if body.context else {}
            result = mod.run(body.prompt, events.put, **extra)
            events.put({"type": "done", "result": result})
        except Exception as exc:  # surfaced to the UI as an error event
            log.exception("agent run failed")
            events.put({"type": "error", "message": str(exc)})
        finally:
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
            yield _sse(ev if isinstance(ev, dict) else {"type": "step", "data": ev})

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
