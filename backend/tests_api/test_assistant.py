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


def test_status_without_key(client) -> None:
    body = client.get("/assistant/status").json()
    assert body == {"mistral": False, "voxtral_model": None, "chat_model": None}


def test_transcribe_without_key_is_422(client) -> None:
    r = client.post("/assistant/transcribe", files={"file": ("a.webm", b"xx", "audio/webm")})
    assert r.status_code == 422
    assert "MISTRAL_API_KEY" in r.json()["error"]["message"]


def test_transcribe_calls_voxtral(client, monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    seen: dict = {}

    def fake_post(url, headers=None, data=None, files=None, timeout=None, **_):
        seen.update(url=url, auth=headers["Authorization"], model=data["model"])
        req = httpx.Request("POST", url)
        return httpx.Response(200, json={"text": " fly to Tokyo "}, request=req)

    monkeypatch.setattr(assistant.httpx, "post", fake_post)
    r = client.post(
        "/assistant/transcribe",
        files={"file": ("speech.webm", b"\x1a\x45\xdf\xa3", "audio/webm")},
        data={"language": "en"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"text": "fly to Tokyo", "model": assistant.VOXTRAL_MODEL}
    assert seen["auth"] == "Bearer test-key" and seen["url"].endswith("/audio/transcriptions")


def test_transcribe_upstream_failure_is_502(client, monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")

    def boom(*a, **k):
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr(assistant.httpx, "post", boom)
    r = client.post("/assistant/transcribe", files={"file": ("a.webm", b"xx", "audio/webm")})
    assert r.status_code == 502
