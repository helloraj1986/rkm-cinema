"""Jobs endpoint (spec §17 Phase 10, §24/§40 Phase 13).

Reads recent scheduled-job runs from the job_runs persistence table through
the repository seam, and provides a stable ``POST /api/jobs/{name}/run``
command the API container (or host cron) can invoke (spec §40: host cron
should call a stable job command, not contain business logic). The route is
thin — it delegates to the job modules in ``jobs/``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api.models import JobRunResponse, JobsResponse
from infrastructure.database.repository import build_repository

router = APIRouter()
logger = logging.getLogger("rkm.api.jobs")


@router.get("/jobs", response_model=JobsResponse)
def get_jobs(limit: int = 20):
    """Recent job_runs most-recent-first."""
    try:
        repo = build_repository()
        runs = repo.list_job_runs(limit=limit)
    except Exception as e:
        logger.warning("jobs: failed to read job_runs: %s", e)
        runs = []
    return JobsResponse(
        jobs=[
            JobRunResponse(
                jobName=r.get("job_name", ""),
                startedAt=r.get("started_at"),
                completedAt=r.get("completed_at"),
                status=r.get("status", ""),
                itemsProcessed=int(r.get("items_processed") or 0),
                error=r.get("error"),
            )
            for r in runs
        ]
    )


@router.post("/jobs/{name}/run")
def run_job_endpoint(name: str):
    """Run a known job command by name and return its recorded result.

    Supported names: ``daily_watchlist`` (recommendation generation) and
    ``reconcile`` (frequent status reconcile). Returns the JobResult shape.
    """
    from jobs.daily_watchlist import run_daily_watchlist
    from jobs.reconcile import run_reconcile
    from jobs.add_watchlist import run_add_watchlist
    from jobs.library_scan import run_library_scan

    jobs = {
        "daily_watchlist": run_daily_watchlist,
        "reconcile": run_reconcile,
        "add_watchlist": run_add_watchlist,
        "library_scan": run_library_scan,
    }
    fn = jobs.get(name)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"Unknown job: {name}")
    result = fn()
    return result.to_dict()