"""Street View preview: provider choice, no-imagery and not-configured paths (no network)."""

from __future__ import annotations

from typing import Any

import pytest

from backend.api import streetview


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GOOGLE_MAPS_API_KEY", "GOOGLE_MAPS_BROWSER_KEY", "MAPILLARY_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(streetview.assistant, "_read_dotenv", dict)


class _Resp:
    def __init__(self, data: Any = None, content: bytes = b"") -> None:
        self._data, self.content = data, content

    def json(self) -> Any:
        return self._data

    def raise_for_status(self) -> None:
        return None


def test_not_configured(client) -> None:
    assert client.get("/streetview/config").json()["provider"] is None
    r = client.get("/streetview/preview", params={"lat": 51.5, "lon": -0.12})
    assert r.status_code == 503 and r.json()["error"]["code"] == "not_configured"


def test_google_preview_and_no_imagery(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "server-key-123")
    cfg = client.get("/streetview/config").json()
    assert cfg["provider"] == "google" and cfg["browser_key"] == "server-key-123"

    def fake_get(url: str, params: dict | None = None, timeout: float = 0) -> _Resp:
        if url.endswith("/metadata"):
            assert (
                params and params["radius"] == streetview.RADIUS_M == 1000
            )  # 1 km search
            ok = params and params["location"].startswith("51.5")
            return _Resp(
                {
                    "status": "OK",
                    "pano_id": "P1",
                    "location": {"lat": 51.5, "lng": -0.12},
                }
                if ok
                else {"status": "ZERO_RESULTS"}
            )
        return _Resp(content=b"\xff\xd8jpeg")

    monkeypatch.setattr(streetview.httpx, "get", fake_get)
    r = client.get("/streetview/preview", params={"lat": 51.5, "lon": -0.12})
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert (
        r.headers["x-pano-id"] == "P1"
        and r.headers["x-streetview-provider"] == "google"
    )
    miss = client.get("/streetview/preview", params={"lat": 10.0, "lon": 10.0})
    assert miss.status_code == 404 and miss.json()["error"]["code"] == "no_imagery"


def test_mapillary_fallback(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAPILLARY_TOKEN", "MLY|token-abc")

    def fake_get(url: str, params: dict | None = None, timeout: float = 0) -> _Resp:
        if "graph.mapillary.com" in url:
            assert (
                params and params["limit"] > 1
            )  # several candidates; the closest wins
            far = {
                "id": "7",
                "thumb_1024_url": "https://img/7.jpg",
                "computed_geometry": {"coordinates": [-0.11, 51.505]},
            }
            near = {
                "id": "42",
                "thumb_1024_url": "https://img/42.jpg",
                "computed_geometry": {"coordinates": [-0.1201, 51.5001]},
            }
            return _Resp({"data": [far, near]})
        return _Resp(content=b"\xff\xd8jpeg")

    monkeypatch.setattr(streetview.httpx, "get", fake_get)
    assert client.get("/streetview/config").json()["provider"] == "mapillary"
    r = client.get("/streetview/preview", params={"lat": 51.5, "lon": -0.12})
    assert r.status_code == 200 and r.headers["x-pano-id"] == "42"
