"""The ROUTE half of Phase 6 — where the embedding fallback is allowed to appear, and where not.

`tests/test_semantic_search.py` pins the core's rules (the trigger, the tier, the per-profile keying).
This file pins the WIRING of those rules into `/api/search/global`, which is a different set of ways
to be wrong:

* the fallback must be invisible unless the trigger says otherwise — asserted by proving the seam is
  never even CALLED on a query the string matcher answered, not by inspecting the response;
* a hit must reach the GROUPED array the screens render (`items`), because reaching only the ranked
  `results` list would make the whole feature invisible on both search surfaces;
* a title that appears twice must appear once.

⚠ Every test here stubs the model at its two seams (`semantic_available`, `semantic_hits`), so
nothing downloads anything and the suite stays offline.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.search import semantic


class _FakeService:
    """The smallest library service the route needs, plus the index source it now fetches."""

    def __init__(self, items=(), index_rows=()):
        self._items = list(items)
        self._index = list(index_rows)
        self.index_calls = 0

    def search(self, q, limit=12):
        return {"provider": "jellyfin", "items": self._items, "people": [], "genres": [],
                "collections": []}

    def episodes(self, series_id, limit=1000):
        return {"provider": "jellyfin", "episodes": []}

    def recently_watched(self, limit=12):
        return {"provider": "jellyfin", "items": []}

    def index_rows(self, limit=None):
        self.index_calls += 1
        return list(self._index)


def _owned(item_id, title, year=2010, kind="movie"):
    return {"id": item_id, "kind": kind, "title": title, "year": year, "genres": [],
            "rating": None, "played": False, "playback_position": 0, "runtime": 8640,
            "play_count": 0, "provider_ids": {}}


def _index_row(item_id, title, year=2010, kind="movie", overview=""):
    return {"id": item_id, "item_id": item_id, "title": title, "year": year, "kind": kind,
            "genres": ["Action"], "overview": overview}


@pytest.fixture
def route_env():
    """Patch the route's seams and hand back its callable + the stubs' call records.

    ⚠ ``WatchlistService`` is patched to EMPTY on purpose. It is unpatched in the sibling search
    tests, which is why they read the developer's real ``watchlist.json`` (471 rows in this checkout);
    for these tests that is not cosmetic — this feature's trigger reads a score, so 471 real rows
    would decide whether it fires. One test below patches a queue row back IN, because the
    queue-vs-library distinction is itself a rule worth pinning.
    """
    from api.routes import search_global as mod

    mod._search_cache.clear()
    state = {"hits": [], "hits_calls": 0, "available_calls": 0, "pref": True, "queue": []}
    cfg = SimpleNamespace()
    cfg.has_tmdb = lambda: False

    def fake_hits(profile_id, query, rows, **kwargs):
        state["hits_calls"] += 1
        state["profile_id"] = profile_id
        state["rows"] = list(rows)
        return list(state["hits"])

    def fake_available():
        state["available_calls"] += 1
        return True

    class _Prefs:
        def semantic(self, profile_id):
            state["pref_profile"] = profile_id
            return state["pref"]

        def personalized(self, profile_id):
            return False

    class _Entry:
        """A queue entry as ``_watchlist_rows`` expects it: something with ``to_dict()``."""

        def __init__(self, row):
            self._row = row

        def to_dict(self):
            return dict(self._row)

    class _Queue:
        def load(self):
            return SimpleNamespace(pending=[_Entry(r) for r in state["queue"]], recommended=[])

    patchers = [
        patch.object(mod, "get_config", return_value=cfg),
        patch.object(mod, "TMDBService", return_value=SimpleNamespace(search_multi=lambda q, media_type=None: [], genre_names=lambda: {})),
        patch.object(mod, "SearchPrefsStore", return_value=_Prefs()),
        patch.object(mod, "WatchlistService", return_value=_Queue()),
        patch.object(mod, "semantic_available", fake_available),
        patch.object(mod, "semantic_hits", fake_hits),
    ]
    for p in patchers:
        p.start()
    semantic.clear_cache()
    yield mod.search_global, state
    semantic.clear_cache()
    for p in patchers:
        p.stop()


def _run(env, service, query):
    fn, state = env
    from api.routes import search_global as mod
    with patch.object(mod, "build_library_service", return_value=service):
        return fn(q=query), state


# --------------------------------------------------------------------------- when it fires
def test_a_weak_query_gets_the_embedding_neighbours_on_both_lists(route_env):
    """The whole phase, end to end: nothing in the library matches the words, and the two closest
    titles still arrive — in the ranked list AND in the group the screens render."""
    service = _FakeService(
        items=[_owned("weak-1", "A Weak Lexical Match")],
        index_rows=[_index_row("i1", "Inception", overview="dreams within dreams"),
                    _index_row("h1", "Hereditary")],
    )
    route_env[1]["hits"] = [(_index_row("i1", "Inception"), 0.42)]
    resp, state = _run(route_env, service, "something with a twist ending")

    assert state["hits_calls"] == 1
    assert state["rows"] and {r["item_id"] for r in state["rows"]} == {"i1", "h1"}
    ids = [row.id for row in resp.items]
    assert "i1" in ids, "the fallback row never reached the group the UI renders"
    assert resp.items[ids.index("i1")].match_type == "semantic"
    ranked_ids = [row.payload.get("id") for row in resp.results if row.match_type == "semantic"]
    assert ranked_ids == ["i1"]


def test_a_strong_query_never_touches_the_fallback_at_all(route_env):
    """⚠ Asserted at the SEAM, not in the response: a title the library already has must cost a
    dictionary lookup and nothing else. A response-shaped assertion would pass even if the model had
    been loaded and the library fetched to produce rows that happened to rank low."""
    service = _FakeService(items=[_owned("m1", "The Matrix")], index_rows=[_index_row("i1", "Inception")])
    resp, state = _run(route_env, service, "the matrix")

    assert state["hits_calls"] == 0
    assert state["available_calls"] == 0, "the model was loaded for a query that already matched"
    assert service.index_calls == 0, "the library was fetched for a query that already matched"
    assert [row.id for row in resp.items] == ["m1"]


def test_the_switch_off_means_no_model_and_no_fetch(route_env):
    route_env[1]["pref"] = False
    service = _FakeService(items=[], index_rows=[_index_row("i1", "Inception")])
    resp, state = _run(route_env, service, "something with a twist ending")

    assert state["hits_calls"] == 0 and state["available_calls"] == 0
    assert service.index_calls == 0
    assert resp.items == []


def test_a_missing_model_is_not_asked_for_the_library(route_env):
    """A box without the wheel must not pay for the Jellyfin fetch either."""
    from api.routes import search_global as mod
    service = _FakeService(index_rows=[_index_row("i1", "Inception")])
    with patch.object(mod, "semantic_available", return_value=False):
        resp, state = _run(route_env, service, "something with a twist ending")

    assert state["hits_calls"] == 0
    assert service.index_calls == 0
    assert resp.items == []


def test_a_short_query_is_not_semantically_searched(route_env):
    """⚠ The 2-character case, at the route: the library returned nothing, top score is 0, and
    WITHOUT the length floor that is indistinguishable from a failed search."""
    service = _FakeService(items=[], index_rows=[_index_row("i1", "Inception")])
    resp, state = _run(route_env, service, "th")

    assert state["hits_calls"] == 0 and service.index_calls == 0
    assert resp.items == []


# --------------------------------------------------------------------------- what it does with them
def test_a_neighbour_that_is_already_in_the_library_appears_once(route_env):
    """A weak lexical row can be the same title as the strongest neighbour. One row per title — and
    the one that keeps the query's match spans is the lexical one."""
    service = _FakeService(items=[_owned("m1", "The Matrix", year=1999)],
                           index_rows=[_index_row("m1", "The Matrix", year=1999)])
    route_env[1]["hits"] = [(_index_row("m1", "The Matrix", year=1999), 0.5)]
    resp, _ = _run(route_env, service, "something like the matrix")

    assert [row.id for row in resp.items].count("m1") == 1
    assert len([r for r in resp.results if r.payload.get("id") == "m1"]) == 1


def test_the_index_is_built_for_the_request_s_own_profile(route_env):
    """⚠ §11 at the route: the fallback asks for the profile the SESSION published, so two household
    members cannot be answered from one index. Here the session is absent, so the owner is the app's
    own default key — never a value another profile could share."""
    service = _FakeService(items=[], index_rows=[_index_row("i1", "Inception")])
    route_env[1]["hits"] = [(_index_row("i1", "Inception"), 0.4)]
    _, state = _run(route_env, service, "something with a twist ending")

    assert state["hits_calls"] == 1
    assert state["profile_id"] == semantic.DEFAULT_IDENTITY_KEY


def test_a_broken_preference_file_fails_closed(route_env):
    """An unreadable store must not switch a feature ON — the same direction `_taste` fails in."""
    from api.routes import search_global as mod

    class _Broken:
        def semantic(self, profile_id):
            raise RuntimeError("search_prefs.json is a directory now")

    service = _FakeService(index_rows=[_index_row("i1", "Inception")])
    with patch.object(mod, "SearchPrefsStore", return_value=_Broken()):
        resp, state = _run(route_env, service, "something with a twist ending")

    assert state["hits_calls"] == 0 and service.index_calls == 0
    assert resp.items == []


def test_a_high_scoring_QUEUE_row_does_not_suppress_the_fallback(route_env):
    """⚠⚠ A rule found by measuring, not by reasoning — and it changed the code.

    Against *"something with a twist ending"*, two rows of his 471-row acquisition queue fuzzy-match
    at **0.742** (*"Teach You a Lesson"*, *"A Toxic Love Story"* — both real rows, printed by the
    scorer). That is a false positive ABOVE a containment hit, and with the trigger reading the whole
    ranked list it silently suppressed the embedding fallback for a query nothing in his library
    matched. The trigger therefore reads only the sources that mean "a TITLE matched": owned + tmdb.
    """
    route_env[1]["queue"] = [
        {"title": "Teach You a Lesson", "year": 2026, "isSeries": False, "tmdbId": 900001},
        {"title": "A Toxic Love Story", "year": 2026, "isSeries": False, "tmdbId": 900002},
    ]
    service = _FakeService(items=[], index_rows=[_index_row("i1", "Inception")])
    route_env[1]["hits"] = [(_index_row("i1", "Inception"), 0.4)]
    resp, state = _run(route_env, service, "something with a twist ending")

    assert state["hits_calls"] == 1, "an acquisition-queue false positive suppressed the fallback"
    assert any(row.id == "i1" for row in resp.items)


def test_a_QUEUE_row_alone_never_suppresses_the_fallback(route_env):
    """The other direction, and it is a deliberate CONSEQUENCE of the rule rather than an accident.

    The queue is not consulted at all — not to suppress, not to trigger. Rather than special-casing
    "a strong queue match counts but a fuzzy one does not" (see the test above: the fuzzy case is
    real, 0.742 against a conversational query), the queue is simply not a source that can answer
    "does he already have this?". So an exact queue match for *inception* leaves the embeddings free
    to find library titles NEAR it, and the queue row keeps its place in the list regardless.
    """
    route_env[1]["queue"] = [{"title": "Inception", "year": 2010, "isSeries": False, "tmdbId": 27205}]
    service = _FakeService(items=[], index_rows=[_index_row("i1", "Interstellar", 2014)])
    route_env[1]["hits"] = [(_index_row("i1", "Interstellar", 2014), 0.44)]
    resp, state = _run(route_env, service, "inception")

    assert state["hits_calls"] == 1
    assert any(row.id == "i1" for row in resp.items)
