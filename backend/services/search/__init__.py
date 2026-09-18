"""Search relevance — the shared scorer, typo tolerance and query understanding.

SEARCH_IMPROVEMENT_PLAN: relevance logic lives HERE, once, instead of being
spread across the two endpoints that happen to need it.

⚠ Deliberately NOT re-exported from ``services/__init__.py``: the parent package
eagerly imports every service (Radarr, Sonarr, Jellyfin, …) and this one must
stay importable on its own, by pure unit tests with no config and no network.
"""
from services.search.normalize import YEAR_MISMATCH_FACTOR, normalize_title, year_factor
from services.search.scoring import (
    EXACT_TITLE_SCORE,
    FieldWeight,
    ScoredResult,
    best_relevance,
    owned_strong_match,
    row_fields,
    score_item,
    title_match_score,
    title_relevance,
)

__all__ = [
    "EXACT_TITLE_SCORE",
    "FieldWeight",
    "ScoredResult",
    "YEAR_MISMATCH_FACTOR",
    "best_relevance",
    "normalize_title",
    "owned_strong_match",
    "row_fields",
    "score_item",
    "title_match_score",
    "title_relevance",
    "year_factor",
]
