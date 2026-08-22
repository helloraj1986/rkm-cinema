"""Tests for Phase 15 caching (spec §29).

Covers the reusable ``core.cache.TTLCache`` primitive, the long-TTL TMDB
metadata cache, the Emby scan TTL correction, *arr write-path cache
invalidation (including the URL-keyed ``_http_cache`` that was previously left
stale), and the upward invalidation hooks (provider -> LibraryService /
AcquisitionService -> Reconciler). All tests are LAN-free with fakes.
"""
import time
from unittest.mock import Mock

import pytest

from core.cache import TTLCache


class TestTTLCache:
    def test_set_get_round_trip(self):
        c = TTLCache(default_ttl=60)
        assert c.get("a") is None
        c.set("a", {"x": 1})
        assert c.get("a") == {"x": 1}

    def test_expiry_returns_default(self):
        c = TTLCache(default_ttl=0.05)
        c.set("a", 1)
        assert c.get("a") == 1
        time.sleep(0.08)
        assert c.get("a") is None  # expired -> miss

    def test_per_key_ttl_override(self):
        c = TTLCache(default_ttl=0.05)
        c.set("short", 1, ttl=0.01)
        c.set("long", 2, ttl=60)
        time.sleep(0.03)
        assert c.get("short") is None
        assert c.get("long") == 2

    def test_invalidate_removes_one(self):
        c = TTLCache(default_ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        c.invalidate("a")
        assert c.get("a") is None
        assert c.get("b") == 2

    def test_clear_removes_all(self):
        c = TTLCache(default_ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        c.clear()
        assert len(c) == 0
        assert c.get("a") is None and c.get("b") is None

    def test_len_and_keys(self):
        c = TTLCache(default_ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        assert len(c) == 2
        assert set(c.keys()) == {"a", "b"}


def _tmdb_service(http=None, **cfg_overrides):
    from services.tmdb import TMDBService
    cfg = Mock(TMDB_API_KEY="key", TMDB_CACHE_TTL=cfg_overrides.get("ttl", 21600))
    return TMDBService(config=cfg, http=http)


class TestTMDBMetadataCache:
    def _movie_payload(self):
        return {
            "id": 603, "title": "The Matrix", "release_date": "1999-03-31",
            "vote_average": 8.7, "runtime": 136, "overview": "o",
            "genres": [{"name": "Sci-Fi"}], "poster_path": "/p.jpg",
            "backdrop_path": "/b.jpg", "release_dates": {"results": []},
            "credits": {"cast": [], "crew": []},
        }

    def test_movie_details_cached_across_calls(self):
        raw = self._movie_payload()
        http = Mock()
        http.get.return_value = raw
        svc = _tmdb_service(http=http)
        m1 = svc.get_movie_details(603)
        m2 = svc.get_movie_details(603)
        assert m1 == m2
        # Only one upstream fetch, even though called twice.
        assert http.get.call_count == 1

    def test_clear_cache_re_fetches(self):
        raw = self._movie_payload()
        http = Mock()
        http.get.return_value = raw
        svc = _tmdb_service(http=http)
        svc.get_movie_details(603)
        svc.get_movie_details(603)
        assert http.get.call_count == 1
        svc.clear_cache()
        svc.get_movie_details(603)
        assert http.get.call_count == 2

    def test_show_details_cached(self):
        raw = {
            "id": 100, "name": "Show", "first_air_date": "2020-01-01",
            "vote_average": 8.0, "episode_run_time": [45], "genres": [],
            "created_by": [], "credits": {"cast": [], "crew": []},
            "poster_path": "", "backdrop_path": "", "content_ratings": {"results": []},
        }
        http = Mock()
        http.get.return_value = raw
        svc = _tmdb_service(http=http)
        svc.get_show_details(100)
        svc.get_show_details(100)
        assert http.get.call_count == 1

    def test_movie_and_show_keys_independent(self):
        raw_movie = self._movie_payload()
        raw_show = {
            "id": 100, "name": "Show", "first_air_date": "2020-01-01",
            "vote_average": 8.0, "episode_run_time": [], "genres": [],
            "created_by": [], "credits": {"cast": [], "crew": []},
            "poster_path": "", "backdrop_path": "", "content_ratings": {"results": []},
        }
        http = Mock()
        http.get.side_effect = [raw_movie, raw_show]
        svc = _tmdb_service(http=http)
        svc.get_movie_details(603)
        svc.get_show_details(100)
        svc.get_movie_details(603)  # cached movie
        svc.get_show_details(100)  # cached show
        assert http.get.call_count == 2  # no re-fetch of either

    def test_search_results_cached(self):
        raw = {"results": [self._movie_payload()]}
        http = Mock()
        http.get.return_value = raw
        svc = _tmdb_service(http=http)
        svc.search_movie("The Matrix", 1999)
        svc.search_movie("The Matrix", 1999)
        assert http.get.call_count == 1


class TestEmbyScanTTL:
    def test_scan_ttl_is_spec_60s(self):
        from services.library.emby import EmbyLibraryProvider
        assert EmbyLibraryProvider.EMBY_SCAN_TTL == 60


class TestArrWritePathInvalidation:
    def test_radarr_add_invalidates_http_cache(self):
        from services.radarr import RadarrService, RadarrMovie, QualityProfile, RootFolder, AddResult
        http = Mock()
        http.get.return_value = [{"id": 1, "tmdbId": 1, "title": "Old",
                                  "year": 2000, "hasFile": False,
                                  "monitored": True, "qualityProfileId": 1}]
        svc = RadarrService(config=Mock(
            RADARR_URL="http://r", RADARR_API_KEY="k",
            RADARR_QUALITY_PROFILE_ID=None), http=http)
        svc._http_cache = {"http://r/api/v3/movie:None": (time.time() + 45, [])}
        svc.get_movies(use_cache=True)

        # Drive a successful add without hitting real HTTP: mock the lookups
        # and write so add_movie reaches its own invalidation path.
        svc.lookup_movie = lambda _imdb: None
        svc.lookup_movie_by_tmdb = lambda _t: RadarrMovie(0, 999_999, "New Movie", 2024, False, True, 5)
        svc.search_movies = lambda *a, **k: []
        svc.find_movie_by_tmdb = lambda _t: None
        svc.get_quality_profiles = lambda *a, **k: [QualityProfile(5, "HD", [])]
        svc.get_root_folders = lambda *a, **k: [RootFolder("/movies")]
        svc._post = lambda _e, _b: {"id": 99, "tmdbId": 999_999, "title": "New Movie",
                                      "year": 2024, "hasFile": False,
                                      "monitored": True, "qualityProfileId": 5}

        res = svc.add_movie("tt9999999", 5, title="New Movie", year=2024,
                            tmdb_id=999_999)
        assert res.state == "requested"
        assert svc._movies_cache == []
        assert len(svc._http_cache) == 0  # url-keyed cache cleared

    def test_sonarr_add_invalidates_http_cache(self):
        from services.sonarr import SonarrService, SonarrSeries, QualityProfile, RootFolder, LanguageProfile
        http = Mock()
        http.get.return_value = [{"id": 1, "tvdbId": 1, "title": "Old",
                                  "year": 2000, "monitored": True,
                                  "qualityProfileId": 1, "languageProfileId": 1,
                                  "statistics": {}}]
        svc = SonarrService(config=Mock(
            SONARR_URL="http://s", SONARR_API_KEY="k",
            SONARR_QUALITY_PROFILE_ID=None), http=http)
        svc._http_cache = {"http://s/api/v3/series:None": (time.time() + 45, [])}
        svc.get_series(use_cache=True)

        svc.lookup_series = lambda _imdb: None
        svc.lookup_series_by_tvdb = lambda _t: SonarrSeries(0, 999_999, "New Show", 2024, True, 5, 1, {}, "")
        svc.search_series = lambda *a, **k: []
        svc.find_series_by_tvdb = lambda _t: None
        svc.get_quality_profiles = lambda *a, **k: [QualityProfile(5, "HD", [])]
        svc.get_language_profiles = lambda *a, **k: [LanguageProfile(1, "English")]
        svc.get_root_folders = lambda *a, **k: [RootFolder("/shows")]
        svc._post = lambda _e, _b: {"id": 99, "tvdbId": 999_999, "title": "New Show",
                                      "year": 2024, "monitored": True,
                                      "qualityProfileId": 5, "languageProfileId": 1,
                                      "statistics": {}}

        res = svc.add_series("tt999", 5, title="New Show", year=2024, tvdb_id=999_999)
        assert res.state == "requested"
        assert svc._series_cache == []
        assert len(svc._http_cache) == 0

    def test_clear_cache_drops_every_typed_cache(self):
        from services.sonarr import SonarrService
        http = Mock()
        http.get.return_value = []
        svc = SonarrService(config=Mock(
            SONARR_URL="http://s", SONARR_API_KEY="k",
            SONARR_QUALITY_PROFILE_ID=None), http=http)
        svc._profiles_cache = [{"id": 1}]
        svc._roots_cache = [{"path": "/x"}]
        svc._series_cache = [1]
        svc._queue_cache = [1]
        svc.clear_cache()
        assert svc._profiles_cache == []
        assert svc._roots_cache == []
        assert svc._series_cache == []
        assert svc._queue_cache == []


class _FakeLibProvider:
    """LibraryProvider fake that counts invalidate() calls."""

    def __init__(self, name="plex"):
        self.name = name
        self.invalidate_calls = 0

    def invalidate(self):
        self.invalidate_calls += 1

    # minimal other interface (unused in these tests)
    def health(self): return True
    def find(self, *a, **k): return None
    def recently_added(self, limit=8): return []
    def build_watch_link(self, match): return {}


class _FakeAcqProvider:
    def __init__(self, name="radarr"):
        self.name = name
        self.invalidate_calls = 0

    def invalidate(self):
        self.invalidate_calls += 1


class TestInvalidateHooks:
    def test_library_service_propagates_to_providers(self):
        from services.library import LibraryService
        p1 = _FakeLibProvider("plex")
        p2 = _FakeLibProvider("emby")
        lib = LibraryService(providers=[p1, p2])
        lib.invalidate()
        assert p1.invalidate_calls == 1 and p2.invalidate_calls == 1

    def test_acquisition_service_propagates_to_providers(self):
        from services.acquisition import AcquisitionService
        a = _FakeAcqProvider("radarr")
        s = _FakeAcqProvider("sonarr")
        acq = AcquisitionService(providers=[a, s])
        acq.invalidate()
        assert a.invalidate_calls == 1 and s.invalidate_calls == 1

    def test_reconciler_invalidate_forwards_to_library_and_acquisition(self):
        from services.library import LibraryService
        from services.acquisition import AcquisitionService
        from services.reconciliation import Reconciler

        lp = _FakeLibProvider("plex")
        ap = _FakeAcqProvider("radarr")
        rec = Reconciler(
            watchlist=Mock(), library=LibraryService(providers=[lp]),
            acquisition=AcquisitionService(providers=[ap]),
            config=Mock(PLEX_URL="", PLEX_TOKEN="", EMBY_URL="", EMBY_API_KEY="",
                        RADARR_API_KEY="", SONARR_API_KEY="", QBITTORRENT_URL=""))
        rec.invalidate()
        assert lp.invalidate_calls == 1
        assert ap.invalidate_calls == 1