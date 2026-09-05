"""Emby service facade (backward-compatible).

The canonical Emby implementation now lives in :mod:`services.library.emby`
(``EmbyLibraryProvider``) — item matching, item/server-id resolution and
deep-link building all happen there (spec §8: the rest of the app must not know
Emby's URL format). This module keeps the legacy ``EmbyService``/``EmbyItem``
names so existing imports and tests keep working, and delegates to the provider
so there is exactly ONE matcher.
"""
from __future__ import annotations

import logging
from typing import Optional, List

from services.library.emby import EmbyLibraryProvider, EmbyItem


logger = logging.getLogger("rkm.emby")


class EmbyService:
    """Emby integration - library and playback information (provider-backed)."""

    def __init__(self, *, config=None, http=None):
        from config.settings import get_config as _gc
        self.config = config if config is not None else _gc()
        self.http = http
        self._provider = EmbyLibraryProvider(config=self.config, http=http)

    def _get_items(self, item_type: str) -> List[dict]:
        # Legacy callers pass through to the provider's EmbyItem list (dict-like).
        return [item.__dict__ for item in self._provider._get_items(item_type)]

    def get_all_movies(self) -> List[EmbyItem]:
        return self._provider._get_items("Movie")

    def get_all_shows(self) -> List[EmbyItem]:
        return self._provider._get_items("Series")

    def has_movie(self, name: str, year: Optional[int] = None) -> bool:
        for movie in self.get_all_movies():
            if movie.matches(name, year):
                return True
        return False

    def has_show(self, name: str, year: Optional[int] = None) -> bool:
        for show in self.get_all_shows():
            if show.matches(name, year):
                return True
        return False

    def has_media(self, name: str, year: Optional[int] = None, is_series: bool = False) -> bool:
        if is_series:
            return self.has_show(name, year)
        return self.has_movie(name, year)

    def get_media_info(self, name: str, year: Optional[int] = None, is_series: bool = False) -> Optional[dict]:
        items = self.get_all_shows() if is_series else self.get_all_movies()
        for item in items:
            if item.matches(name, year):
                return {
                    "id": item.id,
                    "name": item.name,
                    "year": item.year,
                    "thumb": item.thumb,
                    "type": "tv" if is_series else "movie",
                }
        return None

    def get_playback_url(self, item_id: str) -> Optional[str]:
        return self._provider._browser_base().split("/web/index.html")[0] + f"/web/index.html#!/item?id={item_id}"

    def health_check(self) -> bool:
        return self._provider.health()


__all__ = ["EmbyService", "EmbyItem"]