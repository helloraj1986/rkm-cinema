"""Jobs endpoint (spec §17 Phase 10).

Reads recent scheduled-job runs from the job_runs persistence table through
the repository seam. The jobs themselves run in Phase 13/14; this route exposes
whatever runs were recorded. LAN-free — the repository handles storage.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

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