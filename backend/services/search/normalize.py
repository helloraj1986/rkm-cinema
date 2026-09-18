"""Title normalization and year compatibility — the two primitives every search
scorer needs (SEARCH_IMPROVEMENT_PLAN Phase 0).

Split out of :mod:`services.search.scoring` so that ``scoring`` and ``fuzzy`` can
both use them without importing each other. ⚠ There is ONE implementation of
each: a second ``normalize_title`` is exactly the kind of duplicate rule this
codebase's architecture exists to prevent (ARCHITECTURE §0, rule 1).
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["YEAR_MISMATCH_FACTOR", "normalize_title", "year_factor"]

_NON_WORD = re.compile(r"[^0-9A-Za-z]+")
_SPACES = re.compile(r"\s+")

#: Both years known and DIFFERENT — a same-name remake is a different work, so it
#: is heavily discounted… but ⚠ **not zeroed**: an owned "Dune" (1984) should
#: still be *offered* for the query "dune 2021", ranked below the 2021 one. The
#: discrete ``title_match_score`` keeps its historical hard zero; the continuous
#: scorer deliberately does not — the plan's rule that "a slightly off year
#: shouldn't zero out an otherwise-perfect title match".
YEAR_MISMATCH_FACTOR = 0.45


def normalize_title(raw: Any) -> str:
    """Case/punctuation-insensitive key (``"3 Body Problem:"`` → ``"3 body problem"``)."""
    s = _NON_WORD.sub(" ", str(raw or "")).strip().lower()
    return _SPACES.sub(" ", s)


def year_factor(query_year: int | None, title_year: Any) -> float:
    """Multiplier for a title match given both years.

    Unknown on EITHER side is neutral (1.0) — the app must not punish a title for
    metadata the library did not carry, which is exactly the bug that hid the
    real *Sholay* on 2026-09-13.
    """
    try:
        y1 = int(query_year) if query_year is not None else None
        y2 = int(title_year) if title_year is not None else None
    except (TypeError, ValueError):
        return 1.0
    if y1 is None or y2 is None:
        return 1.0
    return 1.0 if y1 == y2 else YEAR_MISMATCH_FACTOR
