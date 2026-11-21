from __future__ import annotations

import numpy as np
import pytest

from backend.scoring.profiles import Profile


def test_weights_renormalise_on_load(tiny_scorer):
    p = tiny_scorer.profile("t")
    assert p.layers["a"].weight == pytest.approx(0.75)
    assert p.layers["b"].weight == pytest.approx(0.25)
    assert sum(lw["weight"] for lw in p.public()["layers"]) == pytest.approx(1.0)


def test_overrides_renormalise(tiny_scorer):
    w = tiny_scorer.resolve_weights(tiny_scorer.profile("t"), {"b": 0.75})
    assert w == pytest.approx({"a": 0.5, "b": 0.5})


def test_direction_inversion(tiny_scorer):
    r = tiny_scorer.compute("t", {"b": 0})
    a = tiny_scorer.data.frame["a"].to_numpy()
    # only layer a, better=lower → sustainability = 1 - a
    np.testing.assert_allclose(r.sustainability, 1 - a)
    assert r.rank[0] == 1  # a == 0 is best


def test_masks_null_out(tiny_scorer):
    cells = tiny_scorer.cells(tiny_scorer.compute("t"), None)
    masked = [c for c in cells if c["masked"]]
    assert len(masked) == 1 and masked[0]["score"] is None
    assert all(c["score"] is not None for c in cells if not c["masked"])
    assert tiny_scorer.compute("t").rank[-1] == 0


def test_breakdown_sums_to_deviation_from_mean(tiny_scorer):
    r = tiny_scorer.compute("t")
    np.testing.assert_allclose(r.contributions.sum(axis=1), r.sustainability - r.sustainability.mean(), atol=1e-12)
    np.testing.assert_allclose(r.contributions.mean(axis=0), 0, atol=1e-12)


def test_breakdown_sign_is_direction_corrected(tiny_scorer):
    r = tiny_scorer.compute("t")
    j = r.layer_ids.index("a")
    assert r.contributions[0, j] > 0   # lowest a, better=lower → helps
    assert r.contributions[5, j] < 0   # highest a → hurts


def test_scores_in_unit_interval(tiny_scorer):
    s = tiny_scorer.compute("t").score
    s = s[~np.isnan(s)]
    assert ((s >= 0) & (s <= 1)).all()


def test_unknown_profile_raises_keyerror(tiny_scorer):
    with pytest.raises(KeyError):
        tiny_scorer.compute("nope")


def test_unknown_layer_in_weights_raises_valueerror(tiny_scorer):
    with pytest.raises(ValueError):
        tiny_scorer.compute("t", {"zzz": 1})


@pytest.mark.parametrize("weights", [{"a": -1}, {"a": float("nan")}, {"a": "x"}, {"a": 0, "b": 0}, {"m": 0.5}])
def test_bad_weights_raise_valueerror(tiny_scorer, weights):
    with pytest.raises(ValueError):
        tiny_scorer.compute("t", weights)


def test_zero_weight_for_non_profile_layer_is_ignored(tiny_scorer):
    assert tiny_scorer.resolve_weights(tiny_scorer.profile("t"), {"m": 0}) == pytest.approx({"a": 0.75, "b": 0.25})


@pytest.mark.parametrize("bbox", [(1, 0, 0, 1), (0, 0, 0, 0), ("a", 0, 1, 1), (0, 0, 1)])
def test_bad_bbox_raises_valueerror(tiny_scorer, bbox):
    with pytest.raises(ValueError):
        tiny_scorer.bbox_mask(bbox)


def test_bbox_filters_cells(tiny_scorer):
    f = tiny_scorer.data.frame
    lat, lon = f["lat"].iloc[0], f["lon"].iloc[0]
    cells = tiny_scorer.cells(tiny_scorer.compute("t"), (lon - 1e-4, lat - 1e-4, lon + 1e-4, lat + 1e-4))
    assert [c["h3"] for c in cells] == [f.index[0]]


def test_profile_rejects_all_zero_weights():
    with pytest.raises(ValueError):
        Profile.model_validate({"id": "z", "label": "Z", "description": "",
                                "layers": {"a": {"weight": 0, "better": "lower"}}})


def test_profile_rejects_extra_keys():
    with pytest.raises(ValueError):
        Profile.model_validate({"id": "z", "label": "Z", "description": "", "colour": "red",
                                "layers": {"a": {"weight": 1, "better": "lower"}}})
