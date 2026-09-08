"""Download service — orchestrates the movie/tv download flow.

Owns: media-type resolution (via domain.resolver) and the cross-service
fallback when an add yields "no match". Actual *arr submission is routed
through the single :class:`AcquisitionService` (spec §14) — no ``if movie:
radarr else: sonarr`` here. Routes stay thin: they validate the request and
return a typed DownloadResponse.
"""
from __future__ import annotations

import logging
from typing import Optional

from domain.enums import DownloadResultState, MediaType
from domain.identity import MediaIdentity
from domain.models import DownloadResult
from domain.resolver import resolve_media_type
from services.acquisition import (
    AcquisitionRequestResult,
    AcquisitionService,
    RadarrAcquisitionProvider,
    SonarrAcquisitionProvider,
)
from services.watchlist import WatchlistService

logger = logging.getLogger("rkm.download")


class DownloadService:
    """Resolve a download request into a typed DownloadResult."""

    def __init__(self, *, radarr=None, sonarr=None, acquisition=None,
                 watchlist=None, config=None):
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        # Legacy ``radarr=``/``sonarr=`` (low-level HTTP services) are wrapped in
        # providers; everything funnels through the single AcquisitionService
        # router (§43, spec §14).
        self._acquisition = acquisition
        if self._acquisition is None:
            providers = []
            if radarr is not None:
                providers.append(RadarrAcquisitionProvider(service=radarr))
            elif self.config.RADARR_API_KEY:
                providers.append(RadarrAcquisitionProvider(config=self.config))
            if sonarr is not None:
                providers.append(SonarrAcquisitionProvider(service=sonarr))
            elif self.config.SONARR_API_KEY:
                providers.append(SonarrAcquisitionProvider(config=self.config))
            self._acquisition = AcquisitionService(providers=providers) if providers else None
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
            radarr_match=bool(self._acquisition and self._radarr_lookup(imdb, tmdb_id)),
            sonarr_match=bool(self._acquisition and self._sonarr_lookup(imdb)),
        )

        return self._do_request(media_type, imdb, tmdb_id, quality_profile_id, title, year)

    # ------------------------------------------------------------------ internals
    def _radarr_lookup(self, imdb: str, tmdb_id: Optional[int]) -> bool:
        try:
            identity = MediaIdentity(media_type=MediaType.MOVIE,
                                     imdb_id=imdb or None, tmdb_id=tmdb_id or None)
            m = self._acquisition.find(identity)
            return m is not None
        except Exception:
            return False

    def _sonarr_lookup(self, imdb: str) -> bool:
        try:
            identity = MediaIdentity(media_type=MediaType.TV,
                                     imdb_id=imdb or None)
            s = self._acquisition.find(identity)
            return s is not None
        except Exception:
            return False

    def _do_request(self, media_type: MediaType, imdb, tmdb_id, qp, title, year) -> DownloadResult:
        identity = MediaIdentity(media_type=media_type, imdb_id=imdb or None, tmdb_id=tmdb_id or None)
        result = self._acquisition.request(identity, title=title, year=year, quality_profile_id=qp)
        return self._map(result, fallback=media_type is MediaType.MOVIE,
                         imdb=imdb, qp=qp, title=title, year=year)

    def _map(self, result: AcquisitionRequestResult, *, fallback: bool,
             imdb, qp, title, year) -> DownloadResult:
        """Convert an acquisition result into a domain DownloadResult."""
        mt = result.media_type
        if result.success:
            state = DownloadResultState.REQUESTED
            if result.state == "already_exists":
                state = DownloadResultState.ALREADY_EXISTS
            return DownloadResult(True, state, result.message, mt, title=result.item)

        # Not successful: cross-service fallback when a "no match" came back.
        if fallback and "No Radarr match" in (result.message or ""):
            tv_identity = MediaIdentity(media_type=MediaType.TV, imdb_id=imdb or None)
            fb = self._acquisition.request(tv_identity, title=title, year=year, quality_profile_id=qp)
            if fb.success:
                return DownloadResult(True, DownloadResultState.REQUESTED,
                                      fb.message, MediaType.TV, title=fb.item)
        if result.state == "ambiguous":
            return DownloadResult(False, DownloadResultState.AMBIGUOUS, result.message, mt)

        return DownloadResult(False, DownloadResultState.UNAVAILABLE, result.message, mt)
