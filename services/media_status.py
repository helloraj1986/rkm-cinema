"""Media status service — resolves every watchlist entry's status.

This service is the bridge between the live external services (Plex, Radarr,
Sonarr, qBittorrent) and the domain state machine. Routes call
``compute_statuses()`` and pass the result straight to the API layer; they
never re-implement the status branching themselves.

Plex remains the source of truth for availability.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from domain.enums import MediaType
from domain.status import StatusFacts, StatusResult, WatchLinks, resolve_status
from services import RadarrService, SonarrService
from services.library import (
    EmbyLibraryProvider,
    LibraryService,
    PlexLibraryProvider,
    resolve_library_identity,
)
from services.qbittorrent import QBittorrentService
from services.watchlist import WatchlistService

logger = logging.getLogger("rkm.media_status")


@dataclass
class StatusSnapshot:
    """All per-entry status results plus the current indexer issue."""

    results: dict[str, StatusResult]
    indexer_issue: Optional[str] = None


class MediaStatusService:
    """Compute per-entry StatusResult using the domain status resolver.

    Availability (spec §12: library always wins) comes from the unified
    :class:`LibraryService` (Plex + Emby as one logical library) via
    ``find_all()`` + ``watch_links()`` — the legacy ``PlexService`` direct calls
    are removed from this path (Phase 6 migration, §42).
    """

    def __init__(self, *, watchlist=None, library=None, plex=None, radarr=None,
                 sonarr=None, qbit=None, config=None):
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        self._watchlist = watchlist if watchlist is not None else WatchlistService()
        self._radarr = radarr if radarr is not None else (RadarrService(config=self.config) if self.config.RADARR_API_KEY else None)
        self._sonarr = sonarr if sonarr is not None else (SonarrService(config=self.config) if self.config.SONARR_API_KEY else None)
        self._qbit = qbit if qbit is not None else QBittorrentService(config=self.config)
        # Canonical availability/watch-link source. If not injected, build one
        # lazily from config. The legacy `plex=` arg (a PlexService) is wrapped
        # in a PlexLibraryProvider so EVERY route goes through LibraryService —
        # no parallel PlexService branch in the resolver (§43).
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

    # ------------------------------------------------------------------ public
    def compute_statuses(self) -> "StatusSnapshot":
        """Return a StatusSnapshot for every pending/recommended entry."""
        data = self._watchlist.load()
        entries = data.pending + data.recommended

        r_movies = self._radarr.get_movies() if self._radarr else []
        r_queue = self._radarr.get_queue() if self._radarr else []
        s_series = self._sonarr.get_series() if self._sonarr else []
        s_queue = self._sonarr.get_queue() if self._sonarr else []

        queue_by_movie = {str(q.movieId): q for q in r_queue}
        queue_by_series = {str(q.seriesId): q for q in s_queue}
        indexer_issue = self._radarr.get_indexer_health() if self._radarr else None

        results: dict[str, StatusResult] = {}
        for entry in entries:
            results[entry.imdbId] = self._resolve_one(
                entry, r_movies, r_queue, s_series, s_queue,
                queue_by_movie, queue_by_series, indexer_issue,
            )
        return StatusSnapshot(results=results, indexer_issue=indexer_issue)

    # ------------------------------------------------------------------ internals
    def _resolve_one(self, entry, r_movies, r_queue, s_series, s_queue,
                     queue_by_movie, queue_by_series, indexer_issue) -> StatusResult:
        is_series = bool(getattr(entry, "isSeries", False))
        mt = MediaType.TV if is_series else MediaType.MOVIE
        title = entry.title
        year = entry.year
        tmdb_id = getattr(entry, "tmdbId", None)
        tvdb_id = getattr(entry, "tvdbId", None)
        imdb_id = getattr(entry, "imdbId", None)

        # Build the fact set the domain status resolver consumes.
        facts = StatusFacts(media_type=mt)

        # 1. Library (Plex/Emby) is source of truth — availability always wins.
        #    Watch links come from the unified LibraryService (failure-safe,
        #    spec §10/§12); a link failure can never flip AVAILABLE away.
        if self._library:
            identity = resolve_library_identity(
                media_type=mt, tmdb_id=tmdb_id, imdb_id=imdb_id, tvdb_id=tvdb_id)
            matches = self._library.find_all(identity, title=title, year=year)
            if matches:
                watch = self._library.watch_links(matches)  # spec §10 map
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
                return resolve_status(facts)

        # 2. *arr facts.
        if mt is MediaType.TV:
            tvdb_id = self._sonarr.resolve_tvdb_id(entry.imdbId) if self._sonarr else None
            rec = next((s for s in s_series if s.tvdbId == tvdb_id), None) if tvdb_id else None
            service = "sonarr"
            stats = getattr(rec, "statistics", None) or {}
            facts.arr_has_file = bool(stats.get("episodeFileCount", 0)) > 0
        else:
            rec = next((m for m in r_movies if m.tmdbId == tmdb_id), None)
            service = "radarr"
            facts.arr_has_file = bool(rec and rec.hasFile)

        facts.arr_record_exists = rec is not None
        facts.indexer_issue = indexer_issue

        if rec is not None and not facts.arr_has_file:
            # Continue resolving download activity for an added title.
            if mt is MediaType.TV:
                q = queue_by_series.get(str(rec.id)) if hasattr(rec, "id") else None
            else:
                q = queue_by_movie.get(str(rec.id))
            if q:
                facts.arr_queue_active = q.status != "completed"
                facts.arr_queue_percent = self._queue_pct(q)
            # qBittorrent direct match (works even before *arr queue reports it).
            t = self._qbit.match(rec.title, str(getattr(rec, "year", "") or ""))
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
        return result

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
