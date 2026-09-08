"""Tests for the \"Because you watched\" similar-titles wiring
(docs/SIMILAR_TITLES_PLAN.md — backend Phase 1).

Covers:
- ``TMDBService.get_similar``: movie/tv endpoint choice + normalisation,
  caching, tolerant failure (``[]``) and no-fabrication row filtering.
- ``JellyfinLibraryProvider.item_similar``: Tmdb id resolution from the light
  single-item fetch, display mapping (kind movie/show), limit, and the None
  cases (missing item / not a movie-or-series / no TMDB id / TMDB failure).
- ``LibraryService.item_similar`` aggregate collapse.
- ``GET /api/jellyfin/similar?id=`` route 200/404/503 + missing id.

All mocked at the network/config/service boundary — no real LAN, no keys.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
import api.main

client = TestClient(api.main.app)


def _cfg(**over):
    vals = {"JELLYFIN_URL": "http://jellyfin:8096", "JELLYFIN_API_KEY": "sekret",
            "TMDB_API_KEY": "tmdbkey"}
    vals.update(over)
    return SimpleNamespace(**vals)


# ------------------------------------------------------------------ TMDBService


def _tmdb_rows():
    """Raw TMDB /similar response shape (live-verified field set)."""
    return {"results": [
        {"id": 135254, "title": "Movie A", "release_date": "2014-09-19",
         "vote_average": 7.1, "poster_path": "/pa.jpg", "backdrop_path": "/ba.jpg"},
        {"id": 495, "name": "Show B", "first_air_date": "2011-04-17",
         "vote_average": 8.9, "poster_path": "/pb.jpg", "backdrop_path": None},
        # Fabrication guards: rows without an id/title must be dropped.
        {"title": "No Id", "release_date": "2020-01-01", "vote_average": 5.0},
        {"id": 999, "title": "", "vote_average": 5.0},
        {"id": 135254, "title": "Movie A dup", "vote_average": 9.9},  # dedupe
    ]}


def test_tmdb_get_similar_movie_normalises_and_caches():
    from services.tmdb import TMDBService
    svc = TMDBService(config=_cfg())
    calls = []
    svc._request = lambda ep, params=None: (calls.append(ep) or _tmdb_rows())
    rows = svc.get_similar(146233, "movie")
    assert calls == ["movie/146233/similar"]
    assert len(rows) == 2  # the no-id / no-title / dup rows are dropped
    r0 = rows[0]
    assert r0["tmdb_id"] == 135254
    assert r0["title"] == "Movie A"
    assert r0["year"] == 2014
    assert r0["media_type"] == "movie"
    assert r0["score"] == 7.1
    assert r0["poster"].endswith("/w500/pa.jpg")
    assert r0["backdrop"].endswith("/w1280/ba.jpg")
    # Second call is served from the cache (loader not re-run).
    rows2 = svc.get_similar(146233, "movie")
    assert len(calls) == 1
    assert rows2 == rows


def test_tmdb_get_similar_tv_uses_name_and_first_air_date():
    from services.tmdb import TMDBService
    svc = TMDBService(config=_cfg())
    svc._request = lambda ep, params=None: _tmdb_rows()
    rows = svc.get_similar(108545, "tv")
    assert len(rows) == 2
    show = rows[1]
    assert show["title"] == "Show B"
    assert show["year"] == 2011
    assert show["media_type"] == "tv"
    assert show["poster"].endswith("/w500/pb.jpg")
    assert show["backdrop"] == ""  # no backdrop_path -> empty, never a guess


def test_tmdb_get_similar_failure_returns_empty():
    from services.tmdb import TMDBService
    svc = TMDBService(config=_cfg())
    svc._request = lambda ep, params=None: (_ for _ in ()).throw(RuntimeError("boom"))
    assert svc.get_similar(146233, "movie") == []
    assert svc.get_similar(0, "movie") == []  # no id -> [], never a call


# --------------------------------------------------------- Jellyfin provider


class _FakeJson:
    def __init__(self, payload):
        self._p = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._p).encode()


def _provider_urlopen(item_payload, items_url_is_list=True):
    """urlopen -> /Users user list, then the single-item fetch (item_payload)."""
    def side_effect(url, *args, **kwargs):
        u = url if isinstance(url, str) else getattr(url, "full_url", "")
        if "/System/Info/Public" in u:
            return _FakeJson({"Id": "srv-abc"})
        if u.endswith("/Users?api_key=sekret"):
            return _FakeJson([{"Id": "user-1", "Name": "admin"}])
        return _FakeJson(item_payload)
    return side_effect


def _movie_item(**over):
    it = {"Id": "m1", "Name": "Prisoners", "Type": "Movie",
          "ProviderIds": {"Imdb": "tt1392214", "Tmdb": "146233"}}
    it.update(over)
    return it


def _provider(tmdb=None):
    from services.library.jellyfin import JellyfinLibraryProvider
    return JellyfinLibraryProvider(config=_cfg(), tmdb=tmdb)


def _call_similar(prov, item_id, item_payload, limit=10):
    """Run item_similar inside the urlopen patch (item fetch -> item_payload)."""
    with patch("urllib.request.urlopen",
               side_effect=_provider_urlopen(item_payload)):
        return prov.item_similar(item_id, limit=limit)


def test_provider_item_similar_movie_maps_rows():
    fake_tmdb = SimpleNamespace()
    seen = {}
    def fake_get_similar(tmdb_id, media_type):
        seen.update(tmdb_id=tmdb_id, media_type=media_type)
        return [
            {"tmdb_id": 135254, "title": "Movie A", "year": 2014,
             "media_type": "movie", "score": 7.1,
             "poster": "http://img/w500/a.jpg", "backdrop": "http://img/w1280/a.jpg"},
            {"tmdb_id": 495, "title": "Show B", "year": 2011,
             "media_type": "tv", "score": 8.9, "poster": "", "backdrop": ""},
        ]
    fake_tmdb.get_similar = fake_get_similar
    p = _provider(tmdb=fake_tmdb)
    rows = _call_similar(p, "m1", _movie_item())
    assert seen == {"tmdb_id": 146233, "media_type": "movie"}
    assert rows == [
        {"id": 135254, "title": "Movie A", "year": 2014, "kind": "movie",
         "score": 7.1, "poster": "http://img/w500/a.jpg", "backdrop": "http://img/w1280/a.jpg"},
        {"id": 495, "title": "Show B", "year": 2011, "kind": "show",
         "score": 8.9, "poster": "", "backdrop": ""},
    ]
    assert rows[0]["id"] == 135254  # tmdb_id surfaced as `id` per contract


def test_provider_item_similar_series_maps_kind_show_and_limit():
    fake_tmdb = SimpleNamespace(get_similar=lambda tmdb_id, media_type: [
        {"tmdb_id": 1000 + i, "title": f"Show {i}", "year": 2020,
         "media_type": "tv", "score": 8.0, "poster": "", "backdrop": ""}
        for i in range(5)])
    p = _provider(tmdb=fake_tmdb)
    rows = _call_similar(p, "s1", {"Id": "s1", "Name": "3 Body Problem",
                                   "Type": "Series", "ProviderIds": {"Tmdb": "108545"}},
                         limit=3)
    assert len(rows) == 3
    assert all(r["kind"] == "show" for r in rows)
    assert rows[0]["id"] == 1000


def test_provider_item_similar_none_cases():
    empty = SimpleNamespace(get_similar=lambda *a, **k: [])
    # Episode type -> None (not a movie/series).
    p = _provider(tmdb=empty)
    assert _call_similar(p, "e1", {"Id": "e1", "Type": "Episode",
                                   "ProviderIds": {"Tmdb": "108545"}}) is None
    # Movie without a TMDB id -> None (never fabricate).
    p = _provider(tmdb=empty)
    assert _call_similar(p, "m1", _movie_item(ProviderIds={"Imdb": "tt1"})) is None
    # Item fetch failure (non-dict body) -> None.
    p = _provider(tmdb=empty)
    assert _call_similar(p, "missing", None) is None
    # TMDB failure -> None (soft miss).
    boom = SimpleNamespace(get_similar=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    p = _provider(tmdb=boom)
    assert _call_similar(p, "m1", _movie_item()) is None


def test_provider_item_similar_empty_list_is_a_real_answer():
    """TMDB answering zero similar titles is [] (row hidden), NOT a 404."""
    p = _provider(tmdb=SimpleNamespace(get_similar=lambda *a, **k: []))
    assert _call_similar(p, "m1", _movie_item()) == []


# ------------------------------------------------------------------ service


def test_service_item_similar_collapses_first_answer():
    from services.library.service import LibraryService
    none_provider = SimpleNamespace(name="plex", item_similar=lambda iid, limit=10: None)
    empty_provider = SimpleNamespace(name="emby", item_similar=lambda iid, limit=10: [])
    full_provider = SimpleNamespace(name="jellyfin", item_similar=lambda iid, limit=10: [{"id": 1, "title": "T"}])
    svc = LibraryService(providers=[none_provider, full_provider])
    assert svc.item_similar("x") == [{"id": 1, "title": "T"}]
    # A provider answering [] (no similar) is authoritative — stop collapsing.
    svc2 = LibraryService(providers=[none_provider, empty_provider])
    assert svc2.item_similar("x") == []
    svc3 = LibraryService(providers=[none_provider])
    assert svc3.item_similar("x") is None


# ---------------------------------------------------------------------- route


def test_similar_route_returns_payload(monkeypatch):
    import api.routes.jellyfin_similar as rmod
    monkeypatch.setattr(rmod, "get_config", lambda: _cfg())
    rows = [{"id": 135254, "title": "Movie A", "year": 2014, "kind": "movie",
             "score": 7.1, "poster": "", "backdrop": ""}]
    fake_svc = SimpleNamespace(item_similar=lambda iid, limit=10: rows)
    with patch("api.routes.jellyfin_similar.build_library_service", return_value=fake_svc):
        r = client.get("/api/jellyfin/similar?id=m1&limit=5")
    assert r.status_code == 200
    assert r.json()["similar"] == rows


def test_similar_route_404_when_item_unresolvable(monkeypatch):
    import api.routes.jellyfin_similar as rmod
    monkeypatch.setattr(rmod, "get_config", lambda: _cfg())
    fake_svc = SimpleNamespace(item_similar=lambda iid, limit=10: None)
    with patch("api.routes.jellyfin_similar.build_library_service", return_value=fake_svc):
        r = client.get("/api/jellyfin/similar?id=nope")
    assert r.status_code == 404


def test_similar_route_404_when_missing_id(monkeypatch):
    import api.routes.jellyfin_similar as rmod
    monkeypatch.setattr(rmod, "get_config", lambda: _cfg())
    with patch("api.routes.jellyfin_similar.build_library_service"):
        r = client.get("/api/jellyfin/similar")
    assert r.status_code == 404


def test_similar_route_503_when_not_configured(monkeypatch):
    import api.routes.jellyfin_similar as rmod
    monkeypatch.setattr(rmod, "get_config",
                        lambda: _cfg(JELLYFIN_URL="", JELLYFIN_API_KEY=""))
    with patch("api.routes.jellyfin_similar.build_library_service"):
        r = client.get("/api/jellyfin/similar?id=m1")
    assert r.status_code == 503
