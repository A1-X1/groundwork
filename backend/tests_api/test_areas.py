"""Areas and structures: CRUD against a temporary SQLite file, plus area scoring."""

DOCKLANDS = {
    "type": "Polygon",
    "coordinates": [[[-0.03, 51.49], [0.02, 51.49], [0.02, 51.52], [-0.03, 51.52]]],
}


def test_area_crud_and_summary(client) -> None:
    r = client.post("/areas", json={"name": "Docklands", "geometry": DOCKLANDS})
    assert r.status_code == 201, r.text
    area = r.json()
    ring = area["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1], "ring is closed by the API"
    assert any(a["id"] == area["id"] for a in client.get("/areas").json())

    s = client.get(
        f"/areas/{area['id']}/summary", params={"profile": "data_centre"}
    ).json()
    assert s["cells"] > 5 and 1 < s["area_km2"] < 50
    assert s["scored_cells"] <= s["cells"]
    if s["best_score"] is not None:
        assert 0 <= s["best_score"] <= 1 and s["best_h3"]

    r = client.patch(f"/areas/{area['id']}", json={"name": "Docklands shortlist"})
    assert r.json()["name"] == "Docklands shortlist"
    assert client.delete(f"/areas/{area['id']}").status_code == 204
    assert client.get(f"/areas/{area['id']}").status_code == 404


def test_area_validation(client) -> None:
    two_points = {"type": "Polygon", "coordinates": [[[0, 51], [1, 51]]]}
    assert (
        client.post("/areas", json={"name": "x", "geometry": two_points}).status_code
        == 422
    )
    huge = {
        "type": "Polygon",
        "coordinates": [[[-10, 40], [20, 40], [20, 60], [-10, 60]]],
    }
    r = client.post("/areas", json={"name": "Europe", "geometry": huge})
    assert r.status_code == 422 and "too large" in r.json()["error"]["message"]
    assert (
        client.post("/areas", json={"name": "", "geometry": DOCKLANDS}).status_code
        == 422
    )


def test_structures_crud(client) -> None:
    area = client.post("/areas", json={"name": "Site", "geometry": DOCKLANDS}).json()
    body = {
        "name": "Training cluster",
        "type": "data_centre",
        "profile": "data_centre",
        "spec": {"gpu": "h100", "gpuCount": 4096, "cooling": "liquid"},
        "area_id": area["id"],
    }
    r = client.post("/structures", json=body)
    assert r.status_code == 201, r.text
    st = r.json()
    assert st["spec"]["gpuCount"] == 4096 and st["area_id"] == area["id"]
    r = client.patch(f"/structures/{st['id']}", json={"name": "Renamed"})
    assert r.json()["name"] == "Renamed"
    # deleting the area unlinks, not deletes, the structure
    client.delete(f"/areas/{area['id']}")
    assert client.get("/structures").json()[0]["area_id"] is None
    assert client.delete(f"/structures/{st['id']}").status_code == 204
    bad = {**body, "profile": "nope", "area_id": None}
    assert client.post("/structures", json=bad).status_code == 404
