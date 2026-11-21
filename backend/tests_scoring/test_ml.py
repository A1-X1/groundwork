from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("lightgbm")

from backend.scoring import data as _data  # noqa: E402
from backend.scoring import ml  # noqa: E402
from backend.scoring.profiles import load_profiles  # noqa: E402


@pytest.fixture(scope="module")
def sample():
    grid = _data.load(_data.LONDON_SAMPLE)
    return grid, load_profiles(set(grid.layer_ids))


def test_presence_model_trains_without_leaky_features(sample):
    grid, profiles = sample
    model = ml.train(grid, profiles["house"])
    assert "land_use_residential" not in model.features
    assert model.metrics["n_positives"] >= 5
    assert model.metrics["auc_spatial_cv"] is None or 0 <= model.metrics["auc_spatial_cv"] <= 1


def test_feasibility_bounded_by_floor(sample):
    grid, profiles = sample
    model = ml.train(grid, profiles["data_centre"])
    _, feas = ml.feasibility(model, grid, floor=0.5)
    assert feas.min() == pytest.approx(0.5) and feas.max() == pytest.approx(1.0)


def test_shap_values_sum_to_logit(sample):
    grid, profiles = sample
    model = ml.train(grid, profiles["data_centre"])
    rows = grid.frame.iloc[:5]
    contrib = model.contributions(rows)
    prob = model.predict(rows)
    np.testing.assert_allclose(1 / (1 + np.exp(-contrib.sum(axis=1))), prob, rtol=1e-6)


def test_saved_model_roundtrip_and_staleness(sample, tmp_path):
    grid, profiles = sample
    model = ml.train(grid, profiles["house"])
    ml.save(model, tmp_path)
    loaded = ml.load_saved(grid, profiles["house"], tmp_path)
    assert loaded is not None
    np.testing.assert_allclose(loaded.predict(grid.frame), model.predict(grid.frame))
    grid.frame.iloc[0, 0] = 1 - grid.frame.iloc[0, 0]  # change the grid → stale
    assert ml.load_saved(grid, profiles["house"], tmp_path) is None
