"""Endpoint behaviour, errors and caching."""

from backend.api.main import score_cache

CITY = {"lat": 51.5155, "lon": -0.0922}


def test_health(client) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["scoring_source"] in {"real", "stub"}
    assert body["real_layers"] + body["synthetic_layers"] <= len(body["layers"])


def test_profiles(client) -> None:
    profiles = client.get("/profiles").json()
    ids = {p["id"] for p in profiles}
    assert {"data_centre", "house", "school", "mine"} <= ids
    one = client.get("/profiles/house").json()
    assert one["id"] == "house"
    assert all(layer["better"] in {"higher", "lower"} for layer in one["layers"])


def test_unknown_profile_is_404_with_error_body(client) -> None:
    for r in (client.get("/profiles/nope"), client.get("/score/nope"),
              client.get("/score/nope/point", params=CITY)):
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"


def test_layers_and_layer_values(client) -> None:
    layers = client.get("/layers").json()
    assert layers and {"id", "unit", "kind", "min", "max"} <= set(layers[0])
    lid = layers[0]["id"]
    body = client.get(f"/layers/{lid}").json()
    assert body["layer"] == lid
    assert all(0 <= c["value"] <= 1 for c in body["cells"])
    assert client.get("/layers/nope").status_code == 404


def test_bbox_filters(client) -> None:
    full = client.get("/score/house").json()["cells"]
    part = client.get("/score/house", params={"bbox": "-0.2,51.45,0.0,51.55"}).json()["cells"]
    assert 0 < len(part) < len(full)


def test_bad_bbox_is_422(client) -> None:
    for bbox in ["1,2,3", "a,b,c,d", "0,51,-1,52"]:
        r = client.get("/score/house", params={"bbox": bbox})
        assert r.status_code == 422, bbox
        assert r.json()["error"]["code"] == "invalid_value"


def test_masked_cells_have_null_score(client) -> None:
    cells = client.get("/score/data_centre").json()["cells"]
    masked = [c for c in cells if c["masked"]]
    assert masked, "stub has flood/protected masks"
    assert all(c["score"] is None for c in masked)
    assert all(c["score"] is not None for c in cells if not c["masked"])


def test_point_has_rank_and_raw(client) -> None:
    body = client.get("/score/house/point", params={"lat": 51.56, "lon": -0.05}).json()
    assert len(body["h3"]) == 15
    assert body["raw"]
    if not body["masked"]:
        assert 1 <= body["rank"] <= body["ranked_cells"]
        assert 0 <= body["percentile"] <= 1


def test_point_outside_region_is_404(client) -> None:
    assert client.get("/score/house/point", params={"lat": 48.85, "lon": 2.35}).status_code == 404


def test_point_validates_lat(client) -> None:
    r = client.get("/score/house/point", params={"lat": 123, "lon": 0})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_custom_weights_change_scores(client) -> None:
    default = client.get("/score/house").json()["cells"]
    custom = client.post(
        "/score/custom", json={"profile": "house", "weights": {"median_house_price": 10}}
    ).json()["cells"]
    assert [c["score"] for c in default] != [c["score"] for c in custom]


def test_custom_bad_weights_are_422(client) -> None:
    for weights in [{"crime_rate": -1}, {"not_a_layer": 1}]:
        r = client.post("/score/custom", json={"profile": "house", "weights": weights})
        assert r.status_code == 422, weights


def test_custom_unknown_profile_is_404(client) -> None:
    assert client.post("/score/custom", json={"profile": "nope"}).status_code == 404


def test_score_is_cached(client) -> None:
    client.get("/score/mine")
    misses = score_cache.misses
    client.get("/score/mine")
    assert score_cache.misses == misses
    assert score_cache.hits >= 1


def test_compare(client) -> None:
    r = client.get("/compare", params={"profiles": "data_centre,house,mine", **CITY})
    assert r.status_code == 200
    body = r.json()
    assert [e["profile"] for e in body["results"]] == ["data_centre", "house", "mine"]
    assert client.get("/compare", params={"profiles": "house,nope", **CITY}).status_code == 404
    assert client.get("/compare", params={"profiles": ",", **CITY}).status_code == 422


def test_gzip(client) -> None:
    r = client.get("/score/house", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"


def test_cors(client) -> None:
    r = client.get("/profiles", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_openapi_documents_every_endpoint(client) -> None:
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    for p in ["/health", "/profiles", "/profiles/{profile_id}", "/layers", "/layers/{layer_id}",
              "/score/{profile_id}", "/score/{profile_id}/point", "/score/custom", "/compare"]:
        assert p in paths
        for op in paths[p].values():
            assert op.get("summary") and op.get("description") and op.get("tags")
    assert client.get("/redoc").status_code == 200
