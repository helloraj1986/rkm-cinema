"""Tests for instant search (SEARCH_IMPROVEMENT_PLAN Phase 4) — the backend half.

Two things belong to the server here:

1. **A 1–2 character query never reaches TMDB.** Two characters are a PREFIX, not
   a search: TMDB answers one with noise (a large fraction of the catalogue starts
   with "th"), and it is the round-trip that would otherwise fire on every
   keystroke of every word.
2. **The matched span travels with the row.** The grouped UI renders `items` and
   `discovery`, not the ranked `results`, so the span has to be carried across —
   otherwise the client would have to re-find the substring itself, which is a
   second implementation of the scorer's decision and is wrong for every fuzzy
   match.

The client-side half (debounce, cancellation, rendering the span) is covered by
`frontend/src/features/search/lib.test.ts`.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.routes import search as legacy_route
from api.routes import search_global as global_route


# --------------------------------------------------------------------------- the short-query floor
def test_the_two_routes_agree_on_the_short_query_floor():
    """⚠ Declared in both routes rather than imported (the legacy endpoint should
    not gain a dependency on the newer module), so a test is what keeps them from
    drifting apart."""
    assert global_route.MIN_TMDB_QUERY_LEN == legacy_route.MIN_TMDB_QUERY_LEN
    assert global_route.MIN_TMDB_QUERY_LEN >= 3


class _FakeService:
    def __init__(self, items=None):
        self._items = items or []

    def search(self, q, limit=12):
        return {"provider": "jellyfin", "items": self._items, "people": [],
                "genres": [], "collections": []}

    def episodes(self, series_id, limit=1000):
        return {"episodes": []}

    def items_by_person(self, pid, limit=6):
        return {"items": []}


def _global_env(lib_service, tmdb_rows=()):
    global_route._search_cache.clear()
    cfg = SimpleNamespace()
    cfg.has_tmdb = lambda: True
    calls = []

    def search_multi(q, media_type=None):
        calls.append(q)
        return list(tmdb_rows)

    patchers = [
        patch.object(global_route, "get_config", return_value=cfg),
        patch.object(global_route, "build_library_service", return_value=lib_service),
        patch.object(global_route, "TMDBService",
                     return_value=SimpleNamespace(search_multi=search_multi)),
        patch.object(global_route, "WatchlistService", return_value=SimpleNamespace(
            load=lambda: SimpleNamespace(pending=[], recommended=[]))),
    ]
    for p in patchers:
        p.start()
    return global_route.search_global, patchers, calls


@pytest.mark.parametrize("query", ["d", "du", "t", "3"])
def test_a_short_query_never_reaches_tmdb(query):
    fn, patchers, calls = _global_env(_FakeService())
    try:
        resp = fn(q=query)
    finally:
        for p in patchers:
            p.stop()
    assert calls == [], f"{query!r} should not have been sent to TMDB"
    assert resp.discovery == []
    # ⚠ The library half still runs — a prefix IS answerable from what he owns.
    assert resp.results == []


def test_a_three_character_query_does_reach_tmdb():
    """The floor is a floor, not a ban — 'dun' may legitimately be 'Dune'."""
    fn, patchers, calls = _global_env(_FakeService(), tmdb_rows=[
        {"id": 438631, "media_type": "movie", "title": "Dune", "release_date": "2021-10-22",
         "overview": "", "poster_path": ""}])
    try:
        resp = fn(q="dun")
    finally:
        for p in patchers:
            p.stop()
    assert calls == ["dun"]
    assert [d.title for d in resp.discovery] == ["Dune"]


def test_a_short_query_leaves_the_tmdb_key_flag_alone():
    """⚠ `tmdb_key` reports whether TMDB is CONFIGURED — the UI reads False as
    "discovery is off, library only". A short query is not that, and reporting it
    as such would print a false sentence under an empty result list."""
    fn, patchers, _ = _global_env(_FakeService())
    try:
        resp = fn(q="du")
    finally:
        for p in patchers:
            p.stop()
    assert resp.tmdb_key is True


# --------------------------------------------------------------------------- the matched span travels with the row
def test_owned_rows_carry_the_span_the_ranker_computed():
    items = [{"id": "m1", "kind": "movie", "title": "The Dark Knight", "year": 2008,
              "genres": [], "rating": 9.0, "played": False, "playback_position": 0,
              "runtime": 0, "play_count": 0, "provider_ids": {"tmdb": 155}}]
    fn, patchers, _ = _global_env(_FakeService(items=items))
    try:
        resp = fn(q="dark")
    finally:
        for p in patchers:
            p.stop()
    row = resp.items[0]
    assert row.ranges == [[4, 8]], "offsets into the DISPLAYED title"
    assert row.match_type == "containment"
    # …and the ranked list carries the same span, so the two cannot disagree.
    ranked = next(r for r in resp.results if r.source == "owned")
    assert ranked.ranges == row.ranges and ranked.match_type == row.match_type


def test_discovery_rows_carry_their_span_too():
    fn, patchers, _ = _global_env(_FakeService(), tmdb_rows=[
        {"id": 155, "media_type": "movie", "title": "The Dark Knight", "release_date": "2008-07-18",
         "overview": "", "poster_path": ""}])
    try:
        resp = fn(q="dark")
    finally:
        for p in patchers:
            p.stop()
    disc = resp.discovery[0]
    assert disc.ranges == [[4, 8]]
    assert disc.match_type == "containment"


def test_a_fuzzy_match_reports_no_span_but_still_reports_the_kind():
    """⚠ The case that makes a client-side highlight wrong: "the knght" matched
    *The Dark Knight* with no substring to point at. The kind still says why."""
    items = [{"id": "m1", "kind": "movie", "title": "The Dark Knight", "year": 2008,
              "genres": [], "rating": 9.0, "played": False, "playback_position": 0,
              "runtime": 0, "play_count": 0, "provider_ids": {}}]
    fn, patchers, _ = _global_env(_FakeService(items=items))
    try:
        resp = fn(q="the knght")
    finally:
        for p in patchers:
            p.stop()
    assert resp.items[0].match_type == "fuzzy"
    assert resp.items[0].ranges == []


def test_the_per_source_arrays_are_still_complete_without_a_ranked_list():
    """⚠ Ranking is additive: if it ever returns nothing, the arrays a pre-Phase-2
    client reads must be untouched — not emptied alongside it."""
    items = [{"id": "m1", "kind": "movie", "title": "The Dark Knight", "year": 2008,
              "genres": [], "rating": 9.0, "played": False, "playback_position": 0,
              "runtime": 0, "play_count": 0, "provider_ids": {}}]
    fn, patchers, _ = _global_env(_FakeService(items=items))
    try:
        with patch.object(global_route, "rank_all", side_effect=RuntimeError("boom")):
            resp = fn(q="dark")
    finally:
        for p in patchers:
            p.stop()
    assert [i.title for i in resp.items] == ["The Dark Knight"]
    assert resp.results == []
