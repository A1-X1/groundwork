"""Suitability reviewer: offline rules and the Mistral path (mocked)."""

import json

import httpx
import pytest

from backend.api import assistant, reviewer


@pytest.fixture(autouse=True)
def _no_key(monkeypatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(assistant, "_read_dotenv", dict)


@pytest.mark.parametrize(
    "text",
    [
        "can you build a house in the ocnea",
        "put a data centre on the moon",
        "build a school inside a volcano",
    ],
)
def test_rules_flag_impossible(client, text) -> None:
    body = client.post("/assistant/review", json={"text": text}).json()
    assert body["verdict"] == "unsuitable" and body["reason"] and body["suggestion"]


def test_rules_pass_normal_requests(client) -> None:
    for text in [
        "show me the best house sites in London",
        "fly to Tokyo",
        "thermal view",
    ]:
        assert (
            client.post("/assistant/review", json={"text": text}).json()["verdict"]
            == "ok"
        )


def test_mistral_review(client, monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "k")

    def fake_post(url, json=None, timeout=None, headers=None):
        content = {
            "verdict": "warning",
            "reason": "Nuclear plants need exclusion zones.",
            "suggestion": "Look outside the M25.",
        }
        payload = {
            "choices": [{"message": {"content": __import__("json").dumps(content)}}]
        }
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(reviewer.httpx, "post", fake_post)
    body = client.post(
        "/assistant/review", json={"text": "nuclear plant in Soho"}
    ).json()
    assert body == {
        "verdict": "warning",
        "reason": "Nuclear plants need exclusion zones.",
        "suggestion": "Look outside the M25.",
        "source": "mistral",
    }
    json.dumps(body)


def test_mistral_failure_falls_back(client, monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    monkeypatch.setattr(
        reviewer.httpx,
        "post",
        lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")),
    )
    body = client.post("/assistant/review", json={"text": "best schools"}).json()
    assert body["verdict"] == "ok" and body["source"] == "rules"


def test_rules_no_false_positives() -> None:
    for text in [
        "build a house by the sea",
        "nuclear plant in Soho",
        "office space in Leeds",
        "a power plant near the coast",
    ]:
        assert reviewer.rules_review(text).verdict == "ok", text
    assert reviewer.rules_review("build a hotel in the sea").verdict == "unsuitable"
