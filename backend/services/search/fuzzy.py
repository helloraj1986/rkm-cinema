"""Typo-tolerant matching — SEARCH_IMPROVEMENT_PLAN Phase 1.

**Why this is the highest-impact phase.** Before it, owned-library matching was a
normalised substring test, so ``"the dark knght"`` and ``"schwarzeneger"``
returned *nothing* from the one source that should be the strongest and most
confident: your own library. TMDB's API has some tolerance of its own, so the
external half of a search was more forgiving than the half made of files you
already have — backwards.

The library is `rapidfuzz` (MIT, C-accelerated, ~10x ``python-Levenshtein`` for
this workload).

Two entry points, because the two jobs are genuinely different:

* :func:`fuzzy_title_score` — whole titles. ``WRatio`` covers typos and length
  differences; ``token_sort_ratio`` covers word order (``"knight dark"`` vs
  ``"dark knight"``). Capped at ``FUZZY_CEILING`` so a near-miss can never
  outrank an exact or prefix hit for the same query.
* :func:`fuzzy_name_score` — PEOPLE. ``partial_ratio`` on purpose: a person is
  matched by a fragment far more often than by a full name (``"pacino"`` must
  find ``"Al Pacino"``, ``"nolan"`` must find ``"Christopher Nolan"``).

⚠ A short query is never fuzzed. Two or three characters are within typo
distance of a large fraction of the alphabet, so fuzzy matching below
``MIN_FUZZY_LEN`` would turn "th" into "every title containing t and h" — noise
presented as relevance. Short queries are served by the prefix path instead
(Phase 4).
"""

from __future__ import annotations

import logging
from typing import Any

from services.search.normalize import normalize_title, year_factor

logger = logging.getLogger("rkm.search.fuzzy")

__all__ = ["FUZZY_CEILING", "FUZZY_FLOOR", "MIN_FUZZY_LEN", "fuzzy_name_score", "fuzzy_title_score"]

#: Below this the input is too short to distinguish a typo from a different word.
MIN_FUZZY_LEN = 3

#: ⚠ The cap that keeps the tiers honest: even a 100/100 fuzzy ratio (0.85 here)
#: ranks BELOW a containment (0.75)? No — below exact (1.0) and prefix (0.9).
#: Do not raise this above 0.9 without revisiting ``title_relevance``'s ordering.
FUZZY_CEILING = 0.85

#: Results under this are dropped rather than ranked. Start value from the plan;
#: it is the knob the Phase 7 metrics loop retunes.
FUZZY_FLOOR = 0.55

_RATIO_SCALE = FUZZY_CEILING

try:  # pragma: no cover - the import is the only branch worth skipping
    from rapidfuzz import fuzz

    _AVAILABLE = True
except ImportError:  # pragma: no cover
    fuzz = None  # type: ignore[assignment]
    _AVAILABLE = False
    logger.warning(
        "rapidfuzz is not installed — search falls back to exact/prefix/containment only. "
        "Typo tolerance is OFF. Add `rapidfuzz` to backend/requirements.txt."
    )


def available() -> bool:
    """Whether typo tolerance is switched on in this process."""
    return _AVAILABLE


def _combine(score: float, query_year: int | None, title_year: Any) -> float:
    """Apply the year factor and the floor, in ONE place for both entry points."""
    if score <= 0.0:
        return 0.0
    scored = score * year_factor(query_year, title_year)
    return scored if scored >= FUZZY_FLOOR else 0.0


def fuzzy_title_score(query: str, candidate: Any, *, query_year: int | None = None,
                      title_year: Any = None) -> float:
    """0.0–``FUZZY_CEILING`` relevance for a near-miss TITLE, else 0.0.

    Returns 0.0 (never a guess) when the dependency is absent, the query is too
    short to fuzz, or the best ratio sits below ``FUZZY_FLOOR``.

    Exact and prefix cases short-circuit to their tier values so callers that use
    this alone (not through ``title_relevance``) still get the right ordering.
    """
    if not _AVAILABLE:
        return 0.0
    q = normalize_title(query)
    c = normalize_title(candidate)
    if not q or not c or len(q) < MIN_FUZZY_LEN:
        return 0.0
    if q == c:
        return _combine(1.0, query_year, title_year)
    if c.startswith(q):
        return _combine(0.9, query_year, title_year)
    # token_sort_ratio handles word-order differences ("knight dark" vs "dark knight");
    # WRatio handles typos, partial matches and length differences.
    ratio = fuzz.WRatio(q, c) / 100.0
    token_ratio = fuzz.token_sort_ratio(q, c) / 100.0
    return _combine(max(ratio, token_ratio) * _RATIO_SCALE, query_year, title_year)


def fuzzy_name_score(query: str, candidate: Any) -> float:
    """0.0–``FUZZY_CEILING`` relevance for a near-miss PERSON name, else 0.0.

    ⚠ ``partial_ratio``, not ``WRatio``: it scores the query against the best
    matching SUBSTRING of the candidate, which is what makes ``"pacino"`` →
    ``"Al Pacino"`` and ``"schwarzeneger"`` → ``"Arnold Schwarzenegger"`` work.
    A whole-string ratio would score both of those near zero and re-introduce the
    bug this phase exists to fix.
    """
    if not _AVAILABLE:
        return 0.0
    q = normalize_title(query)
    c = normalize_title(candidate)
    if not q or not c or len(q) < MIN_FUZZY_LEN:
        return 0.0
    if q == c or q in c:
        return 0.9
    # ⚠ The floor applies HERE too, not only on the title path: ``partial_ratio``
    # is substring-sensitive by design, so it reports ~0.24 for "pacino" against
    # "Meryl Streep" — real number, meaningless match. Without the floor a query
    # would come back carrying every actor in the library.
    score = (fuzz.partial_ratio(q, c) / 100.0) * _RATIO_SCALE
    return score if score >= FUZZY_FLOOR else 0.0
