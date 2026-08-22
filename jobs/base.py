"""Job run helpers (spec §24/§40 Phase 13).

Wraps a job function with job_runs recording so every invocation is auditable
and failures are visible (spec "Job execution is recorded" / "Job failures are
visible"). Uses the repository seam — never touches the DB directly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from infrastructure.database.repository import build_repository

logger = logging.getLogger("rkm.jobs.base")


@dataclass
class JobResult:
    """Typed outcome of a job run."""

    name: str
    status: str = "success"          # success | error
    items_processed: int = 0
    counts: dict = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "items_processed": self.items_processed,
            "counts": self.counts,
            "error": self.error,
            "completed_at": datetime.utcnow().isoformat(),
        }


class JobRunner:
    """Records a job run around an arbitrary callable.

    ``fn`` returns a JobResult (or a value converted into one). On exception the
    run is still persisted with status=error + the message, so the API never
    loses a failed run.
    """

    def __init__(self, *, repository=None):
        self._repository = repository

    @property
    def repo(self):
        if self._repository is None:
            self._repository = build_repository()
        return self._repository

    def run(self, name: str, fn: Callable[..., JobResult], *args, **kwargs) -> JobResult:
        logger.info("job start: %s", name)
        try:
            result = fn(*args, **kwargs)
            if not isinstance(result, JobResult):
                result = JobResult(name=name, items_processed=result or 0)
            result.name = name
            self._record(name, result)
            logger.info("job done: %s status=%s processed=%s",
                        name, result.status, result.items_processed)
            return result
        except Exception as e:
            logger.exception("job failed: %s", name)
            result = JobResult(name=name, status="error", error=str(e))
            self._record(name, result)
            return result

    def _record(self, name: str, result: JobResult) -> None:
        try:
            self.repo.record_job_run(
                job_name=name,
                completed_at=datetime.utcnow().isoformat(),
                status=result.status,
                items_processed=int(result.items_processed or 0),
                error=result.error or "",
            )
        except Exception as e:
            logger.warning("job_runs write failed for %s: %s", name, e)


def run_job(name: str, fn: Callable[..., JobResult], *args, **kwargs) -> JobResult:
    """Module-level convenience: run + record a job."""
    return JobRunner().run(name, fn, *args, **kwargs)


def last_job_runs(*, name: Optional[str] = None, limit: int = 20) -> list[dict]:
    """Recent job_runs (optionally for one job) most-recent-first."""
    try:
        repo = build_repository()
        runs = repo.list_job_runs(limit=limit)
    except Exception as e:
        logger.warning("job_runs read failed: %s", e)
        runs = []
    if name:
        runs = [r for r in runs if r.get("job_name") == name]
    return runs