"""Tests for the Phase 7 canonical reconciler (services/reconciliation/).

Uses injectable fake providers / services — no real LAN, no API keys.
"""
import os
import pytest
from unittest.mock import Mock

from domain.enums import MediaStatus
from services.reconciliation import Reconciler, snapshot_to_status_result
from services.watchlist import WatchlistService, WatchlistEntry


def _seed(imdb_id="tt0133093", tmdb_id=603, is_series=False, year=1999,
          title="The Matrix"):
    path = f"/tmp/test_rec_{imdb_id.replace(':','_')}.json"
    if os.path.exists(path):
        os.remove(path)
    wl = WatchlistService(path)
    entry = WatchlistEntry(
        title=title, year=year, category="Action", lang="English",
        rt=88, imdb=8.7, isSeries=is_series, imdbId=imdb_id, tmdbId=tmdb_id,
        cert="R", snippet="", cast=[], director="", poster="", trailerId="",
        trailerTitle="", added="2026-01-01", state="pending")
    data = wl.load()
    data.pending.append(entry)
    wl.save(data)
    return path, wl


class _FakeLib:
    """Minimal LibraryProvider driving fully-controlled match/watch-link cases."""

    def __init__(self, name, match=None, fail_watch=False):
        self.name = name
        self._match = match
        self._fail_watch = fail_watch

    def health(self):
        return True

    def find(self, identity, *, title="", year=None):
        return self._match

    def recently_added(self, limit=8):
        return []

    def build_watch_link(self, match):
        if self._fail_watch:
            raise RuntimeError("boom")
        if self.name == "plex":
            return {"plex_url": ("https://plex/#!/server/sid/details?key="
                                 f"/library/metadata/{match.metadata['rating_key']}")}
        return {"emby_url": f"https://emby/#!/item?id={match.provider_item_id}&serverId=S1"}


def _lib_with_plex_match():
    from services.library import LibraryMatch, LibraryService
    plex_match = LibraryMatch("plex", "320819", "The Matrix", 1999,
                              metadata={"rating_key": "320819"})
    emby_match = LibraryMatch("emby", "ITEM1", "The Matrix", 1999)
    library = LibraryService(providers=[
        _FakeLib("plex", plex_match), _FakeLib("emby", emby_match)])
    return library


def _cfg():
    return Mock(PLEX_URL="", PLEX_TOKEN="", EMBY_URL="", EMBY_API_KEY="",
                RADARR_API_KEY="k", SONARR_API_KEY="",
                RADARR_URL="http://r", SONARR_URL="http://s",
                QBITTORRENT_URL="http://q")


def _noop_arr():
    radarr = Mock()
    radarr.get_movies.return_value = []
    radarr.get_queue.return_value = []
    radarr.get_indexer_health.return_value = None
    qbit = Mock()
    qbit.match.return_value = None
    return radarr, qbit


class TestReconcilerSingleSnapshot:
    def test_get_snapshot_available_via_library(self):
        path, wl = _seed()
        radarr, qbit = _noop_arr()
        rec = Reconciler(watchlist=wl, library=_lib_with_plex_match(),
                         radarr=radarr, sonarr=None, qbit=qbit, config=_cfg())
        snap = rec.get_snapshot("movie:tmdb:603")
        assert snap.media_id == "movie:tmdb:603"
        assert snap.status is MediaStatus.AVAILABLE
        assert snap.capabilities.can_watch is True
        assert snap.capabilities.can_download is False
        assert snap.plexKey == "320819"
        plex = snap.watch_links.get("plex")
        assert plex and "/library/metadata/320819" in plex["url"]
        emby = snap.watch_links.get("emby")
        assert emby and emby["available"] is True
        os.remove(path)

    def test_get_snapshot_not_added_when_unknown(self):
        path, wl = _seed()
        radarr, qbit = _noop_arr()
        rec = Reconciler(watchlist=wl, library=None,
                         radarr=radarr, sonarr=None, qbit=qbit, config=_cfg())
        snap = rec.get_snapshot("movie:tmdb:999999")
        assert snap.status is MediaStatus.NOT_ADDED
        assert snap.capabilities.can_download is True
        assert snap.capabilities.can_watch is False
        os.remove(path)

    def test_get_snapshot_watch_link_failure_keeps_available(self):
        """§10: a broken watch-link resolver never downgrades AVAILABLE."""
        from services.library import LibraryMatch, LibraryService
        path, wl = _seed()
        radarr, qbit = _noop_arr()
        plex_match = LibraryMatch("plex", "320819", "The Matrix", 1999,
                                  metadata={"rating_key": "320819"})
        library = LibraryService(providers=[_FakeLib("plex", plex_match, fail_watch=True)])
        rec = Reconciler(watchlist=wl, library=library,
                         radarr=radarr, sonarr=None, qbit=qbit, config=_cfg())
        snap = rec.get_snapshot("movie:tmdb:603")
        assert snap.status is MediaStatus.AVAILABLE  # availability independent
        assert snap.capabilities.can_watch is True
        assert snap.plexKey == "320819"
        os.remove(path)

    def test_get_snapshot_unparseable_id_returns_not_added(self):
        path, wl = _seed()
        radarr, qbit = _noop_arr()
        rec = Reconciler(watchlist=wl, library=None,
                         radarr=radarr, sonarr=None, qbit=qbit, config=_cfg())
        snap = rec.get_snapshot("garbage-id")
        assert snap.status is MediaStatus.NOT_ADDED
        assert snap.media_id == "garbage-id"
        os.remove(path)


class TestReconcilerBulk:
    def test_compute_keyed_by_imdb_with_available_item(self):
        path, wl = _seed()
        radarr, qbit = _noop_arr()
        rec = Reconciler(watchlist=wl, library=_lib_with_plex_match(),
                         radarr=radarr, sonarr=None, qbit=qbit, config=_cfg())
        result = rec.compute()
        assert result.indexer_issue is None
        assert "tt0133093" in result.snapshots
        snap = result.snapshots["tt0133093"]
        assert snap.media_id == "movie:tmdb:603"
        assert snap.status is MediaStatus.AVAILABLE
        os.remove(path)


class TestSnapshotToStatusResult:
    def test_roundtrip_available(self):
        path, wl = _seed()
        radarr, qbit = _noop_arr()
        rec = Reconciler(watchlist=wl, library=_lib_with_plex_match(),
                         radarr=radarr, sonarr=None, qbit=qbit, config=_cfg())
        snap = rec.get_snapshot("movie:tmdb:603")
        r = snapshot_to_status_result(snap)
        assert r.state is MediaStatus.AVAILABLE
        assert r.plexKey == "320819"
        assert "/library/metadata/320819" in r.plexUrl
        assert r.embyUrl.startswith("https://emby/")
        os.remove(path)