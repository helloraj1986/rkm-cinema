"""Tests for the live TMDB search path (services/tmdb.py:search_multi) and the
GET /api/search route.

Regression: /api/search used to hand-roll a headerless raw ``urllib`` call to
TMDB which the deployed container's egress rejected (empty ``tmdb`` results
while /api/suggest worked from the same container) and ``except Exception:
pass`` hid the failure. The route now uses the shared TMDBService/HTTPClient
path (RKM User-Agent + Accept, retries) and logs failures instead of silence.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
import api.main

client = TestClient(api.main.app)


def _cfg(**over):
    vals = {"TMDB_API_KEY": "tmdbkey", "RADARR_API_KEY": "rk", "SONARR_API_KEY": "sk"}
    vals.update(over)
    has = bool(vals.get("TMDB_API_KEY"))
    c = SimpleNamespace(**vals)
    c.has_tmdb = lambda: has
    return c


def _wl_svc(entries=None):
    entries = entries or []
    return SimpleNamespace(load=lambda: SimpleNamespace(
        pending=[e for e in entries if e.state != "recommended"],
        recommended=[e for e in entries if e.state == "recommended"],
    ))


def _row(title, media_type, year="2019-01-01", vid=1, poster="/p.jpg", score=7.2, overview="O"):
    return {"id": vid, "title": title, "name": title, "media_type": media_type,
            "release_date": year, "first_air_date": year, "poster_path": poster,
            "vote_average": score, "overview": overview}


class TestSearchMulti:
    def test_returns_movie_and_tv_rows_only(self):
        from services.tmdb import TMDBService
        svc = TMDBService(config=_cfg())
        svc._request = lambda ep, params=None: {"results": [
            _row("Movie A", "movie", vid=1), _row("Show B", "tv", vid=2),
            _row("Person", "person", vid=3), _row("Episode", "episode", vid=4),
        ]}
        rows = svc.search_multi("x")
        assert [r["id"] for r in rows] == [1, 2]

    def test_empty_query_never_calls(self):
        from services.tmdb import TMDBService
        svc = TMDBService(config=_cfg())
        svc._request = lambda ep, params=None: pytest.fail("should not call")
        assert svc.search_multi("   ") == []

    def test_failure_raises(self):
        from services.tmdb import TMDBService
        svc = TMDBService(config=_cfg())
        svc._request = lambda ep, params=None: (_ for _ in ()).throw(RuntimeError("boom"))
        with pytest.raises(RuntimeError):
            svc.search_multi("x")


class TestSearchRoute:
    def test_live_tmdb_group_present(self):
        from api.routes import search as route_mod
        with patch.object(route_mod, "get_config", return_value=_cfg()), \
             patch.object(route_mod, "WatchlistService", return_value=_wl_svc()), \
             patch("services.tmdb.TMDBService.search_multi", return_value=[
                 _row("Mad Max: Fury Road", "movie", vid=76341, score=7.6),
                 _row("Fauda", "tv", vid=69557, score=8.1),
             ]):
            r = client.get("/api/search?q=mad")
        assert r.status_code == 200
        d = r.json()
        assert d["tmdbKey"] is True
        assert len(d["tmdb"]) == 2
        movie = d["tmdb"][0]
        assert movie["title"] == "Mad Max: Fury Road"
        assert movie["type"] == "movie"
        assert movie["year"] == 2019  # release_date prefix
        assert movie["tmdbId"] == 76341
        assert movie["poster"].endswith("/p.jpg")
        assert movie["inWatchlist"] is False

    def test_failure_degrades_to_empty_not_silent(self):
        from api.routes import search as route_mod
        with patch.object(route_mod, "get_config", return_value=_cfg()), \
             patch.object(route_mod, "WatchlistService", return_value=_wl_svc()), \
             patch("services.tmdb.TMDBService.search_multi",
                   side_effect=RuntimeError("edge rejected")):
            r = client.get("/api/search?q=mad")
        assert r.status_code == 200
        d = r.json()
        assert d["tmdbKey"] is True
        assert d["tmdb"] == []

    def test_no_key_skips_tmdb(self):
        from api.routes import search as route_mod
        with patch.object(route_mod, "get_config", return_value=_cfg(TMDB_API_KEY="")), \
             patch.object(route_mod, "WatchlistService", return_value=_wl_svc()), \
             patch("services.tmdb.TMDBService.search_multi") as sm:
            r = client.get("/api/search?q=mad")
        assert r.status_code == 200
        assert r.json()["tmdbKey"] is False
        sm.assert_not_called()
