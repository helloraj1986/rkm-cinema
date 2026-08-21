"""Download service — orchestrates the movie/tv download flow.

Owns: media-type resolution (via domain.resolver), *arr add with title/year
fallback, and cross-service fallback when an add yields "no match". Routes stay
thin: they validate the request and return a typed DownloadResponse.
"""
from __future__ import annotations

import logging
from typing import Optional

from domain.enums import DownloadResultState, MediaType
from domain.models import DownloadResult
from domain.resolver import resolve_media_type
from services import RadarrService, SonarrService
from services.watchlist import WatchlistService

logger = logging.getLogger("rkm.download")


class DownloadService:
    """Resolve a download request into a typed DownloadResult."""

    def __init__(self, *, radarr=None, sonarr=None, watchlist=None, config=None):
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        self._radarr = radarr if radarr is not None else (RadarrService(config=self.config) if self.config.RADARR_API_KEY else None)
        self._sonarr = sonarr if sonarr is not None else (SonarrService(config=self.config) if self.config.SONARR_API_KEY else None)
        self._watchlist = watchlist if watchlist is not None else WatchlistService()

    # ------------------------------------------------------------------ public
    def download(self, *, imdb_id: str = "", tmdb_id: Optional[int] = None,
                 requested_type: str = "", quality_profile_id: Optional[int] = None,
                 title: str = "", year: Optional[int] = None) -> DownloadResult:
        """Execute the full download flow and return a typed result."""
        imdb = (imdb_id or "").strip()

        if not imdb and not tmdb_id:
            return DownloadResult(False, DownloadResultState.UNAVAILABLE,
                                  "imdbId or tmdbId required")

        # Authoritative media-type resolution.
        entry = self._watchlist.find_by_imdb(imdb) if imdb else None
        media_type = resolve_media_type(
            requested_type=requested_type,
            watchlist_is_series=entry.isSeries if entry else None,
            radarr_match=bool(self._radarr and self._radarr_lookup(imdb, tmdb_id)),
            sonarr_match=bool(self._sonarr and self._sonarr_lookup(imdb)),
        )

        if media_type is MediaType.TV:
            return self._do_sonarr(imdb, quality_profile_id, title, year)
        return self._do_radarr(imdb, tmdb_id, quality_profile_id, title, year)

    # ------------------------------------------------------------------ internals
    def _radarr_lookup(self, imdb: str, tmdb_id: Optional[int]) -> bool:
        try:
            if imdb:
                m = self._radarr.lookup_movie(imdb)
                return bool(m and m.tmdbId)
            if tmdb_id:
                m = self._radarr.find_movie_by_tmdb(tmdb_id)
                return bool(m)
        except Exception:
            return False
        return False

    def _sonarr_lookup(self, imdb: str) -> bool:
        try:
            s = self._sonarr.lookup_series(imdb)
            return bool(s and s.tvdbId)
        except Exception:
            return False

    def _do_radarr(self, imdb, tmdb_id, qp, title, year) -> DownloadResult:
        if not self._radarr:
            return DownloadResult(False, DownloadResultState.UNAVAILABLE,
                                  "Radarr is not configured", MediaType.MOVIE)
        if not imdb:
            # tmdbId-only: resolve via Radarr lookup.
            resolved = self._radarr.find_movie_by_tmdb(tmdb_id) if tmdb_id else None
            if not resolved:
                return DownloadResult(False, DownloadResultState.UNAVAILABLE,
                                      "No Radarr match for this title", MediaType.MOVIE)
            imdb = resolved.imdbId or imdb
        result = self._radarr.add_movie(imdb, qp, title=title, year=year)
        return self._map(result, MediaType.MOVIE, fallback_sonarr=self._sonarr,
                         imdb=imdb, qp=qp, title=title, year=year)

    def _do_sonarr(self, imdb, qp, title, year) -> DownloadResult:
        if not self._sonarr:
            return DownloadResult(False, DownloadResultState.UNAVAILABLE,
                                  "Sonarr is not configured", MediaType.TV)
        if not imdb:
            return DownloadResult(False, DownloadResultState.UNAVAILABLE,
                                  "TV downloads need an IMDb ID", MediaType.TV)
        result = self._sonarr.add_series(imdb, qp, title=title, year=year)
        return self._map(result, MediaType.TV, fallback_sonarr=None,
                         imdb=imdb, qp=qp, title=title, year=year)

    def _map(self, result, media_type, *, fallback_sonarr, imdb, qp, title, year) -> DownloadResult:
        """Convert an *arr AddResult into a domain DownloadResult."""
        mt = media_type
        if result.success:
            state = DownloadResultState.REQUESTED
            if "already" in (result.message or "").lower():
                state = DownloadResultState.ALREADY_EXISTS
            return DownloadResult(True, state, result.message, mt,
                                  title=getattr(result, "movie", None) or getattr(result, "series", None))

        # Not successful: try cross-service fallback when a "no match" came back.
        if fallback_sonarr and "No Radarr match" in (result.message or ""):
            fb = fallback_sonarr.add_series(imdb, qp, title=title, year=year)
            if fb.success:
                return DownloadResult(True, DownloadResultState.REQUESTED,
                                      fb.message, MediaType.TV, title=fb.series)
        if "Multiple Radarr match" in (result.message or "") or "Multiple Sonarr match" in (result.message or ""):
            return DownloadResult(False, DownloadResultState.AMBIGUOUS, result.message, mt)

        state = DownloadResultState.UNAVAILABLE
        return DownloadResult(False, state, result.message, mt)
