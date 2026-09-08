"""Recommendation package (spec §21-§25 Phase 12).

Separates recommendation *generation* from media *reconciliation*. The pipeline:

    generator (candidate sources) -> criteria (PASS/FAIL + reasons) ->
    dedupe -> library check -> watchlist check -> history check -> rank -> persist

Modules:
- ``criteria.py``  — CriteriaEngine (config-driven gates + scoring, spec §22)
- ``generator.py`` — CandidateGenerator (sources candidates, normalizes, spec §21)
- ``ranker.py``    — rank() by score (spec §21)
- ``manager.py``   — RecommendationManager (orchestrates the pipeline, spec §21/§24)
"""
from services.recommendation.criteria import (
    CriteriaEngine,
    CriteriaResult,
    RecommendationCandidate,
    RecommendationCriteria,
)
from services.recommendation.generator import CandidateGenerator, CandidateSource
from services.recommendation.ranker import RankedCandidate, rank, rank_tuples
from services.recommendation.manager import RecommendationManager, RecommendationRunResult

__all__ = [
    "CriteriaEngine",
    "CriteriaResult",
    "RecommendationCandidate",
    "RecommendationCriteria",
    "CandidateGenerator",
    "CandidateSource",
    "RankedCandidate",
    "rank",
    "rank_tuples",
    "RecommendationManager",
    "RecommendationRunResult",
]