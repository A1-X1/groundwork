"""Agent stream (with a fake backend.agent) and connections."""

import json
import sys
import types

from backend.api import agent_routes, assistant


def test_agent_unavailable_is_503(client, monkeypatch) -> None:
    monkeypatch.setattr(agent_routes, "_agent_module", lambda: None)
    r = client.post("/agent/run", json={"prompt": "nuclear power plant"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "agent_unavailable"


def test_agent_streams_events(client, monkeypatch) -> None:
    fake = types.ModuleType("backend.agent")

    def run(prompt, on_event, **_):
        on_event({"type": "step", "step": "identify_use_case", "message": f"Use case for {prompt}"})
        on_event({"type": "step", "action": "connect_azure"})
        return {"profile": "nuclear_plant"}

    fake.run = run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "backend.agent", fake)
    with client.stream("POST", "/agent/run", json={"prompt": "nuclear"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
    assert events[0]["step"] == "identify_use_case"
    assert events[1]["action"] == "connect_azure"
    assert events[-1] == {"type": "done", "result": {"profile": "nuclear_plant"}}


def test_agent_error_event(client, monkeypatch) -> None:
    fake = types.ModuleType("backend.agent")

    def run(prompt, on_event, **_):
        raise RuntimeError("boom")

    fake.run = run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "backend.agent", fake)
    with client.stream("POST", "/agent/run", json={"prompt": "x"}) as r:
        body = "".join(r.iter_text())
    assert '"type": "error"' in body and "boom" in body


def test_connections_and_azure_config(client, monkeypatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(assistant, "_read_dotenv", lambda: {})
    c = client.get("/connections").json()
    assert c["mistral"]["configured"] is False
    assert c["azure_ml"]["configured"] is False
    cfg = {"subscription_id": "sub-1", "resource_group": "rg", "workspace": "ws"}
    r = client.put("/connections/azure", json=cfg)
    assert r.status_code == 200 and r.json()["config"] == cfg
    assert client.get("/connections").json()["azure_ml"]["configured"] is True
    assert client.delete("/connections/azure").json()["configured"] is False


def test_azure_login_needs_workspace(client) -> None:
    client.delete("/connections/azure")
    r = client.post("/connections/azure/login")
    assert r.status_code == 422
