"""Canonical service health checker (spec §28 Phase 14).

Every external service gets a structured health result; **one failing service
must not destroy the overall response** — the checker reports each service
independently and flips a ``degraded`` flag when anything is down, instead of
raising. Dependencies are DI-injectable so tests run LAN-free.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from config.settings import get_config

logger = logging.getLogger("rkm.health")


@dataclass
class ServiceHealth:
    """Structured health for one external service (spec §28)."""

    name: str
    configured: bool = False
    ok: bool = False
    detail: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "configured": self.configured,
            "ok": self.ok,
            "detail": self.detail,
            "error": self.error,
        }


@dataclass
class HealthReport:
    """Aggregate report: services map (BC bool) + structured detail + degraded."""

    services: dict = field(default_factory=dict)         # name -> bool (BC)
    serviceDetail: dict = field(default_factory=dict)    # name -> ServiceHealth.to_dict()
    degraded: bool = False

    @property
    def all_ok(self) -> bool:
        return not self.degraded


class HealthChecker:
    """Checks every configured external service independently."""

    def __init__(self, *, config=None, acquisition=None, library=None, qbit=None):
        self.config = config if config is not None else get_config()
        self._acquisition = acquisition
        self._library = library
        self._qbit = qbit

    # ------------------------------------------------------------- deps
    def _acq(self):
        if self._acquisition is not None:
            return self._acquisition
        from services.acquisition import build_acquisition_service
        self._acquisition = build_acquisition_service(config=self.config)
        return self._acquisition

    def _lib(self):
        if self._library is not None:
            return self._library
        from services.library import build_library_service
        self._library = build_library_service(self.config)
        return self._library

    def _qbit_svc(self):
        if self._qbit is not None:
            return self._qbit
        from services.qbittorrent import QBittorrentService
        self._qbit = QBittorrentService(config=self.config)
        return self._qbit

    # ------------------------------------------------------------- check
    def check(self, *, include_tmdb: bool = True) -> HealthReport:
        report = HealthReport()

        # Acquisition backends (Radarr/Sonarr) via the facade (§43).
        acq = self._acq()
        acq_health = self._safe(lambda: acq.health() or {})

        radarr = ServiceHealth(
            "radarr", configured=bool(self.config.RADARR_API_KEY),
            ok=bool(self.config.RADARR_API_KEY) and bool(acq_health.get("radarr")),
            detail="configured" if self.config.RADARR_API_KEY else "not configured",
        )
        sonarr = ServiceHealth(
            "sonarr", configured=bool(self.config.SONARR_API_KEY),
            ok=bool(self.config.SONARR_API_KEY) and bool(acq_health.get("sonarr")),
            detail="configured" if self.config.SONARR_API_KEY else "not configured",
        )

        # Library providers (Plex/Emby) — one abstraction, per-provider health.
        plex = ServiceHealth(
            "plex", configured=bool(self.config.PLEX_URL and self.config.PLEX_TOKEN),
            detail="configured" if (self.config.PLEX_URL and self.config.PLEX_TOKEN) else "not configured",
        )
        emby = ServiceHealth(
            "emby", configured=self.config.has_emby(),
            detail="configured" if self.config.has_emby() else "not configured",
        )
        lib = self._lib()
        for p in lib.providers:
            h = self._safe(lambda: p.health(), default=False)
            if p.name == "plex":
                plex.ok = bool(h)
            elif p.name == "emby":
                emby.ok = bool(h)

        # qBittorrent.
        qbit = ServiceHealth("qbit", configured=True)
        qbit.ok = bool(self._safe(lambda: self._qbit_svc().health(), default=False))

        # TMDB (config-only presence, not pinged — thin check).
        tmdb = ServiceHealth(
            "tmdb", configured=self.config.has_tmdb(),
            ok=bool(self.config.has_tmdb()),
            detail="configured" if self.config.has_tmdb() else "not configured",
        )
        jellyfin = ServiceHealth(
            "jellyfin", configured=self.config.has_jellyfin(),
            ok=bool(self.config.has_jellyfin()),
            detail="configured" if self.config.has_jellyfin() else "not configured",
        )

        healths = {
            "radarr": radarr, "sonarr": sonarr, "plex": plex, "emby": emby,
            "qbit": qbit, "tmdb": tmdb, "jellyfin": jellyfin,
        }
        if not include_tmdb:
            healths.pop("tmdb", None)
            healths.pop("jellyfin", None)

        # Aggregate: services bool map + structured detail + degraded flag.
        for name, h in healths.items():
            report.services[name] = h.ok
            report.serviceDetail[name] = h.to_dict()
            if h.configured and not h.ok:
                report.degraded = True

        return report

    @staticmethod
    def _safe(fn, default=None):
        try:
            return fn()
        except Exception as e:
            logger.warning("health check failed: %s", e)
            return default


def check_health(**kw) -> HealthReport:
    """Module-level convenience."""
    return HealthChecker(**kw).check()