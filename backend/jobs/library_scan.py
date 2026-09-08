"""Daily / on-demand Jellyfin library scan job.

Triggers a full Jellyfin library refresh so media added to the library folders
is scanned and indexed on a cadence (once/day via the in-process scheduler),
even when nothing else asked for it. Also exposed as the on-demand
``POST /api/jobs/library_scan/run`` command, and callable from host cron.

Credential stays server-side (the provider owns Jellyfin specifics).
"""
from __future__ import annotations

import logging

from jobs.base import JobResult

logger = logging.getLogger("rkm.jobs.library_scan")


class LibraryScanJob:
    """Trigger a Jellyfin library refresh through the configured provider."""

    def __init__(self, *, config=None):
        self._config = config

    def _scan(self, cfg) -> bool:
        from services.library import build_library_service
        service = build_library_service(cfg)
        if service is None:
            return False
        for p in getattr(service, "providers", []):
            if hasattr(p, "refresh_library"):
                return bool(p.refresh_library())
        return False

    def run(self) -> JobResult:
        from config.settings import get_config
        cfg = self._config if self._config is not None else get_config()

        if not (cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY):
            # Not a Jellyfin-backed stack — nothing to scan; report cleanly.
            return JobResult(name="library_scan", status="success", items_processed=0,
                             counts={"jellyfin": False, "scanned": 0})
        ok = False
        try:
            ok = self._scan(cfg)
        except Exception as e:  # noqa: BLE001 - survive + record
            logger.warning("library_scan failed: %s", e)
            return JobResult(name="library_scan", status="error", items_processed=0,
                             counts={"jellyfin": True, "scanned": 0}, error=str(e))
        return JobResult(name="library_scan",
                         status="success" if ok else "error",
                         items_processed=1 if ok else 0,
                         counts={"jellyfin": True, "scanned": int(ok)},
                         error=None if ok else "Jellyfin library refresh failed")


def run_library_scan(*, config=None, **kw) -> JobResult:
    """Module-level convenience: build + run the library scan job (records job_run)."""
    from jobs.base import run_job
    return run_job("library_scan", LibraryScanJob(config=config).run)