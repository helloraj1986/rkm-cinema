"""Tests for the Plex-preplay detail wiring (docs/PLEX_UI_PLAN.md Phase 1).

Covers:
- ``GET /api/jellyfin/detail?id=`` surfaces the service's normalised detail
  payload; 404 when there is no detail; 503 when Jellyfin isn't configured.
- ``GET /api/jellyfin/person?id=`` proxies a person headshot through the same
  Primary-image proxy (kind captured, token stays server-side).

All mocked at the config/service boundary — no real LAN, no API keys.
"""
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
import api.main

client = TestClient(api.main.app)

_DETAIL = {
    "type": "movie", "item_id": "m1", "name": "Prisoners", "year": 2013,
    "runtime": 15300, "overview": "Every parent's worst nightmare.",
    "genres": ["Crime", "Drama"], "community_rating": 8.1,
    "official_rating": "AU-MA 15+", "studios": ["Warner Bros."],
    "people": {"actors": [{"id": "p1", "name": "Hugh Jackman",
                           "role": "Keller Dover", "has_image": True}],
               "directors": [], "writers": []},
    "has_backdrop": True, "primary_aspect": 0.6667,
    "play": {"played": False, "resume_ticks": 0, "resume": 0, "play_count": 0},
}


def _cfg(**over):
    vals = {"JELLYFIN_URL": "http://jellyfin:8096", "JELLYFIN_API_KEY": "sekret"}
    vals.update(over)
    return SimpleNamespace(**vals)


def test_jellyfin_detail_route_returns_payload(monkeypatch):
    """GET /api/jellyfin/detail surfaces the service's normalised detail."""
    import api.routes.jellyfin_detail as dmod
    monkeypatch.setattr(dmod, "get_config", lambda: _cfg())
    fake_svc = SimpleNamespace(item_detail=lambda iid: _DETAIL)
    with patch("api.routes.jellyfin_detail.build_library_service", return_value=fake_svc):
        r = client.get("/api/jellyfin/detail?id=m1")
    assert r.status_code == 200
    body = r.json()
    assert body["item_id"] == "m1"
    assert body["type"] == "movie"
    assert body["genres"] == ["Crime", "Drama"]
    assert body["people"]["actors"][0]["id"] == "p1"


def test_jellyfin_detail_route_404_when_no_detail(monkeypatch):
    """A soft miss (provider down / unknown item) is a 404, never a 5xx."""
    import api.routes.jellyfin_detail as dmod
    monkeypatch.setattr(dmod, "get_config", lambda: _cfg())
    fake_svc = SimpleNamespace(item_detail=lambda iid: None)
    with patch("api.routes.jellyfin_detail.build_library_service", return_value=fake_svc):
        r = client.get("/api/jellyfin/detail?id=nope")
    assert r.status_code == 404


def test_jellyfin_detail_route_404_when_missing_id(monkeypatch):
    import api.routes.jellyfin_detail as dmod
    monkeypatch.setattr(dmod, "get_config", lambda: _cfg())
    with patch("api.routes.jellyfin_detail.build_library_service"):
        r = client.get("/api/jellyfin/detail")
    assert r.status_code == 404


def test_jellyfin_detail_route_503_when_not_configured(monkeypatch):
    """No Jellyfin credentials → explicit 503 (mirrors jellyfin_tracks)."""
    import api.routes.jellyfin_detail as dmod
    monkeypatch.setattr(dmod, "get_config",
                        lambda: _cfg(JELLYFIN_URL="", JELLYFIN_API_KEY=""))
    with patch("api.routes.jellyfin_detail.build_library_service"):
        r = client.get("/api/jellyfin/detail?id=m1")
    assert r.status_code == 503


def test_jellyfin_person_route_proxies_primary_headshot(monkeypatch):
    """GET /api/jellyfin/person proxies Primary at a headshot-friendly width."""
    import api.routes.jellyfin_poster as pmod
    monkeypatch.setattr(pmod, "get_config", lambda: _cfg())
    seen = {}

    def fake_get_poster(iid, width, kind):
        seen.update(item_id=iid, width=width, kind=kind)
        return {"content": b"\xff\xd8\xff\xe0jpeg", "content_type": "image/jpeg"}

    fake_svc = SimpleNamespace(get_poster=fake_get_poster)
    with patch("api.routes.jellyfin_poster.build_library_service", return_value=fake_svc):
        r = client.get("/api/jellyfin/person?id=p1&width=300")
    assert r.status_code == 200
    assert seen["kind"] == "Primary"
    assert seen["item_id"] == "p1"
    assert seen["width"] == 300
    assert r.headers["Content-Type"] == "image/jpeg"
