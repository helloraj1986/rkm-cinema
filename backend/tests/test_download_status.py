"""Tests for download status detection (uses injectable DI, no real LAN)."""
import os
import pytest
from unittest.mock import Mock

from services import RadarrService, SonarrService, PlexService, WatchlistService
from services.watchlist import WatchlistEntry
from services.media_status import MediaStatusService
from domain.state_machine import StatusFacts, WatchLinks, resolve_status
from domain.enums import MediaStatus


def remove_tmp(path):
    if os.path.exists(path):
        os.remove(path)


class TestDownloadStatus:
    """Test download status computation."""

    def test_radarr_has_file_detection(self):
        """Radarr has_file detection from injected HTTP payload."""
        http = Mock()
        http.get.return_value = [
            {"id": 1, "tmdbId": 603, "title": "The Matrix", "year": 1999,
             "hasFile": True, "monitored": True, "qualityProfileId": 1},
        ]
        radarr = RadarrService(config=Mock(RADARR_URL="http://r:7878", RADARR_API_KEY="k",
                                           RADARR_QUALITY_PROFILE_ID=None), http=http)
        assert radarr.has_file(603) is True
        assert radarr.has_file(999) is False

    def test_sonarr_has_episodes_detection(self):
        """Sonarr has_episodes detection from injected HTTP payload."""
        http = Mock()
        http.get.side_effect = [
            [  # first call: series with 62 episodes
                {"id": 1, "tvdbId": 81189, "title": "Breaking Bad", "year": 2008,
                 "monitored": True, "qualityProfileId": 1, "languageProfileId": 1,
                 "statistics": {"episodeFileCount": 62}},
            ],
            [  # second call: refreshed series with 0 episodes
                {"id": 1, "tvdbId": 81189, "title": "Breaking Bad", "year": 2008,
                 "monitored": True, "qualityProfileId": 1, "languageProfileId": 1,
                 "statistics": {"episodeFileCount": 0}},
            ],
        ]
        sonarr = SonarrService(config=Mock(SONARR_URL="http://s:8989", SONARR_API_KEY="k",
                                           SONARR_QUALITY_PROFILE_ID=None), http=http)
        assert sonarr.has_episodes(81189) is True
        assert sonarr.has_episodes(81189) is False

    # ------------------------------------------------------------------ state machine
    def test_status_available_when_in_plex(self):
        """Plex is source of truth -> available regardless of *arr."""
        f = StatusFacts(in_plex=True, plex_links=WatchLinks(
            plex_available=True, plex_url="http://plex/item",
            emby_available=True, emby_url="http://emby/item"))
        r = resolve_status(f)
        assert r.state is MediaStatus.AVAILABLE
        assert r.plexUrl == "http://plex/item"
        assert r.embyUrl == "http://emby/item"

    def test_status_downloaded_when_radarr_hasfile_but_not_in_plex(self):
        """hasFile but not in Plex -> downloaded (not available)."""
        f = StatusFacts(in_plex=False, arr_has_file=True)
        assert resolve_status(f).state is MediaStatus.DOWNLOADED

    def test_status_requested_when_arr_record_exists(self):
        f = StatusFacts(in_plex=False, arr_record_exists=True, indexer_issue="Indexers down")
        r = resolve_status(f)
        assert r.state is MediaStatus.REQUESTED
        assert "indexers" in r.detail.lower()

    def test_status_downloading_when_qbit_active(self):
        f = StatusFacts(in_plex=False, qbit_active=True, qbit_percent=37, qbit_speed=2.5)
        r = resolve_status(f)
        assert r.state is MediaStatus.DOWNLOADING
        assert r.progress == 37
        assert r.speed == 2.5

    def test_status_not_added_when_nothing(self):
        assert resolve_status(StatusFacts()).state is MediaStatus.NOT_ADDED

    # ------------------------------------------------------------------ media status service
    def test_media_status_service_routes_pending(self):
        """MediaStatusService resolves entries through the domain status resolver."""
        path = "/tmp/test_watchlist_ms.json"
        remove_tmp(path)
        wl = WatchlistService(path)
        entry = WatchlistEntry(
            title="The Matrix", year=1999, category="Action", lang="English",
            rt=88, imdb=8.7, isSeries=False, imdbId="tt0133093", tmdbId=603,
            cert="R", snippet="", cast=[], director="", poster="", trailerId="",
            trailerTitle="", added="2026-01-01", state="pending")
        data = wl.load()
        data.pending.append(entry)
        wl.save(data)

        # All services mocked out at the service boundary.
        cfg = Mock(PLEX_URL="", PLEX_TOKEN="", RADARR_API_KEY="k", SONARR_API_KEY="",
                   RADARR_URL="http://r", SONARR_URL="http://s", QBITTORRENT_URL="http://q")
        radarr = Mock()
        radarr.get_movies.return_value = []
        radarr.get_queue.return_value = []
        radarr.get_indexer_health.return_value = None
        qbit = Mock()
        qbit.match.return_value = None
        plex = None
        sonarr = None  # empty SONARR key -> no real SonarrService constructed

        svc = MediaStatusService(watchlist=wl, plex=plex, radarr=radarr, sonarr=None,
                                 qbit=qbit, config=cfg)
        snap = svc.compute_statuses()
        assert "tt0133093" in snap.results
        assert snap.results["tt0133093"].state is MediaStatus.NOT_ADDED

        remove_tmp(path)

    # ------------------------------------------------- library-driven availability
    def _seed_one(self, imdb_id="tt0133093", tmdb_id=603, is_series=False):
        """Write a single pending entry and return (path, watchlist)."""
        path = f"/tmp/test_wl_{self.__class__.__name__}_{imdb_id.replace(':','_')}.json"
        remove_tmp(path)
        wl = WatchlistService(path)
        entry = WatchlistEntry(
            title="The Matrix", year=1999, category="Action", lang="English",
            rt=88, imdb=8.7, isSeries=is_series, imdbId=imdb_id, tmdbId=tmdb_id,
            cert="R", snippet="", cast=[], director="", poster="", trailerId="",
            trailerTitle="", added="2026-01-01", state="pending")
        data = wl.load()
        data.pending.append(entry)
        wl.save(data)
        return path, wl

    def test_available_via_library_service_with_watch_links(self):
        """LibraryService (not legacy PlexService) decides AVAILABLE + watch links.

        Phase 6 migration: MediaStatusService must resolve an item found in the
        unified library to AVAILABLE with per-provider Plex/Emby links and the
        numeric plexKey — with NO direct PlexService call in the path.
        """
        from services.library import LibraryMatch, LibraryService

        class _FakeLib:
            """Minimal LibraryProvider that always finds the seeded item."""

            def __init__(self, name, match):
                self.name = name
                self._match = match

            def health(self):
                return True

            def find(self, identity, *, title="", year=None):
                return self._match

            def recently_added(self, limit=8):
                return []

            def build_watch_link(self, match):
                if self.name == "plex":
                    return {"plex_url": ("https://plex/#!/server/sid/details?key="
                                         f"/library/metadata/{match.metadata['rating_key']}")}
                return {"emby_url": f"https://emby/#!/item?id={match.provider_item_id}&serverId=S1"}

        plex_match = LibraryMatch("plex", "320819", "The Matrix", 1999,
                                  metadata={"rating_key": "320819"})
        emby_match = LibraryMatch("emby", "ITEM1", "The Matrix", 1999)
        library = LibraryService(providers=[
            _FakeLib("plex", plex_match), _FakeLib("emby", emby_match)])

        path, wl = self._seed_one()
        cfg = Mock(PLEX_URL="", PLEX_TOKEN="", EMBY_URL="", EMBY_API_KEY="",
                   RADARR_API_KEY="k", SONARR_API_KEY="",
                   RADARR_URL="http://r", SONARR_URL="http://s", QBITTORRENT_URL="http://q")
        radarr = Mock()
        radarr.get_movies.return_value = []
        radarr.get_queue.return_value = []
        radarr.get_indexer_health.return_value = None
        qbit = Mock()
        qbit.match.return_value = None

        svc = MediaStatusService(watchlist=wl, library=library, radarr=radarr,
                                 sonarr=None, qbit=qbit, config=cfg)
        snap = svc.compute_statuses()
        res = snap.results["tt0133093"]
        assert res.state is MediaStatus.AVAILABLE
        assert res.plexUrl.startswith("https://plex/")
        assert "/library/metadata/320819" in res.plexUrl
        assert res.embyUrl.startswith("https://emby/")
        assert res.plexKey == "320819"  # numeric ratingKey, not a URL

        remove_tmp(path)

    def test_legacy_plex_arg_is_wrapped_through_library(self):
        """The legacy `plex=` PlexService is wrapped in a provider — no direct path."""
        plex = Mock()
        svc = MediaStatusService(plex=plex, config=Mock(
            PLEX_URL="http://p", PLEX_TOKEN="t", EMBY_URL=None, EMBY_API_KEY=None,
            RADARR_API_KEY="k", SONARR_API_KEY="",
            RADARR_URL="http://r", SONARR_URL="http://s", QBITTORRENT_URL="http://q"))
        assert svc._library is not None
        assert [p.name for p in svc._library.providers] == ["plex"]
        # Library is the only availability source — no `_plex` attribute remains
        # on the service (the legacy direct member is gone).
        assert not hasattr(svc, "_plex")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
