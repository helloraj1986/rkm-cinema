"""Per-viewer search preferences (SEARCH_IMPROVEMENT_PLAN Phase 5).

One JSON file beside the watchlist, written atomically, tolerant of a corrupt
file — the same shape as :mod:`services.subtitle_store`, for the same reasons:
it matches the live store's write pattern, adds no dependency, needs no schema
migration, and survives an api rebuild because it lives on the media root rather
than in a container volume.

⚠ **Keyed by PROFILE, not by account.** Search personalization is a statement
about what a *viewer* likes, and the app's identity model already separates the
account that signed in (always an administrator) from the profile that is
watching (``session.profile_id()``, ARCHITECTURE §11). Keying on the account
would give two people on one login one shared taste; keying on the profile is
what makes "some users want neutral search regardless of history" a per-person
promise instead of a household-wide one.

⚠ **Default is ON**, and the default is the important half of the entry: a
missing row means "never expressed a preference", not "off". Storing only the
people who turned it off would invert on the day someone reads the file.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import get_config

logger = logging.getLogger("rkm.search.prefs")

#: File name used beside the watchlist (and the container default).
STORE_FILENAME = "search_prefs.json"

#: Where the store lives when the watchlist path is unknown (container default).
DEFAULT_DIR = "/data/rkm"

#: The default for anybody who has not chosen. ⚠ Plain data, not a clever default:
#: every reader asks ``personalized()``, and only this constant decides.
DEFAULT_PERSONALIZED = True

#: The default for the EMBEDDING fallback (Phase 6). ON, for the argument Phase 5 made and one more:
#: it is bounded by construction — the route only runs it when the string matcher has failed — and a
#: feature nobody can find is a feature nobody has. The switch is the way out, and it is per profile.
DEFAULT_SEMANTIC = True


def default_store_path(watchlist_path: Optional[str] = None) -> Path:
    """The store path, derived from the watchlist's own location."""
    if watchlist_path:
        return Path(str(watchlist_path)).with_name(STORE_FILENAME)
    return Path(DEFAULT_DIR) / STORE_FILENAME


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SearchPrefsStore:
    """Atomic, corrupt-tolerant per-profile search preferences.

    Reads are cached on the file's mtime (so a long-lived instance does not re-read
    on every request); writes are tmp-file + ``os.replace``, so a reader can never
    see a half-written store and a crash mid-write leaves the previous state intact.
    """

    def __init__(self, *, path: Optional[Path] = None, config=None):
        self._config = config if config is not None else get_config()
        if path is None:
            path = default_store_path(getattr(self._config, "WATCHLIST_DB_PATH", None))
        self.path = Path(path)
        self._lock = threading.Lock()
        self._cache: Optional[dict] = None
        self._cache_mtime: float = 0.0

    # ------------------------------------------------------------------ reading
    def load(self) -> dict:
        """The whole store as ``{"users": {profile_id: {"personalized": bool}}}``.

        Never raises: a corrupt or unreadable file starts empty (everybody gets the
        default) and is left on disk as evidence rather than overwritten.
        """
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self._cache, self._cache_mtime = {"users": {}}, 0.0
            return dict(self._cache)
        if self._cache is not None and mtime == self._cache_mtime:
            return self._cache
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("search prefs at %s are unreadable (%s) — using defaults",
                           self.path, e)
            raw = {}
        users = raw.get("users") if isinstance(raw, dict) else None
        data = {"users": dict(users) if isinstance(users, dict) else {}}
        self._cache, self._cache_mtime = data, mtime
        return data

    def row(self, profile_id: str) -> dict:
        """One profile's stored row (``{}`` when they have never chosen)."""
        key = str(profile_id or "")
        if not key:
            return {}
        entry = (self.load().get("users") or {}).get(key)
        return dict(entry) if isinstance(entry, dict) else {}

    def personalized(self, profile_id: str) -> bool:
        """Whether this viewer wants taste-biased ranking. Defaults to ON."""
        entry = self.row(profile_id)
        value = entry.get("personalized")
        return DEFAULT_PERSONALIZED if not isinstance(value, bool) else value

    def semantic(self, profile_id: str) -> bool:
        """Whether this viewer wants the embedding fallback (Phase 6). Defaults to ON.

        ⚠ Same shape as :meth:`personalized` on purpose, including the "missing row means the
        DEFAULT, not off" rule: storing only the people who turned it off would invert on the day
        somebody reads the file.
        """
        entry = self.row(profile_id)
        value = entry.get("semantic")
        return DEFAULT_SEMANTIC if not isinstance(value, bool) else value

    # ------------------------------------------------------------------ writing
    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".rkm-tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)
        self._cache, self._cache_mtime = data, self.path.stat().st_mtime

    def set_personalized(self, profile_id: str, enabled: bool) -> dict:
        """Store one viewer's choice and return their fresh row.

        ⚠ An unknown/empty profile id is REFUSED rather than stored under ``""``: a
        route that ran without a published identity would otherwise write a setting
        that belongs to nobody and could never be read back.
        """
        key = str(profile_id or "")
        if not key:
            raise ValueError("search preferences need a profile id")
        with self._lock:
            data = json.loads(json.dumps(self.load()))   # private copy: no shared refs
            users = data.setdefault("users", {})
            entry = dict(users.get(key) or {})
            entry["personalized"] = bool(enabled)
            entry["updated"] = _now()
            users[key] = entry
            data["updated"] = _now()
            self._write(data)
            return entry

    def set_semantic(self, profile_id: str, enabled: bool) -> dict:
        """Store one viewer's embedding-fallback choice and return their fresh row.

        ⚠ It writes into the SAME row as :meth:`set_personalized` (they are two settings of one
        profile's search), which is why both copy the row before editing: a writer that replaced the
        row wholesale would silently clear the other preference.
        """
        key = str(profile_id or "")
        if not key:
            raise ValueError("search preferences need a profile id")
        with self._lock:
            data = json.loads(json.dumps(self.load()))
            users = data.setdefault("users", {})
            entry = dict(users.get(key) or {})
            entry["semantic"] = bool(enabled)
            entry["updated"] = _now()
            users[key] = entry
            data["updated"] = _now()
            self._write(data)
            return entry
