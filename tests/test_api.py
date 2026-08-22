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
def test_download_movie_success(mock_svc, client):
    """POST /api/download with an explicit movie routes to Radarr."""
    from domain.enums import DownloadResultState
    from domain.enums import MediaType
    from domain.models import DownloadResult
    mock_svc.return_value.download.return_value = DownloadResult(
        success=True, state=DownloadResultState.REQUESTED,
        message="added", media_type=MediaType.MOVIE)

    r = client.post("/api/download", json={
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
def test_download_missing_ids_rejected(mock_svc, client):
    """No imdb/tmdb -> unavailable, mapped to 502."""
    from domain.enums import DownloadResultState, MediaType
    from domain.models import DownloadResult
    mock_svc.return_value.download.return_value = DownloadResult(
        success=False, state=DownloadResultState.UNAVAILABLE,
        message="imdbId or tmdbId required", media_type=MediaType.MOVIE)
    r = client.post("/api/download", json={"type": "movie"})
    assert r.status_code == 502
    assert "imdbId or tmdbId required" in r.json()["detail"]


@patch("api.routes.download.DownloadService")
def test_download_ambiguous_maps_to_404(mock_svc, client):
    """Ambiguous result -> HTTP 404 with the pick-one message."""
    from domain.enums import DownloadResultState, MediaType
    from domain.models import DownloadResult
    mock_svc.return_value.download.return_value = DownloadResult(
        success=False, state=DownloadResultState.AMBIGUOUS,
        message="Multiple Radarr matches — pick one: X (2023, tmdb:1)",
        media_type=MediaType.MOVIE)

    r = client.post("/api/download", json={"imdbId": "tt2197033", "title": "X", "year": 2023})
    assert r.status_code == 404
    assert "Multiple Radarr matches" in r.json()["detail"]


@patch("api.routes.plex_thumb.PlexLibraryProvider")
def test_plex_thumb_requires_path(mock_plex, client):
    """Missing path -> 404, no service call."""
    r = client.get("/api/plex/thumb")
    assert r.status_code == 404
    mock_plex.assert_not_called()


@patch("api.routes.health.build_acquisition_service")
@patch("api.routes.health.PlexLibraryProvider")
def test_health_shape(mock_plex, mock_acq_factory, client, monkeypatch):
    """Health returns the expected services map."""
    from config import settings as s
    class FakeCfg:
        RADARR_API_KEY = "k"; SONARR_API_KEY = "k"; PLEX_URL = "http://p"; PLEX_TOKEN = "t"
        def has_tmdb(self): return True
        def has_jellyfin(self): return False
    monkeypatch.setattr(s, "get_config", lambda: FakeCfg())
    mock_plex.return_value.health.return_value = True
    # The acquisition facade reports per-provider health (spec §14).
    mock_acq_factory.return_value.health.return_value = {"radarr": True, "sonarr": True}

    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["services"]["radarr"] is True
    assert body["services"]["plex"] is True
