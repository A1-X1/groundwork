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
