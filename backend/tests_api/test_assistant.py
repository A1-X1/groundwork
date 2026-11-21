"""Assistant: rule-based parsing offline, Mistral path with a mocked HTTP call."""

import json

import httpx
import pytest

from backend.api import assistant


@pytest.fixture(autouse=True)
def _no_key(monkeypatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(assistant, "_read_dotenv", lambda: {})


def types(body: dict) -> list[str]:
    return [c["type"] for c in body["commands"]]


def ask(client, text: str) -> dict:
    r = client.post("/assistant/command", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_rules_profile_overlay_top(client) -> None:
    body = ask(client, "Show me the best data centre sites with the thermal view")
    assert body["source"] == "rules"
    assert {"SET_PROFILE", "SET_OVERLAY", "SHOW_TOP_SITES"} <= set(types(body))
    prof = next(c for c in body["commands"] if c["type"] == "SET_PROFILE")
    assert prof["args"]["id"] == "data_centre"


def test_rules_pan_and_weight(client) -> None:
    body = ask(client, "fly to Paris")
    assert body["commands"][0] == {"type": "PAN_CITY", "args": {"name": "Paris"}}
    body = ask(client, "set crime rate to 80")
    w = next(c for c in body["commands"] if c["type"] == "SET_WEIGHT")
    assert w["args"] == {"layer": "crime_rate", "weight": 80.0}


def test_rules_help_reset_and_nonsense(client) -> None:
    assert "HELP" in types(ask(client, "what can you do?"))
    assert "RESET_VIEW" in types(ask(client, "show me the whole globe"))
    body = ask(client, "qwerty")
    assert body["commands"] == []
    assert body["reply"]


def test_empty_text_is_422(client) -> None:
    assert client.post("/assistant/command", json={"text": ""}).status_code == 422


def test_clean_drops_unknown_commands_and_args() -> None:
    raw = {"commands": [
        {"type": "DELETE_EVERYTHING"},
        {"type": "SET_PROFILE", "args": {"id": "not_a_profile"}},
        {"type": "SET_WEIGHT", "args": {"layer": "crime_rate", "weight": 900, "evil": 1}},
        {"type": "ZOOM", "args": {"direction": "in", "extra": True}},
    ]}
    out = assistant.clean(raw, ["house"], ["crime_rate"])
    assert [c.model_dump() for c in out] == [
        {"type": "SET_WEIGHT", "args": {"layer": "crime_rate", "weight": 100.0}},
        {"type": "ZOOM", "args": {"direction": "in"}},
    ]


def test_mistral_path_is_used_and_validated(client, monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    seen: dict = {}

    def fake_post(url, json=None, timeout=None, headers=None):
        seen["auth"] = headers["Authorization"]
        content = {"reply": "Flying to Lagos.", "commands": [
            {"type": "PAN_CITY", "args": {"name": "Lagos"}}, {"type": "RM_RF"}]}
        req = httpx.Request("POST", url)
        payload = {"choices": [{"message": {"content": __import__("json").dumps(content)}}]}
        return httpx.Response(200, json=payload, request=req)

    monkeypatch.setattr(assistant.httpx, "post", fake_post)
    body = ask(client, "take me to Lagos")
    assert body["source"] == "mistral"
    assert seen["auth"] == "Bearer test-key"
    assert body["commands"] == [{"type": "PAN_CITY", "args": {"name": "Lagos"}}]


def test_mistral_failure_falls_back_to_rules(client, monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")

    def boom(*a, **k):
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr(assistant.httpx, "post", boom)
    body = ask(client, "help")
    assert body["source"] == "rules"
    assert "HELP" in types(body)
    json.dumps(body)
