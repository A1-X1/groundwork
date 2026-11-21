"""Assistant: rule-based parsing offline, Mistral path with a mocked HTTP call."""

import json

import httpx
import pytest

from backend.api import assistant


@pytest.fixture(autouse=True)
def _no_key(monkeypatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(assistant, "_read_dotenv", dict)


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
    raw = {
        "commands": [
            {"type": "DELETE_EVERYTHING"},
            {"type": "SET_PROFILE", "args": {"id": "not_a_profile"}},
            {
                "type": "SET_WEIGHT",
                "args": {"layer": "crime_rate", "weight": 900, "evil": 1},
            },
            {"type": "ZOOM", "args": {"direction": "in", "extra": True}},
        ]
    }
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
        content = {
            "reply": "Flying to Lagos.",
            "commands": [
                {"type": "PAN_CITY", "args": {"name": "Lagos"}},
                {"type": "RM_RF"},
            ],
        }
        req = httpx.Request("POST", url)
        payload = {
            "choices": [{"message": {"content": __import__("json").dumps(content)}}]
        }
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
    r = client.post(
        "/assistant/transcribe", files={"file": ("a.webm", b"xx", "audio/webm")}
    )
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
    assert seen["auth"] == "Bearer test-key" and seen["url"].endswith(
        "/audio/transcriptions"
    )


def test_transcribe_upstream_failure_is_502(client, monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")

    def boom(*a, **k):
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr(assistant.httpx, "post", boom)
    r = client.post(
        "/assistant/transcribe", files={"file": ("a.webm", b"xx", "audio/webm")}
    )
    assert r.status_code == 502


def test_pick_tone_and_voice() -> None:
    assert assistant.pick_tone("I found three strong sites.") == "cheerful"
    assert assistant.pick_tone("Want me to show you why?") == "curious"
    assert assistant.pick_tone("Sorry, I couldn't find that place.") == "neutral"
    assert assistant.voice_for("curious", "gb_oliver") == "gb_oliver_curious"
    assert (
        assistant.voice_for("curious", "en_paul") == "en_paul_happy"
    )  # Paul has no curious
    assert assistant.voice_for("cheerful", "en_paul") == "en_paul_cheerful"
    assert assistant.voice_for("excited", "gb_jane") == "gb_jane_neutral"
    assert (
        assistant.SPEAKER == "en_paul" or assistant.SPEAKER
    )  # default is Paul unless overridden


def test_speak_without_key_is_422(client) -> None:
    r = client.post("/assistant/speak", json={"text": "hello"})
    assert r.status_code == 422


def test_speak_returns_mp3(client, monkeypatch) -> None:
    import base64

    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    seen: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None, **_):
        seen.update(url=url, body=json)
        payload = {"audio_data": base64.b64encode(b"ID3fake").decode()}
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(assistant.httpx, "post", fake_post)
    r = client.post(
        "/assistant/speak", json={"text": "Good news, I found the best site."}
    )
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    assert r.content == b"ID3fake"
    assert r.headers["x-voice"].endswith("_cheerful")
    assert seen["body"]["voice_id"] == r.headers["x-voice"]
    assert seen["url"].endswith("/audio/speech")


def test_rules_compound_request_keeps_order(client) -> None:
    body = ask(
        client,
        "first fly to Paris then show the thermal view, and then reset the weights",
    )
    assert types(body) == ["PAN_CITY", "SET_OVERLAY", "RESET_WEIGHTS"]
    body = ask(client, "show me the best house sites after that zoom in")
    assert types(body)[-1] == "ZOOM"


def test_clean_sorts_by_seq() -> None:
    raw = [
        {"type": "ZOOM", "seq": 1, "args": {"direction": "in"}},
        {"type": "RESET_VIEW", "seq": 0},
    ]
    assert [c.type for c in assistant.clean(raw, [], [])] == ["RESET_VIEW", "ZOOM"]


def test_go_to_rank_rules() -> None:
    """'best location', 'second best', 'number 5', 'next one' zoom to one ranked site."""
    from backend.api.assistant import clean, rules

    def first(t: str):
        cmds, _ = rules(t, [], [])
        return (cmds[0].type, cmds[0].args) if cmds else None

    assert first("take me to the best location") == ("GO_TO_RANK", {"rank": 1})
    assert first("zoom into the second best site") == ("GO_TO_RANK", {"rank": 2})
    assert first("go to number 5") == ("GO_TO_RANK", {"rank": 5})
    assert first("next one") == ("GO_TO_RANK", {"rank": "next"})
    assert first("previous") == ("GO_TO_RANK", {"rank": "prev"})
    assert first("best house sites") == ("SHOW_TOP_SITES", {"n": 10})
    bad = clean([{"type": "GO_TO_RANK", "args": {"rank": "banana"}}], [], [])
    assert bad == []
    assert clean([{"type": "GO_TO_RANK", "args": {"rank": "9999"}}], [], [])[
        0
    ].args == {"rank": 500}


def test_not_understood_matches_agent_wording() -> None:
    """Gibberish gets the same sentence as Person 1's agent, and no commands."""
    from backend.api.assistant import NOT_UNDERSTOOD, clean, rules

    cmds, reply = rules("flibber jabber wobble", [], [])
    assert (
        cmds == []
        and reply == NOT_UNDERSTOOD == "Sorry, I don't understand that command."
    )
    pan = clean(
        [
            {
                "type": "PAN_ADDRESS",
                "args": {"address": "10 Downing St", "lat": 51.5, "lon": -0.13},
            }
        ],
        [],
        [],
    )
    assert pan[0].type == "PAN_ADDRESS" and pan[0].args["address"] == "10 Downing St"


def test_worst_commands() -> None:
    """'the worst location', 'second worst', 'worst sites' / 'bottom 5' rank least suitable first."""
    from backend.api.assistant import clean, rules

    def cmds(t: str):
        return [(c.type, c.args) for c in rules(t, [], [])[0]]

    assert cmds("take me to the worst location") == [
        ("GO_TO_RANK", {"rank": 1, "order": "worst"})
    ]
    assert cmds("zoom into the second worst site") == [
        ("GO_TO_RANK", {"rank": 2, "order": "worst"})
    ]
    assert cmds("show the worst sites") == [
        ("SHOW_TOP_SITES", {"n": 10, "order": "worst"})
    ]
    assert cmds("bottom 5") == [("SHOW_TOP_SITES", {"n": 5, "order": "worst"})]
    assert cmds("next one") == [
        ("GO_TO_RANK", {"rank": "next"})
    ]  # keeps the current order
    bad = clean(
        [{"type": "GO_TO_RANK", "args": {"rank": 1, "order": "sideways"}}], [], []
    )
    assert bad[0].args == {"rank": 1}


def test_open_map_first_from_home(monkeypatch) -> None:
    """On the home screen a map queue starts with OPEN_MAP; on the map it doesn't."""
    from backend.api import assistant

    monkeypatch.setattr(assistant, "mistral_key", lambda: None)
    home = assistant.AssistantRequest(text="fly to Paris", context={"screen": "home"})
    out = assistant.handle(home, [], [])
    assert [c.type for c in out.commands] == ["OPEN_MAP", "PAN_CITY"]
    on_map = assistant.AssistantRequest(
        text="fly to Paris", context={"screen": "explore"}
    )
    assert [c.type for c in assistant.handle(on_map, [], []).commands] == ["PAN_CITY"]
    help_home = assistant.AssistantRequest(text="help", context={"screen": "home"})
    assert [c.type for c in assistant.handle(help_home, [], []).commands] == ["HELP"]


def test_rules_back_up_mistral(monkeypatch) -> None:
    """When the model refuses a plain request or lists sites instead of going to one, the
    deterministic rules' commands are used."""
    from backend.api import assistant

    monkeypatch.setattr(assistant, "mistral_key", lambda: "k")

    def refuse(text, ctx, profiles, layers, key):
        return [], "Please provide a more specific request.", False

    monkeypatch.setattr(assistant, "ask_mistral", refuse)
    out = assistant.handle(
        assistant.AssistantRequest(text="fly to Tokyo", context={}), [], []
    )
    assert [c.type for c in out.commands] == ["PAN_CITY"] and out.understood

    def lists(text, ctx, profiles, layers, key):
        return (
            [assistant.Command(type="SHOW_TOP_SITES", args={"n": 1})],
            "Showing the best.",
            True,
        )

    monkeypatch.setattr(assistant, "ask_mistral", lists)
    req = assistant.AssistantRequest(text="take me to the best location", context={})
    assert [c.type for c in assistant.handle(req, [], []).commands] == ["GO_TO_RANK"]
    # nulls from the model are dropped during validation
    cleaned = assistant.clean(
        [{"type": "SHOW_TOP_SITES", "args": {"n": 3, "profile": None}}], [], []
    )
    assert cleaned[0].args == {"n": 3}
