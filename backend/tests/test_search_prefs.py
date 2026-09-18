"""Tests for per-viewer search preferences (SEARCH_IMPROVEMENT_PLAN Phase 5).

Two halves, and both matter:

* the STORE — per-profile, atomic, corrupt-tolerant, defaulting to ON;
* the RANKING — taste reorders equally-relevant discovery rows and can never
  overturn a better title match, and switching it off gives the old order back.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.main
from services.search_prefs import DEFAULT_PERSONALIZED, SearchPrefsStore

client = TestClient(api.main.app)


def _store(tmp_path) -> SearchPrefsStore:
    return SearchPrefsStore(path=tmp_path / "search_prefs.json")


# --------------------------------------------------------------------------- the store
def test_personalization_defaults_on_for_a_profile_that_has_never_chosen(tmp_path):
    """⚠ The default is the important half of the entry: a missing row means "never
    expressed a preference", not "off". Storing only the people who turned it off
    would invert on the day someone reads the file."""
    assert DEFAULT_PERSONALIZED is True
    store = _store(tmp_path)
    assert store.personalized("uid-a") is True
    assert store.row("uid-a") == {}


def test_a_choice_is_stored_per_profile_and_cannot_bleed_across(tmp_path):
    """⚠ Keyed by PROFILE, not by account: the app separates the account that signed
    in from the profile that is watching (§11), and taste belongs to the watcher."""
    store = _store(tmp_path)
    store.set_personalized("uid-a", False)
    assert store.personalized("uid-a") is False
    assert store.personalized("uid-b") is True, "one person's choice is not the household's"
    assert store.personalized("") is True


def test_a_choice_can_be_switched_back_on(tmp_path):
    store = _store(tmp_path)
    store.set_personalized("uid-a", False)
    row = store.set_personalized("uid-a", True)
    assert row["personalized"] is True and store.personalized("uid-a") is True


def test_an_unknown_profile_id_is_refused_rather_than_stored(tmp_path):
    """⚠ A route that ran without a published identity would otherwise write a
    setting that belongs to nobody and could never be read back."""
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.set_personalized("", False)
    with pytest.raises(ValueError):
        store.set_personalized(None, False)


def test_a_corrupt_file_falls_back_to_defaults_and_is_left_as_evidence(tmp_path):
    path = tmp_path / "search_prefs.json"
    path.write_text("{not json at all", encoding="utf-8")
    store = SearchPrefsStore(path=path)
    assert store.personalized("uid-a") is True          # the feature keeps working
    assert path.read_text(encoding="utf-8") == "{not json at all"   # not overwritten


def test_a_junk_payload_does_not_become_a_junk_setting(tmp_path):
    path = tmp_path / "search_prefs.json"
    path.write_text(json.dumps({"users": "not a dict"}), encoding="utf-8")
    assert SearchPrefsStore(path=path).personalized("uid-a") is True

    path.write_text(json.dumps({"users": {"uid-a": {"personalized": "yes"}}}), encoding="utf-8")
    # A non-boolean must fall back to the default rather than be truthy-coerced —
    # "yes" is not a decision this app made.
    assert SearchPrefsStore(path=path).personalized("uid-a") is True


def test_writes_are_atomic_and_leave_no_debris(tmp_path):
    store = _store(tmp_path)
    store.set_personalized("uid-a", False)
    left = [p.name for p in tmp_path.iterdir()]
    assert left == ["search_prefs.json"], left
    assert json.loads((tmp_path / "search_prefs.json").read_text())["users"]["uid-a"]["personalized"] is False


def test_the_store_creates_its_directory(tmp_path):
    store = SearchPrefsStore(path=tmp_path / "nested" / "deeper" / "search_prefs.json")
    store.set_personalized("uid-a", False)
    assert store.personalized("uid-a") is False


# --------------------------------------------------------------------------- the routes
def test_the_routes_read_and_write_this_profiles_preference(tmp_path, signed_in):
    """`signed_in` mints a real session; the store is isolated so no test can touch
    the developer's own preferences file."""
    from api.routes import search_prefs as route_mod
    c = signed_in(TestClient(api.main.app))
    with patch.object(route_mod, "SearchPrefsStore", lambda: _store(tmp_path)):
        before = c.get("/api/search/prefs")
        assert before.status_code == 200
        assert before.json()["personalized"] is True

        off = c.post("/api/search/prefs", json={"personalized": False})
        assert off.status_code == 200 and off.json()["personalized"] is False
        assert c.get("/api/search/prefs").json()["personalized"] is False

        on = c.post("/api/search/prefs", json={"personalized": True})
        assert on.status_code == 200 and on.json()["personalized"] is True


def test_the_endpoint_reports_whose_setting_it_is(tmp_path, signed_in):
    from api.routes import search_prefs as route_mod
    c = signed_in(TestClient(api.main.app))
    with patch.object(route_mod, "SearchPrefsStore", lambda: _store(tmp_path)):
        assert c.get("/api/search/prefs").json()["profile_name"] != ""


# --------------------------------------------------------------------------- taste in the ranking
COMEDY, DRAMA = 35, 18


class _FakeLibrary:
    """A library whose viewer has watched exactly what the test says they have."""

    def __init__(self, watched=None):
        self._watched = watched or []

    def search(self, q, limit=12):
        return {"provider": "jellyfin", "items": [], "people": [], "genres": [], "collections": []}

    def episodes(self, series_id, limit=1000):
        return {"episodes": []}

    def items_by_person(self, pid, limit=6):
        return {"items": []}

    def recently_watched(self, limit=12):
        return {"provider": "jellyfin", "items": list(self._watched)}


def _route(watched, rows, *, personalized: bool, tmp_path, owned=None):
    """Drive the REAL route with a stubbed library, TMDB and preference store."""
    from api.routes import search_global as mod
    mod._search_cache.clear()
    cfg = SimpleNamespace()
    cfg.has_tmdb = lambda: True
    store = _store(tmp_path)
    if not personalized:
        store.set_personalized("uid-a", False)

    lib = _FakeLibrary(list(watched))
    if owned is not None:
        lib.search = lambda q, limit=12: {"provider": "jellyfin", "items": list(owned),
                                          "people": [], "genres": [], "collections": []}

    patchers = [
        patch.object(mod, "get_config", return_value=cfg),
        patch.object(mod, "build_library_service", return_value=lib),
        patch.object(mod, "TMDBService", return_value=SimpleNamespace(
            search_multi=lambda q, media_type=None: list(rows),
            genre_names=lambda: {COMEDY: "Comedy", DRAMA: "Drama"},
        )),
        patch.object(mod, "WatchlistService", return_value=SimpleNamespace(
            load=lambda: SimpleNamespace(pending=[], recommended=[]))),
        patch.object(mod, "current_session", return_value=SimpleNamespace(
            profile_id=lambda: "uid-a", profile_name=lambda: "Rajeev")),
        patch.object(mod, "SearchPrefsStore", lambda: store),
    ]
    for p in patchers:
        p.start()
    try:
        return mod.search_global(q="dune")
    finally:
        for p in patchers:
            p.stop()


def _tmdb_row(tmdb_id, title, genre_id, year=2021):
    return {"id": tmdb_id, "media_type": "movie", "title": title, "release_date": f"{year}-01-01",
            "overview": "", "poster_path": "", "genre_ids": [genre_id]}


COMEDY_VIEWER = [{"title": "Something Funny", "genres": ["Comedy"], "play_count": 2, "played": True}]


def _titles(resp):
    return [r.payload["title"] for r in resp.results if r.source == "tmdb"]


def test_taste_reorders_equally_relevant_discovery_rows(tmp_path):
    """⚠ Two titles of the SAME length score identically on relevance, so taste is
    the only thing that can order them — which is precisely what personalization is
    for, and precisely how subtle it has to be to be safe."""
    first, second = "Dune Part One", "Dune Part Two"      # equal length ⇒ equal score
    assert len(first) == len(second)
    rows = [_tmdb_row(1, second, DRAMA), _tmdb_row(2, first, COMEDY)]
    assert _titles(_route(COMEDY_VIEWER, rows, personalized=True, tmp_path=tmp_path)) == [first, second]


def test_switching_it_off_gives_the_providers_order_back(tmp_path):
    """The falsification direction for the test above: same data, preference OFF,
    the taste row is NOT promoted — it keeps TMDB's order."""
    rows = [_tmdb_row(1, "Dune Part Two", DRAMA), _tmdb_row(2, "Dune Part One", COMEDY)]
    assert _titles(_route(COMEDY_VIEWER, rows, personalized=False, tmp_path=tmp_path)) == \
        ["Dune Part Two", "Dune Part One"]


def test_a_viewer_with_no_history_ranks_exactly_as_if_off(tmp_path):
    rows = [_tmdb_row(1, "Dune Part Two", DRAMA), _tmdb_row(2, "Dune Part One", COMEDY)]
    assert _titles(_route([], rows, personalized=True, tmp_path=tmp_path)) == \
        ["Dune Part Two", "Dune Part One"]


def test_taste_can_never_overturn_a_better_title_match(tmp_path):
    """⚠ THE SUBTLETY GUARANTEE, and the reason the bonus is bounded by the tier
    step: a genre the viewer loves must not outrank the title they actually typed.
    At a 12% multiplier the comedy below would jump ahead — and search would read as
    broken, not as smart."""
    rows = [
        _tmdb_row(1, "Dune Part Two", COMEDY),   # his favourite genre, weaker match
        _tmdb_row(2, "Dune", DRAMA),             # exact match, genre he never watches
    ]
    assert _titles(_route(COMEDY_VIEWER, rows, personalized=True, tmp_path=tmp_path))[0] == "Dune"


def test_taste_is_applied_only_to_titles_he_does_not_own(tmp_path):
    """⚠ Re-ordering his OWN library by taste would make a search for a film he owns
    feel like it ignored him — the plan scopes personalization to discovery.

    Asserted as a DIFFERENCE between the two runs, on the same data: the discovery
    row's score moves when taste is switched on and the owned row's does not.
    """
    rows = [_tmdb_row(1, "Dune Part Two", COMEDY)]          # his favourite genre
    owned = [{"id": "m1", "kind": "movie", "title": "Dune", "year": 2021,
              "genres": ["Drama"], "played": False, "playback_position": 0,
              "runtime": 0, "play_count": 0, "provider_ids": {"tmdb": 438631}}]

    on = _route(COMEDY_VIEWER, rows, personalized=True, tmp_path=tmp_path, owned=owned)
    off = _route(COMEDY_VIEWER, rows, personalized=False, tmp_path=tmp_path, owned=owned)

    def score_of(resp, source):
        return next(r.score for r in resp.results if r.source == source)

    assert score_of(on, "owned") == score_of(off, "owned"), "taste must not touch owned rows"
    assert score_of(on, "tmdb") > score_of(off, "tmdb"), "…and must move discovery rows"
    assert on.results[0].source == "owned", "his own copy still leads"


def test_a_failing_watched_lookup_degrades_to_neutral_not_to_a_failed_search(tmp_path):
    """A personalization failure must never be able to fail a search."""
    from api.routes import search_global as mod
    rows = [_tmdb_row(1, "Dune Part Two", DRAMA), _tmdb_row(2, "Dune Part One", COMEDY)]

    class _Broken(_FakeLibrary):
        def recently_watched(self, limit=12):
            raise RuntimeError("jellyfin is down")

    mod._search_cache.clear()
    cfg = SimpleNamespace()
    cfg.has_tmdb = lambda: True
    patchers = [
        patch.object(mod, "get_config", return_value=cfg),
        patch.object(mod, "build_library_service", return_value=_Broken()),
        patch.object(mod, "TMDBService", return_value=SimpleNamespace(
            search_multi=lambda q, media_type=None: list(rows),
            genre_names=lambda: {COMEDY: "Comedy", DRAMA: "Drama"})),
        patch.object(mod, "WatchlistService", return_value=SimpleNamespace(
            load=lambda: SimpleNamespace(pending=[], recommended=[]))),
        patch.object(mod, "current_session", return_value=SimpleNamespace(
            profile_id=lambda: "uid-a", profile_name=lambda: "Rajeev")),
        patch.object(mod, "SearchPrefsStore", lambda: _store(tmp_path)),
    ]
    for p in patchers:
        p.start()
    try:
        resp = mod.search_global(q="dune")
    finally:
        for p in patchers:
            p.stop()
    assert _titles(resp) == ["Dune Part Two", "Dune Part One"]
    assert resp.discovery, "the search still returned its rows"
