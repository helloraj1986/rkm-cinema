"""API-level tests for critical endpoints (spec: typed + predictable errors).

The routes construct their services via DI-friendly constructors, so we mock at
the service boundary with ``unittest.mock.patch`` on the service classes the
``api`` package resolves. These tests assert response shape and error mapping
without touching any real LAN.
"""
import pytest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import api.main


@pytest.fixture
def client():
    return TestClient(api.main.app)


@patch("api.routes.download.DownloadService")
def test_download_movie_success(mock_svc, client, signed_in):
    """POST /api/download with an explicit movie routes to Radarr.

    Signed in as an ADMINISTRATOR: this route is admin-gated (Phase E) and strict even while the
    app is unenforced — that refusal is pinned in tests/test_route_protection.py.
    """
    from domain.enums import DownloadResultState
    from domain.enums import MediaType
    from domain.models import DownloadResult
    mock_svc.return_value.download.return_value = DownloadResult(
        success=True, state=DownloadResultState.REQUESTED,
        message="added", media_type=MediaType.MOVIE)

    r = signed_in(client).post("/api/download", json={
        "imdbId": "tt0133093", "type": "movie", "qualityProfileId": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["service"] == "radarr"
    assert body["state"] == "requested"
    # verify the type resolution passed requested_type through
    args, kwargs = mock_svc.return_value.download.call_args
    assert kwargs["requested_type"] == "movie"


@patch("api.routes.download.DownloadService")
def test_download_missing_ids_rejected(mock_svc, client, signed_in):
    """No imdb/tmdb -> unavailable, mapped to 502."""
    from domain.enums import DownloadResultState, MediaType
    from domain.models import DownloadResult
    mock_svc.return_value.download.return_value = DownloadResult(
        success=False, state=DownloadResultState.UNAVAILABLE,
        message="imdbId or tmdbId required", media_type=MediaType.MOVIE)
    r = signed_in(client).post("/api/download", json={"type": "movie"})
    assert r.status_code == 502
    assert "imdbId or tmdbId required" in r.json()["detail"]


@patch("api.routes.download.DownloadService")
def test_download_ambiguous_maps_to_404(mock_svc, client, signed_in):
    """Ambiguous result -> HTTP 404 with the pick-one message."""
    from domain.enums import DownloadResultState, MediaType
    from domain.models import DownloadResult
    mock_svc.return_value.download.return_value = DownloadResult(
        success=False, state=DownloadResultState.AMBIGUOUS,
        message="Multiple Radarr matches — pick one: X (2023, tmdb:1)",
        media_type=MediaType.MOVIE)

    r = signed_in(client).post("/api/download", json={
        "imdbId": "tt2197033", "title": "X", "year": 2023})
    assert r.status_code == 404
    assert "Multiple Radarr matches" in r.json()["detail"]


@patch("api.routes.health.HealthChecker")
def test_health_shape(mock_checker, client, monkeypatch):
    """Health returns the expected services map."""
    from config import settings as s
    class FakeCfg:
        RADARR_API_KEY = "k"; SONARR_API_KEY = "k"
        def has_tmdb(self): return True
        def has_jellyfin(self): return True
    monkeypatch.setattr(s, "get_config", lambda: FakeCfg())
    # The checker reports per-service health (spec §28); one stub result keeps
    # the BC services bool map + structured detail + degraded flag.
    report = Mock()
    report.services = {"radarr": True, "sonarr": True,
                       "qbit": True, "tmdb": True, "jellyfin": True}
    report.degraded = False
    report.serviceDetail = {"radarr": {"ok": True}, "jellyfin": {"ok": True}}
    mock_checker.return_value.check.return_value = report

    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["services"]["radarr"] is True
    assert body["services"]["jellyfin"] is True
    assert "plex" not in body["services"] and "emby" not in body["services"]
    assert body["degraded"] is False
    assert body["serviceDetail"]["radarr"]["ok"] is True
