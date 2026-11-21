from __future__ import annotations

import pandas as pd
import pytest

from backend import layers
from backend.pipeline.normalise import percentile_rank
from backend.pipeline.run import run


def test_percentile_rank_bounds_and_ties():
    r = percentile_rank(pd.Series([5.0, 1.0, 10.0, 7.0]))
    assert r.min() == 0 and r.max() == 1
    r = percentile_rank(pd.Series([5.0, 1.0, 1.0, 10.0]))
    assert r.iloc[1] == r.iloc[2]
    assert (percentile_rank(pd.Series([3.0, 3.0])) == 0.5).all()


def test_every_layer_module_has_contract():
    for lid in layers.LAYER_IDS:
        mod = layers.load(lid)
        assert mod.META.id == lid
        assert callable(mod.fetch) and callable(mod.to_hex) and callable(mod.synthetic)
        for dep in mod.META.depends_on:
            assert layers.LAYER_IDS.index(dep) < layers.LAYER_IDS.index(lid), f"{lid} before {dep}"


@pytest.mark.slow
def test_offline_build_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setenv("GROUNDWORK_RAW_DIR", str(tmp_path / "raw"))
    import backend.layers._common as common

    monkeypatch.setattr(common, "RAW_DIR", tmp_path / "raw")
    a = run(out=tmp_path / "a", offline=True)
    b = run(out=tmp_path / "b", offline=True)
    pd.testing.assert_frame_equal(a, b)
    assert set(layers.LAYER_IDS) <= set(a.columns)
    for lid in layers.LAYER_IDS:
        assert a[lid].dtype == "uint8", lid  # normalised 0–1 stored as 0–255
        assert a[f"raw_{lid}"].notna().all(), lid


def test_overpass_tiles_are_fetched_in_parallel(tmp_path, monkeypatch):
    import time

    from backend.layers import _common, _osm

    monkeypatch.setattr(_common, "RAW_DIR", tmp_path)
    monkeypatch.delenv("GROUNDWORK_OFFLINE", raising=False)  # another test's offline build sets it
    monkeypatch.delenv("GROUNDWORK_REFRESH", raising=False)
    monkeypatch.setattr(_osm, "_down_reason", None)
    monkeypatch.setattr(_common, "REGION", {"id": "london", "kind": "city", "country": "GBR",
                                            "bbox": (-0.56, 51.26, 0.37, 51.72)})
    calls = []

    def fake_run(ql, timeout):
        calls.append(ql)
        time.sleep(0.2)
        return [{"type": "node", "id": hash(ql), "lat": 51.5, "lon": -0.1}]

    monkeypatch.setattr(_osm, "_run", fake_run)
    t = time.time()
    els = _osm.query("test_parallel", ['node["amenity"="cafe"]'], geometry=False)
    took = time.time() - t
    assert len(calls) == 9 and len(els) == 9
    assert took < 9 * 0.2 * 0.6  # 3 at a time ≈ 0.6 s, not 1.8 s sequentially
