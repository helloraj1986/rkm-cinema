"""SQLite persistent store (Phase 3).

The spec (§5) mandates that JSON is no longer the authoritative database. This
module owns the SQLite connection and schema so the rest of the application
talks to a repository, never to a file directly.

Uses the Python stdlib ``sqlite3`` — no third-party ORM dependency, which keeps
the container image small and the deploy unchanged.

Schema (spec §5): media, watchlist, recommendations, library_items,
acquisitions, watch_links, job_runs. The ``watchlist`` and ``recommendations``
rows also carry a ``payload`` JSON column so the rich dashboard fields
(rt/imdb/cast/poster/trailerId/...) round-trip without a hundred columns.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from config.settings import get_config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id          TEXT PRIMARY KEY,          -- canonical media_id e.g. movie:tmdb:603
    media_type  TEXT NOT NULL,
    title       TEXT NOT NULL,
    year        INTEGER,
    tmdb_id     INTEGER,
    imdb_id     TEXT,
    tvdb_id     INTEGER,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    media_id      TEXT PRIMARY KEY REFERENCES media(id),
    active        INTEGER NOT NULL DEFAULT 1,
    reason        TEXT,
    criteria_score REAL,
    priority      INTEGER DEFAULT 0,
    added_at      TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    state         TEXT NOT NULL DEFAULT 'pending',
    payload       TEXT NOT NULL DEFAULT '{}'   -- rich dashboard fields (JSON)
);

CREATE TABLE IF NOT EXISTS recommendations (
    media_id    TEXT NOT NULL REFERENCES media(id),
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    decision    TEXT NOT NULL DEFAULT 'pending',
    score       REAL,
    payload     TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (media_id)
);

CREATE TABLE IF NOT EXISTS library_items (
    media_id         TEXT NOT NULL REFERENCES media(id),
    provider         TEXT NOT NULL,           -- 'plex' | 'emby'
    provider_item_id TEXT NOT NULL,
    title            TEXT,
    year             INTEGER,
    matched_at       TEXT NOT NULL,
    last_seen        TEXT NOT NULL,
    PRIMARY KEY (media_id, provider, provider_item_id)
);

CREATE TABLE IF NOT EXISTS acquisitions (
    media_id         TEXT NOT NULL REFERENCES media(id),
    provider         TEXT NOT NULL,           -- 'radarr' | 'sonarr'
    provider_item_id TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'requested',
    requested_at     TEXT,
    updated_at       TEXT,
    PRIMARY KEY (media_id, provider, provider_item_id)
);

CREATE TABLE IF NOT EXISTS watch_links (
    media_id         TEXT NOT NULL REFERENCES media(id),
    provider         TEXT NOT NULL,           -- 'plex' | 'emby'
    provider_item_id TEXT,
    url              TEXT,
    status           TEXT NOT NULL DEFAULT 'unknown',
    last_validated   TEXT,
    PRIMARY KEY (media_id, provider)
);

CREATE TABLE IF NOT EXISTS job_runs (
    job_name       TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    completed_at   TEXT,
    status         TEXT NOT NULL DEFAULT 'running',
    items_processed INTEGER DEFAULT 0,
    error          TEXT
);
"""


class Database:
    """Thread-safe SQLite connection holder with lazy in-memory support for tests."""

    def __init__(self, path: Optional[str] = None):
        cfg = get_config()
        if path is None:
            path = cfg.WATCHLIST_DB_PATH or self._default_path()
        self.path = str(path)
        self._local = threading.local()

    @staticmethod
    def _default_path() -> str:
        """A persistent file location in the container or dev sandbox."""
        if Path("/app").is_dir():
            return "/app/watchlist.db"
        return "/workspace/projects/rkm-cinema.db"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL") if self.path != ":memory:" else None
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def init(self) -> None:
        """Create schema if absent. Idempotent."""
        with self.connection() as conn:
            conn.executescript(_SCHEMA)

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


def get_database() -> Database:
    """Process-wide singleton database (lazy)."""
    from functools import lru_cache

    @lru_cache(maxsize=1)
    def _build() -> Database:
        db = Database()
        db.init()
        return db

    return _build()