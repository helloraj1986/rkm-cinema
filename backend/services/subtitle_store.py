"""Subtitle preferences + usage counts (SUBTITLES_OPENSUBTITLES_PLAN §3.4, Phase 3).

One JSON file beside the watchlist, written atomically, tolerant of a corrupt file —
and **deliberately not SQLite**: it matches the live store (`JsonWatchlistRepository`)
and its write pattern, adds no dependency and needs no schema migration, which the
plan's scope discipline forbids. The `SqliteWatchlistRepository` in the tree stays
untouched (switching stores is a separate, unrelated decision).

Two distinct things live here, and conflating them is the bug this shape prevents:

* **prefs** — per ITEM, what the user chose ("use this subtitle for this film"). Kept
  as an IDENTITY (provider + subtitle id + language + release title), never as a
  stream index: indices are positional and our own download shifts them.
* **usage** — per SUBTITLE (across items), how often it has been used. This is what
  ranks search results, and what the panel shows as "Used N times". It is global on
  purpose: the same release is usually the right pick for every copy of a film.

A disabled preference KEEPS its record — re-enabling is then one tap, and "off" is
never confused with "never chosen".
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import get_config
from services.subtitles import resolve_active_track, usage_key

logger = logging.getLogger("rkm.subtitles.store")

#: File name used beside the watchlist (and the container default).
STORE_FILENAME = "subtitles.json"

#: Where the store lives when the watchlist path is unknown (container default).
DEFAULT_DIR = "/data/rkm"


def default_store_path(watchlist_path: Optional[str] = None) -> Path:
    """The store path, derived from the watchlist's own location.

    The watchlist is already placed by `.env` (`WATCHLIST_DB_PATH=/data/rkm/…` on the
    media root, so it survives rebuilds); the subtitle store belongs beside it for the
    same reason, and this keeps working when the user moves the media root.
    """
    if watchlist_path:
        return Path(str(watchlist_path)).with_name(STORE_FILENAME)
    return Path(DEFAULT_DIR) / STORE_FILENAME


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SubtitleStore:
    """Atomic, corrupt-tolerant preferences + usage.

    Reads are cached on the file's mtime, so a long-lived config object does not
    re-read the file on every request (the watchlist repository's pattern). Writes are
    tmp-file + ``os.replace``: a reader can never see a half-written store, and a
    crash mid-write leaves the previous state intact.
    """

    def __init__(self, *, path: Optional[Path] = None, config=None):
        self._config = config if config is not None else get_config()
        if path is None:
            watchlist = getattr(self._config, "WATCHLIST_DB_PATH", None)
            path = default_store_path(watchlist)
        self.path = Path(path)
        self._lock = threading.Lock()
        self._cache: Optional[dict] = None
        self._cache_mtime: float = 0.0

    # ------------------------------------------------------------------ reading
    def load(self) -> dict:
        """The whole store as ``{"prefs": {...}, "usage": {...}}`` (never raises)."""
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self._cache, self._cache_mtime = {"prefs": {}, "usage": {}}, 0.0
            return dict(self._cache)
        if self._cache is not None and mtime == self._cache_mtime:
            return self._cache
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError) as e:
            # A corrupt file must never take the feature down: start empty, say so,
            # and leave the damaged file alone rather than overwriting evidence.
            logger.warning("subtitle store at %s is unreadable (%s) — starting empty",
                           self.path, e)
            raw = {}
        data = {
            "prefs": dict(raw.get("prefs") or {}) if isinstance(raw, dict) else {},
            "usage": dict(raw.get("usage") or {}) if isinstance(raw, dict) else {},
        }
        self._cache, self._cache_mtime = data, mtime
        return data

    def preference(self, item_id: str) -> Optional[dict]:
        """The stored preference for an item, or ``None``."""
        item_id = str(item_id or "")
        if not item_id:
            return None
        pref = (self.load().get("prefs") or {}).get(item_id)
        return dict(pref) if isinstance(pref, dict) else None

    def usage_count(self, subtitle_id: str) -> int:
        row = (self.load().get("usage") or {}).get(usage_key(subtitle_id)) or {}
        try:
            return int(row.get("count") or 0)
        except (TypeError, ValueError):
            return 0

    def last_used(self, subtitle_id: str) -> str:
        row = (self.load().get("usage") or {}).get(usage_key(subtitle_id)) or {}
        return str(row.get("last_used") or "")

    def usage_counts(self) -> Dict[str, int]:
        """``{subtitle_id: count}`` for every subtitle — used to rank search results."""
        out: Dict[str, int] = {}
        for key, row in (self.load().get("usage") or {}).items():
            if not isinstance(row, dict):
                continue
            sid = str(row.get("subtitle_id") or f"os:{key}")
            try:
                out[sid] = int(row.get("count") or 0)
            except (TypeError, ValueError):
                out[sid] = 0
        return out

    # ------------------------------------------------------------------ writing
    def _write(self, data: dict) -> None:
        """Atomically persist the whole store (tmp + ``os.replace``)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".rkm-tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)
        self._cache, self._cache_mtime = data, self.path.stat().st_mtime

    def _mutate(self, mutate) -> dict:
        with self._lock:
            data = json.loads(json.dumps(self.load()))   # private copy: no shared refs
            result = mutate(data)
            self._write(data)
            return result

    def set_preference(self, item_id: str, *, subtitle_id: str, language: str,
                       provider: str = "opensubtitles", display_title: str = "",
                       disabled: bool = False) -> dict:
        """Record the chosen subtitle for an item (the identity, never an index)."""
        item_id = str(item_id or "")
        if not item_id:
            raise ValueError("set_preference needs an item_id")

        def mutate(data):
            record = {
                "subtitle_id": str(subtitle_id or ""),
                "language": str(language or ""),
                "provider": str(provider or "opensubtitles"),
                "display_title": str(display_title or ""),
                "disabled": bool(disabled),
                "updated": _now(),
            }
            data.setdefault("prefs", {})[item_id] = record
            return record

        return self._mutate(mutate)

    def disable(self, item_id: str) -> dict:
        """Turn subtitles off for an item WITHOUT clearing the choice.

        Keeping the record is what makes re-enabling one tap, and keeps "off"
        distinguishable from "never chosen".
        """
        existing = self.preference(item_id) or {}
        return self.set_preference(
            item_id,
            subtitle_id=existing.get("subtitle_id", ""),
            language=existing.get("language", ""),
            provider=existing.get("provider", "opensubtitles"),
            display_title=existing.get("display_title", ""),
            disabled=True,
        )

    def clear_preference(self, item_id: str) -> bool:
        """Forget an item entirely; ``True`` when something was removed."""
        item_id = str(item_id or "")

        def mutate(data):
            return bool((data.get("prefs") or {}).pop(item_id, None))

        return bool(self._mutate(mutate)) if item_id else False

    def record_use(self, item_id: str, *, subtitle_id: str, language: str,
                   provider: str = "opensubtitles", display_title: str = "") -> int:
        """Increment the usage counter for a subtitle; returns the new count.

        Called when a subtitle is SELECTED (the plan's criterion 7), not on every
        playback — "used" means the user chose it.
        """
        key = usage_key(subtitle_id)

        def mutate(data):
            usage = data.setdefault("usage", {})
            row = dict(usage.get(key) or {})
            row.update({
                "media_id": str(item_id or ""),
                "subtitle_id": str(subtitle_id or ""),
                "language": str(language or ""),
                "provider": str(provider or "opensubtitles"),
                "display_title": str(display_title or ""),
                "count": int(row.get("count") or 0) + 1,
                "last_used": _now(),
            })
            usage[key] = row
            return int(row["count"])

        return int(self._mutate(mutate))

    # ------------------------------------------------------------------- resolve
    def preferred_subtitle(self, item_id: str, tracks: List[dict]) -> Optional[dict]:
        """The user's choice for an item, resolved to a track index for playback.

        ``None`` when there is no choice, when it is disabled, or when the identity
        cannot be matched among the current tracks — the last case must apply NOTHING
        (the picker opens) rather than substitute a different subtitle.
        """
        pref = self.preference(item_id)
        if not pref or pref.get("disabled"):
            return None
        index = resolve_active_track(tracks or [],
                                    display_title=pref.get("display_title", ""),
                                    language=pref.get("language", ""),
                                    subtitle_id=pref.get("subtitle_id", ""))
        if index is None:
            return None
        return {
            "subtitle_id": pref.get("subtitle_id", ""),
            "provider": pref.get("provider", ""),
            "language": pref.get("language", ""),
            "display_title": pref.get("display_title", ""),
            "index": index,
            "used_count": self.usage_count(pref.get("subtitle_id", "")),
        }
