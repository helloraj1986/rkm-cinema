"""Plex library provider.

Treats Plex as a library provider, not a URL generator (spec §7). Reuses the
cached full-library scan from :class:`services.plex.PlexService` and adds
stable-identity matching on ratingKey/guid (provider ids) before falling back
to title+year. Watch links point at the Plex server's OWN web UI on the
browser-reachable host (never app.plex.tv, never a guessed URL).

Lookups are O(1): the provider indexes the cached scan once per rescan (an
``id(items)`` token tracks which scan the index was built from), so per-candidate
``find`` is a dict/set lookup instead of a linear Python walk of the library.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Optional

from services.library.service import LibraryProvider, LibraryMatch
from services.plex import PlexService

logger = logging.getLogger("rkm.library.plex")

_STOPWORDS = ("the ", "a ", "an ")


class PlexLibraryProvider(LibraryProvider):
    """Provider interface over a cached Plex library scan."""

    name = "plex"

    def __init__(self, *, config=None, http=None, plex: PlexService | None = None):
        self._plex = plex or PlexService(config=config, http=http)
        # Per-media-type index of the current cached scan + the list identity it
        # was built from (invalidate on rescan). None = not yet built.
        self._movie_index = None
        self._movie_token = None
        self._show_index = None
        self._show_token = None

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
        idx = self._ensure_index(is_series, items, id(items))

        # 1. Canonical provider-id match (O(1)).
        match = idx["by_id"].get(("imdb", str(identity.imdb_id or "").lower()))
        if not match and identity.tmdb_id is not None:
            match = idx["by_id"].get(("tmdb", int(identity.tmdb_id)))
        if not match and identity.tvdb_id is not None:
            match = idx["by_id"].get(("tvdb", int(identity.tvdb_id)))
        if match:
            return match

        # 2. Exact normalized title (+ year) match (O(1)) — the path Plex shows
        #    rely on, since Plex shows expose no provider ids.
        if title:
            n = self._norm(title)
            key = (n, year)
            match = idx["by_title"].get(key) or idx["by_title"].get((n, None))
            if match:
                return match

        # 3. Fuzzy substring fallback as a last resort. Runs for ANY candidate
        #    that still has a title after the O(1) id + exact-title lookups
        #    both missed. Previously gated to title-only candidates, which was
        #    WRONG: an id-bearing candidate whose Plex item exposes no provider
        #    ids (provider_ids={}) is NOT authoritatively absent — the id-index
        #    simply has no entry for it, yet the exact-title match can also fail
        #    on a title variant (e.g. candidate "The Dark Knight" vs Plex
        #    "Batman: The Dark Knight"). Fall back to a substring walk so those
        #    genuinely-owned titles are not re-added to the watchlist.
        if title:
            for item in items:
                if item.matches(title, year):
                    return self._match_from(item, identifier_key)
        return None

    # ------------------------------------------------------------- indexing
    def _ensure_index(self, is_series: bool, items, token) -> dict:
        if is_series:
            if self._show_token == token and self._show_index is not None:
                return self._show_index
            self._show_index = self._build_index(items, "show")
            self._show_token = token
            return self._show_index
        if self._movie_token == token and self._movie_index is not None:
            return self._movie_index
        self._movie_index = self._build_index(items, "movie")
        self._movie_token = token
        return self._movie_index

    def _build_index(self, items, identifier_key: str) -> dict:
        by_id: dict = {}
        by_title: dict = {}
        for item in items:
            m = self._match_from(item, identifier_key)
            ids = getattr(item, "provider_ids", lambda: {})() or {}
            for prov, val in (("imdb", ids.get("imdb")),
                              ("tmdb", ids.get("tmdb")),
                              ("tvdb", ids.get("tvdb"))):
                if val:
                    by_id.setdefault(
                        (prov, int(val) if prov in ("tmdb", "tvdb") else str(val).lower()),
                        m)
            t = self._norm(getattr(item, "title", ""))
            y = int(getattr(item, "year", 0) or 0) or None
            if t:
                by_title.setdefault((t, y), m)
                by_title.setdefault((t, None), m)  # year-agnostic
        return {"by_id": by_id, "by_title": by_title}

    @staticmethod
    def _norm(title: str) -> str:
        s = (title or "").lower().replace("&", "and")
        s = re.sub(r"[^a-z0-9]+", " ", s).strip()
        for p in _STOPWORDS:
            if s.startswith(p):
                s = s[len(p):]
                break
        return s

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

    def invalidate(self) -> None:
        """Force a fresh Plex library scan next read (spec §29 invalidation)."""
        try:
            self._plex.clear_cache()
        except Exception:
            pass

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