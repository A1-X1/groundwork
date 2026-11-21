"""API responses and fixtures must validate against the frozen contract schema."""

import json
from pathlib import Path

import jsonschema
import pytest

from backend.tests_api.conftest import CONTRACTS, ROOT

FORMAT = jsonschema.Draft202012Validator.FORMAT_CHECKER


def validate(instance: dict, schema: dict) -> None:
    jsonschema.Draft202012Validator(schema, format_checker=FORMAT).validate(instance)


def test_schema_is_valid(schema: dict) -> None:
    jsonschema.Draft202012Validator.check_schema(schema)


def test_example_fixture_validates(schema: dict) -> None:
    validate(
        json.loads((CONTRACTS / "score_response.example.json").read_text(encoding="utf-8")), schema
    )


def test_frontend_fixture_validates(schema: dict) -> None:
    fixture = ROOT / "frontend" / "src" / "fixtures" / "score_response.json"
    if not fixture.exists():
        pytest.skip("frontend fixture not present")
    validate(json.loads(fixture.read_text(encoding="utf-8")), schema)


@pytest.mark.parametrize("profile", ["data_centre", "house", "school", "mine"])
def test_score_endpoint_validates(client, schema: dict, profile: str) -> None:
    r = client.get(f"/score/{profile}")
    assert r.status_code == 200
    validate(r.json(), schema)


def test_custom_score_validates(client, schema: dict) -> None:
    r = client.post(
        "/score/custom", json={"profile": "house", "weights": {"crime_rate": 1.0}}
    )
    assert r.status_code == 200
    validate(r.json(), schema)


def test_schema_rejects_bad_cell(schema: dict) -> None:
    bad = {
        "profile": "house",
        "resolution": 8,
        "generated_at": "2026-11-21T10:00:00Z",
        "cells": [{"h3": "nope", "score": 1.5, "masked": False, "breakdown": {}}],
    }
    with pytest.raises(jsonschema.ValidationError):
        validate(bad, schema)


def test_contract_files_exist() -> None:
    names = [
        "scoring_interface.md",
        "score_response.schema.json",
        "score_response.example.json",
    ]
    for name in names:
        assert (Path(CONTRACTS) / name).is_file()


def test_null_raw_values_are_valid() -> None:
    """Layers without data in a region return raw = null (normalised value 0.5)."""
    from backend.api.models import LayerValue

    cell = LayerValue(h3="881f1d4a9bfffff", value=0.5, raw=None)
    assert cell.raw is None
    assert "raw" in LayerValue.model_json_schema()["properties"]
