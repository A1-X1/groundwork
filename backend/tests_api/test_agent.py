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
        on_event({"type": "tool_call", "name": "get_catalog", "args": {}})
        on_event(
            {"type": "ui", "commands": [{"command": "SET_PROFILE", "id": "school"}]}
        )
        on_event(
            {"type": "action_required", "action": "connect_azure", "message": "Sign in"}
        )
        on_event({"type": "answer", "content": f"Planned {prompt}", "steps": 3})
        return {
            "content": f"Planned {prompt}",
            "steps": 3,
            "ui": [],
            "actions": [],
            "models": {"mistral-large-latest": 2, "mistral-medium-latest": 5},
            "seconds": 84.2,
        }

    fake.run = run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "backend.agent", fake)
    with client.stream("POST", "/agent/run", json={"prompt": "nuclear"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    events = [
        json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")
    ]
    types_ = [e["type"] for e in events]
    assert types_ == ["tool_call", "ui", "action_required", "answer", "done"]
    assert events[2]["action"] == "connect_azure"
    assert events[-1]["content"] == "Planned nuclear" and "messages" not in events[-1]
    assert events[-1]["models"] == {
        "mistral-large-latest": 2,
        "mistral-medium-latest": 5,
    }
    assert events[-1]["seconds"] == 84.2
    assert "event: action_required" in body


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
    monkeypatch.setattr(assistant, "_read_dotenv", dict)
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


def test_agent_finish_hook_runs(client, monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(agent_routes, "ON_FINISH", [lambda: calls.append(1)])
    fake = types.ModuleType("backend.agent")
    fake.run = lambda prompt, on_event, **_: {"content": "ok"}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "backend.agent", fake)
    with client.stream("POST", "/agent/run", json={"prompt": "x"}) as r:
        "".join(r.iter_text())
    assert calls == [1]


def test_models3d(client, tmp_path, monkeypatch) -> None:
    mod = agent_routes._models3d()
    if mod is None:
        return
    monkeypatch.setattr(mod, "MODELS_DIR", tmp_path)
    spec = mod.ModelSpec(
        id="nuclear_plant",
        label="Nuclear plant",
        footprint_m=(300, 300),
        parts=[
            mod.cooling_tower(-60, 0),
            {"shape": "dome", "radius": 30, "position": [60, 0, 0]},
        ],
    )
    mod.save(spec, tmp_path)
    assert client.get("/models3d").json() == ["nuclear_plant"]
    body = client.get("/models3d/nuclear_plant").json()
    assert body["parts"][0]["shape"] == "hyperboloid" and body["triangles"] <= 5000
    assert client.get("/models3d/nope").status_code == 404


def test_clean_content_drops_thinking() -> None:
    raw = json.dumps(
        [
            "thinking=[TextChunk(text='private reasoning', type='text')] type='thinking'",
            "text='Done \\u2014 London is on screen.' type='text'",
        ]
    )
    assert agent_routes._clean_content(raw) == "Done — London is on screen."
    assert agent_routes._clean_content([{"type": "text", "text": "hi"}]) == "hi"
    assert agent_routes._clean_content("plain") == "plain"
    assert agent_routes._tidy({"type": "message", "content": ["thinking=[x]"]}) is None


def test_mistral_key_save_and_forget(client, monkeypatch, tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("OTHER=1\n")
    monkeypatch.setattr(assistant, "_dotenv_path", lambda: env)
    monkeypatch.setattr(
        assistant,
        "_read_dotenv",
        lambda: {
            k: v
            for k, v in (
                ln.split("=", 1) for ln in env.read_text().splitlines() if "=" in ln
            )
        },
    )
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(
        assistant, "check_mistral_key", lambda key: key != "bad-key-123"
    )
    assert (
        client.put("/connections/mistral", json={"api_key": "bad-key-123"}).status_code
        == 422
    )
    r = client.put("/connections/mistral", json={"api_key": "good-key-123"})
    assert r.status_code == 200 and r.json()["configured"] is True
    assert "good-key-123" not in r.text
    assert (
        "MISTRAL_API_KEY=good-key-123" in env.read_text()
        and "OTHER=1" in env.read_text()
    )
    assert client.delete("/connections/mistral").json()["configured"] is False
    assert "MISTRAL_API_KEY" not in env.read_text()
