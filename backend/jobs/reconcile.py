"""Frequent reconcile job (spec §26 Phase 13).

Re-runs acquisition/library reconciliation to keep statuses current
(REQUESTED / DOWNLOADING / DOWNLOADED / AVAILABLE) — WITHOUT generating new
recommendations. Runs far more often than the daily recommendation job
(spec §26: daily = generation; every 5-15 min = reconcile).

Idempotent: it only reads + reconciles state; it never writes new watchlist
entries.
"""
from __future__ import annotations

import logging
import uuid

from jobs.base import JobResult
from core.logging import log_event

logger = logging.getLogger("rkm.jobs.reconcile")


class ReconcileJob:
    """Reconciles watchlist statuses via the canonical Reconciler."""

    def __init__(self, *, reconciler=None, config=None):
        self._reconciler = reconciler
        self._config = config

    def _rec(self):
        if self._reconciler is not None:
            return self._reconciler
        from services.reconciliation import Reconciler
        self._reconciler = Reconciler(config=self._config)
        return self._reconciler

    def run(self) -> JobResult:
        job_id = str(uuid.uuid4())
        log_event(logger, "reconciliation.start", job_id=job_id)
        rec = self._rec()
        result = rec.compute()

        # Tally statuses across entries (informational counts only).
        from domain.enums import MediaStatus
        status_counts: dict[str, int] = {}
        for snap in result.snapshots.values():
            key = getattr(snap, "status", None)
            val = key.value if isinstance(key, MediaStatus) else str(key or "unknown")
            status_counts[val] = status_counts.get(val, 0) + 1

        log_event(logger, "reconciliation.complete", job_id=job_id,
                  snapshots_count=len(result.snapshots), indexer_issue=bool(result.indexer_issue))
        return JobResult(
            name="reconcile",
            status="success",
            items_processed=len(result.snapshots),
            counts={**status_counts, "indexer_issue": bool(result.indexer_issue)},
        )


def run_reconcile(*, reconciler=None, config=None, **kw) -> JobResult:
    """Module-level convenience: build + run the reconcile job (records job_run)."""
    from jobs.base import run_job
    job = ReconcileJob(reconciler=reconciler, config=config)
    return run_job("reconcile", job.run)