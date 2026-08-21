"""Plex service for library queries and ownership verification."""
import logging
import time
import urllib.parse
from typing import Any, Optional
from xml.etree import ElementTree as ET

from config.settings import get_config
from core.http_client import get_http_client
from core.exceptions import ServiceUnavailableError, NotFoundError
from services.base import BaseService


logger = logging.getLogger("rkm.plex")


class PlexMovie:
    """Represents a movie in Plex library."""
    def __init__(self, title: str, year: int, rating_key: str, thumb: str = "",
                 guid: str = "", library_section: str = ""):
        self.title = title
        self.year = year
        self.rating_key = rating_key
        self.thumb = thumb
        self.guid = guid
        self.library_section = library_section

    def provider_ids(self) -> dict:
        """Parse guid into a dict of provider -> id (e.g. {'imdb': 'tt0133093', 'tmdb': 603})."""
        ids = {}
        guid = (self.guid or "").split("?")[0]
        for prov, key in (("tmdb", "themoviedb"), ("imdb", "imdb"), ("tvdb", "thetvdb")):
            marker = f"{key}://"
            if marker in guid:
                raw = guid.rsplit(marker, 1)[1].rstrip("/")
                if prov == "imdb":
                    if raw and not raw.startswith("tt") and raw.isdigit():
                        raw = f"tt{raw}"
                    ids[prov] = raw
                else:
                    try:
                        ids[prov] = int(raw)
                    except (TypeError, ValueError):
                        pass
        return ids

    def matches(self, title: str, year: Optional[int] = None) -> bool:
        """Check if this movie matches the given title/year."""
        # Case-insensitive substring match in either direction
        search_lower = title.lower()
        plex_lower = self.title.lower()
        if search_lower not in plex_lower and plex_lower not in search_lower:
            return False
        if year is not None and self.year != year:
            return False
        return True


class PlexShow:
    """Represents a TV show in Plex library."""
    def __init__(self, title: str, year: int, rating_key: str, thumb: str = "",
                 guid: str = "", library_section: str = ""):
        self.title = title
        self.year = year
        self.rating_key = rating_key
        self.thumb = thumb
        self.guid = guid
        self.library_section = library_section

    def provider_ids(self) -> dict:
        """Parse guid into a dict of provider -> id (e.g. {'imdb': 'tt0133093', 'tmdb': 603}).

        Plex agent guid looks like ``com.plexapp.agents.themoviedb://603?lang=en``.
        Return normalized ids keyed by provider.
        """
        ids = {}
        guid = (self.guid or "").split("?")[0]
        for prov, key in (("tmdb", "themoviedb"), ("imdb", "imdb"), ("tvdb", "thetvdb")):
            marker = f"{key}://"
            if marker in guid:
                raw = guid.rsplit(marker, 1)[1].rstrip("/")
                if prov == "imdb":
                    if raw and not raw.startswith("tt") and raw.isdigit():
                        raw = f"tt{raw}"
                    ids[prov] = raw
                else:
                    try:
                        ids[prov] = int(raw)
                    except (TypeError, ValueError):
                        pass
        return ids

    def matches(self, title: str, year: Optional[int] = None) -> bool:
        """Check if this show matches the given title/year."""
        # Case-insensitive substring match in either direction
        search_lower = title.lower()
        plex_lower = self.title.lower()
        if search_lower not in plex_lower and plex_lower not in search_lower:
            return False
        if year is not None and self.year != year:
            return False
        return True


class PlexService(BaseService):
    """Plex integration - source of truth for media ownership."""

    def __init__(self, *, config=None, http=None):
        super().__init__("plex", config=config, http=http)
        self._section_cache: dict = {}
        self._section_cache_expiry: float = 0
        self._library_cache: dict = {}
        self._library_cache_expiry: float = 0

    def _get_sections(self) -> list[dict]:
        """Get library sections with caching (~5 min)."""
        now = time.time()
        if self._section_cache and now < self._section_cache_expiry:
            return self._section_cache

        url = f"{self.config.PLEX_URL}/library/sections"
        try:
            data = self.http.get(url, headers={}, params={"X-Plex-Token": self.config.PLEX_TOKEN})
            sections = data.get("MediaContainer", {}).get("Directory", [])
            self._section_cache = sections
            self._section_cache_expiry = now + 300  # 5 min
            return sections
        except Exception as e:
            self._handle_http_error("get_sections", e)

    def _get_section_content(self, section_key: str) -> list[dict]:
        """Get all items in a section."""
        url = f"{self.config.PLEX_URL}/library/sections/{section_key}/all"
        params = {"X-Plex-Token": self.config.PLEX_TOKEN, "includeCollections": "0"}
        try:
            data = self.http.get(url, headers={}, params=params)
            return data.get("MediaContainer", {}).get("Metadata", [])
        except Exception as e:
            self._handle_http_error(f"get_section_content({section_key})", e)

    def get_all_movies(self) -> list[PlexMovie]:
        """Get all movies from all movie library sections (cached ~60s).

        Rescans of the full Plex library (774 movies + 100 shows) are expensive;
        the status service calls this once per entry, so without caching one
        /api/status pass can trigger 17 full rescans and blow the request window.
        """
        now = time.time()
        cached = self._library_cache.get("movies")
        if cached is not None and now < self._library_cache_expiry:
            return cached
        sections = self._get_sections()
        movies = []
        for section in sections:
            if section.get("type") == "movie":
                items = self._get_section_content(section["key"])
                for item in items:
                    if item.get("type") == "movie":
                        movies.append(PlexMovie(
                            title=item.get("title", ""),
                            year=item.get("year", 0),
                            rating_key=item.get("ratingKey", ""),
                            thumb=item.get("thumb", ""),
                            guid=item.get("guid", ""),
                            library_section=section.get("key", ""),
                        ))
        self._library_cache["movies"] = movies
        self._library_cache_expiry = now + 60
        return movies

    def get_all_shows(self) -> list[PlexShow]:
        """Get all TV shows from all show library sections (cached ~60s)."""
        now = time.time()
        cached = self._library_cache.get("shows")
        if cached is not None and now < self._library_cache_expiry:
            return cached
        sections = self._get_sections()
        shows = []
        for section in sections:
            if section.get("type") == "show":
                items = self._get_section_content(section["key"])
                for item in items:
                    if item.get("type") == "show":
                        shows.append(PlexShow(
                            title=item.get("title", ""),
                            year=item.get("year", 0),
                            rating_key=item.get("ratingKey", ""),
                            thumb=item.get("thumb", ""),
                            guid=item.get("guid", ""),
                            library_section=section.get("key", ""),
                        ))
        self._library_cache["shows"] = shows
        self._library_cache_expiry = now + 60
        return shows

    def has_movie(self, title: str, year: Optional[int] = None) -> bool:
        """Check if a movie exists in Plex library."""
        movies = self.get_all_movies()
        for movie in movies:
            if movie.matches(title, year):
                logger.info("Plex ownership: FOUND movie '%s' (%s)", title, year or "any")
                return True
        logger.info("Plex ownership: NOT FOUND movie '%s' (%s)", title, year or "any")
        return False

    def has_show(self, title: str, year: Optional[int] = None) -> bool:
        """Check if a TV show exists in Plex library."""
        shows = self.get_all_shows()
        for show in shows:
            if show.matches(title, year):
                logger.info("Plex ownership: FOUND show '%s' (%s)", title, year or "any")
                return True
        logger.info("Plex ownership: NOT FOUND show '%s' (%s)", title, year or "any")
        return False

    def has_media(self, title: str, year: Optional[int] = None, is_series: bool = False) -> bool:
        """Unified ownership check for movie or show."""
        if is_series:
            return self.has_show(title, year)
        return self.has_movie(title, year)

    def find_item(self, title: str, year: Optional[int] = None, is_series: bool = False):
        """Find a matching movie (or show) and return its rating_key, or None."""
        items = self.get_all_shows() if is_series else self.get_all_movies()
        for it in items:
            if it.matches(title, year):
                return it
        return None

    def plex_key_for(self, title: str, year: Optional[int] = None, is_series: bool = False) -> str:
        """Return the numeric Plex ratingKey for a title, or '' if not found."""
        item = self.find_item(title, year, is_series)
        return str(item.rating_key) if item and item.rating_key else ""

    def server_id(self) -> str:
        """Plex machineIdentifier used in app.plex.tv deep links (cached)."""
        if getattr(self, "_server_id_value", None):
            return self._server_id_value
        try:
            url = f"{self.config.PLEX_URL}/identity"
            data = self.http.get(url, headers={},
                                 params={"X-Plex-Token": self.config.PLEX_TOKEN})
            mid = (data.get("MediaContainer") or {}).get("machineIdentifier") or ""
            if mid:
                self._server_id_value = mid
            return mid
        except Exception:
            return ""

    def _plex_browser_base(self) -> str:
        """Browser-reachable Plex base for deep links.

        Prefer PLEX_BROWSER_URL (Tailscale MagicDNS HTTPS) when configured; else
        default to the documented Tailscale host. PLEX_URL is the LAN/API address
        the backend uses to reach Plex and is NOT browser-reachable, so it is only
        used as a last-resort fallback.
        """
        if self.config.PLEX_BROWSER_URL:
            return self.config.PLEX_BROWSER_URL.rstrip("/")
        if self.config.PLEX_URL and "tail8d5e8.ts.net" in self.config.PLEX_URL:
            return self.config.PLEX_URL.rstrip("/")
        return "https://rkm-hp.tail8d5e8.ts.net:32400"

    def plex_url_for(self, title: str, year: Optional[int] = None, is_series: bool = False) -> str:
        """Build a working deep link into the Plex server's OWN web UI.

        The old approach pointed at app.plex.tv (Plex's cloud app) which needs
        account login + remote relay and rarely auto-opens the item. Linking to
        the local server's /web/index.html over its browser-reachable (Tailscale)
        host — exactly how the Emby links work — opens the item directly with no
        relay. Uses the RAW /library/metadata/<key> path (not %2F-encoded, which
        breaks Plex's hash router).
        """
        base = self._plex_browser_base()
        item = self.find_item(title, year, is_series)  # cached scan
        sid = self.server_id()                            # cached machineIdentifier
        if base and item and item.rating_key and sid:
            return f"{base}/web/index.html#!/server/{sid}/details?key=/library/metadata/{item.rating_key}"
        q = urllib.parse.quote(f"{title} {year or ''}".strip())
        return f"{base}/web/search?query={q}"

    def emby_url_for(self, title: str) -> str:
        import urllib.parse as _up
        # Browser-reachable Emby base: prefer EMBY_BROWSER_URL (Tailscale HTTPS);
        # EMBY_URL is the LAN/API address and is not browser-reachable.
        if self.config.EMBY_BROWSER_URL:
            base = self.config.EMBY_BROWSER_URL.rstrip("/")
        elif self.config.EMBY_URL and "tail8d5e8.ts.net" in self.config.EMBY_URL:
            base = self.config.EMBY_URL.rstrip("/")
        else:
            base = "https://rkm-hp.tail8d5e8.ts.net:8096"
        base += "/web/index.html"
        item_id = self._emby_item_id(str(title or ""))
        sid = self._emby_server_id()
        if item_id and sid:
            return f"{base}#!/item?id={item_id}&serverId={sid}"
        q = _up.quote(str(title or ""))
        return f"{base}#!/search?query={q}"

    def _emby_item_id(self, title: str) -> str:
        """Resolve an Emby item id from a title (cached). Returns str or ''."""
        if not (self.config.EMBY_URL and self.config.EMBY_API_KEY):
            return ""
        if getattr(self, "_emby_items_cache", None) and \
                ((title or "").lower().strip() in self._emby_items_cache):
            return self._emby_items_cache[(title or "").lower().strip()]
        self._emby_items_cache = getattr(self, "_emby_items_cache", {})
        try:
            import urllib.request, json as _json, urllib.parse
            user_id = ""
            req = urllib.request.Request(self.config.EMBY_URL + "/Users?api_key=" + self.config.EMBY_API_KEY)
            with urllib.request.urlopen(req, timeout=8) as r:
                users = _json.load(r)
            for u in users or []:
                if (u.get("Name") or "").lower() in ("rajeev", "admin", "main"):
                    user_id = u.get("Id", "")
                    break
            if not user_id and users:
                user_id = users[0].get("Id", "")
            q = urllib.parse.quote((title or "").lower().strip())
            if user_id:
                url = f"{self.config.EMBY_URL}/Users/{user_id}/Items?api_key={self.config.EMBY_API_KEY}" \
                      f"&searchTerm={q}&Recursive=true&Limit=8"
            else:
                url = f"{self.config.EMBY_URL}/Items?api_key={self.config.EMBY_API_KEY}&searchTerm={q}&Recursive=true&Limit=8"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as r:
                d = _json.load(r)
            items = (d or {}).get("Items", []) or []
            # exact title match first, then first item
            for it in items:
                if (it.get("Name") or "").lower().strip() == (title or "").lower().strip():
                    self._emby_items_cache[(title or "").lower().strip()] = str(it.get("Id", ""))
                    return self._emby_items_cache[(title or "").lower().strip()]
            if items:
                self._emby_items_cache[(title or "").lower().strip()] = str(items[0].get("Id", ""))
                return self._emby_items_cache[(title or "").lower().strip()]
        except Exception as e:
            logger.warning("Emby item lookup failed for %s: %s", title, e)
        return ""

    def _emby_server_id(self) -> str:
        import json as _json
        if getattr(self, "_emby_sid", None):
            return self._emby_sid
        try:
            import urllib.request
            req = urllib.request.Request(self.config.EMBY_URL + "/System/Info/Public")
            with urllib.request.urlopen(req, timeout=8) as r:
                d = _json.load(r)
            sid = d.get("Id") or d.get("ServerId") or ""
            if sid:
                self._emby_sid = sid
            return sid
        except Exception:
            return ""

    def get_library_counts(self) -> dict[str, int]:
        """Get movie/show counts."""
        movies = self.get_all_movies()
        shows = self.get_all_shows()
        return {"movie": len(movies), "show": len(shows)}

    def get_recently_added(self, limit: int = 8) -> list[dict]:
        """Get recently added items across all libraries."""
        url = f"{self.config.PLEX_URL}/library/recentlyAdded"
        params = {"X-Plex-Token": self.config.PLEX_TOKEN, "limit": limit}
        try:
            data = self.http.get(url, headers={}, params=params)
            items = data.get("MediaContainer", {}).get("Metadata", [])
            return [
                {
                    "title": item.get("title", ""),
                    "year": item.get("year"),
                    "type": "tv" if item.get("type") == "show" else "movie",
                    "thumb": item.get("thumb", ""),
                    "rating_key": item.get("ratingKey", ""),
                }
                for item in items
            ]
        except Exception as e:
            self._handle_http_error("get_recently_added", e)

    def health_check(self) -> bool:
        """Check if Plex is reachable."""
        try:
            self._get_sections()
            return True
        except Exception:
            return False

    def get_thumb(self, path: str, width: int = 500) -> Optional[dict]:
        """Proxy a Plex thumbnail without exposing the token.

        Returns a dict of ``{"content": bytes, "content_type": str}`` or None
        if the thumb cannot be resolved. ``path`` is the Plex item ``thumb``
        value (e.g. ``/library/metadata/123/thumb/456``).
        """
        if not path or ".." in path or "://" in path:
            return None
        url = (self.config.PLEX_URL.rstrip("/") + "/photo/:/transcode?width=" + str(width)
               + "&height=" + str(int(width * 1.5))
               + "&url=" + urllib.parse.quote("http://127.0.0.1:32400" + path, safe="")
               + "&X-Plex-Token=" + self.config.PLEX_TOKEN)
        import urllib.request
        try:
            req = urllib.request.Request(url, headers={"Accept": "image/*"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return {
                    "content": r.read(),
                    "content_type": r.headers.get("Content-Type", "image/jpeg"),
                }
        except Exception:
            return None