"""Watchlist service - CRUD operations, state machine, atomic persistence."""
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List
from dataclasses import dataclass, asdict, field

from core.exceptions import WatchlistError, DuplicateError, StateTransitionError


logger = logging.getLogger("rkm.watchlist")


# Valid states in the lifecycle
VALID_STATES = {
    "pending",      # User-approved, awaiting download
    "requested",    # Added to Radarr/Sonarr, searching
    "downloading",  # Active in qBittorrent
    "downloaded",   # File complete in Radarr/Sonarr (hasFile)
    "available",    # Confirmed in Plex (ground truth)
    "failed",       # Radarr/Sonarr rejected/unreachable
    "recommended",  # Completed lifecycle, history
}

# Valid transitions
VALID_TRANSITIONS = {
    "pending": {"requested", "failed", "recommended"},
    "requested": {"downloading", "downloaded", "failed", "available"},
    "downloading": {"downloaded", "failed", "available"},
    "downloaded": {"available", "failed"},
    "available": {"recommended"},
    "failed": {"pending", "requested"},
    "recommended": set(),  # Terminal state
}

# Required fields for a watchlist entry
REQUIRED_FIELDS = [
    "title", "year", "category", "lang", "rt", "imdb",
    "isSeries", "imdbId", "tmdbId", "cert", "snippet",
    "cast", "director", "poster", "trailerId", "trailerTitle", "added"
]


@dataclass
class WatchlistEntry:
    """Watchlist entry with all required fields."""
    title: str
    year: int
    category: str
    lang: str
    rt: int
    imdb: float
    isSeries: bool
    imdbId: str
    tmdbId: int
    cert: str
    snippet: str
    cast: list
    director: str
    poster: str
    trailerId: str
    trailerTitle: str
    added: str
    tmdb_overview: str = ""
    backdrop: str = ""
    tmdb_score: float = 0.0
    runtime: int = 0
    genres: List[str] = field(default_factory=list)
    source: str = "user"
    state: str = "pending"
    completed: Optional[str] = None
    detail: str = ""
    progress: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "WatchlistEntry":
        # Ensure all required fields present with defaults
        for field in REQUIRED_FIELDS:
            if field not in data:
                if field in ("cast",):
                    data[field] = []
                elif field in ("rt", "imdb"):
                    data[field] = 0
                elif field in ("isSeries",):
                    data[field] = False
                elif field in ("tmdbId",):
                    data[field] = 0
                else:
                    data[field] = ""
        # Set defaults for new fields if not present
        if "tmdb_overview" not in data:
            data["tmdb_overview"] = ""
        if "backdrop" not in data:
            data["backdrop"] = ""
        if "tmdb_score" not in data:
            data["tmdb_score"] = 0.0
        if "runtime" not in data:
            data["runtime"] = 0
        if "genres" not in data:
            data["genres"] = []
        if "source" not in data:
            data["source"] = "user"
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class WatchlistData:
    """Complete watchlist data structure."""
    rotation_index: int = 0
    rotation: list = None
    pending: list = None
    recommended: list = None
    updated: str = ""
    hero_mode: str = "auto"

    def __post_init__(self):
        if self.rotation is None:
            self.rotation = [
                "Thriller", "Drama", "Kids & Animation", "Sci-Fi/Fantasy",
                "Comedy", "Action", "Horror", "Crime", "Documentary",
                "Hindi/Indian Cinema", "Romance", "Classic/Essential"
            ]
        if self.pending is None:
            self.pending = []
        if self.recommended is None:
            self.recommended = []
        if not self.updated:
            self.updated = datetime.now().isoformat()


class WatchlistService:
    """Watchlist persistence with atomic writes and state management."""

    def __init__(self, path: str | None = None, repository=None):
        # Backward-compatible: an explicit ``path`` selects the JSON repository.
        # Otherwise build the single active repository from config (WATCHLIST_STORE).
        # All persistence goes through the repository so no business code touches
        # watchlist.json directly (Phase 3).
        if path is not None:
            from infrastructure.database.repository import JsonWatchlistRepository
            self._repo = JsonWatchlistRepository(path)
        elif repository is not None:
            self._repo = repository
        else:
            from infrastructure.database.repository import build_repository
            self._repo = build_repository()
        # Keep a ``path`` attribute for callers that still inspect it.
        self.path = getattr(self._repo, "path", None)

    def load(self) -> WatchlistData:
        """Load watchlist through the active repository."""
        raw = self._repo.load()
        if not raw:
            logger.warning("Watchlist empty, returning fresh data")
            return WatchlistData()

        # Convert raw dicts to WatchlistEntry objects
        try:
            pending = [WatchlistEntry.from_dict(e) for e in raw.get("pending", [])]
            recommended = [WatchlistEntry.from_dict(e) for e in raw.get("recommended", [])]
        except Exception as e:  # noqa: BLE001
            from core.exceptions import WatchlistError
            logger.error("Failed to parse watchlist: %s", e)
            raise WatchlistError(f"Parse failed: {e}")

        return WatchlistData(
            rotation_index=raw.get("rotation_index", 0),
            rotation=raw.get("rotation", WatchlistData().rotation),
            pending=pending,
            recommended=recommended,
            updated=raw.get("updated", ""),
            hero_mode=raw.get("hero_mode", "auto"),
        )

    def save(self, data: WatchlistData) -> None:
        """Persist through the active repository (atomic, dedup, idempotent)."""
        # Validate before saving
        self._validate(data)

        # Update timestamp
        data.updated = datetime.now().isoformat()

        # Convert entries to dicts
        raw = {
            "rotation_index": data.rotation_index,
            "rotation": data.rotation,
            "pending": [e.to_dict() for e in data.pending],
            "recommended": [e.to_dict() for e in data.recommended],
            "updated": data.updated,
            "hero_mode": data.hero_mode,
        }

        self._repo.save(raw)
        logger.info("Watchlist saved: %d pending, %d recommended", len(data.pending), len(data.recommended))

    def _validate(self, data: WatchlistData) -> None:
        """Validate watchlist data before publishing."""
        if not data.pending and not data.recommended:
            raise WatchlistError("Refusing to save: no entries in pending or recommended")

        # Check for duplicate imdbIds in pending
        pending_ids = [e.imdbId for e in data.pending if e.imdbId]
        if len(pending_ids) != len(set(pending_ids)):
            raise WatchlistError("Duplicate imdbIds in pending")

        # Check for duplicate imdbIds in recommended
        rec_ids = [e.imdbId for e in data.recommended if e.imdbId]
        if len(rec_ids) != len(set(rec_ids)):
            raise WatchlistError("Duplicate imdbIds in recommended")

        # Validate states
        for entry in data.pending + data.recommended:
            if entry.state not in VALID_STATES:
                raise WatchlistError(f"Invalid state: {entry.state}")

    # --- CRUD Operations ---

    def get_pending(self) -> list[WatchlistEntry]:
        return self.load().pending

    def get_recommended(self) -> list[WatchlistEntry]:
        return self.load().recommended

    def get_all(self) -> list[WatchlistEntry]:
        data = self.load()
        return data.pending + data.recommended

    def find_by_imdb(self, imdb_id: str) -> Optional[WatchlistEntry]:
        """Find entry by IMDb ID in pending or recommended."""
        data = self.load()
        for entry in data.pending + data.recommended:
            if entry.imdbId == imdb_id:
                return entry
        return None

    def find_by_tmdb(self, tmdb_id: int) -> Optional[WatchlistEntry]:
        """Find entry by TMDB ID in pending or recommended (canonical id)."""
        if not tmdb_id:
            return None
        data = self.load()
        for entry in data.pending + data.recommended:
            if int(entry.tmdbId or 0) == int(tmdb_id):
                return entry
        return None

    def add_pending(self, entry: WatchlistEntry) -> None:
        """Add new entry to pending (validates no duplicate by canonical id)."""
        data = self.load()
        if entry.imdbId and self.find_by_imdb(entry.imdbId):
            raise DuplicateError("Watchlist entry", entry.imdbId)
        if entry.tmdbId and self.find_by_tmdb(entry.tmdbId):
            raise DuplicateError("Watchlist entry", str(entry.tmdbId))

        # Ensure state is pending
        entry.state = "pending"
        data.pending.append(entry)
        self.save(data)

    def remove_pending(self, imdb_id: str) -> bool:
        """Remove entry from pending."""
        data = self.load()
        original_len = len(data.pending)
        data.pending = [e for e in data.pending if e.imdbId != imdb_id]
        if len(data.pending) < original_len:
            self.save(data)
            return True
        return False

    def move_to_recommended(self, imdb_id: str, completed_date: Optional[str] = None) -> bool:
        """Move entry from pending to recommended (auto-complete)."""
        data = self.load()
        for i, entry in enumerate(data.pending):
            if entry.imdbId == imdb_id:
                entry.state = "recommended"
                entry.completed = completed_date or datetime.now().date().isoformat()
                data.recommended.append(entry)
                data.pending.pop(i)
                self.save(data)
                logger.info("Auto-completed %s -> recommended", imdb_id)
                return True
        return False

    def update_status(self, imdb_id: str, state: str, detail: str = "", progress: int = 0) -> bool:
        """Update entry status with validation.

        Transitioning an entry to ``recommended`` also moves it from pending
        into the recommended (completed-history) list — the lifecycle terminal.
        """
        if state not in VALID_STATES:
            raise WatchlistError(f"Invalid state: {state}")

        data = self.load()
        for i, entry in enumerate(data.pending):
            if entry.imdbId == imdb_id:
                # Validate transition
                if state not in VALID_TRANSITIONS.get(entry.state, set()):
                    raise StateTransitionError(entry.state, state, imdb_id)

                if state == "recommended":
                    # Move to completed history.
                    entry.state = state
                    entry.detail = detail
                    entry.progress = progress or 100
                    entry.completed = entry.completed or datetime.now().date().isoformat()
                    data.recommended.append(entry)
                    data.pending.pop(i)
                else:
                    entry.state = state
                    entry.detail = detail
                    entry.progress = progress
                self.save(data)
                return True

        # Also allow updating entries already in recommended history.
        for entry in data.recommended:
            if entry.imdbId == imdb_id:
                entry.state = state
                entry.detail = detail
                entry.progress = progress
                self.save(data)
                return True
        return False

    def get_current_category(self) -> str:
        """Get current rotation category."""
        data = self.load()
        idx = data.rotation_index % len(data.rotation)
        return data.rotation[idx]

    def rotate_category(self) -> str:
        """Advance rotation index and return new category."""
        data = self.load()
        data.rotation_index = (data.rotation_index + 1) % len(data.rotation)
        category = data.rotation[data.rotation_index]
        self.save(data)
        return category

    def get_rotation_index(self) -> int:
        return self.load().rotation_index

    def set_hero_mode(self, mode: str) -> None:
        data = self.load()
        data.hero_mode = mode
        self.save(data)