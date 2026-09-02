"""Sonarr acquisition provider (spec §14).

Thin facade over the existing :class:`services.sonarr.SonarrService` (the
low-level HTTP client). Owns all series↔Sonarr logic (incl. TVDB id
resolution) so no caller branches on ``SonarrService`` directly (§43).
"""
from __future__ import annotations

import logging
import os
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

    # Process-level tmdb→tvdb cache so the resolution is one-off per title
    # across requests (a fresh SonarrAcquisitionProvider is built per reconcile).
    # A CLASS attribute is shared by every instance and item-assignment needs no
    # `global`. Persisted to disk (the rw /workspace/media mount) so a cold
    # reconcile reads the whole map at once instead of re-resolving per title.
    _TMDB_TO_TVDB: dict[int, int] = {}
    _CACHE_PATH: str = "/workspace/media/tmdb_to_tvdb.json"
    _loaded: bool = False

    @classmethod
    def _ensure_loaded(cls) -> None:
        if cls._loaded:
            return
        cls._loaded = True
        try:
            import json as _json
            if os.path.exists(cls._CACHE_PATH):
                with open(cls._CACHE_PATH) as f:
                    data = _json.load(f)
                if isinstance(data, dict):
                    cls._TMDB_TO_TVDB.update(
                        {int(k): int(v) for k, v in data.items()})
        except Exception:
            pass

    @classmethod
    def _persist(cls, tmdb_id: int, tvdb_id: int) -> None:
        try:
            import json as _json
            cls._ensure_loaded()
            cls._TMDB_TO_TVDB[tmdb_id] = tvdb_id
            with open(cls._CACHE_PATH, "w") as f:
                _json.dump(cls._TMDB_TO_TVDB, f)
        except Exception:
            pass

    def __init__(self, *, service: Optional[SonarrService] = None, config=None, http=None):
        self._svc = service if service is not None else SonarrService(config=config, http=http)

    def _tvdb_for(self, identity: MediaIdentity) -> Optional[int]:
        if identity.tvdb_id is not None:
            return identity.tvdb_id
        # tmdb-only ids: resolve to tvdb so get_status/find can match the cached
        # Sonarr series list. Prefer TMDB external_ids (fast, cached on disk)
        # over a live Sonarr /series/lookup — that lookup searches the indexers
        # and TIMES OUT when they're down (AU s115a), which is what made a full
        # reconcile take ~56s.
        if identity.tmdb_id is not None:
            tid = int(identity.tmdb_id)
            self._ensure_loaded()
            cached = self._TMDB_TO_TVDB.get(tid)
            if cached:
                return cached
            tvdb = self._tvdb_via_tmdb(tid)
            if tvdb:
                self._persist(tid, tvdb)
                return tvdb
            # NOTE: no live Sonarr lookup here. /series/lookup?term=tmdb:<id>
            # searches the indexers and TIMES OUT when they're down (AU s115a),
            # which is what made a full reconcile take ~56s. Titles TMDB can't
            # resolve are matched by title+year against the cached series list
            # in get_status()/find() instead.
        if identity.imdb_id:
            try:
                return self._svc.resolve_tvdb_id(identity.imdb_id)
            except Exception:
                return None
        return None

    @staticmethod
    def _tvdb_via_tmdb(tmdb_id: int) -> Optional[int]:
        """Resolve a TMDB show id to its TVDB id via TMDB external_ids."""
        try:
            from services.tmdb import TMDBService
            from config.settings import get_config
            tmdb = TMDBService(config=get_config())
            tvdb = tmdb.get_show_external_ids(tmdb_id)
            return int(tvdb) if tvdb else None
        except Exception:
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
        if not identity.imdb_id and not identity.tmdb_id and not identity.tvdb_id:
            return AcquisitionRequestResult(
                False, "unavailable", "No stable id to request in Sonarr",
                MediaType.TV, self.name)
        add = self._svc.add_series(
            identity.imdb_id or "", quality_profile_id, title=title, year=year,
            tvdb_id=identity.tvdb_id, tmdb_id=identity.tmdb_id)
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
        if rec is None and title:
            # Title+year fallback for entries TMDB couldn't resolve to a tvdb.
            # Matched against the CACHED series list (no live lookup), mirroring
            # the Radarr provider. Solves tvdb-less owned series being reported
            # not_added when TMDB external_ids is empty.
            series = self._svc.get_series(use_cache=True)
            rec = next((s for s in series
                        if str(s.title or "").strip().lower() == str(title).strip().lower()
                        and (not year or not s.year or int(s.year) == int(year))), None)
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

    def invalidate(self) -> None:
        """Drop Sonarr's cached series/queue/profiles (spec §29)."""
        try:
            self._svc.clear_cache()
        except Exception as e:
            logger.warning("sonarr invalidate failed: %s", e)

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