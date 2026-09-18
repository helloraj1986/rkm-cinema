"""Unified relevance ranking — SEARCH_IMPROVEMENT_PLAN Phase 2.

**The problem this phase removes.** ``/api/search/global`` used a BINARY cutoff —
``strong_match = score >= EXACT_TITLE_SCORE`` — to decide whether the external half
ran *at all*. So owned and discovered content were two lists stapled together,
and an exact owned match SUPPRESSED everything else: searching "matrix" while
owning *The Matrix* hid *The Matrix Resurrections* and *The Animatrix* entirely.
That is the "two separate searches" feeling the plan set out to kill.

The replacement is a score-based ownership PREFERENCE, never a gate:

    owned      relevance + OWNED_BONUS      (0.30)
    watchlist  relevance + WATCHLIST_BONUS  (0.15)
    hint       relevance                    (person / genre / collection)
    tmdb       relevance                    (deduped against owned, as before)

His own copy of a film still ranks first — it is both genuinely relevant and
bonused — but the sequels and remakes he does NOT own surface beneath it, which
is the "it knows what I mean" behaviour the plan is after.

⚠ ``score`` is a RANKING KEY, not a probability: 1.0 is a perfect title match on
its own, and a bonused row legitimately exceeds it. Only the ORDER is meaningful
— do not render it as a percentage, and do not compare it across queries.

Pure: no I/O, no config. The route decides what to fetch; this decides what to
show first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from services.search.scoring import (
    EXACT_TITLE_SCORE,
    row_fields,
    score_item,
    title_match_score,
)

__all__ = [
    "OWNED_BONUS",
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


def _rank_owned(query: str, rows: Sequence[dict], *, query_year: int | None) -> list[RankedRow]:
    """Every owned row the provider returned, scored and bonused.

    ⚠ Rows are NOT filtered by relevance here. Jellyfin already decided they match
    (it ran the search), and our field map cannot see every field it matched on —
    dropping a row our scorer happens to score 0 would silently remove content the
    library actually found. They simply rank at the bottom via ``OWNED_BONUS``.
    """
    out: list[RankedRow] = []
    for row in rows or []:
        scored = score_item(query, row_fields(row), query_year=query_year,
                            item_year=row.get("year"), item=row)
        out.append(RankedRow(
            score=scored.score + OWNED_BONUS,
            source="owned",
            kind=_owned_kind(row),
            payload=row,
            matched_fields=scored.matched_fields,
            match_type=scored.match_type,
            ranges=scored.ranges,
        ))
    return out


def _rank_watchlist(query: str, rows: Sequence[dict], taken: set[int],
                    *, query_year: int | None) -> list[RankedRow]:
    """Acquisition-queue entries, minus anything already covered by a better source.

    ⚠ Deduped by TMDB id against ``taken`` (the owned rows plus the discovery rows
    the route is about to send): a title that is on the watchlist AND in the TMDB
    results must appear ONCE, and the discovery row already carries
    ``in_watchlist`` — showing both would read as two different films.
    """
    out: list[RankedRow] = []
    for row in rows or []:
        try:
            tmdb_id = int(row.get("tmdbId") or row.get("tmdb_id") or 0)
        except (TypeError, ValueError):
            tmdb_id = 0
        if tmdb_id and tmdb_id in taken:
            continue
        scored = score_item(query, row_fields(row), query_year=query_year,
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
            score=scored.score + WATCHLIST_BONUS,
            source="watchlist",
            kind="show" if row.get("isSeries") else "movie",
            payload=row,
            matched_fields=scored.matched_fields,
            match_type=scored.match_type,
            ranges=scored.ranges,
        ))
    return out


def _rank_hints(query: str, groups: dict[str, Sequence[dict]], *, query_year: int | None) -> list[RankedRow]:
    """People / genres / collections, scored in the SAME list as the titles.

    The plan's point: these were three top-level arrays the frontend had to
    interleave by hand. Ranking them here means the client renders one list in the
    order the server decided, instead of re-deriving relevance in the UI.
    """
    out: list[RankedRow] = []
    for kind, rows in (groups or {}).items():
        for row in rows or []:
            name = str(row.get("name") or "")
            scored = score_item(query, {"title": name}, query_year=query_year, item=row)
            out.append(RankedRow(
                score=scored.score,
                source="hint",
                kind=kind,
                payload=dict(row),
                matched_fields=scored.matched_fields,
                match_type=scored.match_type,
                ranges=scored.ranges,
            ))
    return out


def _rank_discovery(query: str, rows: Sequence[dict], owned: Sequence[dict],
                    *, query_year: int | None) -> list[RankedRow]:
    """External candidates for titles the library does NOT have."""
    out: list[RankedRow] = []
    for row in rows or []:
        if is_duplicate_discovery(dict(row), owned):
            continue
        scored = score_item(query, row_fields(row), query_year=query_year,
                            item_year=row.get("year"), item=row)
        out.append(RankedRow(
            score=scored.score,
            source="tmdb",
            kind=_discovery_kind(row),
            payload=row,
            matched_fields=scored.matched_fields,
            match_type=scored.match_type,
            ranges=scored.ranges,
        ))
    return out


def _identity(row: "RankedRow") -> str:
    """A stable per-row key for the sort, so two identical queries cannot reshuffle.

    ⚠ Without this a tie fell through to Python's stable sort, i.e. to the order
    the PROVIDER happened to return — which changes when TMDB reorders its results,
    making the same search look different on two consecutive days.
    """
    payload = row.payload or {}
    return str(payload.get("tmdb_id") or payload.get("tmdbId") or payload.get("id") or "")


def rank_all(query: str, *, owned: Sequence[dict] = (), watchlist: Sequence[dict] = (),
             discovery: Sequence[dict] = (), hints: dict[str, Sequence[dict]] | None = None,
             query_year: int | None = None) -> list[RankedRow]:
    """ONE ranked list across every source, highest relevance first.

    Ordering is by ``score`` descending, then by :data:`SOURCE_ORDER`, then by
    title, then by :func:`_identity` — fully determined by the data, so the list
    for a given query and result set is always the same.
    """
    owned_seq = list(owned or [])
    taken: set[int] = set()
    for row in owned_seq:
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

    rows: list[RankedRow] = []
    rows.extend(_rank_owned(query, owned_seq, query_year=query_year))
    rows.extend(_rank_watchlist(query, watchlist or (), taken, query_year=query_year))
    rows.extend(_rank_hints(query, hints or {}, query_year=query_year))
    rows.extend(_rank_discovery(query, discovery_rows, owned_seq, query_year=query_year))

    rows.sort(key=lambda r: (-r.score, SOURCE_ORDER.get(r.source, 99),
                             str(r.payload.get("title") or r.payload.get("name") or ""),
                             _identity(r)))
    return rows
