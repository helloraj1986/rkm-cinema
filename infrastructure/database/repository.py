"""Repository abstraction for RKM Watchlist (Phase 3).

The spec (§5) requires that the rest of the application never touches
``watchlist.json`` directly. All persistence flows through a ``WatchlistRepository``
that operates on a plain serializable structure (the watchlist.json shape):
``{rotation_index, rotation, pending[], recommended[], updated, hero_mode}``.

- ``JsonWatchlistRepository``  — the existing atomic JSON file (kept as the safe
  default and backward-compatible path during migration).
- ``SqliteWatchlistRepository`` — the Phase 3 persistent store.

One active implementation is chosen by ``WATCHLIST_STORE`` (config), so there is
exactly one repository the rest of the app sees.
"""
from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rkm.repository")


class WatchlistRepository(ABC):
    """Persistence seam. Subclasses must be thread-safe and idempotent."""

    @abstractmethod
    def load(self) -> dict:
        """Return the full serializable watchlist structure (or {} if empty)."""

    @abstractmethod
    def save(self, raw: dict) -> None:
        """Persist the structure atomically/durably."""

    def list_job_runs(self, limit: int = 20) -> list[dict]:
        """Recent job_runs most-recent-first (spec Phase 13/14). Default: none."""
        return []

    def record_job_run(self, *, job_name: str, completed_at: str,
                       status: str, items_processed: int = 0,
                       error: str = "") -> None:
        """Persist a completed job run. Default: no-op."""
        return None

    def list_recommendation_history(self, limit: int = 200) -> list[dict]:
        """Recently-seen recommendation history (spec §23) most-recent-first."""
        return []

    def record_recommendation(self, *, media_id: str, decision: str,
                              score: float = 0.0, payload: dict = None) -> None:
        """Record that a candidate was considered/persisted (spec §23). Default: no-op."""
        return None


# --------------------------------------------------------------------------- JSON
class JsonWatchlistRepository(WatchlistRepository):
    """Original watchlist.json backing (atomic tmp + os.replace + mtime cache)."""

    def __init__(self, path: Optional[str] = None):
        if path is None:
            if Path("/app/watchlist.json").exists():
                path = "/app/watchlist.json"
            else:
                path = "/workspace/media/watchlist.json"
        self.path = Path(path)
        self._cache: Optional[dict] = None
        self._cache_mtime: float = 0

    def load(self) -> dict:
        try:
            if not self.path.exists():
                logger.warning("Watchlist file not found, returning empty")
                return {}
            mtime = self.path.stat().st_mtime
            if self._cache is not None and mtime <= self._cache_mtime:
                return self._cache
            with open(self.path) as f:
                raw = json.load(f)
            self._cache = raw
            self._cache_mtime = mtime
            return raw
        except json.JSONDecodeError as e:
            from core.exceptions import WatchlistError
            logger.error("Watchlist JSON corrupted: %s", e)
            raise WatchlistError(f"Corrupted watchlist.json: {e}")
        except Exception as e:  # noqa: BLE001
            from core.exceptions import WatchlistError
            logger.error("Failed to load watchlist: %s", e)
            raise WatchlistError(f"Load failed: {e}")

    def save(self, raw: dict) -> None:
        tmp_path = self.path.with_suffix(".json.tmp")
        try:
            with open(tmp_path, "w") as f:
                json.dump(raw, f, indent=2)
            os.replace(tmp_path, self.path)
            self._cache = raw
            self._cache_mtime = self.path.stat().st_mtime
        except Exception as e:  # noqa: BLE001
            if tmp_path.exists():
                tmp_path.unlink()
            from core.exceptions import WatchlistError
            logger.error("Failed to save watchlist: %s", e)
            raise WatchlistError(f"Save failed: {e}")

    # ------------------------------------------------- recommendation history
    # The recommendation pipeline records EVERY candidate it evaluates (spec §23
    # "failures/decisions are visible"), so a candidate is only ever processed
    # once. Kept in a sidecar file rather than watchlist.json so the persistent
    # watchlist shape (`WatchlistService.save`) never drops it.
    _HISTORY_CAP = 3000

    def _history_path(self):
        return self.path.with_name("recommendations_history.json")

    def list_recommendation_history(self, limit: int = 200) -> list[dict]:
        path = self._history_path()
        try:
            if not path.exists():
                return []
            with open(path) as f:
                rows = json.load(f)
            rows.sort(key=lambda r: str(r.get("last_seen", "")), reverse=True)
            return rows[: max(1, int(limit))]
        except Exception as e:  # noqa: BLE001
            logger.warning("recommendation history read failed: %s", e)
            return []

    def record_recommendation(self, *, media_id: str, decision: str,
                              score: float = 0.0, payload: dict = None) -> None:
        path = self._history_path()
        rows: list[dict] = []
        try:
            if path.exists():
                with open(path) as f:
                    rows = json.load(f)
        except Exception:  # noqa: BLE001
            rows = []
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        existing = next((r for r in rows if r.get("media_id") == media_id), None)
        if existing is None:  # idempotent per media_id
            existing = {"media_id": media_id, "first_seen": now}
            rows.append(existing)
        existing["decision"] = decision or ""
        existing["score"] = float(score or 0)
        existing["payload"] = payload or {}
        existing["last_seen"] = now
        if len(rows) > self._HISTORY_CAP:
            rows.sort(key=lambda r: str(r.get("last_seen", "")), reverse=True)
            rows = rows[: self._HISTORY_CAP]
        tmp = path.with_suffix(".json.tmp")
        try:
            with open(tmp, "w") as f:
                json.dump(rows, f, indent=1)
            os.replace(tmp, path)
        except Exception as e:  # noqa: BLE001
            logger.warning("recommendation history write failed: %s", e)


# --------------------------------------------------------------------------- SQLite
class SqliteWatchlistRepository(WatchlistRepository):
    """SQLite backing. One row per entry keyed by canonical media_id; rich
    dashboard fields kept in a JSON ``payload`` column. Pending entries are
    ``active=1``, recommended history is ``active=0``; rotation/meta live in a
    reserved ``__meta__`` row."""

    META_ID = "__meta__"

    def __init__(self, db=None):
        from infrastructure.database.db import get_database
        self.db = db if db is not None else get_database()

    def load(self) -> dict:
        self.db.init()
        raw = {
            "rotation_index": 0,
            "rotation": None,
            "pending": [],
            "recommended": [],
            "updated": "",
            "hero_mode": "auto",
        }
        with self.db.connection() as conn:
            meta = conn.execute(
                "SELECT payload FROM watchlist WHERE media_id=?", (self.META_ID,)
            ).fetchone()
            if meta and meta["payload"]:
                try:
                    m = json.loads(meta["payload"])
                    raw["rotation_index"] = m.get("rotation_index", 0)
                    raw["rotation"] = m.get("rotation")
                    raw["updated"] = m.get("updated", "")
                    raw["hero_mode"] = m.get("hero_mode", "auto")
                except Exception:  # noqa: BLE001
                    pass

            rows = conn.execute(
                "SELECT payload, active FROM watchlist WHERE media_id != ? ORDER BY updated_at",
                (self.META_ID,),
            ).fetchall()
            for r in rows:
                try:
                    entry = json.loads(r["payload"])
                except Exception:  # noqa: BLE001
                    continue
                (raw["pending"] if r["active"] else raw["recommended"]).append(entry)

        if raw["rotation"] is None:
            raw["rotation"] = self._default_rotation()
        return raw

    def save(self, raw: dict) -> None:
        self.db.init()
        with self.db.connection() as conn:
            # Meta row.
            conn.execute(
                "INSERT OR REPLACE INTO media (id, media_type, title, year, created_at, updated_at) "
                "VALUES (?, 'meta', ?, NULL, datetime('now'), datetime('now'))",
                (self.META_ID, "meta"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO watchlist "
                "(media_id, active, reason, criteria_score, priority, added_at, updated_at, state, payload) "
                "VALUES (?, 0, NULL, NULL, 0, datetime('now'), datetime('now'), 'meta', ?)",
                (
                    self.META_ID,
                    json.dumps(
                        {
                            "rotation_index": raw.get("rotation_index", 0),
                            "rotation": raw.get("rotation"),
                            "updated": raw.get("updated", ""),
                            "hero_mode": raw.get("hero_mode", "auto"),
                        }
                    ),
                ),
            )

            # Clear previous entries then upsert current state (idempotent, no dupes).
            conn.execute("DELETE FROM watchlist WHERE media_id != ?", (self.META_ID,))
            for active, entries in ((1, raw.get("pending", [])), (0, raw.get("recommended", []))):
                for e in entries:
                    media_id = self._media_id_for(e)
                    conn.execute(
                        "INSERT OR REPLACE INTO media "
                        "(id, media_type, title, year, tmdb_id, imdb_id, tvdb_id, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                        (
                            media_id,
                            self._serial_type(e),
                            e.get("title", ""),
                            e.get("year"),
                            e.get("tmdbId"),
                            e.get("imdbId"),
                            e.get("tvdbId"),
                        ),
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO watchlist "
                        "(media_id, active, reason, criteria_score, priority, added_at, updated_at, state, payload) "
                        "VALUES (?, ?, ?, NULL, 0, ?, datetime('now'), ?, ?)",
                        (
                            media_id,
                            active,
                            e.get("reason"),
                            e.get("added", ""),
                            e.get("state", "pending"),
                            json.dumps(e),
                        ),
                    )

    # --------------------------------------------------------------- job runs
    def list_job_runs(self, limit: int = 20) -> list[dict]:
        """Recent job_runs most-recent-first (spec Phase 13/14)."""
        self.db.init()
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT job_name, started_at, completed_at, status, "
                "items_processed, error FROM job_runs "
                "ORDER BY started_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_job_run(self, *, job_name: str, completed_at: str,
                       status: str, items_processed: int = 0,
                       error: str = "") -> None:
        """Persist a completed job run (started_at = now)."""
        self.db.init()
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO job_runs (job_name, started_at, completed_at, status, "
                "items_processed, error) VALUES (?, datetime('now'), ?, ?, ?, ?)",
                (job_name, completed_at, status, int(items_processed), error),
            )

    # ------------------------------------------------- recommendation history
    def list_recommendation_history(self, limit: int = 200) -> list[dict]:
        """Recently-seen recommendation history (spec §23) most-recent-first."""
        self.db.init()
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT media_id, first_seen, last_seen, decision, score, payload "
                "FROM recommendations ORDER BY last_seen DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_recommendation(self, *, media_id: str, decision: str,
                              score: float = 0.0, payload: dict = None) -> None:
        """Record that a candidate was considered (spec §23). Idempotent on
        media_id: re-seeing a candidate updates last_seen/decision/score."""
        self.db.init()
        import json as _json
        with self.db.connection() as conn:
            # Ensure the media row exists so the FK reference is satisfied.
            conn.execute(
                "INSERT OR IGNORE INTO media (id, media_type, title, created_at, updated_at) "
                "VALUES (?, 'movie', '', datetime('now'), datetime('now'))",
                (media_id,),
            )
            conn.execute(
                "INSERT INTO recommendations (media_id, first_seen, last_seen, decision, score, payload) "
                "VALUES (?, datetime('now'), datetime('now'), ?, ?, ?) "
                "ON CONFLICT(media_id) DO UPDATE SET "
                "last_seen=datetime('now'), decision=excluded.decision, score=excluded.score, "
                "payload=excluded.payload",
                (media_id, decision, float(score), _json.dumps(payload or {})),
            )

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _default_rotation() -> list:
        return [
            "Thriller", "Drama", "Kids & Animation", "Sci-Fi/Fantasy", "Comedy",
            "Action", "Horror", "Crime", "Documentary", "Hindi/Indian Cinema",
            "Romance", "Classic/Essential",
        ]

    @staticmethod
    def _serial_type(entry: dict) -> str:
        return "tv" if entry.get("isSeries") else "movie"

    @staticmethod
    def _media_id_for(entry: dict) -> str:
        """Canonical media_id for an entry, preferring tmdb then imdb."""
        imdb = (entry.get("imdbId") or "").strip()
        tmdb = entry.get("tmdbId")
        serial = "tv" if entry.get("isSeries") else "movie"
        if tmdb:
            return f"{serial}:tmdb:{int(tmdb)}"
        if imdb:
            if not imdb.lower().startswith("tt"):
                imdb = "tt" + imdb
            return f"{serial}:imdb:{imdb}"
        tvdb = entry.get("tvdbId")
        if tvdb:
            return f"{serial}:tvdb:{int(tvdb)}"
        # Last resort: title-based key (never used as primary identity, only so an
        # entry with no provider id can still be persisted).
        return f"{serial}:title:{imdb or (entry.get('title') or 'unknown').strip()[:64]}"


def build_repository(store: Optional[str] = None) -> WatchlistRepository:
    """Factory: return the single active repository per config WATCHLIST_STORE."""
    from config.settings import get_config
    cfg = get_config()
    store = store or cfg.WATCHLIST_STORE
    if store == "sqlite":
        logger.info("Using SQLite watchlist repository")
        return SqliteWatchlistRepository()
    logger.info("Using JSON watchlist repository (WATCHLIST_STORE=json)")
    return JsonWatchlistRepository()