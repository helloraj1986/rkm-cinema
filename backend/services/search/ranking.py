"""Unified relevance ranking — SEARCH_IMPROVEMENT_PLAN Phase 2.

**The problem this phase removes.** ``/api/search/global`` used a BINARY cutoff —
``strong_match = score >= EXACT_TITLE_SCORE`` — to decide whether the external half
ran *at all*. So owned and discovered content were two lists stapled together,
and an exact owned match SUPPRESSED everything else: searching "matrix" while
owning *The Matrix* hid *The Matrix Resurrections* and *The Animatrix* entirely.
That is the "two separate searches" feeling the plan set out to kill.

The replacement is a score-based ownership PREFERENCE, never a gate:

    owned      relevance + OWNED_BONUS      (0.03)
    watchlist  relevance + WATCHLIST_BONUS  (0.015)
    hint       relevance                    (person / genre / collection)
    tmdb       relevance                    (deduped against owned, as before)
    semantic   its OWN tier, [0.30, 0.39]   (Phase 6 — see SEMANTIC_BASE)

His own copy of a film still ranks first — it is both genuinely relevant and
bonused — but the sequels and remakes he does NOT own surface beneath it, which
is the "it knows what I mean" behaviour the plan is after.

⚠ ``score`` is a RANKING KEY, not a probability: 1.0 is a perfect title match on
its own, and a bonused row legitimately exceeds it. Only the ORDER is meaningful
— do not render it as a percentage, and do not compare it across queries.

⚠⚠ **The SEMANTIC tier is the one source that is not a string match at all**
(Phase 6, plan `docs/SEMANTIC_SEARCH_PLAN.md`). A cosine similarity is not
comparable to a title score, so it is not allowed to compete with one: its whole
range sits strictly BELOW ``SEMANTIC_TRIGGER_SCORE``, the line below which the
route decides the string matcher has failed. The route only ever passes semantic
rows when no lexical row reached that line, which is what makes the invariant
``SEMANTIC_BASE + SEMANTIC_SPAN < SEMANTIC_TRIGGER_SCORE`` a *proof* about every
response the app can produce rather than a hope.

Pure: no I/O, no config. The route decides what to fetch; this decides what to
show first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from services.search.affinity import Affinity
from services.search.scoring import (
    EXACT_TITLE_SCORE,
    row_fields,
    score_item,
    title_match_score,
)

__all__ = [
    "OWNED_BONUS",
    "SEMANTIC_BASE",
    "SEMANTIC_MIN_COS",
    "SEMANTIC_SPAN",
    "SEMANTIC_TRIGGER_SCORE",
    "SOURCE_ORDER",
    "WATCHLIST_BONUS",
    "RankedRow",
    "is_duplicate_discovery",
    "rank_all",
]

#: How much an owned row is preferred over an equally-relevant external one.
#:
#: ⚠ NOT the plan's 0.30. The plan assumed a 0–1 scale with wide relevance
#: differences; on THIS scale the whole containment tier spans 0.65–0.80 and the
#: step from it to fuzzy (0.85) and to prefix (0.90) is 0.05. A bonus that large
#: would outrank relevance OUTRIGHT — owning *The Matrix* would beat the
#: *Matrix Reloaded* he actually typed, which is the Phase-2 gate re-introduced
#: with a decimal point on it.
#:
#: ⚠ The invariant, pinned by test_owned_bonus_is_smaller_than_a_tier_step:
#:     0 < OWNED_BONUS < FUZZY_CEILING - (CONTAINMENT_BASE + CONTAINMENT_SPAN)
#: i.e. strictly less than the smallest step between two adjacent relevance
#: tiers, so it can never promote a row into the tier above it. It wins ties and
#: within-tier margins; a genuinely better match still wins.
OWNED_BONUS = 0.03

#: A title already on the acquisition queue is a weaker signal than one on disk
#: (it is on its way, not here), and a stronger one than a bare TMDB candidate.
WATCHLIST_BONUS = OWNED_BONUS * 0.5

#: Tie-break order when two rows score identically. Owned first, then what is
#: coming, then navigation hints, then discovery.
SOURCE_ORDER = {"owned": 0, "watchlist": 1, "hint": 2, "tmdb": 3}

#: ⚠ A score difference too small to change any tier, added so that rows of EQUAL
#: relevance keep the order their PROVIDER put them in. Without it, a query the
#: scorer cannot see (a bare decade like "90s", where every row scores 0) would be
#: sorted ALPHABETICALLY — throwing away TMDB's own relevance ranking and showing
#: a worse list than the one that was already in hand.
PROVIDER_ORDER_EPSILON = 1e-6

#: ⚠⚠ THE LINE THE ROUTE TRIGGERS THE EMBEDDING FALLBACK ON (Phase 6): below it,
#: nothing the string matcher found is a real match, and the route may ask the
#: semantic index for rows. Read it as "weaker than a support-field hit and far
#: weaker than the token tier (0.6)" — 0.4 is his own number from the plan text,
#: and it has the property that matters: it sits ABOVE ``SEMANTIC_BASE +
#: SEMANTIC_SPAN``, so a semantic row can never outrank a lexical one.
SEMANTIC_TRIGGER_SCORE = 0.4

#: Where a SEMANTIC row scores, and how much room the similarity has to order the
#: group. ⚠ The range is [0.30, 0.39]: strictly BELOW the trigger line, so a
#: semantic hit lands above the zero-score rows (an owned row the provider returned
#: but our scorer could not see sits at OWNED_BONUS, 0.03) and below anything that
#: matched lexically well enough to have suppressed the fallback.
#:
#: ⚠ A semantic row carries NO bonus: OWNED_BONUS would push the top of the tier to
#: 0.42, back over the trigger line, and the invariant below would be false. The
#: rows are owned by construction anyway — the index IS the library.
#:
#: Invariant (pinned in tests/test_semantic_search.py, mirroring the OWNED_BONUS one):
#:     SEMANTIC_BASE + SEMANTIC_SPAN < SEMANTIC_TRIGGER_SCORE < TOKEN_SCORE (0.6)
SEMANTIC_BASE = 0.30
SEMANTIC_SPAN = 0.09

#: The cosine below which a neighbour is NOISE and is not admitted at all. ⚠ This is
#: a sanity floor, NOT a calibrated relevance claim: measured on a 10-film probe, an
#: unrelated film scored 0.17–0.27 while the right answer scored 0.24–0.45, so no
#: floor at this scale separates "related" from "unrelated" honestly. It exists so a
#: near-orthogonal neighbour cannot pad the list, and CALIBRATING it is Phase 7's job
#: (the metrics loop), not a guess made in the ranker.
SEMANTIC_MIN_COS = 0.05


@dataclass
class RankedRow:
    """One row of the unified result list, carrying its own provenance.

    ``payload`` is the EXISTING provider/response shape, verbatim — so a client
    that already knows how to render a ``GlobalOwnedRow`` or a
    ``GlobalDiscoveryRow`` needs no second renderer for the ranked list.
    """

    score: float
    source: str
    kind: str
    payload: dict
    matched_fields: list[str] = field(default_factory=list)
    match_type: str = "none"
    ranges: list[tuple[int, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON/Pydantic-ready shape (ranges become [start, end] pairs)."""
        return {
            "score": round(self.score, 6),
            "source": self.source,
            "kind": self.kind,
            "matched_fields": list(self.matched_fields),
            "match_type": self.match_type,
            "ranges": [[int(a), int(b)] for a, b in self.ranges],
            "payload": self.payload,
        }


def is_duplicate_discovery(candidate: dict, owned: Iterable[dict]) -> bool:
    """True when a TMDB candidate is already owned (drop it from DISCOVER).

    Matches by TMDB provider id first — the strongest identity signal, always decisive — then by
    title. ⚠ The title path needs ``EXACT_TITLE_SCORE``, not containment: an owned "Sholay —
    Special Ops" would otherwise swallow the real "Sholay" (1975), and it does so **whenever the
    owned row carries no year**, because the remake guard cannot fire without two years
    (measured 2026-09-13: dropped_as_duplicate=True for exactly that pair). Same-name remakes of a
    different year remain distinct on both paths.

    ⚠ Moved here from ``services/global_search.py`` (Phase 2) because it IS a ranking rule —
    "what must not appear twice in one list" — and this module is the one that assembles that
    list. ``global_search`` re-exports it, so the route's import path is unchanged.
    """
    cand_tmdb = candidate.get("tmdb_id")
    for row in owned or []:
        pids = row.get("provider_ids") or {}
        if cand_tmdb is not None:
            try:
                if int(pids.get("tmdb") or 0) == int(cand_tmdb):
                    return True
            except (TypeError, ValueError):
                pass
        score = title_match_score(candidate.get("title", ""), row.get("title", ""),
                                  query_year=candidate.get("year"), title_year=row.get("year"))
        if score >= EXACT_TITLE_SCORE:
            return True
    return False


def _owned_kind(row: dict) -> str:
    return str(row.get("kind") or "movie")


def _discovery_kind(candidate: dict) -> str:
    """TMDB says movie|tv; the rest of the app says movie|show|episode."""
    return "show" if candidate.get("media_type") == "tv" else "movie"


def _rank_owned(query: str, rows: Sequence[dict], *, query_year: int | None,
                query_year_range: tuple[int, int] | None = None) -> list[RankedRow]:
    """Every owned row the provider returned, scored and bonused.

    ⚠ Rows are NOT filtered by relevance here. Jellyfin already decided they match
    (it ran the search), and our field map cannot see every field it matched on —
    dropping a row our scorer happens to score 0 would silently remove content the
    library actually found. They simply rank at the bottom via ``OWNED_BONUS``.
    """
    rows = list(rows or [])
    out: list[RankedRow] = []
    for index, row in enumerate(rows):
        scored = score_item(query, row_fields(row), query_year=query_year,
                            query_year_range=query_year_range,
                            item_year=row.get("year"), item=row)
        out.append(RankedRow(
            score=scored.score + OWNED_BONUS + _provider_bias(index, len(rows)),
            source="owned",
            kind=_owned_kind(row),
            payload=row,
            matched_fields=scored.matched_fields,
            match_type=scored.match_type,
            ranges=scored.ranges,
        ))
    return out


def _rank_watchlist(query: str, rows: Sequence[dict], taken: set[int],
                    *, query_year: int | None,
                    query_year_range: tuple[int, int] | None = None) -> list[RankedRow]:
    """Acquisition-queue entries, minus anything already covered by a better source.

    ⚠ Deduped by TMDB id against ``taken`` (the owned rows plus the discovery rows
    the route is about to send): a title that is on the watchlist AND in the TMDB
    results must appear ONCE, and the discovery row already carries
    ``in_watchlist`` — showing both would read as two different films.
    """
    rows = list(rows or [])
    out: list[RankedRow] = []
    for index, row in enumerate(rows):
        try:
            tmdb_id = int(row.get("tmdbId") or row.get("tmdb_id") or 0)
        except (TypeError, ValueError):
            tmdb_id = 0
        if tmdb_id and tmdb_id in taken:
            continue
        scored = score_item(query, row_fields(row), query_year=query_year,
                            query_year_range=query_year_range,
                            item_year=row.get("year"), item=row)
        if scored.score <= 0.0:
            # ⚠ A watchlist entry only belongs in the list when the QUERY matched
            # it. Unlike an owned row (which the provider already filtered), this
            # is the whole queue — listing it unfiltered would answer every search
            # with the same set of rows.
            continue
        if tmdb_id:
            taken.add(tmdb_id)
        out.append(RankedRow(
            score=scored.score + WATCHLIST_BONUS + _provider_bias(index, len(rows)),
            source="watchlist",
            kind="show" if row.get("isSeries") else "movie",
            payload=row,
            matched_fields=scored.matched_fields,
            match_type=scored.match_type,
            ranges=scored.ranges,
        ))
    return out


def _rank_hints(query: str, groups: dict[str, Sequence[dict]], *, query_year: int | None,
                query_year_range: tuple[int, int] | None = None) -> list[RankedRow]:
    """People / genres / collections, scored in the SAME list as the titles.

    The plan's point: these were three top-level arrays the frontend had to
    interleave by hand. Ranking them here means the client renders one list in the
    order the server decided, instead of re-deriving relevance in the UI.
    """
    out: list[RankedRow] = []
    for kind, raw_rows in (groups or {}).items():
        rows = list(raw_rows or [])
        for index, row in enumerate(rows):
            name = str(row.get("name") or "")
            scored = score_item(query, {"title": name}, query_year=query_year,
                                query_year_range=query_year_range, item=row)
            out.append(RankedRow(
                score=scored.score + _provider_bias(index, len(rows)),
                source="hint",
                kind=kind,
                payload=dict(row),
                matched_fields=scored.matched_fields,
                match_type=scored.match_type,
                ranges=scored.ranges,
            ))
    return out


def _rank_discovery(query: str, rows: Sequence[dict], owned: Sequence[dict],
                    *, query_year: int | None,
                    query_year_range: tuple[int, int] | None = None,
                    affinity: Affinity | None = None) -> list[RankedRow]:
    """External candidates for titles the library does NOT have.

    ⚠ This is the ONLY place taste is applied (SEARCH_IMPROVEMENT_PLAN Phase 5). The
    question personalization answers — "which of these should I watch next?" — is
    only asked about titles he does not already have; re-ordering his OWN library by
    taste would make a search for a film he owns feel like it ignored him.
    """
    rows = list(rows or [])
    out: list[RankedRow] = []
    for index, row in enumerate(rows):
        if is_duplicate_discovery(dict(row), owned):
            continue
        scored = score_item(query, row_fields(row), query_year=query_year,
                            query_year_range=query_year_range,
                            item_year=row.get("year"), item=row)
        taste = affinity.bonus(row.get("genres")) if affinity is not None else 0.0
        out.append(RankedRow(
            score=scored.score + _provider_bias(index, len(rows)) + taste,
            source="tmdb",
            kind=_discovery_kind(row),
            payload=row,
            matched_fields=scored.matched_fields,
            match_type=scored.match_type,
            ranges=scored.ranges,
        ))
    return out


def _provider_bias(index: int, total: int) -> float:
    """A vanishing bias that preserves the PROVIDER's order between equal scores."""
    return (total - index) * PROVIDER_ORDER_EPSILON


def semantic_score(cos: float) -> float:
    """A cosine similarity mapped into the semantic tier, never outside it.

    ⚠ The mapping is what keeps the tier's RANGE honest: a perfect match (cos 1.0)
    scores ``SEMANTIC_BASE + SEMANTIC_SPAN`` and a neighbour at the floor scores
    ``SEMANTIC_BASE``, so ordering inside the group is the similarity's and the
    group's ceiling is a constant. Anything at or below the floor maps to the base
    (the caller drops it anyway — see ``SEMANTIC_MIN_COS``).
    """
    lo = SEMANTIC_MIN_COS
    scaled = (float(cos) - lo) / (1.0 - lo) if cos > lo else 0.0
    return SEMANTIC_BASE + SEMANTIC_SPAN * min(1.0, max(0.0, scaled))


def _rank_semantic(rows: Sequence[tuple[dict, float]]) -> list[RankedRow]:
    """Embedding neighbours of the query — the Phase 6 fallback source.

    ⚠ These rows arrive ALREADY scored (the route ran the index), and their score is
    a cosine similarity, not a string relevance. They are:
      · admitted only when the route decided the string matcher had failed, which is
        the property that makes the tier's placement a proof (§SEMANTIC_TRIGGER_SCORE);
      · given NO bonus of any kind — see SEMANTIC_BASE's note;
      · deduped against the owned rows the provider already returned (``taken``), so a
        title that matched lexically AND semantically cannot appear twice.
    """
    out: list[RankedRow] = []
    for index, pair in enumerate(rows or ()):
        try:
            row, cos = pair
        except (TypeError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        if float(cos) < SEMANTIC_MIN_COS:
            continue
        out.append(RankedRow(
            score=semantic_score(float(cos)) + _provider_bias(index, len(rows or ())),
            source="owned",
            kind=_owned_kind(row),
            payload=row,
            matched_fields=[],
            match_type="semantic",
            ranges=[],
        ))
    return out


def _identity(row: "RankedRow") -> str:
    """A stable per-row key for the sort, so two identical queries cannot reshuffle.

    ⚠ The FINAL guard. :func:`_provider_bias` already separates rows within one
    source, so this is unreachable while that exists — it is kept because a sort
    key that is total is the property that matters: a tie falling through to
    Python's stable sort is a tie falling through to insertion order, which is how
    the list reshuffled between two identical queries.
    """
    payload = row.payload or {}
    return str(payload.get("tmdb_id") or payload.get("tmdbId") or payload.get("id") or "")


def rank_all(query: str, *, owned: Sequence[dict] = (), watchlist: Sequence[dict] = (),
             discovery: Sequence[dict] = (), hints: dict[str, Sequence[dict]] | None = None,
             query_year: int | None = None,
             query_year_range: tuple[int, int] | None = None,
             affinity: Affinity | None = None,
             semantic: Sequence[tuple[dict, float]] = ()) -> list[RankedRow]:
    """ONE ranked list across every source, highest relevance first.

    ``semantic`` is a sequence of ``(owned_row, cosine)`` pairs from the embedding
    index (Phase 6). ⚠ The CALLER is responsible for only passing them when the
    string matcher failed (``SEMANTIC_TRIGGER_SCORE``) — that is the contract that
    keeps a similarity from outranking a title match, and it is asserted in the
    tests rather than assumed here.

    Ordering is by ``score`` descending, then by :data:`SOURCE_ORDER`, then by
    title, then by :func:`_identity` — fully determined by the data, so the list
    for a given query and result set is always the same.
    """
    owned_seq = list(owned or [])
    taken: set[int] = set()
    owned_ids: set[str] = set()
    for row in owned_seq:
        owned_ids.add(str(row.get("id") or row.get("item_id") or ""))
        try:
            pids = row.get("provider_ids") or {}
            tid = int(pids.get("tmdb") or 0)
            if tid:
                taken.add(tid)
        except (TypeError, ValueError):
            continue

    discovery_rows = [r for r in (discovery or []) if not is_duplicate_discovery(dict(r), owned_seq)]
    for row in discovery_rows:
        try:
            tid = int(row.get("tmdb_id") or 0)
            if tid:
                taken.add(tid)
        except (TypeError, ValueError):
            continue

    # ⚠ Deduped by ITEM id against what the provider already returned: the same title
    # can be both a (weak) lexical result and the strongest embedding neighbour, and
    # the person must see it once. Dropping the semantic copy keeps the row that
    # carries the query's match spans.
    semantic_rows = [
        (row, cos) for row, cos in (semantic or ())
        if str(row.get("id") or row.get("item_id") or "") not in owned_ids
    ]

    rows: list[RankedRow] = []
    rows.extend(_rank_owned(query, owned_seq, query_year=query_year,
                            query_year_range=query_year_range))
    rows.extend(_rank_watchlist(query, watchlist or (), taken, query_year=query_year,
                               query_year_range=query_year_range))
    rows.extend(_rank_hints(query, hints or {}, query_year=query_year,
                            query_year_range=query_year_range))
    rows.extend(_rank_discovery(query, discovery_rows, owned_seq, query_year=query_year,
                                query_year_range=query_year_range, affinity=affinity))
    rows.extend(_rank_semantic(semantic_rows))

    rows.sort(key=lambda r: (-r.score, SOURCE_ORDER.get(r.source, 99),
                             str(r.payload.get("title") or r.payload.get("name") or ""),
                             _identity(r)))
    return rows
