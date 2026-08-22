"""Plex library provider.

Treats Plex as a library provider, not a URL generator (spec §7). Reuses the
cached full-library scan from :class:`services.plex.PlexService` and adds
stable-identity matching on ratingKey/guid (provider ids) before falling back
to title+year. Watch links point at the Plex server's OWN web UI on the
browser-reachable host (never app.plex.tv, never a guessed URL).
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Optional

from services.library.service import LibraryProvider, LibraryMatch
from services.plex import PlexService

logger = logging.getLogger("rkm.library.plex")


class PlexLibraryProvider(LibraryProvider):
    """Provider interface over a cached Plex library scan."""

    name = "plex"

    def __init__(self, *, config=None, http=None, plex: PlexService | None = None):
        self._plex = plex or PlexService(config=config, http=http)

    # ------------------------------------------------------------- LibraryProvider
    def health(self) -> bool:
        try:
            return self._plex.health_check()
        except Exception:
            return False

    def find(self, identity, *, title: str = "", year: Optional[int] = None) -> LibraryMatch | None:
        is_series = identity.media_type.value == "tv"
        items = self._plex.get_all_shows() if is_series else self._plex.get_all_movies()
        identifier_key = "show" if is_series else "movie"

        # 1. Stable provider id (guid) match — the canonical route.
        for item in items:
            if not getattr(item, "guid", ""):
                continue
            ids = item.provider_ids()
            if identity.imdb_id and ids.get("imdb") == identity.imdb_id:
                return self._match_from(item, identifier_key)
            if identity.tmdb_id is not None and ids.get("tmdb") == identity.tmdb_id:
                return self._match_from(item, identifier_key)
            if identity.tvdb_id is not None and ids.get("tvdb") == identity.tvdb_id:
                return self._match_from(item, identifier_key)

        # 2. Title+year fallback (last resort, only when a title was given).
        if title:
            for item in items:
                if item.matches(title, year):
                    return self._match_from(item, identifier_key)
        return None

    def _match_from(self, item, identifier_key: str) -> LibraryMatch:
        return LibraryMatch(
            provider=self.name,
            provider_item_id=str(getattr(item, "rating_key", "") or ""),
            title=getattr(item, "title", ""),
            year=int(item.year) if getattr(item, "year", None) else None,
            metadata={
                "rating_key": str(getattr(item, "rating_key", "") or ""),
                "machine_identifier": self._plex.server_id(),
                "guid": getattr(item, "guid", "") or "",
                "library_section": getattr(item, "library_section", "") or "",
                "thumb": getattr(item, "thumb", "") or "",
                "identifier": identifier_key,
            },
        )

    def recently_added(self, limit: int = 8) -> list[dict]:
        return self._plex.get_recently_added(limit=limit)

    def build_watch_link(self, match: LibraryMatch) -> dict:
        return {"plex_url": self._plex_url(match)}

    def get_thumb(self, path: str, width: int = 500) -> Optional[dict]:
        """Proxy a Plex artwork thumbnail (single home for Plex-specific media).

        Exposed so the thumbnail route consumes the provider instead of
        constructing a bare PlexService (§43 no direct-route service branch).
        Returns ``{"content": bytes, "content_type": str}`` or ``None``.
        """
        try:
            return self._plex.get_thumb(path, width)
        except Exception:
            return None

    # ------------------------------------------------------------------ URLs
    def _browser_base(self) -> str:
        """Browser-reachable Plex base (Tailscale or PLEX_BROWSER_URL), never app.plex.tv."""
        if self._plex.config.PLEX_BROWSER_URL:
            return self._plex.config.PLEX_BROWSER_URL.rstrip("/")
        if self._plex.config.PLEX_URL and "tail8d5e8.ts.net" in self._plex.config.PLEX_URL:
            return self._plex.config.PLEX_URL.rstrip("/")
        return "https://rkm-hp.tail8d5e8.ts.net:32400"

    def _plex_url(self, match: LibraryMatch) -> str:
        base = self._browser_base()
        rating_key = str(match.metadata.get("rating_key", "") or "")
        sid = str(match.metadata.get("machine_identifier", "") or "")
        if base and rating_key and sid:
            return (f"{base}/web/index.html#!/server/{sid}/details?key="
                    f"/library/metadata/{rating_key}")
        q = urllib.parse.quote(f"{match.title} {match.year or ''}".strip())
        return f"{base}/web/search?query={q}"