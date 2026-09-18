"""Tests for the global-search feature (GLOBAL_SEARCH_PLAN Phases 1–2).

Pure scoring/state helpers, the Jellyfin provider search (mocked urlopen at the
provider boundary), and the /api/search/global route behaviour (library-first,
strong-match gating, TMDB dedupe).
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

from services.global_search import (
    EXACT_TITLE_SCORE, is_duplicate_discovery, next_episode_facts, normalize_title,
    owned_state, owned_strong_match, title_match_score,
)


# --------------------------------------------------------------------------- pure helpers
def test_normalize_title_key():
    assert normalize_title("3 Body Problem:") == "3 body problem"
    assert normalize_title("  The   Matrix- Reloaded  ") == "the matrix reloaded"
    assert normalize_title("") == ""


def test_title_match_score_tiers_and_years():
    assert title_match_score("3 body problem", "3 Body Problem") == 3
    assert title_match_score("3 Body", "3 Body Problem") == 2
    assert title_match_score("dark", "Dark", query_year=2017, title_year=2017) == 3
    # same name, different year (remake) is NOT a strong match
    assert title_match_score("Cape Fear", "Cape Fear", query_year=1962, title_year=1991) == 0
    assert title_match_score("zzz", "No Match At All") == 0


def test_owned_match_tiers_and_the_gate_that_reads_them():
    """⚠ The tiers are unchanged; the GATE is what changed (2026-09-13).

    ``owned_strong_match`` still reports containment as 2 — but the route now compares against
    ``EXACT_TITLE_SCORE`` (3), because a longer owned title that merely CONTAINS the query is a
    DIFFERENT work. Pinning both numbers here is the point: if someone later "fixes" the gate back to
    >= 2, the assertion below that 2 < EXACT_TITLE_SCORE fails and says why.
    """
    owned = [{"title": "3 Body Problem", "year": 2024}, {"title": "Dark", "year": 2017}]
    assert owned_strong_match(owned, "3 body problem") == EXACT_TITLE_SCORE   # the library has it
    assert owned_strong_match(owned, "3 Body") == 2                           # containment only
    assert owned_strong_match(owned, "Something Else") == 0
    # The library has NOT answered a containment query — which is what let the real "Sholay" be hidden.
    assert owned_strong_match(owned, "3 Body") < EXACT_TITLE_SCORE


def test_duplicate_discovery_ignores_containment():
    """⚠ The landmine behind the gate: with the owned row carrying NO year, the remake guard cannot
    fire, so a containment match used to swallow the candidate (measured True on 2026-09-13). The
    real "Sholay" (1975) must survive against an owned "Sholay — Special Ops" either way."""
    candidate = {"tmdb_id": 12259, "title": "Sholay", "year": 1975}
    assert not is_duplicate_discovery(dict(candidate), [{"title": "Sholay — Special Ops", "year": 2025}])
    assert not is_duplicate_discovery(dict(candidate), [{"title": "Sholay — Special Ops"}])
    # …while an EXACT owned title is still a duplicate, and the tmdb-id path stays decisive.
    assert is_duplicate_discovery(dict(candidate), [{"title": "Sholay", "year": 1975}])
    assert is_duplicate_discovery(
        {"tmdb_id": 12259, "title": "Something Else Entirely", "year": 1975},
        [{"title": "Sholay — Special Ops", "provider_ids": {"tmdb": 12259}}],
    )


def test_duplicate_discovery_by_tmdb_id_and_title():
    owned = [
        {"title": "3 Body Problem", "year": 2024, "provider_ids": {"tmdb": 108545}},
        {"title": "Prisoners", "year": 2013, "provider_ids": {"tmdb": 146233}},
    ]
    assert is_duplicate_discovery({"tmdb_id": 108545, "title": "3 Body Problem", "year": 2024}, owned)
    assert is_duplicate_discovery({"tmdb_id": 999, "title": "3 Body Problem", "year": 2024}, owned)  # title dup
    assert not is_duplicate_discovery({"tmdb_id": 999, "title": "3 Body Problem", "year": 2025}, owned)  # diff year
    assert not is_duplicate_discovery({"tmdb_id": 603, "title": "The Matrix", "year": 1999}, owned)


def test_next_episode_facts_prefers_resume():
    eps = [
        {"id": "e1", "name": "One", "season": 1, "episode": 1, "played": True, "playback_position": 0, "runtime": 3600},
        {"id": "e2", "name": "Two", "season": 1, "episode": 2, "played": False, "playback_position": 900, "runtime": 3600},
        {"id": "e3", "name": "Three", "season": 1, "episode": 3, "played": False, "playback_position": 0, "runtime": 3600},
    ]
    f = next_episode_facts(eps)
    assert f == {"id": "e2", "name": "Two", "season": 1, "episode": 2, "position": 900,
                 "remaining": 2700, "kind": "continue"}
    # all watched -> None
    assert next_episode_facts([{**e, "played": True} for e in eps]) is None
    # nothing watched -> first unwatched, kind play
    f2 = next_episode_facts([{**e, "played": False, "playback_position": 0} for e in eps])
    assert f2["id"] == "e1" and f2["kind"] == "play"


def test_owned_state_map():
    assert owned_state({"kind": "movie", "played": False, "playback_position": 0}) == "watch"
    assert owned_state({"kind": "movie", "played": False, "playback_position": 120}) == "resume"
    assert owned_state({"kind": "movie", "played": True, "playback_position": 0}) == "watch_again"
    assert owned_state({"kind": "show", "played": False, "playback_position": 0}, next_ep={"id": "x"}) == "next_episode"
    assert owned_state({"kind": "show", "played": True, "playback_position": 0}) == "watch_again"


# --------------------------------------------------------------------------- provider (mocked urlopen)
def _cfg(**over):
    vals = dict(JELLYFIN_URL="http://jellyfin:8096", JELLYFIN_API_KEY="jkey",
                JELLYFIN_BROWSER_URL="http://localhost:8098", MEDIA_SERVER="jellyfin")
    vals.update(over)
    cfg = SimpleNamespace(**vals)
    cfg.has_jellyfin = lambda: bool(cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY)
    return cfg


class _FakeJson:
    def __init__(self, payload):
        self._p = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._p).encode()


def _search_side(items, hints):
    def side_effect(url, *args, **kwargs):
        u = url if isinstance(url, str) else getattr(url, "full_url", "")
        if u.endswith("/Users?api_key=jkey"):
            return _FakeJson([{"Id": "user-1", "Name": "admin"}])
        if "Search/Hints" in u:
            return _FakeJson({"SearchHints": hints})
        return _FakeJson({"Items": items})
    return side_effect


def test_jellyfin_search_items_normalizes_rows():
    from services.library.jellyfin import JellyfinLibraryProvider
    items = [{
        "Id": "itm-s1", "Name": "3 Body Problem", "Type": "Series", "ProductionYear": 2024,
        "Genres": ["Sci-Fi & Fantasy"], "CommunityRating": 7.5, "RunTimeTicks": 0,
        "ProviderIds": {"Tmdb": 108545, "Imdb": "tt13016388"},
        "UserData": {"Played": False, "PlaybackPositionTicks": 0, "PlayCount": 0},
    }, {
        "Id": "ep-1", "Name": "Countdown", "Type": "Episode", "SeriesId": "itm-s1",
        "SeriesName": "3 Body Problem", "ParentIndexNumber": 1, "IndexNumber": 1,
        "RunTimeTicks": 36351680000, "ProviderIds": {},
        "UserData": {"Played": False, "PlaybackPositionTicks": 15583930410, "PlayCount": 2},
    }]
    hints = [{"Id": "p-1", "Name": "D. B. Weiss", "Type": "Person"},
             {"Id": "g-1", "Name": "Sci-Fi & Fantasy", "Type": "Genre"}]
    with patch("urllib.request.urlopen", side_effect=_search_side(items, hints)):
        p = JellyfinLibraryProvider(config=_cfg())
        out = p.search_items("3 body")
    assert len(out["items"]) == 2
    show = out["items"][0]
    assert show["kind"] == "show" and show["title"] == "3 Body Problem"
    assert show["provider_ids"] == {"tmdb": 108545, "imdb": "tt13016388"}
    ep = out["items"][1]
    assert ep["kind"] == "episode" and ep["season"] == 1 and ep["episode"] == 1
    assert ep["series_name"] == "3 Body Problem"
    assert ep["playback_position"] == 1558  # 15583930410 ticks / 1e7
    assert out["people"][0]["name"] == "D. B. Weiss"
    assert out["people"][0]["id"] == "p-1"
    assert out["genres"][0]["name"] == "Sci-Fi & Fantasy"
    assert out["collections"] == []


def test_jellyfin_search_items_empty_and_unconfigured():
    from services.library.jellyfin import JellyfinLibraryProvider
    with patch("urllib.request.urlopen", side_effect=_search_side([], [])):
        p = JellyfinLibraryProvider(config=_cfg())
        assert p.search_items("nope") == {"items": [], "people": [], "genres": [], "collections": []}
    p2 = JellyfinLibraryProvider(config=_cfg(JELLYFIN_URL="", JELLYFIN_API_KEY=""))
    assert p2.search_items("x") == {}


def test_jellyfin_items_by_person():
    from services.library.jellyfin import JellyfinLibraryProvider
    items = [{"Id": "itm-1", "Name": "3 Body Problem", "Type": "Series", "ProductionYear": 2024,
              "Genres": [], "ProviderIds": {"Tmdb": 108545}, "UserData": {}}]
    with patch("urllib.request.urlopen", side_effect=_search_side(items, [])):
        p = JellyfinLibraryProvider(config=_cfg())
        rows = p.items_by_person("p-1", limit=3)
    assert len(rows) == 1 and rows[0]["title"] == "3 Body Problem"


# --------------------------------------------------------------------------- route (direct call, patched deps)
class _FakeService:
    def __init__(self, items=None, people=None, person_rows=None, eps=None):
        self._items = items or []
        self._people = people or []
        self._person_rows = person_rows or []
        self._eps = eps or []

    def search(self, q, limit=12):
        return {"provider": "jellyfin", "items": self._items, "people": self._people,
                "genres": [], "collections": []}

    def episodes(self, series_id, limit=1000):
        return {"provider": "jellyfin", "episodes": self._eps}

    def items_by_person(self, pid, limit=6):
        return {"provider": "jellyfin", "items": self._person_rows}


def _route_env(lib_service, tmdb_rows=(), counter=None):
    from api.routes import search_global as mod
    # ⚠ The route's external-search cache is MODULE-level: without this clear, a test that uses a
    # query a previous test already asked would be answered from that test's rows instead of this
    # stub, and the assertion would be about the wrong fixture.
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
    patchers = [
        patch.object(mod, "get_config", return_value=cfg),
        patch.object(mod, "build_library_service", return_value=lib_service),
        patch.object(mod, "TMDBService", return_value=fake_tmdb),
    ]
    for p in patchers:
        p.start()
    return mod.search_global, patchers


def test_route_exact_match_suppresses_discovery():
    """An EXACT owned title means the library has answered the query — no external section."""
    svc = _FakeService(
        items=[{"id": "s1", "kind": "show", "title": "3 Body Problem", "year": 2024,
                "genres": [], "rating": None, "played": False, "playback_position": 0,
                "runtime": 0, "play_count": 0, "provider_ids": {"tmdb": 108545}}],
        eps=[{"id": "e1", "name": "Countdown", "season": 1, "episode": 1,
              "played": False, "playback_position": 0, "runtime": 3635}],
    )
    fn, patchers = _route_env(svc, tmdb_rows=[{"id": 108545, "media_type": "tv",
                                               "title": "3 Body Problem", "overview": ""}])
    try:
        resp = fn(q="3 Body Problem")
    finally:
        for p in patchers:
            p.stop()
    assert resp.strong_match is True
    assert resp.discovery == []
    assert len(resp.items) == 1
    row = resp.items[0]
    assert row.state == "next_episode"
    assert row.next_episode is not None and row.next_episode.kind == "play"
    assert resp.people == []


def test_route_containment_match_still_returns_discovery():
    """⚠ HIS BUG (2026-09-13), verbatim: searching **"sholay"** while the library holds only
    "Sholay — Special Ops" (a different work) returned that one unrelated row and NO external
    section, because containment scored 2 and the gate was `>= 2`.

    Both halves are asserted: the unrelated owned row is still OFFERED (library first), and the real
    film now appears beside it. Run against the old gate this test fails at `strong_match is False`.
    """
    owned_row = {"id": "ep-shso", "kind": "episode", "title": "Sholay — Special Ops",
                 "year": 2025, "season": 1, "episode": 8, "series_id": "s-shso",
                 "series_name": "Sholay — Special Ops", "genres": [], "rating": None, "played": False,
                 "playback_position": 120, "runtime": 3600, "play_count": 1, "provider_ids": {}}
    tmdb = [
        {"id": 12259, "media_type": "movie", "title": "Sholay", "release_date": "1975-08-15",
         "overview": "Two friends, their village, and a bandit.", "poster_path": "/sholay.jpg"},
        {"id": 586776, "media_type": "movie", "title": "The Sholay Girl", "release_date": "2019-03-01",
         "overview": "", "poster_path": ""},
    ]
    # (a) the owned row carries a year, and (b) it does not — the second is the landmine, because the
    # remake guard cannot fire without two years.
    for label, owned in (("with a year", dict(owned_row)), ("with NO year", {**owned_row, "year": None})):
        fn, patchers = _route_env(_FakeService(items=[owned]), tmdb_rows=tmdb)
        try:
            resp = fn(q="sholay")
        finally:
            for p in patchers:
                p.stop()
        assert resp.strong_match is False, label
        assert [d.title for d in resp.discovery] == ["Sholay", "The Sholay Girl"], label
        assert [i.title for i in resp.items] == ["Sholay — Special Ops"], label
        assert resp.discovery[0].year == 1975 and resp.discovery[0].media_type == "movie", label
        assert resp.discovery[0].poster.endswith("/sholay.jpg"), label


def test_route_never_offers_a_title_it_already_owns():
    """The other direction: a containment QUERY opens the external search, and the exact title among
    the candidates is then deduped away — the section must not offer to acquire what he has."""
    fn, patchers = _route_env(
        _FakeService(items=[{"id": "m1", "kind": "movie", "title": "The Matrix", "year": 1999,
                             "genres": [], "rating": None, "played": True, "playback_position": 0,
                             "runtime": 8160, "play_count": 2, "provider_ids": {"tmdb": 603}}]),
        tmdb_rows=[{"id": 603, "media_type": "movie", "title": "The Matrix",
                    "release_date": "1999-03-31", "overview": "", "poster_path": ""}],
    )
    try:
        resp = fn(q="matrix")   # containment: the library answers, but not EXACTLY
    finally:
        for p in patchers:
            p.stop()
    assert resp.strong_match is False
    assert resp.discovery == []
    assert [i.title for i in resp.items] == ["The Matrix"]


def test_route_caches_the_external_search_per_query():
    """His report asks for a short-lived cache. Only the EXTERNAL half is cached (the local rows carry
    playback state), keyed on the NORMALISED query, so a refinement that normalises to the same key
    does not call the provider twice."""
    seen: list[str] = []
    fn, patchers = _route_env(
        _FakeService(items=[]), counter=seen,
        tmdb_rows=[{"id": 12259, "media_type": "movie", "title": "Sholay",
                    "release_date": "1975-08-15", "overview": "", "poster_path": ""}],
    )
    try:
        first = fn(q="sholay")
        second = fn(q="  Sholay  ")      # same normalised key
        third = fn(q="sholay 2")         # a different query must reach the provider
    finally:
        for p in patchers:
            p.stop()
    assert seen == ["sholay", "sholay 2"], seen
    assert [d.title for d in first.discovery] == ["Sholay"]
    assert [d.title for d in second.discovery] == ["Sholay"]


def test_route_no_owned_match_returns_discovery():
    fn, patchers = _route_env(_FakeService(items=[]), tmdb_rows=[{"id": 603, "media_type": "movie",
                                                                  "title": "The Matrix", "release_date": "1999-03-31",
                                                                  "overview": "A hacker learns.", "poster_path": "/x.jpg"}])
    try:
        resp = fn(q="the matrix")
    finally:
        for p in patchers:
            p.stop()
    assert resp.strong_match is False
    assert len(resp.discovery) == 1
    d = resp.discovery[0]
    assert d.tmdb_id == 603 and d.year == 1999 and d.media_type == "movie"
    assert d.in_watchlist is False


def test_route_person_drilldown_rows():
    svc = _FakeService(
        items=[],
        people=[{"id": "p-1", "name": "D. B. Weiss"}],
        person_rows=[{"id": "s1", "kind": "show", "title": "3 Body Problem", "year": 2024,
                      "genres": [], "rating": None, "played": True, "playback_position": 0,
                      "runtime": 0, "play_count": 1, "provider_ids": {"tmdb": 108545}}],
    )
    fn, patchers = _route_env(svc, tmdb_rows=[])
    try:
        resp = fn(q="weiss")
    finally:
        for p in patchers:
            p.stop()
    assert [p.kind for p in resp.people] == ["person"]
    assert len(resp.person_titles) == 1
    assert resp.person_titles[0].state == "watch_again"
