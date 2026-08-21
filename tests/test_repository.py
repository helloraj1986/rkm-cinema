"""Tests for Phase 3 — persistent store + repository abstraction."""
import os
import tempfile

import pytest

from config.settings import get_config
from infrastructure.database.db import Database
from infrastructure.database.repository import (
    JsonWatchlistRepository,
    SqliteWatchlistRepository,
    build_repository,
)
from services.watchlist import WatchlistEntry, WatchlistService


def _entry(**over):
    base = {
        "title": "The Matrix", "year": 1999, "category": "Sci-Fi/Fantasy",
        "lang": "English", "rt": 87, "imdb": 8.7, "isSeries": False,
        "imdbId": "tt0133093", "tmdbId": 603, "cert": "R", "snippet": "s",
        "cast": ["Keanu Reeves"], "director": "Wachowskis", "poster": "",
        "trailerId": "abc", "trailerTitle": "t", "added": "2026-08-01",
    }
    base.update(over)
    return WatchlistEntry.from_dict(base)


# ------------------------------------------------------------------- JSON repo
def test_json_repository_roundtrip(tmp_path):
    p = str(tmp_path / "watchlist.json")
    repo = JsonWatchlistRepository(p)
    raw = {"rotation_index": 1, "pending": [{"title": "A", "year": 2000}], "recommended": []}
    repo.save(raw)
    loaded = repo.load()
    assert loaded["pending"][0]["title"] == "A"
    assert loaded["rotation_index"] == 1


def test_watchlist_service_json_backed(tmp_path):
    p = str(tmp_path / "watchlist.json")
    svc = WatchlistService(p)
    svc.add_pending(_entry())
    svc.add_pending(_entry(title="A Clockwork Orange", year=1971, imdbId="tt0066921", tmdbId=185))
    assert svc.find_by_imdb("tt0133093") is not None
    assert svc.remove_pending("tt0133093") is True
    assert svc.find_by_imdb("tt0133093") is None
    assert svc.find_by_imdb("tt0066921") is not None


# ---------------------------------------------------------------- SQLite repo
def test_sqlite_repository_roundtrip():
    db = Database(":memory:")
    repo = SqliteWatchlistRepository(db)
    entry = _entry()
    raw = {
        "rotation_index": 2,
        "rotation": ["Drama", "Action"],
        "pending": [entry.to_dict()],
        "recommended": [],
        "updated": "",
        "hero_mode": "auto",
    }
    repo.save(raw)
    loaded = repo.load()
    assert loaded["rotation_index"] == 2
    assert len(loaded["pending"]) == 1
    assert loaded["pending"][0]["imdbId"] == "tt0133093"
    assert loaded["pending"][0]["tmdbId"] == 603

    # Idempotent re-save -> no duplicates.
    repo.save(raw)
    twice = repo.load()
    assert len(twice["pending"]) == 1


def test_sqlite_repository_media_table():
    db = Database(":memory:")
    repo = SqliteWatchlistRepository(db)
    repo.save({"pending": [_entry().to_dict()], "recommended": [], "rotation": None})
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM media WHERE imdb_id=?", ("tt0133093",)).fetchone()
        assert row is not None
        assert row["media_type"] == "movie"
        assert row["tmdb_id"] == 603


def test_sqlite_repository_job_runs_table_exists():
    db = Database(":memory:")
    db.init()
    with db.connection() as conn:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(job_runs)")]
        assert "job_name" in cols and "started_at" in cols and "status" in cols


# ------------------------------------------------------- config-driven factory
def test_build_repository_defaults_to_json():
    # No WATCHLIST_STORE set in env -> json (backward compatible).
    os.environ.pop("WATCHLIST_STORE", None)
    get_config.cache_clear()
    assert isinstance(build_repository(), JsonWatchlistRepository)


def test_build_repository_sqlite(tmp_path, monkeypatch):
    dbp = str(tmp_path / "wl.db")
    monkeypatch.setenv("WATCHLIST_STORE", "sqlite")
    monkeypatch.setenv("WATCHLIST_DB_PATH", dbp)
    get_config.cache_clear()
    try:
        repo = build_repository()
        assert isinstance(repo, SqliteWatchlistRepository)
        # A WatchlistService configured to sqlite persists durably.
        svc = WatchlistService()
        svc.add_pending(_entry())
        assert svc.find_by_imdb("tt0133093") is not None
    finally:
        os.environ.pop("WATCHLIST_STORE", None)
        os.environ.pop("WATCHLIST_DB_PATH", None)
        get_config.cache_clear()