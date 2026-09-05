"""Jellyfin library provider.

Implements the :class:`LibraryProvider` interface for Jellyfin (the bundled,
self-contained media server). Mirrors ``services/library/emby.py`` because
Jellyfin is Emby-derived and shares the same API shape (``/Items``,
``/System/Info/Public``, provider ids ``Imdb``/``Tmdb``/``Tvdb``). This module
is the single home for Jellyfin item matching, item-id / server-id resolution
and deep-link building — no other code path reverses Jellyfin's URL format.

Availability only — per-episode *watched / progress* state is a separate,
later capability (experiment Appendix A Phase 1); this provider answers "is
the movie/series in the library at all".
"""
from __future__ import annotations

import logging
import urllib.parse
import urllib.request
from typing import Optional

from services.library.service import LibraryProvider, LibraryMatch

logger = logging.getLogger("rkm.library.jellyfin")


class JellyfinItem:
    """A single item in the Jellyfin library (provider model)."""

    def __init__(self, name: str, year: int, id: str, thumb: str = "",
                 is_series: bool = False, provider_ids: Optional[dict] = None,
                 user_data: Optional[dict] = None):
        self.name = name
        self.year = year
        self.id = id
        self.thumb = thumb
        self.is_series = is_series
        self.provider_ids = provider_ids or {}
        self.user_data = user_data or {}

    def matches(self, name: str, year: Optional[int] = None) -> bool:
        search_lower = name.lower()
        item_lower = self.name.lower()
        if search_lower not in item_lower and item_lower not in search_lower:
            return False
        if year is not None and self.year != year:
            return False
        return True


class JellyfinLibraryProvider(LibraryProvider):
    """Provider interface over a Jellyfin library."""

    name = "jellyfin"

    #: How long a full library scan is considered fresh (spec §29: same 60s as Emby).
    JELLYFIN_SCAN_TTL = 60

    def __init__(self, *, config=None, http=None):
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        self.http = http
        self._item_cache: Optional[dict] = None      # {"Movie": [...], "Series": [...]}
        self._item_cache_expiry: float = 0
        self._server_id_value: str = ""
        self._user_id_value: str = ""

    # ------------------------------------------------------------- LibraryProvider
    def health(self) -> bool:
        try:
            self._get_items("Movie")
            return True
        except Exception:
            return False

    def _configured(self) -> bool:
        return bool(self.config.JELLYFIN_URL and self.config.JELLYFIN_API_KEY)

    def find(self, identity, *, title: str = "", year: Optional[int] = None) -> Optional[LibraryMatch]:
        if not self._configured():
            return None
        itype = "Series" if identity.media_type.value == "tv" else "Movie"
        items = self._get_items(itype)

        # 1. Stable provider-id match (Imdb/Tmdb/Tvdb embedded in the item).
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

    def _match_from(self, item: JellyfinItem) -> LibraryMatch:
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
                "user_data": dict(getattr(item, "user_data", {}) or {}),
            },
        )

    def recently_added(self, limit: int = 8) -> list[dict]:
        out = []
        for itype in ("Series", "Movie"):
            for item in self._get_items(itype)[:limit]:
                out.append({
                    "title": item.name,
                    "year": item.year or None,
                    "type": "tv" if item.is_series else "movie",
                    "thumb": item.thumb,
                    "item_id": item.id,
                    "jellyfin_url": self._item_web(item.id),
                })
        return out

    def get_poster(self, item_id: str, max_width: int = 500) -> Optional[dict]:
        """Proxy a Jellyfin item's primary image (keeps the token server-side).

        Returns ``{"content": bytes, "content_type": str}`` or None.
        """
        if not self._configured() or not item_id:
            return None
        url = (f"{self.config.JELLYFIN_URL}/Items/{item_id}/Images/Primary"
               f"?api_key={self.config.JELLYFIN_API_KEY}&maxWidth={max_width}&quality=90&tag=")
        try:
            with urllib.request.urlopen(url, timeout=12) as r:
                data = r.read()
                content_type = r.headers.get("Content-Type", "image/jpeg")
            if not data:
                return None
            return {"content": data, "content_type": content_type}
        except Exception as e:
            logger.warning("Jellyfin get_poster(%s) failed: %s", item_id, e)
            return None

    def get_library_counts(self) -> dict:
        return {
            "movie": len(self._get_items("Movie")),
            "show": len(self._get_items("Series")),
        }

    def invalidate(self) -> None:
        self._item_cache = None
        self._item_cache_expiry = 0
        self._server_id_value = ""
        self._user_id_value = ""

    def build_watch_link(self, match: LibraryMatch) -> dict:
        item_id = str(match.metadata.get("item_id", "") or "")
        base = self._browser_base()
        if item_id:
            # Jellyfin web 10.10+ uses `#/` routes (NO `#!/` hashbang — that's
            # Emby's legacy form and 404s on Jellyfin).
            return {"jellyfin_url": self._item_web(item_id)}
        q = urllib.parse.quote(str(match.title or ""))
        return {"jellyfin_url": f"{base}#/search?query={q}"}

    def _item_web(self, item_id: str) -> str:
        base = self._browser_base()
        url = f"{base}#/details?id={item_id}"
        sid = self._server_id()
        if sid:
            url += f"&serverId={sid}"
        return url

    # ------------------------------------------------------------------ Jellyfin API
    def _browser_base(self) -> str:
        if self.config.JELLYFIN_BROWSER_URL:
            return self.config.JELLYFIN_BROWSER_URL.rstrip("/") + "/web/index.html"
        if self.config.JELLYFIN_URL and "tail8d5e8.ts.net" in (self.config.JELLYFIN_URL or ""):
            return self.config.JELLYFIN_URL.rstrip("/") + "/web/index.html"
        # Default: bundled Jellyfin on the dashboard host (or plain localhost).
        return f"{self.config.JELLYFIN_URL.rstrip('/')}/web/index.html"

    def _user_id(self) -> str:
        if self._user_id_value:
            return self._user_id_value
        try:
            import json
            with urllib.request.urlopen(
                f"{self.config.JELLYFIN_URL}/Users?api_key={self.config.JELLYFIN_API_KEY}",
                timeout=8,
            ) as r:
                users = json.load(r)
            if users:
                self._user_id_value = str(users[0].get("Id", ""))
        except Exception as e:
            logger.warning("Jellyfin _user_id failed: %s", e)
            self._user_id_value = ""
        return self._user_id_value

    def _get_items(self, item_type: str) -> list[JellyfinItem]:
        import time
        now = time.time()
        if self._item_cache and now < self._item_cache_expiry:
            return self._item_cache.get(item_type, [])

        if not self._configured():
            return []

        user_id = self._user_id()
        if not user_id:
            return []

        url = (f"{self.config.JELLYFIN_URL}/Users/{user_id}/Items"
               f"?api_key={self.config.JELLYFIN_API_KEY}"
               f"&Recursive=true&IncludeItemTypes={item_type}"
               f"&Fields=PrimaryImageAspectRatio,ProductionYear,ProviderIds,UserData")
        try:
            import json
            with urllib.request.urlopen(url, timeout=10) as r:
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
                items.append(JellyfinItem(
                    name=it.get("Name", ""),
                    year=it.get("ProductionYear", 0),
                    id=str(it.get("Id", "")),
                    thumb=it.get("Thumb", "") or it.get("PrimaryImageAspectRatio", "") or "",
                    is_series=(item_type == "Series"),
                    provider_ids=pids,
                    user_data=it.get("UserData") or {},
                ))
            if self._item_cache is None:
                self._item_cache = {}
            self._item_cache[item_type] = items
            self._item_cache_expiry = now + self.JELLYFIN_SCAN_TTL
            return items
        except Exception as e:
            logger.warning("Jellyfin _get_items(%s) failed: %s", item_type, e)
            return []

    def _server_id(self) -> str:
        if self._server_id_value:
            return self._server_id_value
        try:
            import json
            with urllib.request.urlopen(f"{self.config.JELLYFIN_URL}/System/Info/Public", timeout=8) as r:
                d = json.load(r)
            self._server_id_value = str(d.get("Id") or d.get("ServerId") or "")
        except Exception:
            self._server_id_value = ""
        return self._server_id_value