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
        assert set(p) == {"id", "label", "description", "layers", "masks", "has_model", "generated"}
        assert math.isclose(sum(lw["weight"] for lw in p["layers"]), 1.0, abs_tol=1e-5)
        assert all(set(lw) == {"id", "weight", "better"} for lw in p["layers"])
    gen = {p["id"]: p["generated"] for p in profiles}
    assert gen["nuclear_power_plant"] is True and gen["house"] is False


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
    regions = {r["id"]: r for r in scoring.list_regions()}
    assert {"london", "uk"} <= set(regions)
    assert list(regions)[0] == "london"  # finest first
    w, s, e, n = regions["london"]["bbox"]
    assert w < -0.1 < e and s < 51.5 < n and regions["london"]["cells"] > 1000
    assert regions["uk"]["resolution"] == 7 and regions["uk"]["cells"] > 40000
    # markers trace the land: ≤600 coarse cells, none over the open North Sea
    import h3

    uk = regions["uk"]
    assert len(uk["marker_cells"]) > 50
    sea = h3.latlng_to_cell(56.5, 2.5, uk["marker_resolution"])
    assert sea not in uk["marker_cells"]


def test_region_outlines_never_overlap():
    regions = scoring.list_regions()
    assert len({r["marker_resolution"] for r in regions}) == 1  # one shared resolution
    seen: dict[str, str] = {}
    for r in regions:
        for c in r["marker_cells"]:
            assert c not in seen, f"{c} in both {seen.get(c)} and {r['id']}"
            seen[c] = r["id"]
    nested = {r["id"]: r["nested_in"] for r in regions}
    assert nested["london"] == "uk" and nested["uk_urban"] == "uk" and nested["uk"] is None
    assert not next(r for r in regions if r["id"] == "london")["marker_cells"]


def test_unavailable_masks_do_not_mask():
    # Scotland: flood_zone_3 / protected_land have no data (England-only sources) → not masked
    cells = scoring.score("house", bbox=(-3.4, 55.85, -3.0, 56.05))
    assert cells and sum(c["masked"] for c in cells) == 0
    assert all(c["score"] is not None for c in cells)


def test_multi_region_routing():
    import h3

    # Edinburgh is in the UK grid only; central London resolves to the finer London grid
    edinburgh = scoring.score_point("wind_farm", 55.95, -3.19)
    assert edinburgh["region"] == "uk_urban"  # towns and cities get res-8 hexes
    rural = scoring.score_point("wind_farm", 57.3, -4.5)
    assert rural["region"] == "uk" and h3.get_resolution(rural["h3"]) == 7
    assert "crime_rate" in edinburgh["unavailable"] and edinburgh["raw"]["crime_rate"] is None
    assert scoring.score_point("house", 51.5074, -0.1278)["region"] == "london"
    # a bbox over Greater London returns London res-8 cells, not the UK res-7 cells beneath them
    import h3

    cells = scoring.score("house", bbox=(-0.2, 51.45, -0.05, 51.55))
    assert cells and {h3.get_resolution(c["h3"]) for c in cells} == {8}
    # a bbox over Scotland returns UK cells
    scot = scoring.score("wind_farm", bbox=(-4.5, 56.0, -3.5, 56.5))
    assert scot and {h3.get_resolution(c["h3"]) for c in scot} <= {7, 8}


def test_list_pois_real_or_seeded_only():
    pois = scoring.list_pois(["ixp", "data_centre", "water"])
    assert pois and all(p["source"] != "synthetic" for p in pois)
    assert all({"id", "kind", "name", "lat", "lon", "source"} <= set(p) for p in pois)


def test_uk_pois_cover_the_country():
    edinburgh = scoring.list_pois(["station"], (-3.3, 55.9, -3.1, 56.0))
    assert any("Edinburgh" in p["name"] for p in edinburgh)
    plants = scoring.list_pois(["power_plant"], (-6.5, 49.8, 2.0, 59.0))
    assert len(plants) > 1000 and all(p.get("detail") for p in plants[:10])
    docklands = scoring.list_pois(["ixp"], (-0.05, 51.49, 0.03, 51.52))
    assert docklands and all(-0.05 <= p["lon"] <= 0.03 for p in docklands)
    with pytest.raises(KeyError):
        scoring.list_pois(["volcano"])


def test_default_profiles_have_their_data():
    defaults = scoring.default_profiles()
    assert defaults == ["data_centre", "house", "school", "solar_farm", "wind_farm"]
    layer_ids = {m["id"] for m in scoring.list_layers()}
    for pid in defaults:
        prof = next(p for p in scoring.list_profiles() if p["id"] == pid)
        assert {lw["id"] for lw in prof["layers"]} | set(prof["masks"]) <= layer_ids, pid
        assert any(c["score"] is not None for c in scoring.score(pid)), pid


def test_bboxes_never_wrap_the_globe():
    for r in scoring.list_regions():
        w, s_, e, n = r["bbox"]
        assert -180 <= w < e <= 180 and e - w < 180, r["id"]
    usa = next(r for r in scoring.list_regions() if r["id"] == "usa")
    assert usa["bbox"][2] < -60  # east edge is Maine, not Asia


def test_region_outline_is_dissolved_geojson():
    uk = next(r for r in scoring.list_regions() if r["id"] == "uk")
    geo = uk["outline"]
    assert geo["type"] in ("Polygon", "MultiPolygon") and geo["coordinates"]
    from shapely.geometry import Point, shape

    poly = shape(geo)
    assert poly.contains(Point(-1.9, 52.48))      # Birmingham inside
    assert not poly.contains(Point(2.5, 56.5))    # North Sea outside
