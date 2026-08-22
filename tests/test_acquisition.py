"""Tests for the Phase 8 acquisition abstraction (services/acquisition/).

Verifies the single-service movie→Radarr / series→Sonarr routing (spec §14) —
no `if movie: radarr else: sonarr` in callers. Fakes at the service boundary.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from domain.enums import MediaType
from domain.identity import MediaIdentity
from services.acquisition import (
    AcquisitionService,
    RadarrAcquisitionProvider,
    SonarrAcquisitionProvider,
)
from services.download import DownloadService
from services.radarr import RadarrMovie
from services.sonarr import SonarrSeries


def movie_ident(tmdb=603, imdb="tt0133093"):
    return MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=tmdb, imdb_id=imdb)


def series_ident(tvdb=81189, imdb="tt0903747"):
    return MediaIdentity(media_type=MediaType.TV, tvdb_id=tvdb, imdb_id=imdb)


class _FakeRadarr:
    """Fake RadarrService exposing the low-level API the provider wraps."""

    def __init__(self, movies=None, has_file_for=None, queue=None, indexer=None):
        self.movies = movies or []
        self._has_file = has_file_for or {}
        self.queue = queue or []
        self.indexer = indexer

    def get_movies(self, use_cache=True):
        return self.movies

    def get_queue(self, use_cache=True):
        return self.queue

    def get_indexer_health(self):
        return self.indexer

    def find_movie_by_tmdb(self, tmdb):
        return next((m for m in self.movies if m.tmdbId == tmdb), None)

    def lookup_movie(self, imdb):
        return next((m for m in self.movies if m.imdbId == imdb), None)

    def lookup_movie_by_tmdb(self, tmdb):
        return next((m for m in self.movies if m.tmdbId == tmdb), None)

    def search_movies(self, title, year=None):
        return [m for m in self.movies if m.title == title]

    def add_movie(self, imdb, qp=None, title="", year=None, tmdb_id=None):
        from services.radarr import AddResult
        m = self.lookup_movie(imdb) if imdb else self.lookup_movie_by_tmdb(tmdb_id)
        if m:
            return AddResult(True, m, f"{m.title} is already in Radarr", "requested")
        return AddResult(False, None, "No Radarr match for imdb:" + imdb, "unavailable")


def make_radarr_movie(tmdb=603, imdb="tt0133093", has_file=False, title="The Matrix", year=1999):
    return RadarrMovie(id=tmdb, tmdbId=tmdb, title=title, year=year,
                       hasFile=has_file, monitored=True, qualityProfileId=1,
                       imdbId=imdb)


class TestAcquisitionServiceRouting:
    """The single acquisition router (spec §14: no if movie/series in callers)."""

    def test_provider_for_routes_by_media_type(self):
        svc = AcquisitionService(providers=[
            RadarrAcquisitionProvider(service=_FakeRadarr()),
            SonarrAcquisitionProvider(service=Mock()),
        ])
        assert svc.provider_for(MediaType.MOVIE).name == "radarr"
        assert svc.provider_for(MediaType.TV).name == "sonarr"
        # A movie identity is routed to Radarr, a series identity to Sonarr.
        assert svc.provider_for(movie_ident().media_type).name == "radarr"
        assert svc.provider_for(series_ident().media_type).name == "sonarr"

    def test_find_routes_movie_to_radarr(self):
        f = _FakeRadarr(movies=[make_radarr_movie()])
        svc = AcquisitionService(providers=[RadarrAcquisitionProvider(service=f)])
        assert svc.find(movie_ident()).tmdbId == 603

    def test_find_unknown_returns_none(self):
        svc = AcquisitionService(providers=[RadarrAcquisitionProvider(service=_FakeRadarr())])
        assert svc.find(movie_ident(tmdb=999)) is None

    def test_request_routing_with_no_provider(self):
        # No provider for MOVIE -> unavailable, not a raw AttributeError.
        svc = AcquisitionService(providers=[])
        res = svc.request(movie_ident())
        assert res.success is False
        assert res.state == "unavailable"

    def test_get_status_radarr_has_file(self):
        f = _FakeRadarr(movies=[make_radarr_movie(has_file=True)])
        svc = AcquisitionService(providers=[RadarrAcquisitionProvider(service=f)])
        st = svc.get_status(movie_ident())
        assert st.record_exists is True
        assert st.has_file is True
        assert st.record_title == "The Matrix"

    def test_get_status_radarr_queued_download(self):
        class _Q:
            movieId = 603
            status = "downloading"
            size = 100.0
            sizeleft = 40.0
        f = _FakeRadarr(movies=[make_radarr_movie(has_file=False)],
                        queue=[_Q()])
        svc = AcquisitionService(providers=[RadarrAcquisitionProvider(service=f)])
        st = svc.get_status(movie_ident())
        assert st.record_exists is True
        assert st.has_file is False
        assert st.queue_active is True
        assert st.queue_percent == 60

    def test_request_movie_tmdb_only(self):
        """Canonical movie:tmdb:* ids carry no imdb -> Radarr must resolve by
        TMDB (fix: There Will Be Blood 'No Radarr match for imdb')."""
        f = _FakeRadarr(movies=[make_radarr_movie(tmdb=7345, imdb="tt0469494",
                                                 title="There Will Be Blood", year=2007)])
        svc = AcquisitionService(providers=[RadarrAcquisitionProvider(service=f)])
        ident = MediaIdentity(media_type=MediaType.MOVIE, tmdb_id=7345, imdb_id=None)
        res = svc.request(ident)
        assert res.success is True
        assert "No Radarr match" not in res.message
        assert res.item.title == "There Will Be Blood"


class TestSonarrRouting:
    def test_sonarr_find_by_tvdb(self):
        class _Series:
            tvdbId = 81189
            title = "Breaking Bad"
            year = 2008
            statistics = {"episodeFileCount": 62}

        class _FakeSonarr:
            def find_series_by_tvdb(self, tvdb):
                return _Series() if tvdb == 81189 else None
            def get_series(self, use_cache=True):
                return [_Series()]
            def get_queue(self, use_cache=True):
                return []
            def resolve_tvdb_id(self, imdb):
                return 81189 if imdb == "tt0903747" else None
            def health_check(self):
                return True

        svc = AcquisitionService(providers=[SonarrAcquisitionProvider(service=_FakeSonarr())])
        assert svc.find(series_ident()) is not None
        st = svc.get_status(series_ident())
        assert st.record_exists is True
        assert st.has_file is True

    def test_request_series_tvdb_only(self):
        """Canonical tv:tvdb:* ids carry no imdb -> Sonarr must resolve by TVDB."""
        class _FakeSonarr:
            def __init__(self):
                self.add_kwargs = {}
            def lookup_series(self, imdb):
                return None
            def lookup_series_by_tvdb(self, tvdb):
                return SimpleNamespace(tvdbId=tvdb, title="Breaking Bad", year=2008)
            def find_series_by_tvdb(self, tvdb):
                return None
            def add_series(self, imdb, qp=None, title="", year=None, tvdb_id=None):
                self.add_kwargs = {"imdb": imdb, "tvdb_id": tvdb_id}
                return SimpleNamespace(
                    success=True, state="requested",
                    message="Breaking Bad added to Sonarr — downloads starting",
                    series=SimpleNamespace(title="Breaking Bad", tvdbId=tvdb_id))
            def health_check(self):
                return True

        svc = AcquisitionService(providers=[SonarrAcquisitionProvider(service=_FakeSonarr())])
        ident = MediaIdentity(media_type=MediaType.TV, tvdb_id=81189, imdb_id=None)
        res = svc.request(ident)
        assert res.success is True
        assert res.state == "requested"
        assert res.item.title == "Breaking Bad"
        # the provider resolved & passed the tvdb id (not the empty imdb)
        assert res.item.tvdbId == 81189


class TestDownloadServiceThroughAcquisition:
    """DownloadService now routes through AcquisitionService (§14)."""

    def _reco(self, config_radarr=True, config_sonarr=True):
        cfg = Mock(RADARR_API_KEY="r" if config_radarr else "",
                   SONARR_API_KEY="s" if config_sonarr else "",
                   RADARR_URL="http://r", SONARR_URL="http://s")
        return DownloadService(acquisition=Mock(), config=cfg)

    def test_constructor_wraps_legacy_radarr_sonarr(self):
        svc = DownloadService(radarr=Mock(), sonarr=Mock(),
                              config=Mock(RADARR_API_KEY="r", SONARR_API_KEY="s"))
        assert svc._acquisition is not None
        names = [p.name for p in svc._acquisition.providers]
        assert "radarr" in names and "sonarr" in names