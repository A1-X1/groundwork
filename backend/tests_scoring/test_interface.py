"""The public interface (contract §5.1) against the committed sample grid."""

from __future__ import annotations

import math

import pytest

import backend.scoring as scoring
from backend.layers import LAYER_IDS


@pytest.fixture(autouse=True, scope="module")
def _sample(tmp_path_factory):
    import os

    from backend.scoring.data import SAMPLE_DIR

    old = os.environ.get("GROUNDWORK_DATA_DIR")
    os.environ["GROUNDWORK_DATA_DIR"] = str(SAMPLE_DIR)
    scoring.reload()
    yield
    if old is None:
        os.environ.pop("GROUNDWORK_DATA_DIR")
    else:
        os.environ["GROUNDWORK_DATA_DIR"] = old
    scoring.reload()


def test_list_profiles_shape():
    profiles = scoring.list_profiles()
    assert {p["id"] for p in profiles} >= {"data_centre", "house", "school", "mine"}
    for p in profiles:
        assert set(p) == {"id", "label", "description", "layers", "masks", "has_model"}
        assert math.isclose(sum(lw["weight"] for lw in p["layers"]), 1.0, abs_tol=1e-5)
        assert all(set(lw) == {"id", "weight", "better"} for lw in p["layers"])


def test_list_layers_covers_every_layer():
    layers = scoring.list_layers()
    assert [m["id"] for m in layers] == list(LAYER_IDS)
    for m in layers:
        assert set(m) == {"id", "label", "unit", "kind", "description", "source", "min", "max"}
        assert m["kind"] in {"raster", "proximity", "aggregate"}
        assert m["min"] <= m["max"]


def test_get_layer_values_normalised():
    rows = scoring.get_layer("crime_rate")
    assert len(rows) > 1000
    assert all(0 <= r["value"] <= 1 and set(r) == {"h3", "value", "raw"} for r in rows)


def test_get_layer_bbox_and_unknown():
    full = scoring.get_layer("elevation")
    part = scoring.get_layer("elevation", (-0.2, 51.45, -0.05, 51.55))
    assert 0 < len(part) < len(full)
    with pytest.raises(KeyError):
        scoring.get_layer("nope")


@pytest.mark.parametrize("profile", ["data_centre", "house", "school", "mine"])
def test_score_cells_match_contract(profile):
    cells = scoring.score(profile)
    assert len(cells) > 1000
    pids = {lw["id"] for p in scoring.list_profiles() if p["id"] == profile for lw in p["layers"]}
    for c in cells:
        assert set(c) == {"h3", "score", "masked", "breakdown"}
        assert (c["score"] is None) == c["masked"]
        assert c["score"] is None or 0 <= c["score"] <= 1
        assert set(c["breakdown"]) <= pids


def test_score_point_agrees_with_score():
    cells = {c["h3"]: c for c in scoring.score("house")}
    p = scoring.score_point("house", 51.5074, -0.1278)
    assert p["h3"] in cells and p["score"] == cells[p["h3"]]["score"]
    assert p["breakdown"] == pytest.approx(cells[p["h3"]]["breakdown"], abs=1e-4)
    assert set(p["raw"]) == set(LAYER_IDS)
    assert p["shap"] is not None and set(p["shap"]) == {"base_value", "positive", "negative"}
    assert len(p["shap"]["positive"]) <= 5 and len(p["shap"]["negative"]) <= 5
    assert all(isinstance(v, float) for v in p["shap_flat"].values())
    assert p["feasibility"] == p["feasibility_score"]


def test_score_point_without_model_has_no_shap():
    p = scoring.score_point("mine", 51.4, 0.1)
    assert p["shap"] is None and p["model"] is None and p["feasibility"] is None
    assert p["feasibility_score"] == 1.0


def test_score_point_errors():
    with pytest.raises(KeyError):
        scoring.score_point("house", 48.85, 2.35)  # Paris
    with pytest.raises(ValueError):
        scoring.score_point("house", 120, 0)
    with pytest.raises(KeyError):
        scoring.score_point("castle", 51.5, -0.1)


def test_custom_weights_change_scores():
    base = {c["h3"]: c["score"] for c in scoring.score("house")}
    tilted = {c["h3"]: c["score"] for c in scoring.score("house", {"crime_rate": 1.0, "dist_station": 0.0})}
    assert base != tilted


def test_data_status_reports_synthetic_layers():
    status = scoring.data_status()
    assert status["is_sample"] and status["cells"] > 1000
    assert set(status["real_layers"]) | set(status["synthetic_layers"]) == set(LAYER_IDS)


def test_health_extension():
    h = scoring.health()
    assert set(h["layers"]) == set(LAYER_IDS)
    assert set(h["layers"].values()) <= {"real", "synthetic", "unknown"}


@pytest.mark.parametrize("profile", ["hospital", "warehouse", "office", "solar_farm"])
def test_extra_profiles_score(profile):
    cells = scoring.score(profile)
    assert any(c["score"] is not None for c in cells)


def test_list_regions():
    (region,) = scoring.list_regions()
    w, s, e, n = region["bbox"]
    assert region["id"] == "london" and w < -0.1 < e and s < 51.5 < n and region["cells"] > 1000


def test_list_pois_real_or_seeded_only():
    pois = scoring.list_pois(["ixp", "data_centre", "water"])
    assert pois and all(p["source"] in {"osm", "seeded"} for p in pois)
    assert all(set(p) == {"id", "kind", "name", "lat", "lon", "source"} for p in pois)
    docklands = scoring.list_pois(["ixp"], (-0.05, 51.49, 0.03, 51.52))
    assert docklands and all(-0.05 <= p["lon"] <= 0.03 for p in docklands)
    with pytest.raises(KeyError):
        scoring.list_pois(["volcano"])
