"""Tests for query understanding (SEARCH_IMPROVEMENT_PLAN Phase 3).

The headline case is the plan's own: ``"tom hanks movies 1994"`` is a person, a
media type and a year — and matched as one literal string it finds NOTHING,
because that string is in no title anywhere.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.search.query_parser import (
    PERSON_MATCH_THRESHOLD,
    ParsedQuery,
    best_person_match,
    parse_query,
)


# --------------------------------------------------------------------------- year & decade
def test_a_bare_year_is_extracted_and_stripped_from_the_terms():
    p = parse_query("dune 2021")
    assert p.year == 2021 and p.year_range is None
    assert p.title_terms == "dune"


def test_a_full_decade_is_a_range_not_a_year():
    """⚠ The ordering trap: read the year FIRST and "1990s" becomes the single
    year 1990, silently turning a decade browse into a one-year search."""
    p = parse_query("1990s action")
    assert p.year is None
    assert p.year_range == (1990, 1999)
    assert p.title_terms == "action"


@pytest.mark.parametrize("token,expected", [
    ("90s", (1990, 1999)),
    ("80s", (1980, 1989)),
    ("30s", (1930, 1939)),      # nobody searching a media library means the 2030s
    ("20s", (2020, 2029)),      # …but nobody means the 1920s either
    ("00s", (2000, 2009)),
    ("'90s", (1990, 1999)),
])
def test_short_decades_follow_the_convention_films_are_discussed_in(token, expected):
    assert parse_query(f"comedy {token}").year_range == expected


def test_a_year_and_a_decade_are_the_same_kind_of_penalty_not_a_hard_filter():
    """The plan's rule, and the mistake that hid the real *Sholay*: a slightly-off
    year must lose an argument, not the whole match."""
    p = parse_query("dune 2021")
    assert p.matches_year(2021) is True
    assert p.matches_year(2020) is False
    # ⚠ No opinion when the row carries no year — never a mismatch.
    assert p.matches_year(None) is None
    assert p.matches_year("nonsense") is None
    # …and no year in the query means no opinion about any row.
    assert parse_query("dune").matches_year(1999) is None

    decade = parse_query("dune 80s")
    assert decade.matches_year(1984) is True
    assert decade.matches_year(2021) is False


# --------------------------------------------------------------------------- media type
def test_media_type_words_are_recognised_and_removed():
    assert parse_query("tom hanks movies").media_type == "movie"
    assert parse_query("tom hanks film").media_type == "movie"
    assert parse_query("the office series").media_type == "tv"
    assert parse_query("breaking bad tv").media_type == "tv"
    assert parse_query("dune").media_type is None


def test_type_words_are_matched_on_word_boundaries():
    """⚠ "TVs" must not be read as the type word "tv" — a title that merely
    contains one would be mangled into a different query."""
    assert parse_query("the TVs of tomorrow").media_type is None
    assert parse_query("the TVs of tomorrow").title_terms == "the TVs of tomorrow"


def test_only_the_first_type_word_is_removed():
    """A title may legitimately contain the word; stripping every occurrence would
    turn "movie movie" into nothing at all."""
    p = parse_query("movie the movie")
    assert p.media_type == "movie"
    assert p.title_terms == "the movie"


# --------------------------------------------------------------------------- terms & fallback
def test_the_plan_example_parses_into_all_three_parts():
    p = parse_query("tom hanks movies 1994")
    assert p.year == 1994
    assert p.media_type == "movie"
    assert p.title_terms == "tom hanks"
    assert p.has_filters is True


def test_scoring_query_falls_back_to_the_raw_text():
    """⚠ A query that is ONLY a filter ("1994") still has to match something.
    Falling back to "" would score 0 against every row and quietly turn a real
    query into an alphabetical list."""
    assert parse_query("1994").scoring_query == "1994"
    assert parse_query("dune 2021").scoring_query == "dune"
    assert parse_query("").scoring_query == ""


def test_terms_are_whitespace_normalised():
    assert parse_query("  dune   2021  ").title_terms == "dune"
    assert parse_query("   ").title_terms == ""


def test_a_query_with_no_structure_is_left_alone():
    p = parse_query("the dark knight")
    assert p.title_terms == "the dark knight"
    assert p.has_filters is False
    assert p.year is None and p.media_type is None and p.person_hint is None


# --------------------------------------------------------------------------- person hint
def test_a_person_is_only_named_when_a_candidate_list_is_supplied():
    """Without names to match against there is no way to tell a person from a
    title, so the parser says nothing rather than guessing."""
    assert parse_query("tom hanks").person_hint is None
    assert parse_query("tom hanks", ["Tom Hanks", "Meryl Streep"]).person_hint == "Tom Hanks"


def test_a_near_miss_name_still_matches():
    assert best_person_match("tom hanks", ["Tom Hanks"]) == "Tom Hanks"
    assert best_person_match("tomm hanks", ["Tom Hanks"]) == "Tom Hanks"


def test_a_title_is_not_silently_re_read_as_a_person():
    """⚠ The threshold is what stops every search for a film whose name resembles
    an actor from being treated as a person query."""
    assert PERSON_MATCH_THRESHOLD >= 80
    assert best_person_match("the dark knight", ["Tom Hanks"]) is None
    assert best_person_match("dune", ["Tom Hanks"]) is None


def test_the_original_spelling_is_returned_not_the_comparison_key():
    assert best_person_match("weiss", ["D. B. Weiss"]) == "D. B. Weiss"


def test_person_matching_without_names_or_text_is_silent():
    assert best_person_match("", ["Tom Hanks"]) is None
    assert best_person_match("tom hanks", []) is None
    assert best_person_match("tom hanks", None) is None


def test_the_person_text_is_NOT_stripped_from_the_terms():
    """The plan's example still searches the library for "tom hanks" while ALSO
    using him as a drill-down hint — removing the name would leave nothing to
    match on."""
    p = parse_query("tom hanks movies 1994", ["Tom Hanks"])
    assert p.person_hint == "Tom Hanks"
    assert "tom hanks" in p.title_terms


# --------------------------------------------------------------------------- route wiring
class _FakeService:
    def __init__(self, items=None, people=None, person_rows=None):
        self._items = items or []
        self._people = people or []
        self._person_rows = person_rows or []
        self.asked_person = None

    def search(self, q, limit=12):
        self.last_query = q
        return {"provider": "jellyfin", "items": self._items, "people": self._people,
                "genres": [], "collections": []}

    def episodes(self, series_id, limit=1000):
        return {"episodes": []}

    def recently_watched(self, limit=12):
        # ⚠ Phase 5 reads this for taste ranking. A stub that LACKS it makes the route
        # log a warning and rank neutrally on every call, which buries a real failure
        # in the noise — so every fake here answers it.
        return {"provider": "jellyfin", "items": []}

    def items_by_person(self, pid, limit=6):
        self.asked_person = pid
        return {"items": self._person_rows}


def _route_env(lib_service, tmdb_rows=()):
    from api.routes import search_global as mod
    mod._search_cache.clear()
    cfg = SimpleNamespace()
    cfg.has_tmdb = lambda: True
    calls = []

    def search_multi(q, media_type=None):
        calls.append({"q": q, "media_type": media_type})
        return list(tmdb_rows)

    fake_wl = SimpleNamespace(load=lambda: SimpleNamespace(pending=[], recommended=[]))
    patchers = [
        patch.object(mod, "get_config", return_value=cfg),
        patch.object(mod, "build_library_service", return_value=lib_service),
        patch.object(mod, "TMDBService", return_value=SimpleNamespace(search_multi=search_multi)),
        patch.object(mod, "WatchlistService", return_value=fake_wl),
    ]
    for p in patchers:
        p.start()
    return mod.search_global, patchers, calls


def test_route_sends_the_stripped_terms_and_the_type_to_tmdb():
    """"tom hanks movies 1994" must reach TMDB as "tom hanks" + a movie filter —
    the whole query is what found nothing before."""
    svc = _FakeService()
    fn, patchers, calls = _route_env(svc)
    try:
        fn(q="tom hanks movies 1994")
    finally:
        for p in patchers:
            p.stop()
    assert calls and calls[0]["q"] == "tom hanks"
    assert calls[0]["media_type"] == "movie"
    # …and the library is searched for the same stripped terms.
    assert svc.last_query == "tom hanks"


def test_route_prefers_the_person_the_query_named():
    """Phase 3's explicit ask: connect the parsed person to the drill-down path
    that already exists, instead of always taking whoever the provider listed
    first."""
    svc = _FakeService(
        people=[{"id": "p-first", "name": "Somebody Else"}, {"id": "p-nolan", "name": "Christopher Nolan"}],
        person_rows=[{"id": "m1", "kind": "movie", "title": "Tenet", "year": 2020}],
    )
    fn, patchers, _ = _route_env(svc)
    try:
        resp = fn(q="nolan")
    finally:
        for p in patchers:
            p.stop()
    assert svc.asked_person == "p-nolan"
    assert resp.person_titles[0].title == "Tenet"
    # the legacy people array is still everything the provider returned
    assert len(resp.people) == 2


def test_route_falls_back_to_the_first_person_when_the_query_names_nobody():
    svc = _FakeService(people=[{"id": "p-first", "name": "Somebody Else"}], person_rows=[])
    fn, patchers, _ = _route_env(svc)
    try:
        fn(q="something unrelated")
    finally:
        for p in patchers:
            p.stop()
    assert svc.asked_person == "p-first"


def test_a_decade_query_keeps_the_providers_order():
    """A bare decade is unscoreable as text, so TMDB's own ranking must survive —
    the ranked list is not allowed to alphabetise it."""
    rows = [
        {"id": 1, "media_type": "movie", "title": "Zulu", "release_date": "1964-01-01",
         "overview": "", "poster_path": ""},
        {"id": 2, "media_type": "movie", "title": "Alien", "release_date": "1979-05-25",
         "overview": "", "poster_path": ""},
    ]
    fn, patchers, _ = _route_env(_FakeService(), tmdb_rows=rows)
    try:
        resp = fn(q="80s")
    finally:
        for p in patchers:
            p.stop()
    assert [r.payload["title"] for r in resp.results] == ["Zulu", "Alien"]
