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
from services.acquisition import (
    AcquisitionService,
    RadarrAcquisitionProvider,
    SonarrAcquisitionProvider,
)
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
                 sonarr=None, qbit=None, acquisition=None, config=None):
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        self._watchlist = watchlist if watchlist is not None else WatchlistService()
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
        # Canonical acquisition source. Legacy ``radarr=``/``sonarr=`` (the
        # low-level HTTP services) are wrapped in providers; everything funnels
        # through the single AcquisitionService router (§43, spec §14).
        self._acquisition = acquisition
        if self._acquisition is None:
            acq_providers = []
            if radarr is not None:
                acq_providers.append(RadarrAcquisitionProvider(service=radarr))
            elif self.config.RADARR_API_KEY:
                acq_providers.append(RadarrAcquisitionProvider(config=self.config))
            if sonarr is not None:
                acq_providers.append(SonarrAcquisitionProvider(service=sonarr))
            elif self.config.SONARR_API_KEY:
                acq_providers.append(SonarrAcquisitionProvider(config=self.config))
            self._acquisition = AcquisitionService(providers=acq_providers) if acq_providers else None

    # ------------------------------------------------------------ public API
    def invalidate(self) -> None:
        """Drop library + acquisition caches (force a fresh reconcile).

        After the app writes media to a provider this should be called so a
        subsequent :meth:`get_snapshot`/:meth:`compute` re-reads the real state
        instead of serving stale cached scans (spec §29 invalidation on writes).
        Provider ``invalidate()`` hooks are the canonical choke-point (§43).
        """
        if self._library is not None:
            try:
                self._library.invalidate()
            except Exception as e:
                logger.warning("reconciler invalidate library failed: %s", e)
        if self._acquisition is not None:
            try:
                self._acquisition.invalidate()
            except Exception as e:
                logger.warning("reconciler invalidate acquisition failed: %s", e)

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

        # One bulk fetch per acquisition backend warms the 45s cache, so each
        # per-entry get_status below hits memory instead of re-scanning *arr.
        if self._acquisition:
            self._acquisition.preload()
        indexer_issue = self._acquisition.indexer_issue() if self._acquisition else None

        snapshots: dict[str, MediaSnapshot] = {}
        for entry in entries:
            snap = self._snapshot_for_entry(entry, indexer_issue)
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
        if self._acquisition:
            self._acquisition.preload()
        indexer_issue = self._acquisition.indexer_issue() if self._acquisition else None
        return self._snapshot_for_entry(entry, indexer_issue, identity=identity)

    def _snapshot_for_entry(self, entry, indexer_issue=None,
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
                return self._to_snapshot(identity, result, watch,
                                         title=title, year=year, media_type=mt)

        # 2. *arr facts through the single acquisition router (spec §14).
        service = mt.arr_service
        if self._acquisition:
            st = None
            try:
                st = self._acquisition.get_status(identity, title=title, year=year)
            except Exception as e:
                logger.warning("reconcile acquisition get_status failed: %s", e)
            if st is not None and st.record_exists:
                facts.arr_record_exists = True
                facts.arr_has_file = st.has_file
                facts.indexer_issue = indexer_issue
                if st.queue_active:
                    facts.arr_queue_active = True
                    facts.arr_queue_percent = st.queue_percent
                if not st.has_file:
                    # qBittorrent matches by name (the download client has no
                    # provider id), so cross-match on the *arr record's title/year.
                    t = self._qbit.match(st.record_title, str(st.record_year or ""))
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
        return self._to_snapshot(identity, result, watch,
                                 title=title, year=year, media_type=mt)

    @staticmethod
    def _to_snapshot(identity: MediaIdentity, result: StatusResult,
                     watch: dict, *, title: str = "", year: Optional[int] = None,
                     media_type: Optional[MediaType] = None) -> MediaSnapshot:
        try:
            mid = identity.media_id
        except ValueError:
            mid = ""
        mt = media_type if media_type is not None else (identity.media_type if identity else MediaType.MOVIE)
        return MediaSnapshot.from_result(
            result, media_id=mid, media_type=mt, title=title, year=year,
            watch_links=watch)