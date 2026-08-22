"""Tests for the Phase 10 resource API (api/routes/media|watchlist|reconcile|jobs)
and the acquisition quality-profiles materialization.

Mocks at the service boundary — no real LAN, no API keys.
"""
import pytest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import api.main

from domain.enums import MediaStatus, MediaType, RequestMediaState
from domain.status import Capabilities, MediaSnapshot


@pytest.fixture
def client():
    return TestClient(api.main.app)


# ------------------------------------------------------------------ helpers
def _snap(media_id="movie:tmdb:603", status=MediaStatus.AVAILABLE, title="The Matrix",
          year=1999, mt=MediaType.MOVIE, watch=None, service="radarr"):
    return MediaSnapshot(
        media_id=media_id, media_type=mt, title=title, year=year,
        status=status,
        capabilities=Capabilities.from_status(status),
        watch_links=watch or {},
        service=service,
    )


def _config_patch(monkeypatch):
    from config import settings as s
    class FakeCfg:
        RADARR_API_KEY = "k"
        SONARR_API_KEY = ""
        PLEX_URL = ""
        PLEX_TOKEN = ""
        EMBY_URL = ""
        EMBY_API_KEY = ""
        def has_tmdb(self):
            return True
        def has_jellyfin(self):
            return False
    monkeypatch.setattr(s, "get_config", lambda: FakeCfg())
    return FakeCfg


# ------------------------------------------------------------- GET /api/media
@patch("api.routes.media.Reconciler")
def test_get_media_returns_spec18_resource(mock_rec, client):
    """GET /api/media/{id} renders one complete §18 object."""
    snap = _snap(
        watch={"plex": {"available": True, "url": "https://plex/x", "error": None}})
    mock_rec.return_value.get_snapshot.return_value = snap

    r = client.get("/api/media/movie:tmdb:603")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "movie:tmdb:603"
    assert body["title"] == "The Matrix"
    assert body["year"] == 1999
    assert body["type"] == "movie"
    assert body["status"] == "available"
    assert body["capabilities"] == {"can_download": False, "can_watch": True}
    assert body["watch"]["plex"]["available"] is True
    assert body["watch"]["plex"]["url"] == "https://plex/x"
    assert body["acquisition"]["provider"] == "radarr"
    assert body["acquisition"]["status"] == "available"


@patch("api.routes.media.Reconciler")
def test_get_media_not_added_capabilities(mock_rec, client):
    """NOT_ADDED resource advertises can_download (spec §18)."""
    mock_rec.return_value.get_snapshot.return_value = _snap(
        status=MediaStatus.NOT_ADDED, service="")
    r = client.get("/api/media/movie:tmdb:999")
    body = r.json()
    assert body["status"] == "not_added"
    assert body["capabilities"] == {"can_download": True, "can_watch": False}
    assert body["acquisition"] is None


# ------------------------------------------------- POST /api/media/{id}/request
@patch("api.routes.media.request_media")
def test_request_success(mock_req, client):
    mock_req.return_value = Mock(
        success=True, state=RequestMediaState.REQUESTED, message="added",
        media_id="movie:tmdb:603", service="radarr", candidates=[])
    r = client.post("/api/media/movie:tmdb:603/request")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["state"] == "requested"
    assert body["service"] == "radarr"
    assert body["mediaId"] == "movie:tmdb:603"


@patch("api.routes.media.request_media")
def test_request_available_is_ok(mock_req, client):
    """Library-present -> AVAILABLE is a success, not an error (idempotency)."""
    mock_req.return_value = Mock(
        success=True, state=RequestMediaState.AVAILABLE, message="Already in the library",
        media_id="movie:tmdb:603", service="", candidates=[])
    r = client.post("/api/media/movie:tmdb:603/request")
    assert r.status_code == 200
    assert r.json()["state"] == "available"


@patch("api.routes.media.request_media")
def test_request_not_configured_503(mock_req, client):
    mock_req.return_value = Mock(
        success=False, state=RequestMediaState.NOT_CONFIGURED, message="not configured",
        media_id="", service="", candidates=[])
    r = client.post("/api/media/movie:tmdb:603/request")
    assert r.status_code == 503


@patch("api.routes.media.request_media")
def test_request_provider_unavailable_502(mock_req, client):
    mock_req.return_value = Mock(
        success=False, state=RequestMediaState.PROVIDER_UNAVAILABLE,
        message="radarr down", media_id="", service="radarr", candidates=[])
    r = client.post("/api/media/movie:tmdb:603/request")
    assert r.status_code == 502


@patch("api.routes.media.request_media")
def test_request_ambiguous_409(mock_req, client):
    mock_req.return_value = Mock(
        success=False, state=RequestMediaState.AMBIGUOUS, message="pick one",
        media_id="", service="radarr", candidates=[{"title": "X", "year": 2023}])
    r = client.post("/api/media/movie:tmdb:603/request")
    assert r.status_code == 409
    assert r.json()["detail"]["candidates"] == [{"title": "X", "year": 2023}]


# ------------------------------------------------------- GET /api/watchlist
@patch("api.routes.watchlist.Reconciler")
def test_watchlist_renders_entries(mock_rec, client):
    result = Mock(indexer_issue=None)
    result.snapshots = {"tt0133093": _snap(), "tt1": _snap(media_id="tv:tmdb:2",
                       title="Ozark", year=2017, mt=MediaType.TV, status=MediaStatus.REQUESTED)}
    mock_rec.return_value.compute.return_value = result
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    body = r.json()
    assert len(body["entries"]) == 2
    assert body["indexerIssue"] is None
    tv = body["entries"][1]
    assert tv["type"] == "tv"
    assert tv["status"] == "requested"


# ------------------------------------------------------ POST /api/reconcile
@patch("api.routes.reconcile.Reconciler")
def test_reconcile_ok(mock_rec, client):
    result = Mock(indexer_issue=None)
    result.snapshots = {"tt0133093": _snap()}
    mock_rec.return_value.compute.return_value = result
    r = client.post("/api/reconcile")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["entries"]) == 1
    assert body["entries"][0]["status"] == "available"


# -------------------------------------------------------------- GET /api/jobs
@patch("api.routes.jobs.build_repository")
def test_jobs_returns_runs(mock_build, client):
    repo = Mock()
    repo.list_job_runs.return_value = [
        {"job_name": "daily_watchlist", "started_at": "2026-08-22 00:00:00",
         "completed_at": "2026-08-22 00:01:00", "status": "success",
         "items_processed": 17, "error": None},
    ]
    mock_build.return_value = repo
    r = client.get("/api/jobs")
    assert r.status_code == 200
    body = r.json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["jobName"] == "daily_watchlist"
    assert body["jobs"][0]["itemsProcessed"] == 17


@patch("api.routes.jobs.build_repository")
def test_jobs_empty_on_failure(mock_build, client):
    mock_build.side_effect = RuntimeError("db down")
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert r.json()["jobs"] == []


# ------------------------------------------------------------- quality profiles
@patch("api.routes.quality.build_acquisition_service")
def test_quality_uses_acquisition_facade(mock_acq, client):
    mock_acq.return_value.quality_profiles.return_value = {
        "radarr": [{"id": 1, "name": "1080p", "items": []}],
        "sonarr": [],
    }
    r = client.get("/api/quality")
    assert r.status_code == 200
    body = r.json()
    assert body["radarr"][0]["name"] == "1080p"
    assert body["sonarr"] == []


def test_acquisition_service_quality_profiles_grouped():
    """quality_profiles aggregates per-provider, safe against a failing backend."""
    from services.acquisition.service import AcquisitionService

    class _Radarr:
        name = "radarr"

        def quality_profiles(self):
            return [{"id": 1, "name": "1080p", "items": []}]

    class _Sonarr:
        name = "sonarr"

        def quality_profiles(self):
            raise RuntimeError("down")

    svc = AcquisitionService(providers=[_Radarr(), _Sonarr()])
    out = svc.quality_profiles()
    assert out["radarr"] == [{"id": 1, "name": "1080p", "items": []}]
    assert out["sonarr"] == []


def test_build_acquisition_service_from_radarr_inject():
    """The facade factory wires an injected low-level Radarr as its provider."""
    from services.acquisition.service import build_acquisition_service
    radarr = Mock()
    svc = build_acquisition_service(config=_FakeCfg(), radarr=radarr)
    providers = svc.providers
    assert [p.name for p in providers] == ["radarr"]
    assert providers[0]._svc is radarr


class _FakeCfg:
    RADARR_API_KEY = ""
    SONARR_API_KEY = ""


def _seed_watchlist_entry():
    from services.watchlist import WatchlistService, WatchlistEntry
    path = "/tmp/test_res_api_seed.json"
    import os
    if os.path.exists(path):
        os.remove(path)
    wl = WatchlistService(path)
    entry = WatchlistEntry(
        title="The Matrix", year=1999, category="Action", lang="English",
        rt=88, imdb=8.7, isSeries=False, imdbId="tt0133093", tmdbId=603,
        cert="R", snippet="", cast=[], director="", poster="", trailerId="",
        trailerTitle="", added="2026-01-01", state="pending")
    data = wl.load()
    data.pending.append(entry)
    wl.save(data)
    return path, wl


def test_reconciler_populates_title_year_mediatype():
    """The reconciler fills title/year/media_type so the resource API can
    render the full §18 object (not mocks)."""
    from services.reconciliation import Reconciler
    from domain.enums import MediaStatus, MediaType
    from services.library import LibraryMatch, LibraryService

    class _FakeLib:
        name = "plex"

        def health(self):
            return True

        def find(self, identity, *, title="", year=None):
            return LibraryMatch("plex", "320819", "The Matrix", 1999)

        def recently_added(self, limit=8):
            return []

        def build_watch_link(self, match):
            return {"plex_url": "https://plex/x#!/library/metadata/320819"}

    path, wl = _seed_watchlist_entry()
    radarr = Mock()
    radarr.get_movies.return_value = []
    radarr.get_queue.return_value = []
    radarr.get_indexer_health.return_value = None
    qbit = Mock()
    qbit.match.return_value = None
    rec = Reconciler(
        watchlist=wl,
        library=LibraryService(providers=[_FakeLib()]),
        radarr=radarr, sonarr=None, qbit=qbit,
        config=Mock(PLEX_URL="", PLEX_TOKEN="", EMBY_URL="", EMBY_API_KEY="",
                    RADARR_API_KEY="k", SONARR_API_KEY="", RADARR_URL="",
                    SONARR_URL="", QBITTORRENT_URL=""))
    snap = rec.get_snapshot("movie:tmdb:603")
    assert snap.media_type is MediaType.MOVIE
    assert snap.title == "The Matrix"
    assert snap.year == 1999
    assert snap.status is MediaStatus.AVAILABLE
    import os
    os.remove(path)