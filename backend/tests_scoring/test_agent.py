"""Planning agent: tool validation, 3D specs, the training job and the tool loop (no network)."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from backend import layers
from backend.agent import models3d, runner, tools
from backend.layers import _generic


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point every agent write at a temp dir and use the committed sample grid."""
    from backend.scoring import data as _data

    gen = tmp_path / "generated"
    gen.mkdir()
    monkeypatch.setattr(_generic, "GENERATED_DIR", gen)
    monkeypatch.setattr(models3d, "MODELS_DIR", tmp_path / "models")
    prof = tmp_path / "profiles"
    prof.mkdir()
    for p in tools.PROFILES_DIR.glob("*.yaml"):
        (prof / p.name).write_text(p.read_text())
    monkeypatch.setattr(tools, "PROFILES_DIR", prof)
    import backend.scoring.profiles as profiles_mod

    monkeypatch.setattr(profiles_mod, "PROFILES_DIR", prof)
    monkeypatch.setattr(profiles_mod.load_profiles, "__defaults__", (prof,))
    monkeypatch.setattr(_data, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setenv("GROUNDWORK_DATA_DIR", str(_data.SAMPLE_DIR))
    monkeypatch.setenv("GROUNDWORK_OFFLINE", "1")
    import backend.scoring as scoring

    scoring.reload()
    yield tmp_path
    layers.refresh()
    scoring.reload()


def test_add_layer_validates_and_registers(sandbox):
    bad = tools.call("add_layer", {"id": "dist_x", "label": "X dist", "unit": "m", "kind": "proximity",
                                   "description": "d", "template": "osm_proximity",
                                   "params": {"selectors": ["nwr[power=plant]"]}})
    assert "error" in bad and "selector" in bad["error"]
    ok = tools.call("add_layer", {"id": "dist_power_plant", "label": "Distance to power plant", "unit": "m",
                                  "kind": "proximity", "description": "Nearest mapped power plant.",
                                  "template": "osm_proximity", "params": {"selectors": ['nwr["power"="plant"]']}})
    assert ok["layer"] == "dist_power_plant"
    assert "dist_power_plant" in layers.LAYER_IDS


def test_add_layer_does_not_overwrite_human_layers(sandbox):
    (_generic.GENERATED_DIR / "seismic_x.yaml").write_text(
        "id: seismic_x\nlabel: Seismic\nunit: n\nkind: aggregate\ndescription: d\n"
        "template: usgs_earthquakes\nparams: {min_magnitude: 4}\nadded_by: human\n")
    r = tools.call("add_layer", {"id": "seismic_x", "label": "Seismic", "unit": "n", "kind": "aggregate",
                                 "description": "d", "template": "usgs_earthquakes", "params": {"min_magnitude": 3}})
    assert "already exists" in r["error"]


def test_add_layer_refuses_builtin_ids(sandbox):
    r = tools.call("add_layer", {"id": "slope", "label": "Slope", "unit": "%", "kind": "raster",
                                 "description": "d", "template": "usgs_earthquakes", "params": {}})
    assert "built-in" in r["error"]


def test_create_profile_validates_layers_and_protects_builtins(sandbox):
    assert "built-in" in tools.call("create_profile", {"id": "house", "label": "H", "description": "d",
                                                       "layers": {"slope": {"weight": 1, "better": "lower"}}})["error"]
    assert "unknown layer" in tools.call("create_profile", {
        "id": "nuke", "label": "N", "description": "d",
        "layers": {"not_built": {"weight": 1, "better": "lower"}}})["error"]
    ok = tools.call("create_profile", {
        "id": "nuclear_power_plant", "label": "Nuclear power plant", "description": "Test.",
        "layers": {"population_density": {"weight": 3, "better": "lower"},
                   "dist_water_body": {"weight": 2, "better": "lower"},
                   "seismic_activity": {"weight": 1, "better": "lower"}},
        "masks": ["flood_zone_3", "protected_land"]})
    assert ok["profile"] == "nuclear_power_plant"
    assert abs(sum(lw["weight"] for lw in ok["weights"]) - 1) < 1e-6
    preview = tools.call("preview_scores", {"profile_id": "nuclear_power_plant", "top_n": 3})
    assert len(preview["top"]) == 3 and preview["top"][0]["score"] >= preview["top"][-1]["score"]


def _nuclear_spec() -> dict:
    return {"id": "nuclear_power_plant", "label": "Nuclear power plant", "footprint_m": [500, 400], "parts": [
        models3d.cooling_tower(-150, 100), models3d.cooling_tower(-150, -100),
        {"shape": "cylinder", "position": [50, 0, 0], "radius": 40, "height": 45},
        {"shape": "dome", "position": [50, 45, 0], "radius": 40, "color": "white"},
        {"shape": "box", "position": [170, 0, 0], "size": [100, 25, 30], "color": "steel"},
    ]}


def test_3d_model_spec_saved_and_budgeted(sandbox):
    r = tools.call("design_3d_model", {"spec": _nuclear_spec()})
    assert r["triangles"] <= models3d.MAX_TRIANGLES
    assert models3d.load("nuclear_power_plant")["parts"][0]["shape"] == "hyperboloid"
    too_many = dict(_nuclear_spec(), parts=[{"shape": "dome", "radius": 5}] * 40)
    assert "triangles" in tools.call("design_3d_model", {"spec": too_many})["error"]
    outside = dict(_nuclear_spec(), parts=[{"shape": "box", "position": [900, 0, 0], "size": [1, 1, 1]}])
    assert "footprint" in tools.call("design_3d_model", {"spec": outside})["error"]


def test_train_model_runs_azure_job_script_locally(sandbox):
    from backend.scoring.ml import lightgbm_available

    if not lightgbm_available():
        pytest.skip("lightgbm unavailable")
    r = tools.call("train_model", {"profile_id": "data_centre", "backend": "local"})
    assert r["trained"] and r["backend"] == "local"
    meta = json.loads((sandbox / "processed" / "jobs" / "data_centre" / "data" / "meta.json").read_text())
    from backend.scoring import data as _data
    from backend.scoring import ml
    from backend.scoring.profiles import load_profiles

    grid = _data.load(_data.LONDON_SAMPLE)
    loaded = ml.load_saved(grid, load_profiles(set(grid.layer_ids))["data_centre"], grid.directory / "models")
    assert loaded is not None and loaded.features == meta["features"]


def test_train_model_offers_choice_when_azure_not_connected(sandbox, monkeypatch):
    for k in ("AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "AZUREML_WORKSPACE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(tools.azure_ml, "_api_setting", lambda: {})
    for backend in ("azure", "auto"):
        r = tools.call("train_model", {"profile_id": "data_centre", "backend": backend})
        assert r["action_required"] == "choose_training" and r["options"] == ["connect_azure", "use_aggregator"]


def test_layer_stats_and_profile_notes(sandbox):
    st = tools.call("layer_stats", {"layer_ids": ["crime_rate", "slope"], "region": "london"})
    assert st["layers"]["crime_rate"]["p10"] <= st["layers"]["crime_rate"]["median"] <= st["layers"]["crime_rate"]["p90"]
    ok = tools.call("create_profile", {
        "id": "cafe", "label": "Café", "description": "Test.",
        "layers": {"population_density": {"weight": 2, "better": "higher"}, "crime_rate": {"weight": 1, "better": "lower"}},
        "notes": {"crime_rate": "Higher crime gives a worse score."}})
    assert ok["profile"] == "cafe"
    import backend.scoring as scoring

    notes = scoring.profile_notes("cafe")
    assert notes["crime_rate"] == "Higher crime gives a worse score."
    assert "better score" in notes["population_density"]  # default from direction
    bad = tools.call("create_profile", {"id": "cafe2", "label": "C", "description": "d",
                                        "layers": {"slope": {"weight": 1, "better": "lower"}},
                                        "notes": {"crime_rate": "not in profile"}})
    assert "notes for layers not in the profile" in bad["error"]


def test_aggregator_agent_has_no_training_tools():
    names = {s["function"]["name"] for s in tools.schemas_for("aggregator")}
    assert "train_model" not in names and "azure_status" not in names
    assert {"layer_stats", "create_profile", "design_3d_model", "build_layers"} <= names


def test_runner_routes_to_aggregator_and_blocks_other_tools():
    class Client:
        def __init__(self):
            self.n, self.chat = 0, SimpleNamespace(complete=self.complete)

        def complete(self, **kw):
            self.n += 1
            if self.n == 1:
                assert kw["messages"][0]["content"].startswith("You are **Groundwork Data Aggregator**")
                assert "train_model" not in {t["function"]["name"] for t in kw["tools"]}
                call = SimpleNamespace(id="c1", function=SimpleNamespace(name="train_model", arguments="{}"))
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[call]))])
            assert "not available" in kw["messages"][-1]["content"]
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))])

    out = runner.run("build a café", client=Client(), context={"agent": "aggregator"})
    assert out["agent"] == "aggregator" and out["content"] == "ok"


def test_ui_command_whitelist():
    q = tools.call("ui_command", {"commands": [{"command": "PAN_CITY", "name": "London"},
                                               {"command": "SET_PROFILE", "id": "house"}]})
    assert [c["seq"] for c in q["ui"]] == [0, 1] and q["ui"][0]["command"] == "PAN_CITY"
    assert "error" in tools.call("ui_command", {"commands": [{"command": "RM_RF"}]})


def test_schemas_match_tools():
    assert {s["function"]["name"] for s in tools.SCHEMAS} == set(tools.TOOLS)


class _FakeClient:
    """Scripted Mistral client: one tool call, then a final answer."""

    def __init__(self):
        self.calls = 0
        self.chat = SimpleNamespace(complete=self._complete)

    def _complete(self, **kw):
        self.calls += 1
        assert kw["tools"] and kw["messages"][0]["role"] == "system"
        if self.calls == 1:
            call = SimpleNamespace(id="c1", function=SimpleNamespace(
                name="ui_command", arguments=json.dumps({"commands": [{"command": "PAN_CITY", "name": "London"}]})))
            msg = SimpleNamespace(content="", tool_calls=[call])
        else:
            assert kw["messages"][-1]["role"] == "tool"
            msg = SimpleNamespace(content="Showing London.", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def test_runner_executes_tool_calls_and_streams_events():
    events = []
    out = runner.run("show me London", events.append, client=_FakeClient())
    assert out["content"] == "Showing London." and out["ui"] == [{"command": "PAN_CITY", "name": "London", "seq": 0}]
    assert [e["type"] for e in events] == ["tool_call", "tool_result", "ui", "answer"]
    assert all(e.get("message") for e in events)
    # progress for the UI: elapsed time, phase n of N and a remaining-time estimate on every event
    assert all({"elapsed_s", "eta_s", "phase_index", "phase_total", "phase_label"} <= set(e) for e in events)
    assert events[0]["detail"].startswith("Map:")
    assert "messages" not in out
    json.dumps(out)  # the API sends the return value as JSON


def test_runner_accepts_ui_context():
    client = _FakeClient()
    seen = []
    orig = client.chat.complete
    client.chat = SimpleNamespace(complete=lambda **kw: (seen.append(kw["messages"]), orig(**kw))[1])
    runner.run("where am I", client=client, context={"profile": "house", "view": "london"})
    assert "Current UI context" in seen[0][1]["content"]


def test_context_hides_raw_coordinates():
    ctx = runner._context_for_model({"screen": "map", "place": "London", "center": [-0.12, 51.5], "zoom": 10,
                                     "bbox": [1, 2, 3, 4], "profile": "house"})
    assert ctx == {"screen": "map", "place": "London", "profile": "house", "view": "city"}


@pytest.mark.skipif(not os.environ.get("GROUNDWORK_LIVE_MISTRAL"), reason="set GROUNDWORK_LIVE_MISTRAL=1 to hit the API")
def test_live_mistral_navigation():
    out = runner.run("Take me to London and show the best data centre sites")
    assert any(c["command"] in ("PAN_CITY", "SET_PROFILE", "SHOW_TOP_SITES") for c in out["ui"])


def test_text_drops_reasoning_chunks():
    chunks = [SimpleNamespace(type="thinking", thinking=[SimpleNamespace(text="plan…")]),
              SimpleNamespace(type="text", text="Final answer.")]
    assert runner._text(chunks) == "Final answer."
    assert runner._text([{"type": "thinking", "thinking": [{"text": "only thoughts"}]}]) == "only thoughts"


def test_generated_profile_with_unbuilt_layer_is_skipped(tmp_path):
    from backend.scoring.profiles import ProfileError, load_profiles

    (tmp_path / "ok.yaml").write_text("id: ok\nlabel: OK\ndescription: d\nlayers:\n  slope: {weight: 1, better: lower}\n")
    (tmp_path / "gen.yaml").write_text(tools.GENERATED_HEADER + "id: gen\nlabel: G\ndescription: d\n"
                                       "layers:\n  not_built: {weight: 1, better: lower}\n")
    assert set(load_profiles({"slope"}, tmp_path)) == {"ok"}
    (tmp_path / "bad.yaml").write_text("id: bad\nlabel: B\ndescription: d\nlayers:\n  nope: {weight: 1, better: lower}\n")
    with pytest.raises(ProfileError):
        load_profiles({"slope"}, tmp_path)


def test_scoring_survives_lightgbm_oserror(monkeypatch):
    """macOS without libomp: importing lightgbm raises OSError; scoring must fall back to 1.0."""
    import builtins

    from backend.scoring import data as _data
    from backend.scoring import ml
    from backend.scoring.profiles import load_profiles

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "lightgbm" or name.startswith("lightgbm."):
            raise OSError("dlopen(lib_lightgbm.dylib): Library not loaded: libomp.dylib")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert ml.lightgbm_available() is False
    grid = _data.load(_data.LONDON_SAMPLE)
    assert ml.get_model(grid, load_profiles(set(grid.layer_ids))["data_centre"]) is None


def test_runner_routes_routine_steps_to_fast_model():
    seen = []

    class Client:
        def __init__(self):
            self.chat = SimpleNamespace(complete=self.complete)

        def complete(self, **kw):
            seen.append(kw["model"])
            n = len(seen)
            if n == 1:   # plan: a bad call → error
                call = SimpleNamespace(id="a", function=SimpleNamespace(name="ui_command", arguments='{"commands":[{"command":"NOPE"}]}'))
            elif n == 2:  # after an error: big model again
                call = SimpleNamespace(id="b", function=SimpleNamespace(name="ui_command", arguments='{"commands":[{"command":"HELP"}]}'))
            else:
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=None))])
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[call]))])

    out = runner.run("help", client=Client(), model="big", fast_model="fast")
    assert seen == ["big", "big", "fast"]
    assert out["models"] == {"big": 2, "fast": 1}


def test_build_layers_refuses_whole_countries(sandbox):
    assert set(tools.city_regions()) >= {"london", "uk_urban", "usa_urban"}
    assert "uk" not in tools.city_regions() and "usa" not in tools.city_regions()
    r = tools.call("build_layers", {"layer_ids": ["slope"], "region": "usa"})
    assert "too big" in r["error"]


def test_find_address_validates_and_ui_accepts_pan_address():
    assert "error" in tools.call("find_address", {})
    q = tools.call("ui_command", {"commands": [{"command": "PAN_ADDRESS", "address": "x", "lat": 51.5, "lon": -0.1}]})
    assert q["ui"][0]["command"] == "PAN_ADDRESS"
    ctx = runner._context_for_model({"place": "London", "selection": {"lat": 51.5, "lon": -0.12, "h3": "abc"}})
    assert ctx["selection"] == {"lat": 51.5, "lon": -0.12, "h3": "abc"}
