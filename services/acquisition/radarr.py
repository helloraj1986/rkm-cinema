"""Radarr acquisition provider (spec §14).

Thin facade over the existing :class:`services.radarr.RadarrService` (the
low-level HTTP client). Owns all movie↔Radarr logic so no caller branches on
``RadarrService`` directly (§43 no parallel implementation).
"""
from __future__ import annotations

import logging
from typing import Optional

from domain.enums import MediaType
from services.acquisition.service import (
    AcquisitionProvider,
    AcquisitionRequestResult,
    AcquisitionStatus,
)
from services.radarr import RadarrService

logger = logging.getLogger("rkm.acquisition.radarr")

__all__ = ["RadarrAcquisitionProvider"]


class RadarrAcquisitionProvider(AcquisitionProvider):
    """Movie acquisition through Radarr."""

    name = "radarr"
    media_type = MediaType.MOVIE

    def __init__(self, *, service: Optional[RadarrService] = None, config=None, http=None):
        self._svc = service if service is not None else RadarrService(config=config, http=http)

    # ------------------------------------------------------- AcquisitionProvider
    def health(self) -> bool:
        try:
            return self._svc.health_check()
        except Exception:
            return False

    def find(self, identity, *, title: str = "", year: Optional[int] = None):
        """Existing Radarr movie matching *identity* (stable id, then title/year)."""
        # 1. Stable tmdb id.
        if identity.tmdb_id is not None:
            m = self._svc.find_movie_by_tmdb(identity.tmdb_id)
            if m is not None:
                return m
        # 2. IMDb id via lookup (resolves to Radarr's own record if present).
        if identity.imdb_id:
            m = self._svc.lookup_movie(identity.imdb_id)
            if m is not None:
                existing = self._svc.find_movie_by_tmdb(m.tmdbId) if m.tmdbId else None
                if existing is not None:
                    return existing
        # 3. Title/year fallback (last resort).
        if title:
            cands = self._svc.search_movies(title, year)
            if len(cands) == 1:
                return cands[0]
            exact = next((c for c in cands if year and c.year == year), None)
            if exact is not None:
                return exact
        return None

    def request(self, identity, *, title: str = "", year: Optional[int] = None,
                quality_profile_id: Optional[int] = None) -> AcquisitionRequestResult:
        if not identity.imdb_id and not identity.tmdb_id:
            return AcquisitionRequestResult(
                False, "unavailable", "No stable id to request in Radarr",
                MediaType.MOVIE, self.name)
        add = self._svc.add_movie(
            identity.imdb_id or "", quality_profile_id, title=title, year=year,
            tmdb_id=identity.tmdb_id)
        state = add.state  # "requested" | "ambiguous" | "unavailable"
        mapped = {
            "requested": "already_exists" if ("already" in (add.message or "").lower()) else "requested",
            "ambiguous": "ambiguous",
            "unavailable": "unavailable",
        }.get(state, "unavailable")
        return AcquisitionRequestResult(
            success=add.success, state=mapped, message=add.message,
            media_type=MediaType.MOVIE, service=self.name, item=add.movie)

    def get_status(self, identity, *, title: str = "", year: Optional[int] = None) -> AcquisitionStatus:
        movies = self._svc.get_movies(use_cache=True)
        rec = None
        if identity.tmdb_id is not None:
            rec = next((m for m in movies if m.tmdbId == identity.tmdb_id), None)
        if rec is None and identity.imdb_id:
            # IMDb may not match a stored movie's tmdbId; fall back to a scan match.
            rec = next((m for m in movies if (m.imdbId or "") == identity.imdb_id), None)
        if rec is None:
            return AcquisitionStatus(service=self.name, record_exists=False)
        st = AcquisitionStatus(
            service=self.name,
            record_exists=True,
            has_file=bool(rec.hasFile),
            record_title=rec.title,
            record_year=rec.year or None,
        )
        if not rec.hasFile:
            try:
                q = next((q for q in self._svc.get_queue(use_cache=True) if q.movieId == rec.id), None)
                if q:
                    st.queue_active = q.status != "completed"
                    st.queue_percent = self._queue_pct(q)
            except Exception as e:
                logger.debug("radarr get_status queue lookup failed: %s", e)
        return st

    def indexer_issue(self) -> Optional[str]:
        try:
            return self._svc.get_indexer_health()
        except Exception:
            return None

    def quality_profiles(self) -> list[dict]:
        try:
            return [
                {"id": p.id, "name": p.name, "items": p.items}
                for p in self._svc.get_quality_profiles()
            ]
        except Exception as e:
            logger.warning("radarr quality_profiles failed: %s", e)
            return []

    def preload(self) -> None:
        self._svc.get_movies(use_cache=True)
        self._svc.get_queue(use_cache=True)

    def invalidate(self) -> None:
        """Drop Radarr's cached movies/queue/profiles (spec §29)."""
        try:
            self._svc.clear_cache()
        except Exception as e:
            logger.warning("radarr invalidate failed: %s", e)

    @staticmethod
    def _queue_pct(q) -> int:
        try:
            total = float(getattr(q, "size", 0))
            left = float(getattr(q, "sizeleft", 0))
            if total <= 0:
                return 0
            return max(0, min(99, int((1 - left / total) * 100)))
        except Exception:
            return 0