"""Tests for the in-app Jellyfin playback wiring.

Covers:
- ``/api/jellyfin/stream/{item_id}`` proxies direct-play bytes, forwards the
  client ``Range`` header upstream, and passes through a ``206`` + headers.
- ``watch.<jellyfin>.item_id`` reaches the resource API (the frontend reads
  ``s.watch.jellyfin.item_id`` to build the in-app Play button).

All mocked at the network/config boundary — no real LAN, no API keys.
"""
from types import SimpleNamespace
from unittest.mock import patch
import json

from fastapi.testclient import TestClient
import api.main

from domain.enums import MediaStatus, MediaType
from domain.status import Capabilities, MediaSnapshot

client = TestClient(api.main.app)


class _FakeHeaders:
    def __init__(self, d):
        self._d = d

    def get(self, name, default=None):
        return self._d.get(name, default)


class _FakeStreamResponse:
    """Mimic urllib's HTTPResponse for the stream proxy: seeded bytes + status."""

    def __init__(self, body=b"0123456789", status=206, headers=None):
        self._body = body
        self._pos = 0
        self.status = status
        self.headers = _FakeHeaders(headers or {"Content-Type": "video/mp4"})

    def read(self, n=-1):
        if self._pos >= len(self._body):
            return b""
        chunk = self._body[self._pos:self._pos + (n if n and n > 0 else len(self._body))]
        self._pos += len(chunk)
        return chunk

    def close(self):
        pass


def _cfg(**over):
    defaults = {
        "JELLYFIN_URL": "http://jellyfin:8096",
        "JELLYFIN_API_KEY": "sekret",
        "JELLYFIN_BROWSER_URL": "",
    }
    defaults.update(over)
    return SimpleNamespace(**defaults)


def _patch_config(monkeypatch, **over):
    # The stream route does `from config.settings import get_config` at module
    # load, so we must patch the route's own binding, not the source module.
    fake = _cfg(**over)
    import api.routes.jellyfin_stream as route_mod
    monkeypatch.setattr(route_mod, "get_config", lambda: fake)
    return fake


# ------------------------------------------------------------- stream proxy
def test_stream_returns_206_and_forwards_range(monkeypatch):
    """A Range request is passed upstream and the 206 + headers come back."""
    _patch_config(monkeypatch)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["range"] = req.get_header("Range")
        return _FakeStreamResponse(
            body=b"0123456789", status=206,
            headers={"Content-Type": "video/mp4", "Accept-Ranges": "bytes",
                     "Content-Range": "bytes 0-9/1882377499"})

    with patch("api.routes.jellyfin_stream.urllib.request.urlopen", fake_urlopen):
        r = client.get("/api/jellyfin/stream/abc123", headers={"Range": "bytes=0-9"})

    assert r.status_code == 206
    assert r.headers["Content-Range"] == "bytes 0-9/1882377499"
    assert r.headers["Accept-Ranges"] == "bytes"
    assert r.headers["Content-Type"] == "video/mp4"
    assert r.content == b"0123456789"
    # Upstream request carried the api key + the forwarded Range.
    assert "api_key=sekret" in captured["url"]
    assert "Static=true" in captured["url"]
    assert captured["range"] == "bytes=0-9"


def test_stream_returns_200_for_full_request(monkeypatch):
    """Without a Range header the upstream's 200 body streams through."""
    _patch_config(monkeypatch)

    def fake_urlopen(req, timeout=None):
        return _FakeStreamResponse(body=b"FULLBODY", status=200,
                                   headers={"Content-Type": "video/mp4"})

    with patch("api.routes.jellyfin_stream.urllib.request.urlopen", fake_urlopen):
        r = client.get("/api/jellyfin/stream/abc123")

    assert r.status_code == 200
    assert r.content == b"FULLBODY"


def test_stream_503_when_not_configured(monkeypatch):
    """No JELLYFIN_URL/API_KEY -> 503 before any network call."""
    _patch_config(monkeypatch, JELLYFIN_URL="", JELLYFIN_API_KEY="")
    with patch("api.routes.jellyfin_stream.urllib.request.urlopen") as m:
        r = client.get("/api/jellyfin/stream/abc123")
    m.assert_not_called()
    assert r.status_code == 503


# ------------------------------------------------- item_id -> resource API
def test_resource_watch_carries_jellyfin_item_id(monkeypatch):
    """watch.jellyfin.item_id is present in the §18 resource (frontend reads it)."""
    _patch_config(monkeypatch)
    snap = MediaSnapshot(
        media_id="movie:tmdb:603", media_type=MediaType.MOVIE,
        title="500 Days of Summer", year=2009, status=MediaStatus.AVAILABLE,
        capabilities=Capabilities.from_status(MediaStatus.AVAILABLE),
        watch_links={"jellyfin": {"available": True,
                                  "url": "http://jellyfin/web/index.html#/details?id=abc",
                                  "error": None, "item_id": "53756c83d38f47afbb1fd721dd089711"}},
        service="jellyfin",
    )
    with patch("api.routes.media.Reconciler") as m:
        m.return_value.get_snapshot.return_value = snap
        r = client.get("/api/media/movie:tmdb:603")

    assert r.status_code == 200
    body = r.json()
    assert body["watch"]["jellyfin"]["item_id"] == "53756c83d38f47afbb1fd721dd089711"
    assert body["watch"]["jellyfin"]["available"] is True


def test_resource_watch_carries_playback_facts(monkeypatch):
    """watch.jellyfin carries played/playback_position/runtime for progress UI."""
    _patch_config(monkeypatch)
    snap = MediaSnapshot(
        media_id="movie:tmdb:603", media_type=MediaType.MOVIE,
        title="The Matrix", year=1999, status=MediaStatus.AVAILABLE,
        capabilities=Capabilities.from_status(MediaStatus.AVAILABLE),
        watch_links={"jellyfin": {
            "available": True, "url": "http://jellyfin/web/index.html#/details?id=abc",
            "error": None, "item_id": "abc",
            "played": False, "playback_position": 2718, "runtime": 9000,
        }},
        service="jellyfin",
    )
    with patch("api.routes.media.Reconciler") as m:
        m.return_value.get_snapshot.return_value = snap
        r = client.get("/api/media/movie:tmdb:603")

    assert r.status_code == 200
    jf = r.json()["watch"]["jellyfin"]
    assert jf["played"] is False
    assert jf["playback_position"] == 2718
    assert jf["runtime"] == 9000


def test_progress_forwards_to_jellyfin_sessions(monkeypatch):
    """POST /api/jellyfin/progress maps events to the right Sessions endpoint."""
    _patch_config(monkeypatch)
    calls = {}

    def fake_urlopen(req, timeout=None):
        calls["url"] = req.full_url
        calls["data"] = json.loads(req.data)
        return _FakeStreamResponse(status=204, headers={})

    with patch("api.routes.jellyfin_stream.urllib.request.urlopen", fake_urlopen):
        r = client.post("/api/jellyfin/progress", json={
            "item_id": "m1", "position_ticks": 1200000000,
            "is_paused": False, "event": "timeupdate",
        })

    assert r.status_code == 204
    assert "/Sessions/Playing/Progress" in calls["url"]
    assert "api_key=sekret" in calls["url"]
    assert calls["data"]["ItemId"] == "m1"
    assert calls["data"]["PositionTicks"] == 1200000000
    assert calls["data"]["EventName"] == "timeupdate"


def test_progress_uses_playing_for_start_event(monkeypatch):
    """event=start hits /Sessions/Playing (starts the session with a position)."""
    _patch_config(monkeypatch)
    calls = {}

    def fake_urlopen(req, timeout=None):
        calls["url"] = req.full_url
        calls["data"] = json.loads(req.data)
        return _FakeStreamResponse(status=204, headers={})

    with patch("api.routes.jellyfin_stream.urllib.request.urlopen", fake_urlopen):
        r = client.post("/api/jellyfin/progress", json={
            "item_id": "m1", "position_ticks": 0, "is_paused": False, "event": "start",
        })

    assert r.status_code == 204
    assert "/Sessions/Playing" in calls["url"]
    assert "/Sessions/Playing/Progress" not in calls["url"]


def test_library_items_route_returns_all(monkeypatch):
    """GET /api/library/items proxies all_items() from the provider."""
    _patch_config(monkeypatch)
    fake_prov = SimpleNamespace(
        name="jellyfin",
        all_items=lambda: [{"title": "A", "item_id": "a1", "type": "movie",
                            "played": False, "playback_position": 0, "runtime": 6000}])
    fake_svc = SimpleNamespace(providers=[fake_prov])
    with patch("api.routes.library.build_library_service", return_value=fake_svc):
        r = client.get("/api/library/items")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "jellyfin"
    assert body["items"][0]["item_id"] == "a1"


def test_library_continue_watching_route(monkeypatch):
    """GET /api/library/continue-watching proxies the provider's resume list."""
    _patch_config(monkeypatch)
    fake_prov = SimpleNamespace(
        name="jellyfin",
        continue_watching=lambda limit=12: [{"title": "Half", "item_id": "m1", "type": "movie",
                                             "played": False, "playback_position": 3000, "runtime": 6000}])
    fake_svc = SimpleNamespace(providers=[fake_prov])
    with patch("api.routes.library.build_library_service", return_value=fake_svc):
        r = client.get("/api/library/continue-watching")
    assert r.status_code == 200
    assert r.json()["items"][0]["title"] == "Half"


def test_series_episodes_route(monkeypatch):
    """GET /api/library/series/{id}/episodes proxies the provider's episodes()."""
    _patch_config(monkeypatch)
    fake_prov = SimpleNamespace(
        name="jellyfin",
        episodes=lambda series_id: [{"id": "e1", "name": "Pilot", "season": 1, "episode": 1,
                                     "played": False, "playback_position": 2000, "runtime": 4000}])
    fake_svc = SimpleNamespace(providers=[fake_prov])
    with patch("api.routes.library.build_library_service", return_value=fake_svc):
        r = client.get("/api/library/series/s1/episodes")
    assert r.status_code == 200
    assert r.json()["episodes"][0]["name"] == "Pilot"
    assert r.json()["episodes"][0]["playback_position"] == 2000


def test_jobs_library_scan_endpoint(monkeypatch):
    """POST /api/jobs/library_scan/run triggers the library-scan job."""
    from jobs.library_scan import LibraryScanJob
    from jobs.base import JobResult

    def fake_run(self):
        return JobResult(name="library_scan", status="success",
                         items_processed=1, counts={"jellyfin": True, "scanned": 1})

    monkeypatch.setattr(LibraryScanJob, "run", fake_run)
    r = client.post("/api/jobs/library_scan/run")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["counts"]["scanned"] == 1


def test_library_scan_get_route(monkeypatch):
    """GET /api/library/scan lets a browser address bar trigger the scan."""
    from jobs.library_scan import LibraryScanJob
    from jobs.base import JobResult

    def fake_run(self):
        return JobResult(name="library_scan", status="success",
                         items_processed=1, counts={"jellyfin": True, "scanned": 1})

    monkeypatch.setattr(LibraryScanJob, "run", fake_run)
    r = client.get("/api/library/scan")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["counts"]["scanned"] == 1