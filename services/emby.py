"""Emby service for library queries and ownership verification."""
import logging
import time
import urllib.parse
from typing import Any, Optional, List

from config.settings import get_config
from core.http_client import get_http_client
from core.exceptions import ServiceUnavailableError, NotFoundError
from services.base import BaseService


logger = logging.getLogger("rkm.emby")


class EmbyItem:
    """Represents an item in Emby library."""
    def __init__(self, name: str, year: int, id: str, thumb: str = "", is_series: bool = False):
        self.name = name
        self.year = year
        self.id = id
        self.thumb = thumb
        self.is_series = is_series

    def matches(self, name: str, year: Optional[int] = None) -> bool:
        """Check if this item matches the given name/year."""
        search_lower = name.lower()
        item_lower = self.name.lower()
        if search_lower not in item_lower and item_lower not in search_lower:
            return False
        if year is not None and self.year != year:
            return False
        return True


class EmbyService(BaseService):
    """Emby integration - library and playback information."""

    def __init__(self, *, config=None, http=None):
        super().__init__("emby", config=config, http=http)
        self._item_cache: dict = {}
        self._item_cache_expiry: float = 0

    def _get_items(self, item_type: str) -> List[dict]:
        """Get all items of a type (Movie or Series) with caching (~5 min)."""
        now = time.time()
        if self._item_cache and now < self._item_cache_expiry:
            return self._item_cache.get(item_type, [])

        if not self.config.EMBY_URL or not self.config.EMBY_API_KEY:
            raise ServiceUnavailableError("Emby URL or API key not configured")

        url = f"{self.config.EMBY_URL}/Items"
        params = {
            "api_key": self.config.EMBY_API_KEY,
            "IncludeItemTypes": item_type,
            "Recursive": "true",
            "Fields": "PrimaryImageAspectRatio,DateCreated,ProductionYear"
        }
        try:
            data = self.http.get(url, params=params)
            items = data.get("Items", [])
            if self._item_cache is None:
                self._item_cache = {}
            self._item_cache[item_type] = items
            self._item_cache_expiry = now + 300  # 5 min
            return items
        except Exception as e:
            self._handle_http_error(f"get_items({item_type})", e)

    def get_all_movies(self) -> List[EmbyItem]:
        """Get all movies from Emby library."""
        items = self._get_items("Movie")
        movies = []
        for item in items:
            movies.append(EmbyItem(
                name=item.get("Name", ""),
                year=item.get("ProductionYear", 0),
                id=item.get("Id", ""),
                thumb=item.get("Thumb", ""),
                is_series=False
            ))
        return movies

    def get_all_shows(self) -> List[EmbyItem]:
        """Get all TV shows from Emby library."""
        items = self._get_items("Series")
        shows = []
        for item in items:
            shows.append(EmbyItem(
                name=item.get("Name", ""),
                year=item.get("ProductionYear", 0),
                id=item.get("Id", ""),
                thumb=item.get("Thumb", ""),
                is_series=True
            ))
        return shows

    def has_movie(self, name: str, year: Optional[int] = None) -> bool:
        """Check if a movie exists in Emby library."""
        movies = self.get_all_movies()
        for movie in movies:
            if movie.matches(name, year):
                logger.info("Emby ownership: FOUND movie '%s' (%s)", name, year or "any")
                return True
        logger.info("Emby ownership: NOT FOUND movie '%s' (%s)", name, year or "any")
        return False

    def has_show(self, name: str, year: Optional[int] = None) -> bool:
        """Check if a TV show exists in Emby library."""
        shows = self.get_all_shows()
        for show in shows:
            if show.matches(name, year):
                logger.info("Emby ownership: FOUND show '%s' (%s)", name, year or "any")
                return True
        logger.info("Emby ownership: NOT FOUND show '%s' (%s)", name, year or "any")
        return False

    def has_media(self, name: str, year: Optional[int] = None, is_series: bool = False) -> bool:
        """Unified ownership check for movie or show."""
        if is_series:
            return self.has_show(name, year)
        return self.has_movie(name, year)

    def get_media_info(self, name: str, year: Optional[int] = None, is_series: bool = False) -> Optional[dict]:
        """Get detailed info for a media item if found."""
        if is_series:
            shows = self.get_all_shows()
            for show in shows:
                if show.matches(name, year):
                    return {
                        "id": show.id,
                        "name": show.name,
                        "year": show.year,
                        "thumb": show.thumb,
                        "type": "tv"
                    }
        else:
            movies = self.get_all_movies()
            for movie in movies:
                if movie.matches(name, year):
                    return {
                        "id": movie.id,
                        "name": movie.name,
                        "year": movie.year,
                        "thumb": movie.thumb,
                        "type": "movie"
                    }
        return None

    def get_playback_url(self, item_id: str) -> Optional[str]:
        """Get a direct playback URL for an item (requires authentication token in URL)."""
        if not self.config.EMBY_URL or not self.config.EMBY_API_KEY:
            return None
        # Emby playback URL format: /Videos/{item_id}/stream.{ext}?api_key={key}&DeviceId=...&MediaSourceId=...
        # For simplicity, we'll return the item info URL; the frontend can construct the play URL.
        # Alternatively, we can return a deep link to the Emby web interface.
        # We'll return a URL to the item page for now.
        return f"{self.config.EMBY_URL}/web/index.html#!/item?id={item_id}"

    def health_check(self) -> bool:
        """Check if Emby is reachable."""
        try:
            self._get_items("Movie")
            return True
        except Exception:
            return False