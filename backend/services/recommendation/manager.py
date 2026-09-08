"""Recommendation manager (spec §21 Phase 12).

Orchestrates the full recommendation pipeline:

    Candidate sources -> normalize -> apply criteria -> dedupe ->
    check library -> check active watchlist -> check recommendation history ->
    rank -> persist

The manager wires the generator + criteria engine + ranker, plus DI-injectable
library/watchlist checks and a recommendation-history repository. Each stage
reports counts so the daily job result matches the spec §25 shape.

Idempotency (spec §1.5 / §43): re-running with the same library/watchlist/history
never re-adds a title already present or already recommended.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from domain.enums import MediaType
from services.recommendation.criteria import (
    CriteriaEngine,
    CriteriaResult,
    RecommendationCandidate,
)
from services.recommendation.generator import CandidateGenerator

logger = logging.getLogger("rkm.recommendation.manager")


@dataclass
class RecommendationRunResult:
    """Outcome of one manager run (spec §25 job-result shape)."""

    status: str = "success"
    candidates: int = 0
    passed_criteria: int = 0
    already_in_library: int = 0
    already_recommended: int = 0
    watchlist_duplicates: int = 0
    new_recommendations: int = 0
    recommended: list = field(default_factory=list)  # list[RankedCandidate]
    error: Optional[str] = None


class RecommendationManager:
    """The canonical recommendation pipeline (spec §21/§24)."""

    def __init__(self, *, generator=None, criteria=None, library=None,
                 watchlist=None, history=None, config=None):
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        self.generator = generator if generator is not None else CandidateGenerator(config=self.config)
        self.criteria = criteria if criteria is not None else CriteriaEngine()
        self._library = library
        self._watchlist = watchlist
        self._history = history  # See note in _history_repo().

    # ------------------------------------------------------------- deps
    def _history_repo(self):
        """Lazily build the history repository (persistence seam, §23)."""
        if self._history is not None:
            return self._history
        from infrastructure.database.repository import build_repository
        self._history = build_repository()
        return self._history

    def _check_library(self, cand: RecommendationCandidate) -> bool:
        """True if already in the media library (library = authority, §1.2)."""
        if self._library is None:
            return False
        from domain.identity import MediaIdentity
        identity = MediaIdentity(
            media_type=cand.media_type,
            tmdb_id=cand.tmdb_id or None,
            imdb_id=cand.imdb_id or None,
        )
        try:
            owner = self._library
            has = owner.has(identity, title=cand.title, year=cand.year) \
                if hasattr(owner, "has") else False
            return bool(has)
        except Exception as e:
            logger.warning("manager: library check failed: %s", e)
            return False

    def _check_watchlist(self, cand: RecommendationCandidate) -> bool:
        """True if already on the active watchlist (pending)."""
        wl = self._watchlist
        if wl is None:
            return False
        try:
            if hasattr(wl, "find_by_imdb") and cand.imdb_id:
                return wl.find_by_imdb(cand.imdb_id) is not None
            if hasattr(wl, "find_by_tmdb") and cand.tmdb_id:
                return wl.find_by_tmdb(cand.tmdb_id) is not None
        except Exception as e:
            logger.warning("manager: watchlist check failed: %s", e)
        return False

    def _check_history(self, cand: RecommendationCandidate) -> bool:
        """True if this media_id was previously persisted as recommended (§23)."""
        try:
            repo = self._history_repo()
            seen = repo.list_recommendation_history(limit=1000)
            mid = cand.media_id
            return any(h.get("media_id") == mid for h in seen)
        except Exception as e:
            logger.warning("manager: history check failed: %s", e)
            return False

    # ------------------------------------------------------------- run
    def run(self, *, category: str = "", count: int = 20,
            media_type: Optional[MediaType] = None,
            persist_recommendations: bool = True,
            max_persist: int = 5) -> RecommendationRunResult:
        """Execute the pipeline for a category (or a specific media_type)."""
        result = RecommendationRunResult()
        try:
            # 0. Seen-set: candidates already evaluated on a prior run are skipped
            #    BEFORE criteria/Plex so re-runs don't reprocess the same TMDB
            #    popular titles (spec §23 history; every candidate is recorded).
            repo = self._history_repo()
            seen = {h.get("media_id") for h in
                    repo.list_recommendation_history(limit=1000)}

            # 1. Candidate sources -> normalize (generator owns sourcing).
            if media_type is not None:
                cand_all = self.generator.candidates(
                    category=category, count=count, media_type=media_type)
            else:
                cand_all = (self.generator.candidates(category=category, count=count,
                                                      media_type=MediaType.MOVIE)
                            + self.generator.candidates(category=category, count=count,
                                                        media_type=MediaType.TV))
            result.candidates = len(cand_all)

            decision: dict[str, str] = {}  # media_id -> reason seen/criteria/library/etc.
            passing: list[tuple[RecommendationCandidate, CriteriaResult]] = []
            for cand in cand_all:
                # 2. Seen-set dedup (cheap) — skip, don't re-evaluate.
                if cand.media_id in seen:
                    result.already_recommended += 1
                    decision[cand.media_id] = "seen"
                    continue
                decision[cand.media_id] = "criteria_fail"
                res = self.criteria.evaluate(cand)
                if res.passed:
                    passing.append((cand, res))
            result.passed_criteria = len(passing)

            survivors = []
            for cand, res in passing:
                # 3. Library check (exclude available) — library always wins.
                if self._check_library(cand):
                    decision[cand.media_id] = "in_library"
                    result.already_in_library += 1
                    continue
                # 4. Watchlist duplicate check.
                if self._check_watchlist(cand):
                    decision[cand.media_id] = "on_watchlist"
                    result.watchlist_duplicates += 1
                    continue
                decision[cand.media_id] = "recommended"
                survivors.append((cand, res))

            # 5. Rank survivors by score.
            from services.recommendation.ranker import rank
            ranked = rank(survivors, limit=None)
            result.recommended = ranked
            result.new_recommendations = len(ranked)

            # 6. Persist recommendation history for every NEWLY-seen candidate
            #    (with its reason) so future runs skip it (§23). Idempotent upsert.
            if persist_recommendations:
                self._persist(decision, ranked, max_persist, seen)

        except Exception as e:
            logger.exception("recommendation manager run failed")
            result.status = "error"
            result.error = str(e)
        return result

    def _persist(self, decisions: dict, ranked, max_persist: int, seen: set) -> None:
        """Persist recommendation history (spec §23) for every NEWLY-seen candidate.

        ``decisions`` maps media_id -> why it was handled (criteria_fail /
        in_library / on_watchlist / recommended / seen). Candidates already in
        ``seen`` were recorded on a prior run and are skipped. Ranked survivors
        carry their score. This is what makes the seen-set dedup idempotent:
        once a media_id is recorded, future runs skip it.
        """
        repo = self._history_repo()
        scores = {r.candidate.media_id: r.score for r in ranked}
        for mid, decision in decisions.items():
            if mid in seen:
                continue  # previously recorded — no need to rewrite
            try:
                is_ranked = decision == "recommended"
                repo.record_recommendation(
                    media_id=mid,
                    decision=decision,
                    score=float(scores.get(mid, 0.0)) if is_ranked else 0.0,
                    payload={"decision": decision},
                )
            except Exception as e:
                logger.warning("manager: persist history failed for %s: %s",
                               mid, e)