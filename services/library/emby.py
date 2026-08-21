"""Emby library provider.

Implements the :class:`LibraryProvider` interface for Emby (spec §8). Captures
``item_id`` and ``server_id`` so the rest of the app never needs to know Emby's
URL format. This module is the SINGLE home for Emby item matching, item-id /
server-id resolution and deep-link building — the old scattered copies in
``services/plex.py`` and ``api/routes/library.py`` are consolidated here.
"""
from __future__ import annotations

import logging
import urllib.parse
import urllib.request
from typing import Optional

from services.library.service import LibraryProvider, LibraryMatch

logger = logging.getLogger("rkm.library.emby")


class EmbyItem:
    """A single item in the Emby library (provider model)."""

    def __init__(self, name: str, year: int, id: str, thumb: str = "",
                 is_series: bool = False, provider_ids: Optional[dict] = None):
        self.name = name
        self.year = year
        self.id = id
        self.thumb = thumb
        self.is_series = is_series
        self.provider_ids = provider_ids or {}

    def matches(self, name: str, year: Optional[int] = None) -> bool:
        search_lower = name.lower()
        item_lower = self.name.lower()
        if search_lower not in item_lower and item_lower not in search_lower:
            return False
        if year is not None and self.year != year:
            return False
        return True


class EmbyLibraryProvider(LibraryProvider):
    """Provider interface over the Emby library."""

    name = "emby"

    def __init__(self, *, config=None, http=None):
        # Emby HTTP is routed through urllib in the legacy helpers; we keep the
        # injected client signature for DI parity with other providers.
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        self.http = http
        self._item_cache: Optional[dict] = None
        self._item_cache_expiry: float = 0
        self._server_id_value: str = ""

    # ------------------------------------------------------------- LibraryProvider
    def health(self) -> bool:
        try:
            self._get_items("Movie")
            return True
        except Exception:
            return False

    def _configured(self) -> bool:
        return bool(self.config.EMBY_URL and self.config.EMBY_API_KEY)

    def find(self, identity, *, title: str = "", year: Optional[int] = None) -> Optional[LibraryMatch]:
        if not self._configured():
            return None
        itype = "Series" if identity.media_type.value == "tv" else "Movie"
        items = self._get_items(itype)

        # 1. Stable provider-id match (Tmdb/Imdb/Tvdb embedded in the item).
        for item in items:
            pids = getattr(item, "provider_ids", {}) or {}
            if identity.imdb_id and pids.get("imdb") == identity.imdb_id:
                return self._match_from(item)
            if identity.tmdb_id is not None and pids.get("tmdb") == identity.tmdb_id:
                return self._match_from(item)
            if identity.tvdb_id is not None and pids.get("tvdb") == identity.tvdb_id:
                return self._match_from(item)

        # 2. Title/year fallback.
        if title:
            for item in items:
                if item.matches(title, year):
                    return self._match_from(item)
        return None

    def _match_from(self, item: EmbyItem) -> LibraryMatch:
        return LibraryMatch(
            provider=self.name,
            provider_item_id=str(item.id),
            title=item.name,
            year=int(item.year) if item.year else None,
            metadata={
                "item_id": str(item.id),
                "server_id": self._server_id(),
                "thumb": item.thumb,
                "provider_ids": dict(getattr(item, "provider_ids", {}) or {}),
            },
        )

    def recently_added(self, limit: int = 8) -> list[dict]:
        # Emby fallback exposes counts but not a lightweight recent list in the
        # legacy path; reuse the item lists to render a small snapshot.
        out = []
        for itype in ("Movie", "Series"):
            for item in self._get_items(itype)[:limit]:
                out.append({
                    "title": item.name,
                    "year": item.year or None,
                    "type": "tv" if item.is_series else "movie",
                    "thumb": item.thumb,
                    "item_id": item.id,
                })
        return out

    def build_watch_link(self, match: LibraryMatch) -> dict:
        item_id = str(match.metadata.get("item_id", "") or "")
        sid = str(match.metadata.get("server_id", "") or "")
        base = self._browser_base()
        if item_id and sid:
            return {"emby_url": f"{base}#!/item?id={item_id}&serverId={sid}"}
        q = urllib.parse.quote(str(match.title or ""))
        return {"emby_url": f"{base}#!/search?query={q}"}

    # ------------------------------------------------------------------ Emby API
    def _browser_base(self) -> str:
        if self.config.EMBY_BROWSER_URL:
            return self.config.EMBY_BROWSER_URL.rstrip("/") + "/web/index.html"
        if self.config.EMBY_URL and "tail8d5e8.ts.net" in (self.config.EMBY_URL or ""):
            return self.config.EMBY_URL.rstrip("/") + "/web/index.html"
        return "https://rkm-hp.tail8d5e8.ts.net:8096/web/index.html"

    def _get_items(self, item_type: str) -> list[EmbyItem]:
        import time
        now = time.time()
        if self._item_cache and now < self._item_cache_expiry:
            return self._item_cache.get(item_type, [])

        if not self._configured():
            return []

        url = (f"{self.config.EMBY_URL}/Items?api_key={self.config.EMBY_API_KEY}"
               f"&IncludeItemTypes={item_type}&Recursive=true"
               f"&Fields=PrimaryImageAspectRatio,DateCreated,ProductionYear,ProviderIds")
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                import json
                d = json.load(r)
            raw = (d or {}).get("Items", []) or []
            items = []
            for it in raw:
                pids = {}
                p = it.get("ProviderIds") or {}
                if p.get("Imdb"):
                    pids["imdb"] = str(p["Imdb"])
                if p.get("Tmdb"):
                    try:
                        pids["tmdb"] = int(p["Tmdb"])
                    except (TypeError, ValueError, KeyError):
                        pass
                if p.get("Tvdb"):
                    try:
                        pids["tvdb"] = int(p["Tvdb"])
                    except (TypeError, ValueError, KeyError):
                        pass
                items.append(EmbyItem(
                    name=it.get("Name", ""),
                    year=it.get("ProductionYear", 0),
                    id=str(it.get("Id", "")),
                    thumb=it.get("Thumb", "") or "",
                    is_series=(item_type == "Series"),
                    provider_ids=pids,
                ))
            if self._item_cache is None:
                self._item_cache = {}
            self._item_cache[item_type] = items
            self._item_cache_expiry = now + 300
            return items
        except Exception as e:
            logger.warning("Emby _get_items(%s) failed: %s", item_type, e)
            return []

    def _server_id(self) -> str:
        if self._server_id_value:
            return self._server_id_value
        try:
            with urllib.request.urlopen(f"{self.config.EMBY_URL}/System/Info/Public", timeout=8) as r:
                import json
                d = json.load(r)
            self._server_id_value = str(d.get("Id") or d.get("ServerId") or "")
        except Exception:
            self._server_id_value = ""
        return self._server_id_value