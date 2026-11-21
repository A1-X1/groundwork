def test_pois_all_and_filtered(client) -> None:
    allp = client.get("/pois").json()
    assert {p["kind"] for p in allp} >= {"substation", "ixp", "station"}
    assert all(p["source"] for p in allp)
    power = client.get("/pois", params={"kinds": "substation"}).json()
    assert power and all(p["kind"] == "substation" for p in power)
    box = client.get("/pois", params={"bbox": "-0.2,51.45,0.0,51.55"}).json()
    assert 0 < len(box) < len(allp)


def test_pois_bad_kind_is_422(client) -> None:
    r = client.get("/pois", params={"kinds": "volcano"})
    assert r.status_code == 422


def test_pois_new_kinds_and_fields(client) -> None:
    """Every published kind is accepted; region/detail pass through; responses are capped."""
    from backend.api import pois

    r = client.get("/pois", params={"kinds": "power_plant,airport,port"})
    assert r.status_code == 200
    body = client.get("/pois", params={"bbox": "-125,24,-66,50"}).json()
    assert len(body) <= pois.MAX_POIS
    for p in body[:50]:
        assert "region" in p and "detail" in p
