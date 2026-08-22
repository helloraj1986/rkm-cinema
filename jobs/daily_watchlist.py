"""Daily recommendation job (spec §24/§25 Phase 13).

Generates new watchlist recommendations each run:

    start job -> load criteria -> fetch candidates -> normalize -> dedupe ->
    library check -> watchlist check -> history check -> rank -> persist
    recommendations -> add survivors to the watchlist -> record job_run

Idempotent (spec §1.5/§24 "safe to execute repeatedly"): the manager's
library/watchlist/history gates ensure a title already present or already
recommended is never re-added. Only NEW survivors flow into the watchlist.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from jobs.base import JobResult

logger = logging.getLogger("rkm.jobs.daily_watchlist")


@dataclass
class DailyWatchlistJob:
    """Runs the recommendation pipeline and adds new picks to the watchlist."""

    manager = None       # RecommendationManager (built lazily)
    adder = None         # callable(candidate, score) -> adds a watchlist entry

    def __init__(self, *, manager=None, adder=None, config=None,
                 candidates=None, category="", count=20):
        self._manager = manager
        self._adder = adder
        self._config = config
        self.candidates = candidates      # optional pre-fetched candidate list
        self.category = category
        self.count = count

    # ------------------------------------------------------------- deps
    def _mgmt(self):
        if self._manager is not None:
            return self._manager
        from services.recommendation import RecommendationManager
        self._manager = RecommendationManager(config=self._config)
        return self._manager

    def _add(self, cand, score) -> bool:
        """Add a ranked recommendation to the watchlist (via injected adder or
        the canonical RecommendationService enrichment+add path)."""
        if self._adder is not None:
            return bool(self._adder(cand, score))
        from services.recommendations import RecommendationService
        svc = RecommendationService(config=self._config)
        legacy = _to_legacy_candidate(cand)
        try:
            entry = svc.process_recommendation(legacy)
            return entry is not None
        except Exception as e:
            logger.warning("daily: add %s failed: %s", cand.title, e)
            return False

    # ------------------------------------------------------------- run
    def run(self) -> JobResult:
        mgr = self._mgmt()
        result = mgr.run(category=self.category, count=self.count,
                         persist_recommendations=True)
        if result.status == "error":
            return JobResult(name="daily_watchlist", status="error",
                             error=result.error, counts=result.counts if hasattr(result, "counts") else {})

        added = 0
        for ranked in result.recommended:
            if self._add(ranked.candidate, ranked.score):
                added += 1

        return JobResult(
            name="daily_watchlist",
            status="success",
            items_processed=added,
            counts={
                "candidates": result.candidates,
                "passed_criteria": result.passed_criteria,
                "already_in_library": result.already_in_library,
                "watchlist_duplicates": result.watchlist_duplicates,
                "already_recommended": result.already_recommended,
                "new_recommendations": result.new_recommendations,
                "watchlist_added": added,
            },
        )


def _to_legacy_candidate(cand):
    """Map a RecommendationCandidate to the legacy Candidate shape the
    enrichment/add path expects (canonical ids preserved)."""
    from services.recommendations import Candidate
    return Candidate(
        title=cand.title,
        year=cand.year or 0,
        category=cand.category or "Other",
        lang=cand.lang or "English",
        imdb=cand.imdb,
        rt=cand.rt,
        is_series=(cand.media_type.value == "tv"),
        imdb_id=cand.imdb_id or "",
        tmdb_id=cand.tmdb_id or 0,
        director="",
        cast=[],
        snippet=cand.snippet or "",
        poster=cand.poster or "",
    )


def run_daily_watchlist(*, candidates=None, category="", count=20, **kw) -> JobResult:
    """Module-level convenience: build + run the daily job (records job_run)."""
    from jobs.base import run_job
    job = DailyWatchlistJob(candidates=candidates, category=category,
                            count=count, **kw)
    return run_job("daily_watchlist", job.run)