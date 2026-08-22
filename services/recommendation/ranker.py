"""Recommendation ranker (spec §21 Phase 12).

Ranks surviving candidates by their criteria score so the manager persists the
best N. Pure and tiny — ranking happens AFTER criteria/library/watchlist/history
filters, so ranker only orders what already passed the funnel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from services.recommendation.criteria import CriteriaResult, RecommendationCandidate


@dataclass
class RankedCandidate:
    candidate: RecommendationCandidate
    score: float
    result: CriteriaResult


def rank(candidates, limit: Optional[int] = None) -> list[RankedCandidate]:
    """Rank ``(candidate, CriteriaResult)`` by score desc (ties by vote count)."""
    ranked = [
        RankedCandidate(candidate=c, score=res.score, result=res)
        for c, res in candidates
    ]
    ranked.sort(key=lambda r: (r.score, r.candidate.vote_count), reverse=True)
    if limit is not None:
        ranked = ranked[:max(0, limit)]
    return ranked


def rank_tuples(candidates, limit=None) -> list[tuple[RecommendationCandidate, float]]:
    """Convenience returning [(candidate, score)] pairs."""
    return [(r.candidate, r.score) for r in rank(candidates, limit=limit)]