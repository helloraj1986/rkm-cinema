"""qBittorrent service — isolated download-state integration.

Only this module knows about the qBittorrent API. Routes ask it for torrents
or a matched torrent; they never build qBittorrent URLs or call it directly.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
from typing import Any, Optional

from config.settings import get_config

logger = logging.getLogger("rkm.qbittorrent")

_STOP_WORDS = {
    "the", "and", "for", "not", "but", "are", "all", "any", "was", "you",
    "your", "his", "her", "with", "from", "that", "this", "have", "has",
}


class QBittorrentService:
    """qBittorrent integration (unauthenticated local connection)."""

    def __init__(self, *, config=None):
        self.config = config if config is not None else get_config()
        self._cache: list = []
        self._cache_expiry: float = 0

    # ------------------------------------------------------------------ health
    def health(self) -> bool:
        """Reachable if we can connect + list torrents (unauthenticated)."""
        import urllib.request
        try:
            url = f"{self.config.QBITTORRENT_URL}/api/v2/torrents/info"
            req = urllib.request.Request(url, headers={"User-Agent": "RKM-Cinema/2.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                return r.status == 200
        except Exception:
            return False

    # ------------------------------------------------------------------ data
    def get_torrents(self, *, use_cache: bool = True, ttl: int = 30) -> list[dict]:
        """Return all qBittorrent torrents (short-TTL cached)."""
        import time
        now = time.time()
        if use_cache and self._cache and now < self._cache_expiry:
            return self._cache
        url = f"{self.config.QBITTORRENT_URL}/api/v2/torrents/info"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RKM-Cinema/2.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.load(r)
            self._cache = data
            self._cache_expiry = time.time() + ttl
            return data
        except Exception:
            return []

    # ------------------------------------------------------------------ matching
    def match(self, title: str, year: str = "") -> Optional[dict]:
        """Find the torrent matching a title (fuzzy word-set scoring)."""
        key = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
        words = {w for w in key.split() if len(w) > 3 and w not in _STOP_WORDS}
        if not words:
            return None

        best, best_score = None, 0
        for t in self.get_torrents():
            name = re.sub(r"[^a-z0-9]+", " ", (t.get("name") or "").lower())
            nwords = set(name.split())
            score = len(words & nwords)
            if score > best_score:
                best_score, best = score, t

        # Require a majority word overlap to avoid weak false matches.
        if best and best_score >= 1 and best_score / len(words) >= 0.5:
            return best
        return None

    # ------------------------------------------------------------------ state helpers
    @staticmethod
    def state(t: dict) -> dict:
        """Compact download-state from a qBittorrent torrent dict."""
        prog = round(float(t.get("progress") or 0) * 100)
        speed = float(t.get("dlspeed") or 0) / 1e6  # MB/s
        eta = int(t.get("eta") or -1)
        return {
            "progress": prog,
            "speed": round(speed, 2),
            "eta": eta if eta >= 0 else None,
            "qbitState": t.get("state") or "",
            "qbitName": (t.get("name") or "")[:60],
        }
