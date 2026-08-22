"""Jobs package (spec §24-§26 Phase 13).

Stable, idempotent job commands that the API container or host cron invokes
(spec §40: host cron should invoke a stable job command, not contain business
logic). Each job records its run in the ``job_runs`` table via the repository
seam, so ``GET /api/jobs`` shows a full history and failures are visible.

Jobs:
- ``daily_watchlist`` — recommendation generation (feeds RecommendationManager)
- ``reconcile``        — frequent acquisition/library reconcile (statuses only,
                         never generates new recommendations)
"""
from jobs.base import JobResult, JobRunner, run_job, last_job_runs
from jobs.daily_watchlist import DailyWatchlistJob, run_daily_watchlist
from jobs.reconcile import ReconcileJob, run_reconcile

__all__ = [
    "JobResult",
    "JobRunner",
    "run_job",
    "last_job_runs",
    "DailyWatchlistJob",
    "run_daily_watchlist",
    "ReconcileJob",
    "run_reconcile",
]