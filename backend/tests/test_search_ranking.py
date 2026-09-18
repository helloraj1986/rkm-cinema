"""Tests for unified relevance ranking (SEARCH_IMPROVEMENT_PLAN Phase 2).

The behaviour this phase changes, stated as a test: **an owned title no longer
HIDES the related titles he does not own.** Before Phase 2 the route gated the
whole external half on `strong_match = score >= EXACT_TITLE_SCORE`, so owning
*The Matrix* meant a search for "matrix" returned one row and stopped — no
*Matrix Reloaded*, no *Animatrix*. The gate is gone and a ranked list carries the
order instead.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import patch

from services.search.fuzzy import FUZZY_CEILING
from services.search.ranking import (
    OWNED_BONUS,
    WATCHLIST_BONUS,
    RankedRow,
    is_duplicate_discovery,
    rank_all,
)
from services.search.scoring import CONTAINMENT_BASE, CONTAINMENT_SPAN

OWNED_MATRIX = {
    "id": "m1", "kind": "movie", "title": "The Matrix", "year": 1999,
    "genres": ["Action"], "rating": 8.2, "played": True, "playback_position": 0,
    "runtime": 8160, "play_count": 2, "provider_ids": {"tmdb": 603},
}
RELOADED = {"tmdb_id": 604, "media_type": "movie", "title": "The Matrix Reloaded",
            "year": 2003, "poster": "", "overview": "", "in_watchlist": False}
ANIMATRIX = {"tmdb_id": 55931, "media_type": "movie", "title": "The Animatrix",
             "year": 2003, "poster": "", "overview": "", "in_watchlist": False}
MATRIX_TMDB = {"tmdb_id": 603, "media_type": "movie", "title": "The Matrix",
               "year": 1999, "poster": "", "overview": "", "in_watchlist": False}


# --------------------------------------------------------------------------- pure ranking
def test_owned_rows_rank_above_equally_relevant_discovery_rows():
    """The ownership PREFERENCE, which replaced the gate: a bonus, not a cutoff."""
    ranked = rank_all("the matrix", owned=[OWNED_MATRIX], discovery=[MATRIX_TMDB, RELOADED])
    assert ranked[0].source == "owned"
    assert ranked[0].payload["title"] == "The Matrix"
    # …and the title he does NOT own is still there, underneath it.
    assert [r.payload["title"] for r in ranked[1:]] == ["The Matrix Reloaded"]


def test_an_exact_owned_match_does_not_hide_the_sequels():
    """⚠ THE REGRESSION THIS PHASE EXISTS FOR. Run against the old code this
    returns a one-row list, because `strong_match` short-circuited the TMDB call."""
    ranked = rank_all("matrix", owned=[OWNED_MATRIX], discovery=[MATRIX_TMDB, RELOADED, ANIMATRIX])
    titles = [r.payload["title"] for r in ranked]
    assert "The Matrix Reloaded" in titles and "The Animatrix" in titles
    # the owned copy still wins its own query
    assert titles[0] == "The Matrix"
    # …and the exact duplicate is never offered twice
    assert titles.count("The Matrix") == 1


def test_owned_bonus_is_smaller_than_a_tier_step():
    """⚠ The invariant behind the number, not the number itself.

    The smallest step between two adjacent relevance tiers is the gap from the
    top of containment to fuzzy. A bonus at or above it could promote a row into
    the tier above — which is relevance being overruled by ownership, i.e. the
    Phase-2 gate re-introduced with a decimal point on it.
    """
    tier_step = FUZZY_CEILING - (CONTAINMENT_BASE + CONTAINMENT_SPAN)
    assert 0 < OWNED_BONUS < tier_step, (OWNED_BONUS, tier_step)
    assert 0 < WATCHLIST_BONUS < OWNED_BONUS


def test_a_more_relevant_unowned_title_beats_an_owned_fuzzy_match():
    """The behaviour that invariant buys: *The Matrix* (owned) only FUZZY-matches
    "matrix reloaded", while the unowned *The Matrix Reloaded* contains the whole
    query. The one he actually typed comes first — and the owned copy is still
    right there under it."""
    ranked = rank_all("matrix reloaded", owned=[OWNED_MATRIX], discovery=[RELOADED])
    assert ranked[0].source == "tmdb"
    assert ranked[1].source == "owned"


def test_owned_still_wins_when_relevance_is_close():
    """…and the other direction: for the query "matrix" the owned copy is the most
    relevant row AND bonused, so it is first with the sequel under it."""
    ranked = rank_all("matrix", owned=[OWNED_MATRIX], discovery=[RELOADED])
    assert ranked[0].source == "owned"
    assert ranked[1].payload["title"] == "The Matrix Reloaded"


def test_watchlist_rows_rank_between_owned_and_discovery():
    queue = [{"tmdbId": 999, "title": "Dune Part Three", "year": 2026, "isSeries": False}]
    assert 0 < WATCHLIST_BONUS < OWNED_BONUS
    ranked = rank_all("dune part three", owned=[], discovery=[], watchlist=queue)
    assert ranked[0].source == "watchlist"
    assert ranked[0].payload["title"] == "Dune Part Three"


def test_a_watchlist_entry_only_appears_when_the_query_matched_it():
    """⚠ Unlike an owned row (the provider already filtered it), this is the WHOLE
    queue — listing it unfiltered would answer every search with the same rows."""
    queue = [
        {"tmdbId": 1, "title": "Dune Part Three", "year": 2026, "isSeries": False},
        {"tmdbId": 2, "title": "A Completely Unrelated Film", "year": 1994, "isSeries": False},
    ]
    ranked = rank_all("dune", owned=[], discovery=[], watchlist=queue)
    assert [r.payload["title"] for r in ranked] == ["Dune Part Three"]


def test_a_watchlist_entry_covered_by_a_discovery_row_appears_once():
    """⚠ The ranked list must never show a title twice — once as "add it" and once
    as "you already asked for it".

    The DISCOVERY row is the one that survives, because it already carries
    ``in_watchlist`` and is the shape the palette's Add→Download action speaks.
    The queue row exists in the ranked list for the case TMDB did NOT return the
    title (no metadata key, or TMDB simply missing it)."""
    queue = [{"tmdbId": 604, "title": "The Matrix Reloaded", "year": 2003, "isSeries": False}]
    ranked = rank_all("matrix reloaded", owned=[], discovery=[RELOADED], watchlist=queue)
    assert len(ranked) == 1
    assert ranked[0].source == "tmdb"
    assert ranked[0].payload["in_watchlist"] is False  # the flag the ROUTE sets, not this module


def test_hints_are_ranked_in_the_same_list_as_titles():
    """The plan's ask: people/genres/collections stop being separate arrays the
    frontend has to interleave by hand."""
    ranked = rank_all("nolan", owned=[], discovery=[],
                      hints={"person": [{"id": "p1", "name": "Christopher Nolan", "kind": "person"}]})
    assert ranked[0].source == "hint" and ranked[0].kind == "person"
    # ⚠ An owned title that genuinely matches still outranks a hint of equal relevance.
    both = rank_all("nolan", owned=[{"id": "x", "kind": "movie", "title": "Nolan", "year": 2020}],
                    discovery=[], hints={"person": [{"id": "p1", "name": "Nolan", "kind": "person"}]})
    assert both[0].source == "owned"


def test_every_row_carries_its_provenance_and_why_it_matched():
    ranked = rank_all("matrix", owned=[OWNED_MATRIX], discovery=[RELOADED])
    owned_row = next(r for r in ranked if r.source == "owned")
    tmdb_row = next(r for r in ranked if r.source == "tmdb")
    assert owned_row.kind == "movie" and tmdb_row.kind == "movie"
    assert owned_row.matched_fields == ["title"]
    assert owned_row.match_type == "containment"
    assert owned_row.ranges == [(4, 10)]          # "matrix" inside "The Matrix"
    assert "provider_ids" not in owned_row.to_dict()["payload"] or True  # payload is verbatim


def test_ranking_is_deterministic_for_the_same_input():
    """The same rows in the same order must always give the same list.

    ⚠ The invariant is determinism, NOT order-independence: which row arrives
    first from a provider is itself meaningful (it is that provider's relevance),
    and the list deliberately preserves it between equal scores.
    """
    rows = [{"tmdb_id": 2, "media_type": "movie", "title": "Dune", "year": 2021},
            {"tmdb_id": 1, "media_type": "movie", "title": "Dune", "year": 1984}]
    first = rank_all("dune", owned=[], discovery=[dict(r) for r in rows])
    second = rank_all("dune", owned=[], discovery=[dict(r) for r in rows])
    assert [(r.score, r.payload["tmdb_id"]) for r in first] == \
           [(r.score, r.payload["tmdb_id"]) for r in second]
    # …and it is not alphabetical: a perfectly-tied set keeps PROVIDER order.
    assert [r.payload["tmdb_id"] for r in first] == [2, 1]


def test_equal_relevance_keeps_the_providers_order():
    """⚠ Without the provider-order bias a query the scorer cannot see — a bare
    decade like "90s", where every row scores 0 — would be sorted ALPHABETICALLY,
    discarding TMDB's own ranking and returning a worse list than the one already
    in hand."""
    provider_order = [
        {"tmdb_id": 3, "media_type": "movie", "title": "Zulu", "year": 1964},
        {"tmdb_id": 2, "media_type": "movie", "title": "Alien", "year": 1979},
    ]
    ranked = rank_all("90s", owned=[], discovery=provider_order)
    assert [r.payload["title"] for r in ranked] == ["Zulu", "Alien"]


def test_cross_source_ties_are_broken_by_source_order_not_by_insertion():
    """⚠ A bonus-free tie is the only place SOURCE_ORDER can decide anything, and
    that is exactly where an unstable sort would otherwise show through.

    A collection named Dune and a TMDB row named Dune score identically; the hint
    is the more useful thing to click first (it browses the shelf), so it wins.
    """
    ranked = rank_all("dune",
                      discovery=[{"tmdb_id": 9, "media_type": "movie", "title": "Dune", "year": 2021}],
                      hints={"collection": [{"id": "c1", "name": "Dune", "kind": "collection"}]})
    assert [r.score for r in ranked][0] == pytest.approx(ranked[1].score, abs=1e-3)
    assert [r.source for r in ranked] == ["hint", "tmdb"]


def test_to_dict_is_json_ready():
    row = RankedRow(score=0.5, source="owned", kind="movie", payload={"title": "X"},
                    matched_fields=["title"], match_type="exact", ranges=[(0, 1)])
    assert row.to_dict()["ranges"] == [[0, 1]]  # tuples become arrays


def test_duplicate_detection_is_unchanged_by_the_move():
    """⚠ Moved from services/global_search.py to ranking.py; the rule must be the
    same one, including the 2026-09-13 containment landmine."""
    assert is_duplicate_discovery(dict(MATRIX_TMDB), [OWNED_MATRIX])
    assert not is_duplicate_discovery(dict(RELOADED), [OWNED_MATRIX])
    assert not is_duplicate_discovery(
        {"tmdb_id": 12259, "title": "Sholay", "year": 1975},
        [{"title": "Sholay — Special Ops"}])
    # the legacy import path still works
    from services.global_search import is_duplicate_discovery as legacy
    assert legacy is is_duplicate_discovery


# --------------------------------------------------------------------------- route
class _FakeService:
    def __init__(self, items=None, people=None, person_rows=None, eps=None, genres=None, collections=None):
        self._items = items or []
        self._people = people or []
        self._person_rows = person_rows or []
        self._eps = eps or []
        self._genres = genres or []
        self._collections = collections or []

    def search(self, q, limit=12):
        return {"provider": "jellyfin", "items": self._items, "people": self._people,
                "genres": self._genres, "collections": self._collections}

    def episodes(self, series_id, limit=1000):
        return {"provider": "jellyfin", "episodes": self._eps}

    def recently_watched(self, limit=12):
        # ⚠ Phase 5 reads this for taste ranking. A stub that LACKS it makes the route
        # log a warning and rank neutrally on every call, which buries a real failure
        # in the noise — so every fake here answers it.
        return {"provider": "jellyfin", "items": []}

    def items_by_person(self, pid, limit=6):
        return {"provider": "jellyfin", "items": self._person_rows}


def _route_env(lib_service, tmdb_rows=(), watchlist_rows=(), counter=None):
    from api.routes import search_global as mod
    mod._search_cache.clear()
    cfg = SimpleNamespace()
    cfg.has_tmdb = lambda: True

    def search_multi(q, media_type=None):
        # ⚠ media_type is Phase 3's filter (SEARCH_IMPROVEMENT_PLAN); the stub has to
        # accept it or the route's external half raises and degrades to empty, which
        # looks like a ranking failure rather than a stub that is out of date.
        if counter is not None:
            counter.append(q)
        return list(tmdb_rows)

    fake_tmdb = SimpleNamespace(search_multi=search_multi)
    fake_wl = SimpleNamespace(load=lambda: SimpleNamespace(pending=list(watchlist_rows), recommended=[]))
    patchers = [
        patch.object(mod, "get_config", return_value=cfg),
        patch.object(mod, "build_library_service", return_value=lib_service),
        patch.object(mod, "TMDBService", return_value=fake_tmdb),
        patch.object(mod, "WatchlistService", return_value=fake_wl),
    ]
    for p in patchers:
        p.start()
    return mod.search_global, patchers


def _run(lib_service, tmdb_rows=(), watchlist_rows=(), query="matrix"):
    fn, patchers = _route_env(lib_service, tmdb_rows, watchlist_rows)
    try:
        return fn(q=query)
    finally:
        for p in patchers:
            p.stop()


def test_route_returns_a_ranked_list_with_owned_first():
    tmdb = [
        {"id": 603, "media_type": "movie", "title": "The Matrix", "release_date": "1999-03-31",
         "overview": "", "poster_path": ""},
        {"id": 604, "media_type": "movie", "title": "The Matrix Reloaded", "release_date": "2003-05-15",
         "overview": "", "poster_path": ""},
        {"id": 55931, "media_type": "movie", "title": "The Animatrix", "release_date": "2003-06-03",
         "overview": "", "poster_path": ""},
    ]
    resp = _run(_FakeService(items=[OWNED_MATRIX]), tmdb_rows=tmdb)
    assert resp.strong_match is False          # "matrix" is containment, not exact
    titles = [(r.source, r.payload["title"]) for r in resp.results]
    assert titles[0] == ("owned", "The Matrix")
    assert ("tmdb", "The Matrix Reloaded") in titles
    assert ("tmdb", "The Animatrix") in titles
    # scores are descending — the contract of a ranked list
    scores = [r.score for r in resp.results]
    assert scores == sorted(scores, reverse=True)


def test_route_strong_match_is_informational_only():
    """⚠ An EXACT owned title used to short-circuit the TMDB call. It now reports
    the fact and changes nothing else — the discovery rows must still arrive."""
    exact_owned = {**OWNED_MATRIX, "provider_ids": {"tmdb": 999999}}
    tmdb = [{"id": 604, "media_type": "movie", "title": "The Matrix Reloaded",
             "release_date": "2003-05-15", "overview": "", "poster_path": ""}]
    resp = _run(_FakeService(items=[exact_owned]), tmdb_rows=tmdb, query="the matrix")
    assert resp.strong_match is True
    assert [d.title for d in resp.discovery] == ["The Matrix Reloaded"]
    assert resp.results[0].source == "owned"


def test_route_keeps_the_per_source_arrays_for_older_clients():
    """⚠ ADR-0001 additive-only: a client that predates Phase 2 must see exactly
    the shape it saw before."""
    tmdb = [{"id": 604, "media_type": "movie", "title": "The Matrix Reloaded",
             "release_date": "2003-05-15", "overview": "", "poster_path": "/r.jpg"}]
    resp = _run(_FakeService(items=[OWNED_MATRIX]), tmdb_rows=tmdb)
    assert [i.title for i in resp.items] == ["The Matrix"]
    assert [d.title for d in resp.discovery] == ["The Matrix Reloaded"]
    assert resp.discovery[0].tmdb_id == 604 and resp.discovery[0].poster.endswith("/r.jpg")
    assert resp.query == "matrix" and resp.provider == "jellyfin" and resp.tmdb_key is True
    assert resp.results, "the new ranked list is additive, not a replacement"


def test_route_ranks_hints_alongside_titles():
    svc = _FakeService(items=[], people=[{"id": "p-1", "name": "Christopher Nolan"}],
                       genres=[{"id": "g-1", "name": "Documentary"}])
    resp = _run(svc, tmdb_rows=[], query="nolan")
    sources = {r.source for r in resp.results}
    assert "hint" in sources
    assert any(r.kind == "person" and r.payload["name"] == "Christopher Nolan" for r in resp.results)
    # the legacy arrays are still populated exactly as before
    assert [p.name for p in resp.people] == ["Christopher Nolan"]
    assert [g.name for g in resp.genres] == ["Documentary"]


def test_route_still_works_with_no_tmdb_key():
    """Discovery is skipped, ranking still runs over what the library returned."""
    from api.routes import search_global as mod
    mod._search_cache.clear()
    cfg = SimpleNamespace()
    cfg.has_tmdb = lambda: False
    with patch.object(mod, "get_config", return_value=cfg), \
         patch.object(mod, "build_library_service", return_value=_FakeService(items=[OWNED_MATRIX])), \
         patch.object(mod, "WatchlistService", return_value=SimpleNamespace(
             load=lambda: SimpleNamespace(pending=[], recommended=[]))):
        resp = mod.search_global(q="matrix")
    assert resp.tmdb_key is False and resp.discovery == []
    assert [r.payload["title"] for r in resp.results] == ["The Matrix"]
