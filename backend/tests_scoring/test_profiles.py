from __future__ import annotations

import pytest

from backend.layers import LAYER_IDS
from backend.scoring.profiles import PROFILES_DIR, ProfileError, load_profile, load_profiles


def test_shipped_profiles_are_valid():
    profiles = load_profiles(set(LAYER_IDS))
    assert {"data_centre", "house", "school", "mine"} <= set(profiles)
    assert profiles["data_centre"].model is not None and profiles["house"].model is not None


def test_unknown_layer_fails_loudly(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "id: bad\nlabel: Bad\ndescription: x\nlayers:\n  not_a_layer: {weight: 1, better: lower}\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="not_a_layer"):
        load_profile(tmp_path / "bad.yaml", set(LAYER_IDS))


def test_unknown_mask_fails_loudly(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "id: bad\nlabel: Bad\ndescription: x\nlayers:\n  slope: {weight: 1, better: lower}\nmasks: [moon]\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="moon"):
        load_profile(tmp_path / "bad.yaml", set(LAYER_IDS))


def test_id_must_match_filename(tmp_path):
    (tmp_path / "a.yaml").write_text("id: b\nlabel: B\ndescription: x\nlayers:\n  slope: {weight: 1, better: lower}\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="file name"):
        load_profile(tmp_path / "a.yaml", set(LAYER_IDS))


def test_new_use_case_is_yaml_only(tmp_path):
    (tmp_path / "hospital.yaml").write_text(
        "id: hospital\nlabel: Hospital\ndescription: Access for many people.\n"
        "layers:\n  population_density: {weight: 2, better: higher}\n  dist_major_road: {weight: 1, better: lower}\n"
        "masks: [flood_zone_3]\n", encoding="utf-8")
    p = load_profile(tmp_path / "hospital.yaml", set(LAYER_IDS))
    assert p.public()["layers"][0] == {"id": "population_density", "weight": pytest.approx(2 / 3), "better": "higher"}
    assert PROFILES_DIR.exists()
