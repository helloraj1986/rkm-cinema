"""Sonarr acquisition provider (spec §14).

Thin facade over the existing :class:`services.sonarr.SonarrService` (the
low-level HTTP client). Owns all series↔Sonarr logic (incl. TVDB id
resolution) so no caller branches on ``SonarrService`` directly (§43).
"""
from __future__ import annotations

import logging
from typing import Optional

from domain.enums import MediaType
from domain.identity import MediaIdentity
from services.acquisition.service import (
    AcquisitionProvider,
    AcquisitionRequestResult,
    AcquisitionStatus,
)
from services.sonarr import SonarrService

logger = logging.getLogger("rkm.acquisition.sonarr")

__all__ = ["SonarrAcquisitionProvider"]


class SonarrAcquisitionProvider(AcquisitionProvider):
    """Series acquisition through Sonarr."""

    name = "sonarr"
    media_type = MediaType.TV

    def __init__(self, *, service: Optional[SonarrService] = None, config=None, http=None):
        self._svc = service if service is not None else SonarrService(config=config, http=http)

    def _tvdb_for(self, identity: MediaIdentity) -> Optional[int]:
        if identity.tvdb_id is not None:
            return identity.tvdb_id
        if identity.imdb_id:
            try:
                return self._svc.resolve_tvdb_id(identity.imdb_id)
            except Exception:
                return None
        return None

    # ------------------------------------------------------- AcquisitionProvider
    def health(self) -> bool:
        try:
            return self._svc.health_check()
        except Exception:
            return False

    def find(self, identity, *, title: str = "", year: Optional[int] = None):
        """Existing Sonarr series matching *identity*."""
        tvdb = self._tvdb_for(identity)
        if tvdb is not None:
            s = self._svc.find_series_by_tvdb(tvdb)
            if s is not None:
                return s
        if title:
            cands = self._svc.search_series(title, year)
            if len(cands) == 1:
                return cands[0]
            ltitle = str(title).strip().lower()
            exact = next((c for c in cands if c.title.strip().lower() == ltitle), None)
            if exact is not None:
                return exact
        return None

    def request(self, identity, *, title: str = "", year: Optional[int] = None,
                quality_profile_id: Optional[int] = None) -> AcquisitionRequestResult:
        add = self._svc.add_series(
            identity.imdb_id or "", quality_profile_id, title=title, year=year)
        mapped = {
            "requested": "already_exists" if ("already" in (add.message or "").lower()) else "requested",
            "ambiguous": "ambiguous",
            "unavailable": "unavailable",
        }.get(add.state, "unavailable")
        return AcquisitionRequestResult(
            success=add.success, state=mapped, message=add.message,
            media_type=MediaType.TV, service=self.name, item=add.series)

    def get_status(self, identity, *, title: str = "", year: Optional[int] = None) -> AcquisitionStatus:
        tvdb = self._tvdb_for(identity)
        rec = None
        if tvdb is not None:
            rec = next((s for s in self._svc.get_series(use_cache=True) if s.tvdbId == tvdb), None)
        if rec is None:
            return AcquisitionStatus(service=self.name, record_exists=False)
        stats = getattr(rec, "statistics", None) or {}
        st = AcquisitionStatus(
            service=self.name,
            record_exists=True,
            has_file=bool(int(stats.get("episodeFileCount", 0)) > 0),
            record_title=rec.title,
            record_year=rec.year or None,
        )
        if not st.has_file:
            try:
                q = next((q for q in self._svc.get_queue(use_cache=True) if q.seriesId == rec.id), None)
                if q:
                    st.queue_active = q.status != "completed"
                    st.queue_percent = self._queue_pct(q)
            except Exception as e:
                logger.debug("sonarr get_status queue lookup failed: %s", e)
        return st

    def preload(self) -> None:
        self._svc.get_series(use_cache=True)
        self._svc.get_queue(use_cache=True)

    def quality_profiles(self) -> list[dict]:
        try:
            return [
                {"id": p.id, "name": p.name, "items": p.items}
                for p in self._svc.get_quality_profiles()
            ]
        except Exception as e:
            logger.warning("sonarr quality_profiles failed: %s", e)
            return []

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