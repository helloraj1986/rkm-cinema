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

⚠ **Two guards exist to stop typo tolerance decaying into "everything matches
everything"**, both measured rather than guessed:

1. ``MIN_FUZZY_LEN`` — a 2-character query is within typo distance of a large
   fraction of the alphabet. Short queries are served by the prefix path instead
   (Phase 4).
2. ``MIN_LENGTH_RATIO`` — **a typo barely changes the length of a title.** So a
   4-character query is not a mistyping of a 28-character one; it is a different
   string that happens to share a fragment. Without this guard ``"dune"`` scored
   0.67 against *A Completely Unrelated Film* (``WRatio`` finds "uned" inside
   "unrelated"), and every search quietly returned the whole library.

Exact and prefix cases short-circuit to their tier values, so the tiers a caller
sees are the same whether it uses this module directly or goes through
``scoring.title_relevance``.
"""

from __future__ import annotations

import logging
from typing import Any

from services.search.normalize import normalize_title, year_factor

logger = logging.getLogger("rkm.search.fuzzy")

__all__ = ["FUZZY_CEILING", "FUZZY_FLOOR", "MIN_FUZZY_LEN", "MIN_LENGTH_RATIO",
           "available", "fuzzy_name_score", "fuzzy_title_score"]

#: Below this the input is too short to distinguish a typo from a different word.
MIN_FUZZY_LEN = 3

#: ⚠ How close in LENGTH two strings must be before a whole-string ratio is
#: trusted. A typo barely changes a title's length, so this is the cheapest and
#: most effective guard against substring-driven false positives. 0.6 admits
#: "knght"→"knight" (0.83), "the dark knght"→"the dark knight" (0.93) and
#: "schwarzeneger"→"schwarzenegger" (0.93), and rejects "dune"→"unrelated" (0.44).
MIN_LENGTH_RATIO = 0.6

#: ⚠ The cap that keeps the tiers honest: even a 100/100 fuzzy ratio is 0.85 here,
#: which is BELOW prefix (0.90) and ABOVE containment (≤0.80). Do not raise it
#: without revisiting ``scoring.title_relevance``'s documented ordering.
FUZZY_CEILING = 0.85

#: Results under this are dropped rather than ranked. Start value from the plan;
#: it is the knob the Phase 7 metrics loop retunes.
FUZZY_FLOOR = 0.55

#: A near-miss on ONE WORD of a title is weaker evidence than a near-miss on the
#: whole thing, so it is scaled down. Measured: "knght" → 0.70 against
#: "The Dark Knight", under the 0.82 a full-title typo earns.
TOKEN_QUERY_SCALE = 0.9

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


def _length_ratio(a: str, b: str) -> float:
    """Shorter/longer, 0.0–1.0. 1.0 means the two are the same length."""
    if not a or not b:
        return 0.0
    return min(len(a), len(b)) / max(len(a), len(b))


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

    Two shapes of near-miss are recognised:

    * the WHOLE title is mistyped or reordered (lengths must be comparable); and
    * ONE WORD of the title is mistyped (``"knght"`` for *The Dark Knight*), which
      needs its own comparison because the whole-string ratio is diluted by the
      words that match exactly.
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

    best = 0.0
    # (a) The whole string, when the two are plausibly the same words.
    if _length_ratio(q, c) >= MIN_LENGTH_RATIO:
        # token_sort_ratio handles word-order differences ("knight dark" vs "dark knight");
        # WRatio handles typos, partial matches and length differences.
        best = max(fuzz.WRatio(q, c), fuzz.token_sort_ratio(q, c)) / 100.0

    # (b) One word of the title, when the query is close to THAT word.
    for word in c.split():
        if len(word) < MIN_FUZZY_LEN or _length_ratio(q, word) < MIN_LENGTH_RATIO:
            continue
        best = max(best, (fuzz.WRatio(q, word) / 100.0) * TOKEN_QUERY_SCALE)

    return _combine(best * _RATIO_SCALE, query_year, title_year)


def fuzzy_name_score(query: str, candidate: Any) -> float:
    """0.0–``FUZZY_CEILING`` relevance for a near-miss PERSON name, else 0.0.

    ⚠ ``partial_ratio``, not ``WRatio``: it scores the query against the best
    matching SUBSTRING of the candidate, which is what makes ``"pacino"`` →
    ``"Al Pacino"`` and ``"schwarzeneger"`` → ``"Arnold Schwarzenegger"`` work.
    A whole-string ratio would score both of those near zero and re-introduce the
    bug this phase exists to fix.

    ⚠ The floor applies HERE too, not only on the title path: ``partial_ratio``
    is substring-sensitive by design, so it reports ~0.24 for ``"pacino"`` against
    ``"Meryl Streep"`` — a real number and a meaningless match. Without the floor a
    query would come back carrying every actor in the library.
    """
    if not _AVAILABLE:
        return 0.0
    q = normalize_title(query)
    c = normalize_title(candidate)
    if not q or not c or len(q) < MIN_FUZZY_LEN:
        return 0.0
    if q == c or q in c:
        return 0.9
    score = (fuzz.partial_ratio(q, c) / 100.0) * _RATIO_SCALE
    return score if score >= FUZZY_FLOOR else 0.0
