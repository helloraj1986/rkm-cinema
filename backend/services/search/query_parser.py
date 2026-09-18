"""Query understanding — SEARCH_IMPROVEMENT_PLAN Phase 3.

IMDb-style search understands ``"tom hanks movies 1994"`` as *person=Tom Hanks,
type=movie, year=1994*, not as one literal string to substring-match. Before this
module every query went into the scorer and into ``TMDBService.search_multi`` as a
single blob, so a query with any structure in it matched almost nothing — the
literal string ``"tom hanks movies 1994"`` appears in no title anywhere.

Three extractions, in the order that matters:

1. **year / decade** — ``"1994"``, ``"1990s"``, ``"90s"``. ⚠ A bare decade is
   ambiguous in English, so it follows the convention films are discussed in:
   ``90s`` → 1990s, ``80s`` → 1980s, ``30s`` → 1930s, but ``20s`` → 2020s and
   ``00s`` → 2000s. The cut is at ``3`` — nobody searching a media library for
   "20s" means the 1920s.
2. **media type** — ``movie``/``film``/``films`` → movie, ``show``/``series``/
   ``tv``/``episode`` → tv.
3. **person** — only when the caller supplies a candidate list of names. ⚠ It is
   NOT removed from the remaining terms: the plan's own example still wants to
   search the library for "tom hanks" while also using him as a drill-down hint.

Pure: no I/O, no config. ``rapidfuzz`` is optional (the person step simply finds
nothing without it) so the year/type extraction always works.

⚠ The extracted values are NOT filters. They are passed to the scorer as a
penalty/boost so that an off-by-one year cannot zero out an otherwise-perfect
title match — the plan's explicit rule, and the same mistake that hid the real
*Sholay* on 2026-09-13.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from services.search.normalize import normalize_title

logger = logging.getLogger("rkm.search.query")

__all__ = ["ParsedQuery", "best_person_match", "parse_query"]

#: ``1994`` — a full four-digit year.
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

#: ``1990s`` / ``2020s``.
FULL_DECADE_RE = re.compile(r"\b(19|20)\d0s\b")

#: ``90s`` / ``'90s`` / ``00s``. Applied only after the two above, because
#: ``"1990s"`` would otherwise be read as the decade ``"90s"`` AND the year 1990.
SHORT_DECADE_RE = re.compile(r"\b'?(\d)0s\b")

#: Word → media type. Matched on WORD BOUNDARIES: ``"tv"`` must not fire inside
#: ``"TVs"`` of a title, and ``"series"`` must not fire inside "Series 7".
TYPE_HINTS: dict[str, str] = {
    "movie": "movie", "movies": "movie", "film": "movie", "films": "movie",
    "show": "tv", "shows": "tv", "series": "tv", "tv": "tv",
    "episode": "tv", "episodes": "tv",
}
_TYPE_RE = re.compile(r"\b(" + "|".join(sorted(TYPE_HINTS, key=len, reverse=True)) + r")\b")

#: A person is only offered as a hint when the match is this strong, so a title
#: that merely resembles a name is never silently re-read as one.
PERSON_MATCH_THRESHOLD = 80


def _decade_bounds(tens: int, century: int | None = None) -> tuple[int, int]:
    """``(start, end)`` for a decade, applying the English "20s" convention."""
    if century is not None:
        start = century * 100 + tens * 10
    elif tens >= 3:
        start = 1900 + tens * 10
    else:
        start = 2000 + tens * 10
    return start, start + 9


@dataclass
class ParsedQuery:
    """What the user's text actually asked for."""

    raw: str
    #: The free text that is left once year/decade/type words are removed. This is
    #: what titles are matched against.
    title_terms: str
    year: int | None = None
    year_range: tuple[int, int] | None = None
    media_type: str | None = None
    person_hint: str | None = None

    @property
    def has_filters(self) -> bool:
        """True when the query carried structure beyond free text."""
        return bool(self.year or self.year_range or self.media_type or self.person_hint)

    @property
    def scoring_query(self) -> str:
        """The text to SCORE with — the stripped terms, else the raw query.

        ⚠ Falls back to ``raw`` rather than to ``""``: a query that is nothing but
        a year (``"1994"``) still has to match something, and ``""`` scores 0
        against every row, which would silently turn a real query into an
        alphabetical list.
        """
        return self.title_terms or self.raw

    def matches_year(self, other: int | None) -> bool | None:
        """Is ``other`` inside what the query asked for? ``None`` when it cannot be told.

        ``None`` means "no opinion" — either the query named no year, or the row
        carries none. Callers must treat that as neutral, never as a mismatch:
        punishing a row for metadata the library did not carry is the bug that
        hid the real *Sholay*.
        """
        if other is None:
            return None
        try:
            y = int(other)
        except (TypeError, ValueError):
            return None
        if self.year is not None:
            return y == self.year
        if self.year_range is not None:
            return self.year_range[0] <= y <= self.year_range[1]
        return None


def best_person_match(text: str, names: list[str] | None,
                      threshold: int = PERSON_MATCH_THRESHOLD) -> str | None:
    """The name in ``names`` that ``text`` most likely refers to, else ``None``.

    Returns the name in its ORIGINAL spelling (what the UI shows), not the
    normalised key it was compared on.
    """
    if not text or not names:
        return None
    try:
        from rapidfuzz import fuzz, process
    except ImportError:  # pragma: no cover - optional dependency
        return None
    keys = [normalize_title(n) for n in names if n]
    if not keys:
        return None
    match = process.extractOne(normalize_title(text), keys, scorer=fuzz.WRatio)
    if not match or match[1] < threshold:
        return None
    try:
        return names[keys.index(match[0])]
    except (ValueError, IndexError):  # pragma: no cover - defensive
        return None


def parse_query(q: str, known_people: list[str] | None = None) -> ParsedQuery:
    """Split ``q`` into free text plus whatever intent it carried.

    ⚠ Order matters and is asserted by the tests: the FULL decade is read before
    the bare year, and both before the short decade. Reading ``"1990s"`` as the
    year 1990 (which the naive order does) would turn a decade browse into a
    single-year search.
    """
    raw = str(q or "")
    remaining = raw

    year: int | None = None
    year_range: tuple[int, int] | None = None

    if m := FULL_DECADE_RE.search(remaining):
        tens = int(m.group(0)[2])
        year_range = _decade_bounds(tens, int(m.group(0)[:2]))
        remaining = remaining.replace(m.group(0), " ")
    elif m := YEAR_RE.search(remaining):
        year = int(m.group(0))
        remaining = remaining.replace(m.group(0), " ")
    elif m := SHORT_DECADE_RE.search(remaining):
        year_range = _decade_bounds(int(m.group(1)))
        remaining = remaining.replace(m.group(0), " ")

    media_type: str | None = None
    if m := _TYPE_RE.search(remaining.lower()):
        media_type = TYPE_HINTS[m.group(1)]
        # Replace only the FIRST occurrence — a title may legitimately contain the
        # word ("The TV Set") and stripping every one would mangle it.
        remaining = remaining[:m.start()] + " " + remaining[m.end():]

    title_terms = " ".join(remaining.split())
    person_hint = best_person_match(title_terms, known_people)

    return ParsedQuery(raw=raw, title_terms=title_terms, year=year, year_range=year_range,
                       media_type=media_type, person_hint=person_hint)
