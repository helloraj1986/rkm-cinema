"""Tests for GET /api/watchlist/entries (legacy-parity rich-entry source).

The route is thin: it reads the authoritative store through WatchlistService
(the same seam the dashboard generator uses) and maps each entry with the
shared ``services.dashboard.to_rich_entry`` mapper. Mocks at the service
boundary — no real DB, no API keys.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
import api.main

from services.watchlist import WatchlistEntry


@pytest.fixture
def client():
    return TestClient(api.main.app)


def _entry(**over):
    base = dict(
        title="The Matrix", year=1999, category="Sci-Fi/Fantasy", lang="English",
        rt=88, imdb=8.7, isSeries=False, imdbId="tt0133093", tmdbId=603,
        cert="AU-M", snippet="A computer hacker learns the truth.",
        cast=["Keanu Reeves"], director="The Wachowskis", poster="https://p/m.jpg",
        trailerId="vKQi3bBA1y8", trailerTitle="The Matrix Trailer", added="2026-01-01",
        genres=["Science Fiction", "Action"], tmdb_overview="Neo discovers the Matrix.",
        backdrop="https://p/m-b.jpg", tmdb_score=8.1, runtime=136,
        source="auto", state="pending", detail="", progress=0,
    )
    base.update(over)
    return WatchlistEntry.from_dict(base)


# The patch decorator form reads cleaner than the context above.
def _loaded(entries, updated="2026-09-07T00:00:00"):
    svc = SimpleNamespace(load=lambda: SimpleNamespace(
        pending=[e for e in entries if e.state != "recommended"],
        recommended=[e for e in entries if e.state == "recommended"],
        updated=updated,
    ))
    return patch("api.routes.watchlist.WatchlistService", return_value=svc)


def test_entries_returns_rich_shape_matching_dashboard_mapper(client):
    """The route emits the same rich fields rebuild_dashboard writes (genres,
    scores, poster/backdrop, overview, trailer, status) — one mapper shared."""
    movie = _entry()
    show = _entry(
        title="Severance", year=2022, isSeries=True, tmdbId=95396,
        imdbId="tt11280740", category="Thriller", genres=[],
        imdb=0.0, tmdb_score=0.0, rt=0, snippet="Mark leads a team…",
        tmdb_overview="", backdrop="https://p/s-b.jpg",
        state="recommended",
    )
    with _loaded([movie, show], updated="2026-09-07T01:02:03"):
        r = client.get("/api/watchlist/entries")
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == "2026-09-07T01:02:03"
    assert len(body["entries"]) == 2

    m = body["entries"][0]
    assert m["title"] == "The Matrix"
    assert m["type"] == "movie"
    assert m["imdbId"] == "tt0133093"
    assert m["tmdbId"] == 603
    assert m["tmdbScore"] == 8.1          # explicit tmdb score wins
    assert m["genres"] == ["Science Fiction", "Action"]
    assert m["overview"] == "Neo discovers the Matrix."   # tmdb_overview preferred
    assert m["poster"] == "https://p/m.jpg"
    assert m["backdrop"] == "https://p/m-b.jpg"
    assert m["trailerId"] == "vKQi3bBA1y8"
    assert m["trailerUrl"].startswith("https://www.youtube.com/embed/")
    assert m["state"] == "pending"

    s = body["entries"][1]
    assert s["type"] == "tv"
    # Empty genres fall back to the category hint; zero tmdb score falls back
    # to IMDb; missing tmdb_overview falls back to snippet — the same rules the
    # static dashboard applies (parity between live + generated sources).
    assert s["genres"] == ["Thriller"]
    assert s["tmdbScore"] == 0.0
    assert s["overview"] == "Mark leads a team…"


def test_entries_empty_repo_returns_empty_list(client):
    with _loaded([]):
        r = client.get("/api/watchlist/entries")
    assert r.status_code == 200
    body = r.json()
    assert body["entries"] == []


def test_entries_invalid_trailer_id_is_scrubbed(client):
    """A malformed trailer id must not leak into the UI (mirrors the dashboard
    generator's validation): the Search-YouTube fallback URL is used instead."""
    bad = _entry(trailerId="not-a-real-trailer-id!!!")
    with _loaded([bad]):
        r = client.get("/api/watchlist/entries")
    body = r.json()
    assert body["entries"][0]["trailerId"] == ""
    assert "youtube.com/results?search_query=" in body["entries"][0]["trailerUrl"]
