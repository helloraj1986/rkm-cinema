"""Canonical media reconciler (spec §13 Phase 7).

The :class:`Reconciler` is the SINGLE home for fact-gathering across the
external systems and emitting :class:`MediaSnapshot`. It wires

    MediaIdentity
      -> LibraryService + *arr services + qBittorrentService
      -> StatusFacts
      -> domain.status.resolve_status  (pure resolver)
      -> MediaSnapshot

API routes consume the produced :class:`MediaSnapshot`; they never re-derive
the state machine. Unlike a route, the reconciler owns its dependency graph
(``watchlist``, ``library``, ``radarr``/``sonarr``, ``qbit``) so it is fully
mockable and LAN-free in tests.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from domain.enums import MediaStatus, MediaType
from domain.identity import MediaIdentity, parse_media_id
from domain.status import (
    MediaSnapshot,
    StatusFacts,
    StatusResult,
    WatchLinks,
    resolve_status,
)
from services import RadarrService, SonarrService
from services.library import (
    EmbyLibraryProvider,
    LibraryService,
    PlexLibraryProvider,
    resolve_library_identity,
)
from services.qbittorrent import QBittorrentService
from services.watchlist import WatchlistService

logger = logging.getLogger("rkm.reconciliation")

__all__ = ["Reconciler", "ReconcileResult", "snapshot_to_status_result"]


@dataclass
class ReconcileResult:
    """Bulk reconcile output: every watchlist entry's snapshot + indexer issue."""

    snapshots: dict[str, MediaSnapshot]   # keyed by the watchlist imdbId
    indexer_issue: Optional[str] = None


def snapshot_to_status_result(snap: MediaSnapshot) -> StatusResult:
    """Reconstruct the legacy ``StatusResult`` shape from a snapshot.

    Used by the backwards-compatible :class:`MediaStatusService` shim so older
    consumers (and the pre-Phase-7 tests) stay green with zero duplicated logic.
    """
    plex = (snap.watch_links or {}).get("plex") or {}
    emby = (snap.watch_links or {}).get("emby") or {}
    return StatusResult(
        state=snap.status,
        service=snap.service,
        detail=snap.detail,
        plexUrl=plex.get("url") or "",
        embyUrl=emby.get("url") or "",
        plexKey=snap.plexKey,
        progress=snap.progress,
        speed=snap.speed,
        eta=snap.eta,
        qbitState=snap.qbitState,
        qbitName=snap.qbitName,
    )


class Reconciler:
    """Gathers facts for media item(s) and emits canonical MediaSnapshots."""

    def __init__(self, *, watchlist=None, library=None, plex=None, radarr=None,
                 sonarr=None, qbit=None, config=None):
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        self._watchlist = watchlist if watchlist is not None else WatchlistService()
        self._radarr = radarr if radarr is not None else (RadarrService(config=self.config) if self.config.RADARR_API_KEY else None)
        self._sonarr = sonarr if sonarr is not None else (SonarrService(config=self.config) if self.config.SONARR_API_KEY else None)
        self._qbit = qbit if qbit is not None else QBittorrentService(config=self.config)
        # Canonical availability/watch-link source. Legacy ``plex=`` (a
        # PlexService) is wrapped in a PlexLibraryProvider so every path goes
        # through LibraryService — no parallel PlexService branch (§43).
        self._library = library
        if self._library is None:
            providers = []
            if plex is not None:
                providers.append(PlexLibraryProvider(config=self.config, plex=plex))
            elif self.config.PLEX_URL and self.config.PLEX_TOKEN:
                providers.append(PlexLibraryProvider(config=self.config))
            if self.config.EMBY_URL and self.config.EMBY_API_KEY:
                providers.append(EmbyLibraryProvider(config=self.config))
            self._library = LibraryService(providers=providers) if providers else None

    # ------------------------------------------------------------ public API
    def get_snapshot(self, media_id: str) -> MediaSnapshot:
        """Reconcile a single canonical ``media_id`` to a MediaSnapshot.

        ``media_id`` is a canonical identity string (e.g. ``movie:tmdb:603``).
        If it references a watchlist entry that entry's metadata is used to
        enrich the facts; otherwise the identity alone drives the gather. An
        unparseable id yields a NOT_ADDED snapshot rather than raising.
        """
        try:
            identity = parse_media_id(media_id)
        except ValueError:
            logger.warning("reconcile: unparseable media_id=%r", media_id)
            return MediaSnapshot(media_id=media_id, status=MediaStatus.NOT_ADDED)
        entry = self._watchlist_entry_for(identity)
        return self._snapshot_for(identity, entry)

    def compute(self) -> ReconcileResult:
        """Reconcile every pending + recommended entry in one batch."""
        data = self._watchlist.load()
        entries = data.pending + data.recommended

        r_movies = self._radarr.get_movies() if self._radarr else []
        r_queue = self._radarr.get_queue() if self._radarr else []
        s_series = self._sonarr.get_series() if self._sonarr else []
        s_queue = self._sonarr.get_queue() if self._sonarr else []

        queue_by_movie = {str(q.movieId): q for q in r_queue}
        queue_by_series = {str(q.seriesId): q for q in s_queue}
        indexer_issue = self._radarr.get_indexer_health() if self._radarr else None

        snapshots: dict[str, MediaSnapshot] = {}
        for entry in entries:
            snap = self._snapshot_for_entry(
                entry, r_movies, r_queue, s_series, s_queue,
                queue_by_movie, queue_by_series, indexer_issue,
            )
            snapshots[entry.imdbId] = snap
        return ReconcileResult(snapshots=snapshots, indexer_issue=indexer_issue)

    # ------------------------------------------------------------- internals
    def _watchlist_entry_for(self, identity: MediaIdentity):
        target_tmdb = int(identity.tmdb_id) if identity.tmdb_id is not None else None
        target_tvdb = int(identity.tvdb_id) if identity.tvdb_id is not None else None
        target_imdb = identity.imdb_id
        data = self._watchlist.load()
        for entry in data.pending + data.recommended:
            eid = getattr(entry, "imdbId", None)
            etmdb = getattr(entry, "tmdbId", None)
            etvdb = getattr(entry, "tvdbId", None)
            if target_tmdb is not None and int(etmdb or 0) == target_tmdb:
                return entry
            if target_tvdb is not None and int(etvdb or 0) == target_tvdb:
                return entry
            if target_imdb and eid == target_imdb:
                return entry
        return None

    def _snapshot_for(self, identity: MediaIdentity, entry=None) -> MediaSnapshot:
        r_movies = self._radarr.get_movies() if self._radarr else []
        r_queue = self._radarr.get_queue() if self._radarr else []
        s_series = self._sonarr.get_series() if self._sonarr else []
        s_queue = self._sonarr.get_queue() if self._sonarr else []
        queue_by_movie = {str(q.movieId): q for q in r_queue}
        queue_by_series = {str(q.seriesId): q for q in s_queue}
        indexer_issue = self._radarr.get_indexer_health() if self._radarr else None
        return self._snapshot_for_entry(
            entry, r_movies, r_queue, s_series, s_queue,
            queue_by_movie, queue_by_series, indexer_issue,
            identity=identity,
        )

    def _snapshot_for_entry(self, entry, r_movies, r_queue, s_series, s_queue,
                            queue_by_movie, queue_by_series, indexer_issue,
                            *, identity: Optional[MediaIdentity] = None) -> MediaSnapshot:
        if entry is None and identity is None:
            return MediaSnapshot(media_id="", status=MediaStatus.NOT_ADDED)
        if entry is not None:
            is_series = bool(getattr(entry, "isSeries", False))
        else:
            is_series = identity.media_type is MediaType.TV
        mt = MediaType.TV if is_series else MediaType.MOVIE
        title = getattr(entry, "title", "") if entry else ""
        year = getattr(entry, "year", None) if entry else None
        tmdb_id = getattr(entry, "tmdbId", None) if entry else None
        tvdb_id = getattr(entry, "tvdbId", None) if entry else None
        imdb_id = getattr(entry, "imdbId", None) if entry else None

        if identity is None:
            identity = resolve_library_identity(
                media_type=mt, tmdb_id=tmdb_id, imdb_id=imdb_id, tvdb_id=tvdb_id)

        facts = StatusFacts(media_type=mt)
        watch: dict = {}

        # 1. Library (Plex/Emby) is source of truth — availability always wins.
        if self._library:
            try:
                matches = self._library.find_all(identity, title=title, year=year)
            except Exception:
                matches = []
            if matches:
                try:
                    watch = self._library.watch_links(matches)
                except Exception:
                    watch = {}
                plex_match = next((m for m in matches if m.provider == "plex"), None)
                facts.in_plex = True
                facts.plex_links = WatchLinks(
                    plex_available=bool((watch.get("plex") or {}).get("available")),
                    plex_url=(watch.get("plex") or {}).get("url") or "",
                    plex_key=str((plex_match.metadata or {}).get("rating_key", ""))
                    if plex_match else "",
                    emby_available=bool((watch.get("emby") or {}).get("available")),
                    emby_url=(watch.get("emby") or {}).get("url") or "",
                )
                facts.indexer_issue = indexer_issue
                result = resolve_status(facts)
                return self._to_snapshot(identity, result, watch)

        # 2. *arr facts.
        service = mt.arr_service
        if mt is MediaType.TV:
            tvdb_id = self._sonarr.resolve_tvdb_id(entry.imdbId) if (self._sonarr and entry and entry.imdbId) else None
            rec = next((s for s in s_series if s.tvdbId == tvdb_id), None) if tvdb_id else None
            stats = getattr(rec, "statistics", None) or {}
            facts.arr_has_file = bool(stats.get("episodeFileCount", 0)) > 0
        else:
            tref = int(identity.tmdb_id) if getattr(identity, "tmdb_id", None) is not None else None
            rec = next((m for m in r_movies if m.tmdbId == tref), None) if tref is not None else None
            if rec is None and entry and getattr(entry, "tmdbId", None) is not None:
                rec = next((m for m in r_movies if m.tmdbId == entry.tmdbId), None)
            facts.arr_has_file = bool(rec and rec.hasFile)

        facts.arr_record_exists = rec is not None
        facts.indexer_issue = indexer_issue

        if rec is not None and not facts.arr_has_file:
            if mt is MediaType.TV:
                q = queue_by_series.get(str(rec.id)) if hasattr(rec, "id") else None
                t = self._qbit.match(getattr(rec, "title", ""), str(getattr(rec, "year", "") or ""))
            else:
                q = queue_by_movie.get(str(rec.id))
                t = self._qbit.match(getattr(rec, "title", ""), str(getattr(rec, "year", "") or ""))
            if q:
                facts.arr_queue_active = q.status != "completed"
                facts.arr_queue_percent = self._queue_pct(q)
            if t:
                prog = float(t.get("progress") or 0)
                if prog < 1.0:
                    facts.qbit_active = True
                    facts.qbit_percent = round(prog * 100)
                    facts.qbit_speed = float(t.get("dlspeed") or 0) / 1e6
                    facts.qbit_eta = None if int(t.get("eta") or -1) < 0 else int(t.get("eta"))
                    facts.qbit_state = t.get("state") or ""
                    facts.qbit_name = (t.get("name") or "")[:60]
                else:
                    facts.qbit_done = True
                    facts.qbit_percent = 100

        result = resolve_status(facts)
        result.service = service
        return self._to_snapshot(identity, result, watch)

    @staticmethod
    def _to_snapshot(identity: MediaIdentity, result: StatusResult,
                     watch: dict) -> MediaSnapshot:
        try:
            mid = identity.media_id
        except ValueError:
            mid = ""
        return MediaSnapshot.from_result(result, media_id=mid, watch_links=watch)

    @staticmethod
    def _queue_pct(q) -> int:
        """Calculate *arr queue progress percentage."""
        try:
            total = float(getattr(q, "size", 0))
            left = float(getattr(q, "sizeleft", 0))
            if total <= 0:
                return 0
            return max(0, min(99, int((1 - left / total) * 100)))
        except Exception:
            return 0