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
                 user_data: Optional[dict] = None,
                 played: bool = False, position_ticks: int = 0,
                 runtime_ticks: int = 0, play_count: int = 0,
                 last_played: str = ""):
        self.name = name
        self.year = year
        self.id = id
        self.thumb = thumb
        self.is_series = is_series
        self.provider_ids = provider_ids or {}
        self.user_data = user_data or {}
        # Playback facts (UserData + RunTimeTicks) — drives watched/progress UI.
        self.played = played
        self.position_ticks = position_ticks
        self.runtime_ticks = runtime_ticks
        # Extra watch-state facts (roadmap item 2) — play count + last-played date.
        self.play_count = play_count
        self.last_played = last_played

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
        self._item_cache_expiry: dict = {}           # per-type expiry (item_type -> epoch)
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
                # Playback facts (seconds) for watched/progress UI.
                "played": bool(getattr(item, "played", False)),
                "playback_position": self._ticks_to_sec(getattr(item, "position_ticks", 0)),
                "runtime": self._ticks_to_sec(getattr(item, "runtime_ticks", 0)),
            },
        )

    @staticmethod
    def _ticks_to_sec(ticks) -> int:
        """Jellyfin time values are in 10ms ticks; seconds = ticks / 1e7."""
        try:
            return max(0, int(int(ticks) // 10_000_000))
        except (TypeError, ValueError):
            return 0

    def recently_added(self, limit: int = 8) -> list[dict]:
        out = []
        for itype in ("Series", "Movie"):
            for item in self._get_items(itype)[:limit]:
                out.append(self._item_public(item))
        return out

    def all_items(self, limit: Optional[int] = None) -> list[dict]:
        """Every Movie + Series in the library (poster-wall grid)."""
        out = []
        for itype in ("Movie", "Series"):
            for item in self._get_items(itype):
                out.append(self._item_public(item))
                if limit and len(out) >= limit:
                    return out
        return out

    def continue_watching(self, limit: int = 12) -> list[dict]:
        """In-progress titles — started but not finished.

        Filters the already-fetched library scan (UserData.PlaybackPositionTicks
        > 0 and not Played) rather than Jellyfin's finicky ``/Items/Resume``
        endpoint, so it's deterministic and matches exactly what the UI renders.
        """
        out = []
        for itype in ("Movie", "Series"):
            for item in self._get_items(itype):
                if item.played or item.position_ticks <= 0:
                    continue
                out.append(self._item_public(item))
                if len(out) >= limit:
                    return out
        return out

    def episodes(self, series_id: str, limit: int = 1000) -> list[dict]:
        """Every episode of a series, with per-episode playback facts.

        Episodes carry their own ``UserData`` (Played / PlaybackPositionTicks),
        so resume + watched work per-episode. Ordered by (season, episode).
        """
        if not self._configured() or not series_id:
            return []
        user_id = self._user_id()
        if not user_id:
            return []
        url = (f"{self.config.JELLYFIN_URL}/Users/{user_id}/Items"
               f"?api_key={self.config.JELLYFIN_API_KEY}&ParentId={series_id}"
               f"&IncludeItemTypes=Episode&Recursive=true"
               f"&SortBy=IndexNumber,ParentIndexNumber&Limit={limit}"
               f"&Fields=PrimaryImageAspectRatio,ProductionYear,ProviderIds,UserData,IndexNumber,ParentIndexNumber")
        try:
            raw = self._fetch_raw(url)
        except Exception as e:  # noqa: BLE001
            logger.warning("Jellyfin episodes(%s) failed: %s", series_id, e)
            return []
        out = []
        for it in raw:
            eid = str(it.get("Id", ""))
            if not eid:
                continue
            item = self._parse_item(it, "Series")  # reuses user_data/runtime/thumb parsing
            out.append({
                "id": eid,
                "name": it.get("Name", ""),
                "season": self._int(it.get("ParentIndexNumber")),
                "episode": self._int(it.get("IndexNumber")),
                "thumb": item.thumb,
                "played": bool(item.played),
                "playback_position": self._ticks_to_sec(item.position_ticks),
                "runtime": self._ticks_to_sec(item.runtime_ticks),
            })
        out.sort(key=lambda e: (e["season"], e["episode"]))
        return out

    def refresh_library(self) -> bool:
        """Trigger a full Jellyfin library scan (picks up newly-added media).

        Returns True when Jellyfin accepted the refresh (204). ``POST`` with an
        empty body via the server-side api key.
        """
        if not self._configured():
            return False
        url = f"{self.config.JELLYFIN_URL}/Library/Refresh?api_key={self.config.JELLYFIN_API_KEY}"
        try:
            req = urllib.request.Request(url, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=20) as r:
                ok = 200 <= int(getattr(r, "status", 0)) < 300
            if ok:
                self.invalidate()  # drop the item cache so the scan is seen immediately
            return ok
        except Exception as e:
            logger.warning("Jellyfin library refresh failed: %s", e)
            return False

    @staticmethod
    def _int(v) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    def _item_public(self, item: JellyfinItem) -> dict:
        """Player-ready dict shared by recently_added/all_items/continue_watching."""
        return {
            "title": item.name,
            "year": item.year or None,
            "type": "tv" if item.is_series else "movie",
            "thumb": item.thumb,
            "item_id": item.id,
            "jellyfin_url": self._item_web(item.id),
            "played": bool(item.played),
            "playback_position": self._ticks_to_sec(item.position_ticks),
            "runtime": self._ticks_to_sec(item.runtime_ticks),
            "play_count": int(item.play_count or 0),
            "last_played": item.last_played or None,
        }

    def _fetch_raw(self, url: str) -> list[dict]:
        import json
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.load(r)
        return (d or {}).get("Items", []) or []

    @staticmethod
    def _parse_item(it: dict, item_type: str) -> JellyfinItem:
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
        return JellyfinItem(
            name=it.get("Name", ""),
            year=it.get("ProductionYear", 0),
            id=str(it.get("Id", "")),
            thumb=it.get("Thumb", "") or it.get("PrimaryImageAspectRatio", "") or "",
            is_series=(item_type == "Series"),
            provider_ids=pids,
            user_data=it.get("UserData") or {},
            played=bool((it.get("UserData") or {}).get("Played")),
            position_ticks=int((it.get("UserData") or {}).get("PlaybackPositionTicks") or 0),
            runtime_ticks=int(it.get("RunTimeTicks") or 0),
            play_count=int((it.get("UserData") or {}).get("PlayCount") or 0),
            last_played=str((it.get("UserData") or {}).get("LastPlayedDate") or ""),
        )

    def recently_watched(self, limit: int = 12) -> list[dict]:
        """Recently *finished* titles, most-recently-played first.

        Filters the already-fetched library scan for played items and sorts by
        ``UserData.LastPlayedDate`` (items with no recorded date sort last).
        """
        played = [i for i in (self._get_items("Movie") + self._get_items("Series")) if i.played]
        played.sort(key=lambda i: i.last_played or "", reverse=True)
        return [self._item_public(i) for i in played[:limit]]

    def mark_state(self, item_id: str, watched: bool) -> dict:
        """Mark an item watched (``watched=True``) or unwatched via Jellyfin's
        ``/Users/{uid}/PlayedItems|UnplayedItems`` endpoints.

        Returns the fresh ``{"played": bool, "play_count": int}`` state. Drops the
        scan cache so the next library read reflects the change immediately.
        """
        if not self._configured() or not item_id:
            return {"played": False, "play_count": 0}
        uid = self._user_id()
        if not uid:
            return {"played": False, "play_count": 0}
        action = "PlayedItems" if watched else "UnplayedItems"
        url = (f"{self.config.JELLYFIN_URL}/Users/{uid}/{action}/{item_id}"
               f"?api_key={self.config.JELLYFIN_API_KEY}")
        try:
            req = urllib.request.Request(url, method="POST", data=b"",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10):
                pass
            self.invalidate()  # next library read reflects the change
            return self._user_state(item_id)
        except Exception as e:
            logger.warning("Jellyfin mark_state(%s, %s) failed: %s", item_id, watched, e)
            return {"played": False, "play_count": 0}

    def _user_state(self, item_id: str) -> dict:
        """Fresh ``{played, play_count}`` for one item, for the state mutation."""
        uid = self._user_id()
        if not uid:
            return {"played": False, "play_count": 0}
        url = (f"{self.config.JELLYFIN_URL}/Users/{uid}/Items/{item_id}"
               f"?api_key={self.config.JELLYFIN_API_KEY}&Fields=UserData")
        try:
            import json
            with urllib.request.urlopen(url, timeout=10) as r:
                it = json.load(r)
            ud = it.get("UserData") or {}
            return {
                "played": bool(ud.get("Played")),
                "play_count": int(ud.get("PlayCount") or 0),
            }
        except Exception as e:
            logger.warning("Jellyfin _user_state(%s) failed: %s", item_id, e)
            return {"played": False, "play_count": 0}

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
        self._item_cache_expiry = {}
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
        # Per-type cache so a busy Movie path can't keep a stale-empty Series
        # cache alive via a shared expiry (the bug that hid newly-added shows).
        if self._item_cache and now < self._item_cache_expiry.get(item_type, 0):
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
            raw = self._fetch_raw(url)
            items = [self._parse_item(it, item_type) for it in raw]
            if self._item_cache is None:
                self._item_cache = {}
            self._item_cache[item_type] = items
            self._item_cache_expiry[item_type] = now + self.JELLYFIN_SCAN_TTL
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