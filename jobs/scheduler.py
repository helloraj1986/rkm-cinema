"""In-process job scheduler (spec §26 Phase 13/14).

Runs the two jobs on their cadences inside the API container (spec §40 prefers
container jobs over host ad-hoc cron):

- ``reconcile`` — every ``RECONCILE_INTERVAL_MIN`` minutes (default 10); keeps
  REQUESTED/DOWNLOADING/DOWNLOADED/AVAILABLE current, never generates recs.
- ``daily_watchlist`` — once per day at ``DAILY_JOB_HOUR`` (default 18); the
  recommendation generation job.

Opt-in: only starts when ``WATCHLIST_SCHEDULER=true`` (set in .env). Runs in a
daemon thread so it never blocks the API. Each invocation goes through the
JobRunner, so every run lands in ``job_runs`` and failures are visible.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Optional

from config.settings import get_config

logger = logging.getLogger("rkm.jobs.scheduler")


_ACTIVE: list[JobScheduler] = []  # holds a ref so the daemon thread isn't GC'd


class JobScheduler:
    """Background scheduler daemon. Safe to start multiple times (no-op 2nd)."""

    def __init__(self, *, config=None, run_reconcile=None, run_daily=None):
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        from jobs.reconcile import run_reconcile as _rr
        from jobs.daily_watchlist import run_daily_watchlist as _rd
        self._run_reconcile = run_reconcile or _rr
        self._run_daily = run_daily or _rd
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._enabled = bool(self.config.WATCHLIST_SCHEDULER)

    # ------------------------------------------------------------- control
    def start(self) -> bool:
        """Start the daemon loop if enabled. Returns True if it started."""
        if not self._enabled:
            return False
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="rkm-scheduler", daemon=True)
            self._thread.start()
        logger.info("scheduler started (reconcile=%dm, daily_hour=%d)",
                    self.config.RECONCILE_INTERVAL_MIN, self.config.DAILY_JOB_HOUR)
        return True

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------- loop
    def _loop(self) -> None:
        reconcile_iv = max(1, int(self.config.RECONCILE_INTERVAL_MIN or 10)) * 60
        last_reconcile = 0.0
        last_daily = -1  # -1 so the daily job can fire on the first matching hour

        while not self._stop.is_set():
            now = time.time()
            now_dt = datetime.now()

            # Frequent reconcile (from first start; no initial delay penalty).
            if now - last_reconcile >= reconcile_iv:
                logger.info("scheduler: running frequent reconcile")
                self._safe(lambda: self._run_reconcile())
                last_reconcile = now

            # Daily recommendation job once/day at the configured hour.
            if now_dt.hour == self.config.DAILY_JOB_HOUR and last_daily != now_dt.date().toordinal():
                logger.info("scheduler: running daily watchlist job")
                self._safe(lambda: self._run_daily())
                last_daily = now_dt.date().toordinal()

            self._stop.wait(min(30, reconcile_iv))

    @staticmethod
    def _safe(fn) -> None:
        try:
            fn()
        except Exception as e:
            logger.exception("scheduler job failed: %s", e)


def start_if_enabled(*, config=None) -> bool:
    """One-line bootstrap callable from app startup (spec §40)."""
    sched = JobScheduler(config=config)
    started = sched.start()
    if started:
        _ACTIVE.append(sched)
    return started