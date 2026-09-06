"""Library provider abstraction and the unified LibraryService.

Spec §4/§6: ``LibraryProvider`` is the interface every library backend (Plex,
Emby) implements. The app talks to the library through ``LibraryService``,
which treats all providers as views of ONE logical library (spec §9) so a
single media item collapses to a single ``LibraryMatch`` / ``AVAILABLE`` state.

Providers match by stable identity first (spec §7: ratingKey / guid / machine
identifier / library_section), never by a guessed URL or bare title+year.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Tuple

from domain.enums import MediaType
from domain.identity import MediaIdentity

logger = logging.getLogger("rkm.library")

# How long a library confirmation is considered valid (spec §24: degraded state)
LIBRARY_CONFIRMATION_TTL = 24 * 60 * 60  # 24 hours in seconds


@dataclass
class LibraryMatch:
    """A concrete item found inside one library provider.

    ``provider`` is the provider name (``"plex"`` / ``"emby"``);
    ``provider_item_id`` is that provider's stable id for the item
    (Plex ``ratingKey`` / Emby ``itemId``). ``metadata`` carries provider
    extras (Plex ``guid``/``machine_identifier``/``library_section``; Emby
    ``server_id``) so watch-link builders never re-query.
    """

    provider: str
    provider_item_id: str
    title: str
    year: Optional[int] = None
    metadata: dict = field(default_factory=dict)

    @property
    def watch_link(self) -> dict:
        """The ready-to-emit watch-link fields for this match."""
        return {"provider": self.provider, "provider_item_id": self.provider_item_id,
                "title": self.title, "year": self.year, "metadata": self.metadata}


class LibraryProvider(ABC):
    """Interface implemented by each physical library backend."""

    #: stable provider name ("plex" / "emby")
    name: str = "base"

    @abstractmethod
    def health(self) -> bool:
        """Whether the backend is reachable right now."""

    @abstractmethod
    def find(self, identity: MediaIdentity, *, title: str = "", year: Optional[int] = None) -> Optional[LibraryMatch]:
        """Return the item matching *identity*, or ``None`` if absent.

        Must match on stable provider identity (guid, ratingKey, itemId,
        provider ids such as imdb/tmdb/tvdb) where available, falling back to
        title+year ONLY when no stable id matched and a title was given.
        """

    @abstractmethod
    def recently_added(self, limit: int = 8) -> list[dict]:
        """Recently added items as lightweight dicts (title/year/thumb/type)."""

    def invalidate(self) -> None:
        """Drop any provider-level caches. Default no-op (§43: subclasses
        override only when they cache, so fake providers stay cheap)."""

    @abstractmethod
    def build_watch_link(self, match: LibraryMatch) -> dict:
        """Build the watch links (e.g. ``plex``/``emby`` browser URLs) for a match."""

    # ----------------------------------------------- capability surface (Phase 1)
    # Newer providers (Jellyfin) implement richer views; others inherit the
    # harmless default so ROUTES call the ABC uniformly (never ``getattr``/
    # ``hasattr``). See docs/modular-scalable-architecture.md Phase 1.
    def all_items(self, limit: Optional[int] = None) -> list[dict]:
        """Full library (Movies+Series) with playback facts. Default ``[]``."""
        return []

    def continue_watching(self, limit: int = 12) -> list[dict]:
        """Started-and-unfinished titles. Default ``[]``."""
        return []

    def episodes(self, series_id: str, limit: int = 1000) -> list[dict]:
        """Episodes of one series with per-episode playback facts. Default ``[]``."""
        return []

    def refresh_library(self) -> bool:
        """Trigger a backend library rescan. Default ``False`` (not supported)."""
        return False

    def get_poster(self, item_id: str, max_width: int = 500, kind: str = "Primary") -> Optional[dict]:
        """Fetch an item's primary image (``{"content": bytes, "content_type": str}``). Default ``None``."""
        return None

    def playback_info(self, item_id: str) -> Optional[dict]:
        """Enumerate an item's audio + text-subtitle tracks. Default ``None``."""
        return None

    def recently_watched(self, limit: int = 12) -> list[dict]:
        """Recently *finished* titles (most-recently-played first). Default ``[]``."""
        return []

    def mark_state(self, item_id: str, watched: bool) -> Optional[dict]:
        """Mutate watched/unwatched state; return ``{"played": bool, "play_count": int}``
        or ``None`` when the backend doesn't support marking."""
        return None


class LibraryService:
    """Unified library facade.

    Providers are views of ONE logical library (spec §9): ``find`` returns the
    first match across providers (a single AVAILABLE state). ``watch_links``
    still returns per-provider links so the UI can offer "Watch on Plex" and
    "Watch on Emby" for the same (one) available item.
    """

    def __init__(self, providers: Optional[list[LibraryProvider]] = None):
        self._providers: list[LibraryProvider] = providers or []
        # Cache for library confirmation state (spec §24 degraded state handling)
        self._library_cache: dict[str, Tuple[Optional[LibraryMatch], float]] = {}
        self._library_cache_expiry: float = 0

    @classmethod
    def build(cls, providers: Optional[list[LibraryProvider]] = None) -> "LibraryService":
        """Construct a service with the given providers (falls back to caller wiring)."""
        return cls(providers=providers)

    def add_provider(self, provider: LibraryProvider) -> None:
        self._providers.append(provider)

    @property
    def providers(self) -> list[LibraryProvider]:
        return list(self._providers)

    # ------------------------------------------------------------------ health
    def health(self) -> dict[str, bool]:
        return {p.name: p.health() for p in self._providers}

    # ------------------------------------------------------------------- find
    def find(self, identity: MediaIdentity, *, title: str = "", year: Optional[int] = None) -> Optional[LibraryMatch]:
        """Return the FIRST match across providers (single logical library).
        
        Implements degraded state handling (spec §24): if providers are temporarily
        unavailable but we have recent confirmation, return the cached match.
        """
        cache_key = self._make_cache_key(identity, title, year)
        now = time.time()
        
        # Check if we have a valid cached result
        if (now < self._library_cache_expiry and 
                cache_key in self._library_cache):
            cached_match, cached_time = self._library_cache[cache_key]
            # If cache is still fresh (within TTL), return it
            if now - cached_time < LIBRARY_CONFIRMATION_TTL:
                return cached_match
        
        # No valid cache, try to get fresh result from providers
        try:
            match = self._find_fresh(identity, title=title, year=year)
            # Update cache with fresh result
            self._library_cache[cache_key] = (match, now)
            self._library_cache_expiry = now + 300  # 5 min cache for fresh lookups
            return match
        except Exception:
            # Providers are unavailable, check if we have recent cached confirmation
            if (now < self._library_cache_expiry and 
                    cache_key in self._library_cache):
                cached_match, cached_time = self._library_cache[cache_key]
                # If we have confirmation from within the TTL window, return it
                # This handles spec §24: degraded state for temporary outages
                if now - cached_time < LIBRARY_CONFIRMATION_TTL:
                    return cached_match
            # No recent confirmation available
            return None

    def _find_fresh(self, identity: MediaIdentity, *, title: str = "", year: Optional[int] = None) -> Optional[LibraryMatch]:
        """Fresh provider lookup without caching - used internally by find()."""
        for provider in self._providers:
            try:
                match = provider.find(identity, title=title, year=year)
            except Exception as e:  # noqa: BLE001 - a provider failure is contained
                logger.warning("library provider %s find failed: %s", provider.name, e)
                match = None
            if match is not None:
                logger.info("library: %s FOUND %s (%s)",
                            provider.name, identity.media_id, match.provider_item_id)
                return match
        logger.info("library: no provider has %s", identity.media_id)
        return None

    def _make_cache_key(self, identity: MediaIdentity, title: str = "", year: Optional[int] = None) -> str:
        """Create a cache key for library lookup."""
        parts = [
            identity.media_id or "",
            str(identity.tmdb_id or ""),
            str(identity.imdb_id or ""),
            str(identity.tvdb_id or ""),
            title or "",
            str(year or ""),
        ]
        return "|".join(parts)

    def has(self, identity: MediaIdentity, *, title: str = "", year: Optional[int] = None) -> bool:
        """True if ANY provider has the item (single AVAILABLE gate)."""
        return self.find(identity, title=title, year=year) is not None

    def find_all(self, identity: MediaIdentity, *, title: str = "", year: Optional[int] = None) -> list[LibraryMatch]:
        """All provider matches (e.g. same film in Plex and Emby).

        Defensive like :meth:`find`: a failing provider is skipped with a warning
        so one broken backend can't block the whole reconciler.
        Uses degraded state handling (spec §24) for temporary outages.
        """
        cache_key = self._make_cache_key(identity, title, year)
        now = time.time()

        # Check if we have a valid cached result
        if (now < self._library_cache_expiry and 
                cache_key in self._library_cache):
            cached_match, cached_time = self._library_cache[cache_key]
            # If cache is still fresh (within TTL), return it as a list
            if now - cached_time < LIBRARY_CONFIRMATION_TTL:
                return [cached_match] if cached_match is not None else []

        # No valid cache, try to get fresh result from providers
        try:
            matches = self._find_all_fresh(identity, title=title, year=year)
            # Update cache with fresh result (store first match for find() compatibility)
            first_match = matches[0] if matches else None
            self._library_cache[cache_key] = (first_match, now)
            self._library_cache_expiry = now + 300  # 5 min cache for fresh lookups
            return matches
        except Exception:
            # Providers are unavailable, check if we have recent cached confirmation
            if (now < self._library_cache_expiry and 
                    cache_key in self._library_cache):
                cached_match, cached_time = self._library_cache[cache_key]
                # If we have confirmation from within the TTL window, return it
                # This handles spec §24: degraded state for temporary outages
                if now - cached_time < LIBRARY_CONFIRMATION_TTL:
                    return [cached_match] if cached_match is not None else []
            # No recent confirmation available
            return []

    def _find_all_fresh(self, identity: MediaIdentity, *, title: str = "", year: Optional[int] = None) -> list[LibraryMatch]:
            """Fresh provider lookup for all matches - used internally by find_all()."""
            out: list[LibraryMatch] = []
            for provider in self._providers:
                try:
                    m = provider.find(identity, title=title, year=year)
                except Exception as e:  # noqa: BLE001 - a provider failure is contained
                    logger.warning("library provider %s find_all failed: %s", provider.name, e)
                    m = None
                if m is not None:
                    out.append(m)
            return out

    # ------------------------------------------------------------- watch links
    def watch_links(self, matches) -> dict:
        """Build the spec §10 ``watch`` map for one available item.

        ``matches`` is a single :class:`LibraryMatch` or an iterable of them
        (pass ``find_all(...)`` to surface both Plex and Emby links for the same
        item). Returns ``{provider: {"available": bool, "url": str|None,
        "error": str|None}}``.

        Failure containment (spec §10): a failed provider watch-link resolver
        yields ``available: False`` and **never** turns AVAILABLE into
        NOT_REQUESTED — availability is decided separately by the domain state
        machine from ``find()``.
        """
        from services.library.watch_links import WatchLinkResolver

        return WatchLinkResolver(self).resolve(matches)

    def recently_added(self, limit: int = 8, provider: Optional[str] = None) -> list[dict]:
        """Recently added items, optionally from one provider."""
        for p in self._providers:
            if provider is not None and p.name != provider:
                continue
            try:
                return p.recently_added(limit=limit)
            except Exception as e:
                logger.warning("recently_added failed for %s: %s", p.name, e)
        return []

    # ----------------------------------------------- capability aggregate (Phase 1)
    # Collapse the provider capability surface into "first provider with a
    # meaningful result", so routes call the service, not ``getattr`` instances.
    # A provider that exposes the method but returns the ABC default ``[]``/``False``
    # (e.g. Plex/Emby for the Jellyfin-only views) is skipped in favour of the
    # backend that actually implements it — preserving the old "first provider
    # WITH the method" semantics without feature-detection.
    def all_items(self, limit: Optional[int] = None) -> dict:
        """Poster-wall library: ``{"provider": str|None, "items": [...]}``."""
        for p in self._providers:
            try:
                items = p.all_items(limit=limit) or []
            except Exception as e:
                logger.warning("all_items failed for %s: %s", p.name, e)
                continue
            if items:
                return {"provider": p.name, "items": items}
        return {"provider": None, "items": []}

    def continue_watching(self, limit: int = 12) -> dict:
        """Continue Watching row: ``{"provider": str|None, "items": [...]}``."""
        for p in self._providers:
            try:
                items = p.continue_watching(limit=limit) or []
            except Exception as e:
                logger.warning("continue_watching failed for %s: %s", p.name, e)
                continue
            if items:
                return {"provider": p.name, "items": items}
        return {"provider": None, "items": []}

    def episodes(self, series_id: str, limit: int = 1000) -> dict:
        """Episodes of one series: ``{"provider": str|None, "episodes": [...]}``."""
        for p in self._providers:
            try:
                eps = p.episodes(series_id, limit=limit) or []
            except Exception as e:
                logger.warning("episodes failed for %s: %s", p.name, e)
                continue
            if eps:
                return {"provider": p.name, "episodes": eps}
        return {"provider": None, "episodes": []}

    def refresh_library(self) -> bool:
        """Trigger a rescan; ``True`` if any provider refreshed successfully."""
        for p in self._providers:
            try:
                if p.refresh_library():
                    return True
            except Exception as e:
                logger.warning("refresh_library failed for %s: %s", p.name, e)
        return False

    def get_poster(self, item_id: str, max_width: int = 500, kind: str = "Primary") -> Optional[dict]:
        """Fetch an item image from the first provider able to serve it."""
        for p in self._providers:
            try:
                result = p.get_poster(item_id, max_width=max_width, kind=kind)
            except Exception as e:
                logger.warning("get_poster failed for %s: %s", p.name, e)
                continue
            if result:
                return result
        return None

    def playback_info(self, item_id: str) -> Optional[dict]:
        """Enumerate an item's tracks from the first provider able to serve it."""
        for p in self._providers:
            try:
                result = p.playback_info(item_id)
            except Exception as e:
                logger.warning("playback_info failed for %s: %s", p.name, e)
                continue
            if result:
                return result
        return None

    def recently_watched(self, limit: int = 12) -> dict:
        """Recently-finished row: ``{"provider": str|None, "items": [...]}``."""
        for p in self._providers:
            try:
                items = p.recently_watched(limit=limit) or []
            except Exception as e:
                logger.warning("recently_watched failed for %s: %s", p.name, e)
                continue
            if items:
                return {"provider": p.name, "items": items}
        return {"provider": None, "items": []}

    def mark_state(self, item_id: str, watched: bool) -> dict:
        """Mark watched/unwatched via the first provider that supports it."""
        for p in self._providers:
            try:
                result = p.mark_state(item_id, watched)
            except Exception as e:
                logger.warning("mark_state failed for %s: %s", p.name, e)
                continue
            if result:
                return result
        return {"played": False, "play_count": 0}

    def invalidate(self) -> None:
        """Drop every provider's library caches (force a fresh scan next read).

        Called after the app writes media into the library (or knows a change
        happened) so a subsequent reconcile re-reads instead of serving a
        stale cached scan (spec §29 invalidation on writes).
        """
        for p in self._providers:
            try:
                p.invalidate()
            except Exception as e:  # noqa: BLE001 - never break on a cache clear
                logger.warning("library invalidate %s failed: %s", p.name, e)


def resolve_library_identity(*, media_type: MediaType, tmdb_id=None, imdb_id=None,
                             tvdb_id=None) -> MediaIdentity:
    """Build a MediaIdentity for a library lookup, tolerating missing ids."""
    return MediaIdentity(
        media_type=media_type,
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        tvdb_id=tvdb_id,
    )