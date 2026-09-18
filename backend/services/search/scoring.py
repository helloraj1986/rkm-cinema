"""The ONE relevance scorer for search (SEARCH_IMPROVEMENT_PLAN Phase 0).

Before this module the app answered "does this match?" in two different places,
with two different number systems, and **neither of them ranked anything a
person sees**:

* ``services/global_search.py`` held a 0–3 DISCRETE tier (``title_match_score``)
  used only as a GATE — it decided whether the external (TMDB) half of the
  response was populated at all. Result #1 and result #6 were indistinguishable
  to it.
* ``api/routes/search.py`` did its own inline ``ql in hay`` substring test over
  six watchlist fields, with no weighting between them: a hit in ``snippet``
  counted exactly as much as a hit in ``title``.

This module owns both answers now:

* the discrete tiers are kept **verbatim** (``title_match_score`` /
  ``owned_strong_match``) because ``EXACT_TITLE_SCORE`` is a published contract
  the route and the tests both read; and
* ``score_item`` produces the CONTINUOUS 0.0–1.0 relevance that ranking needs,
  combining fields through :class:`FieldWeight` so a title hit outranks a
  synopsis hit.

Pure by design: no I/O, no config, no network — so every rule here is
unit-testable and the route stays thin (the repo's layering rule, ARCHITECTURE
§4). Typo tolerance lives in :mod:`services.search.fuzzy` and is applied here;
that module reports itself unavailable rather than raising, so a missing
optional dependency degrades a search to exact matching instead of failing it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from services.search.fuzzy import fuzzy_name_score, fuzzy_title_score
from services.search.normalize import YEAR_MISMATCH_FACTOR, normalize_title, year_factor

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

# Retained from ``services/global_search.py`` — the ONE threshold that decides
# "the library already has what was asked for". It is deliberately the EXACT
# tier (3), not containment (2): an owned "Sholay — Special Ops" is a DIFFERENT
# work from "Sholay". ⚠ Re-exported from here so the number has one home.
EXACT_TITLE_SCORE = 3

#: Fields whose "perfect match" means the item IS what was asked for.
PRIMARY_FIELDS = ("title", "original_title", "series_name")

#: Fields matched as PEOPLE (substring/token), not as whole titles.
NAME_FIELDS = ("cast", "director")

#: Short label fields — matched like titles, but a containment hit is normal
#: rather than suspicious ("sci" finding "Sci-Fi & Fantasy").
LABEL_FIELDS = ("genre", "collection")

#: How much of the remaining headroom extra fields can fill. With this at 0.5 a
#: perfect CAST match on a title that does not match at all scores 0.5 — enough
#: to rank a person's filmography above nothing, never enough to outrank a real
#: title match.
SUPPORT_WEIGHT = 0.5

#: A field match below this is noise, and is not reported in ``matched_fields``.
MATCH_FLOOR = 0.2

#: ``overview`` is free prose: every query token appearing in a 40-word synopsis
#: is weak evidence, so it is scaled down from an otherwise-normal coverage
#: score. Paired with the 1.0 default weight this keeps a synopsis hit strictly
#: below a title hit — which is the whole point of having weights at all.
OVERVIEW_SCALE = 0.5

#: A query that is genuinely CONTAINED in a title is scored by how much of that
#: title it accounts for, not by a flat constant. ⚠ This is what stops
#: ``"matrix"`` scoring the same against *The Matrix* and *The Matrix Reloaded*
#: — a flat containment tier made those indistinguishable, so the film he owns
#: and its sequel ranked equally. Range is [BASE, BASE + SPAN] = [0.65, 0.80],
#: which keeps every containment below the fuzzy ceiling (0.85).
CONTAINMENT_BASE = 0.65
CONTAINMENT_SPAN = 0.15

#: Every significant query token present, in any order, and nothing better. Above
#: nothing, below everything real — this tier exists so a "dark knight" query
#: still finds "The Dark Knight" on a build with no fuzzy dependency.
TOKEN_SCORE = 0.6


@dataclass(frozen=True)
class FieldWeight:
    """Relative importance of each searchable field.

    The numbers are a RATIO, not a percentage: ``title`` at 10.0 against
    ``overview`` at 1.0 is what makes a title hit worth ten synopsis hits. They
    are the ONE knob the relevance tuning in Phase 7 turns.
    """

    title: float = 10.0
    original_title: float = 8.0
    series_name: float = 8.0
    cast: float = 4.0
    director: float = 4.0
    collection: float = 3.0
    genre: float = 2.0
    year: float = 2.0
    overview: float = 1.0

    def of(self, name: str) -> float:
        """Weight for a field name; 0.0 for anything unknown (never a guess)."""
        return float(getattr(self, name, 0.0) or 0.0)


@dataclass
class ScoredResult:
    """One item's relevance verdict.

    ``score`` is continuous and 0.0–1.0: 1.0 is a perfect TITLE match on its own.
    ``matched_fields`` and ``ranges`` are for the UI (Phase 4 highlights the
    matched span in ``title``); ``match_type`` is the strongest match kind seen,
    for debugging and for the query-understanding boosts in Phase 3.
    """

    item: object = None
    score: float = 0.0
    matched_fields: list[str] = field(default_factory=list)
    match_type: str = "none"
    ranges: list[tuple[int, int]] = field(default_factory=list)


# --------------------------------------------------------------------------- the discrete tiers (kept verbatim)
def title_match_score(query: str, title: Any, *, query_year: int | None = None,
                      title_year: Any = None) -> int:
    """How strongly an owned title answers the query (0 = no match).

    3 = exact normalized title · 2 = containment (len>=3) with compatible year
    or no year either side · 1 = every significant token contained (len>=5).
    Years must agree when both are known so same-name remakes stay distinct.

    ⚠ This is the LEGACY contract (``EXACT_TITLE_SCORE`` reads it). Ranking uses
    :func:`title_relevance` / :func:`score_item` instead — do not build new
    ordering on a four-value scale.
    """
    q = normalize_title(query)
    t = normalize_title(title)
    if not q or not t:
        return 0
    # Same-name remakes of a different year are DISTINCT titles, never a match.
    if year_factor(query_year, title_year) != 1.0:
        return 0
    if q == t:
        return 3
    if len(q) >= 3 and (q in t or t in q):
        return 2
    words = q.split()
    if len(q) >= 5 and all(w in t for w in words):
        return 1
    return 0


def owned_strong_match(owned: Iterable[dict], query: str, *,
                       query_year: int | None = None) -> int:
    """Best ``title_match_score`` across owned rows.

    ⚠ The caller compares this against ``EXACT_TITLE_SCORE`` — a number alone
    cannot say whether the library *answered* the query. Kept as a thin wrapper
    so no call site reaches into the scorer's internals.
    """
    best = 0
    for row in owned or []:
        best = max(best, title_match_score(query, row.get("title", ""), query_year=query_year,
                                           title_year=row.get("year")))
    return best


# --------------------------------------------------------------------------- continuous field relevance
def _ranges(query_raw: str, candidate_raw: str) -> list[tuple[int, int]]:
    """Where the query sits inside the candidate, for UI highlighting.

    Deliberately operates on the RAW strings so the offsets are valid against the
    text the user is actually shown, not against the normalised key.
    """
    q = str(query_raw or "").strip()
    c = str(candidate_raw or "")
    if not q or not c:
        return []
    i = c.lower().find(q.lower())
    return [(i, i + len(q))] if i >= 0 else []


def _token_coverage(query: str, text: Any) -> float:
    """Fraction of the query's significant tokens present in ``text`` (0.0–1.0)."""
    words = [w for w in normalize_title(query).split() if len(w) >= 2]
    if not words:
        return 0.0
    hay = normalize_title(text)
    hits = sum(1 for w in words if w in hay)
    return hits / len(words)


def title_relevance(query: str, candidate: Any, *, query_year: int | None = None,
                    title_year: Any = None,
                    query_year_range: tuple[int, int] | None = None
                    ) -> tuple[float, str, list[tuple[int, int]]]:
    """Continuous 0.0–1.0 relevance of ONE title field, with its match kind.

    Every applicable tier is evaluated and the STRONGEST one wins, so the result
    is monotone and a query that could be read two ways is never scored by the
    weaker reading:

        exact 1.00 · prefix 0.90 · fuzzy ≤0.85 · containment 0.65–0.80 · token 0.60

    ⚠ The split between **containment** and **fuzzy** is the load-bearing part:

    * the query is literally IN the title → containment, scored by how much of
      that title it accounts for, so ``"matrix"`` ranks *The Matrix* above
      *The Matrix Reloaded*; and
    * the query is NOT in the title → fuzzy, which is what catches typos
      (``"the dark knght"``) and word order (``"knight dark"``).

    Reading it the other way round is what produced a tie between a film and its
    own sequel — a flat containment tier scored both 0.75 while the fuzzy path
    scored both 0.765, so neither number could tell them apart.
    """
    q = normalize_title(query)
    c = normalize_title(candidate)
    if not q or not c:
        return 0.0, "none", []

    factor = year_factor(query_year, title_year, year_range=query_year_range)
    tiers: list[tuple[float, str]] = []
    if q == c:
        tiers.append((1.0 * factor, "exact"))
    if c.startswith(q):
        tiers.append((0.9 * factor, "prefix"))

    contained = q in c or c in q
    if contained:
        coverage = min(len(q), len(c)) / max(len(q), len(c))
        tiers.append(((CONTAINMENT_BASE + CONTAINMENT_SPAN * coverage) * factor, "containment"))
    else:
        # Only reach for typo tolerance when the query is not literally present:
        # a fuzzy ratio on a clean substring is substring-sensitive, and letting
        # it compete with containment is what flattened the sequel distinction.
        fuzzy = fuzzy_title_score(query, candidate, query_year=query_year, title_year=title_year,
                                  query_year_range=query_year_range)
        if fuzzy > 0.0:
            tiers.append((fuzzy, "fuzzy"))
        words = q.split()
        if len(q) >= 5 and all(w in c for w in words):
            tiers.append((TOKEN_SCORE * factor, "token"))

    if not tiers:
        return 0.0, "none", []
    score, kind = max(tiers, key=lambda t: t[0])
    return score, kind, _ranges(query, candidate)


def name_relevance(query: str, candidate: Any) -> tuple[float, str]:
    """Relevance of a PERSON name field (cast / director).

    ⚠ Names are matched as substrings on purpose: ``"pacino"`` must find
    ``"Al Pacino"``, and ``"nolan"`` must find ``"Christopher Nolan"``. A
    whole-string comparison would score both of those zero — the reason
    :func:`services.search.fuzzy.fuzzy_name_score` uses ``partial_ratio``.
    """
    q = normalize_title(query)
    c = normalize_title(candidate)
    if not q or not c:
        return 0.0, "none"
    if q == c:
        return 1.0, "exact"
    if q in c:
        return 0.9, "containment"
    fuzzy = fuzzy_name_score(query, candidate)
    return (fuzzy, "fuzzy") if fuzzy > 0.0 else (0.0, "none")


def _year_relevance(query: str, value: Any) -> tuple[float, str, list[tuple[int, int]]]:
    """A year matches EXACTLY or not at all.

    ⚠ No fuzzy, no containment: ``"1994"`` is not a near-miss for ``"1993"``, and
    fuzzing digits would make every year within one edit of the query a match.
    Phase 3 turns a year the user typed into a proper filter/boost; this field
    exists so a bare ``"2024"`` search still finds 2024's titles.
    """
    q = str(query or "").strip()
    v = str(value or "").strip()
    if not q or not v or q != v:
        return 0.0, "none", []
    return 1.0, "exact", []


def _field_relevance(name: str, query: str, value: Any, *, query_year: int | None,
                     title_year: Any,
                     query_year_range: tuple[int, int] | None = None
                     ) -> tuple[float, str, list[tuple[int, int]]]:
    """Relevance of one item field, dispatching on what KIND of field it is."""
    if name == "year":
        return _year_relevance(query, value)
    if name in NAME_FIELDS:
        score, kind = name_relevance(query, value)
        return score, kind, []
    if name == "overview":
        return _token_coverage(query, value) * OVERVIEW_SCALE, "token", []
    if name in LABEL_FIELDS:
        score, kind, rng = title_relevance(query, value)
        return score, kind, rng
    return title_relevance(query, value, query_year=query_year, title_year=title_year,
                           query_year_range=query_year_range)


def score_item(query: str, fields: Mapping[str, Any], *,
               weights: FieldWeight | None = None, query_year: int | None = None,
               query_year_range: tuple[int, int] | None = None,
               item_year: int | None = None, item: object = None) -> ScoredResult:
    """Score ONE item against ``query`` across its searchable ``fields``.

    ``fields`` maps a :class:`FieldWeight` name to a value — a string, or a
    sequence (``cast``, ``genres``) where the BEST element wins.

    The combination rule, stated plainly:

    * the strongest PRIMARY (title-ish) field score is the backbone, and
    * the remaining fields fill in ``SUPPORT_WEIGHT`` of the leftover headroom,
      weight-averaged so a cast hit and a synopsis hit are not equal.

    So: perfect title → 1.0. No title match at all but a perfect cast → 0.5.
    Perfect title AND perfect cast → still 1.0: the title already answered the
    query, and extra evidence must not inflate past the ceiling, or Phase 2's
    ``OWNED_BONUS`` would stop meaning anything.
    """
    w = weights or FieldWeight()
    matches: list[tuple[str, float, str, list[tuple[int, int]]]] = []
    for name, raw in (fields or {}).items():
        weight = w.of(name)
        if weight <= 0.0 or raw is None:
            continue
        values: Sequence[Any] = raw if isinstance(raw, (list, tuple, set)) else (raw,)
        best: tuple[float, str, list[tuple[int, int]]] = (0.0, "none", [])
        for v in values:
            if not v:
                continue
            cand = _field_relevance(name, query, v, query_year=query_year, title_year=item_year,
                                    query_year_range=query_year_range)
            if cand[0] > best[0]:
                best = cand
        if best[0] > 0.0:
            matches.append((name, best[0], best[1], best[2]))

    if not matches:
        return ScoredResult(item=item, score=0.0)

    primary = max((m for m in matches if m[0] in PRIMARY_FIELDS),
                  key=lambda m: m[1] * w.of(m[0]), default=None)
    support = [m for m in matches if m is not primary]

    backbone = primary[1] if primary else 0.0
    support_score = 0.0
    if support:
        total_weight = sum(w.of(m[0]) for m in support)
        if total_weight > 0:
            support_score = sum(w.of(m[0]) * m[1] for m in support) / total_weight
    score = backbone + (1.0 - backbone) * SUPPORT_WEIGHT * support_score

    matched = [m[0] for m in sorted(matches, key=lambda m: -m[1]) if m[1] >= MATCH_FLOOR]
    strongest = primary or max(matches, key=lambda m: m[1])
    return ScoredResult(
        item=item,
        score=round(min(1.0, score), 6),
        matched_fields=matched,
        match_type=strongest[2],
        ranges=list(strongest[3]) if strongest[0] in PRIMARY_FIELDS else [],
    )


def row_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map a provider row onto :class:`FieldWeight` names.

    ⚠ ONE place translates row shape → searchable fields, so a new provider field
    is added here instead of in every caller (and so the route never has to know
    which key a provider happens to use).
    """
    return {
        "title": row.get("title") or row.get("name"),
        "original_title": row.get("original_title"),
        "series_name": row.get("series_name"),
        "cast": row.get("cast") or row.get("people"),
        "director": row.get("director"),
        "genre": row.get("genres"),
        "collection": row.get("collection"),
        "year": row.get("year"),
        "overview": row.get("overview") or row.get("snippet"),
    }


def best_relevance(rows: Iterable[dict], query: str, *, weights: FieldWeight | None = None,
                   query_year: int | None = None,
                   query_year_range: tuple[int, int] | None = None) -> float:
    """Highest :func:`score_item` score across ``rows``.

    The continuous twin of :func:`owned_strong_match`, for callers that need a
    number to RANK with rather than a threshold to gate on.
    """
    best = 0.0
    for row in rows or []:
        scored = score_item(query, row_fields(row), weights=weights, query_year=query_year,
                            query_year_range=query_year_range,
                            item_year=row.get("year"), item=row)
        best = max(best, scored.score)
    return best
