"""Library provider abstraction and the unified LibraryService.

Spec §4/§6: ``LibraryProvider`` is the interface a library backend implements
(Jellyfin today). The app talks to the library through ``LibraryService``,
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

    ``provider`` is the provider name (``"jellyfin"`` today — the media server
    the app is wired to);
    ``provider_item_id`` is that provider's stable id for the item
    (Jellyfin ``ItemId``). ``metadata`` carries provider
    extras (Jellyfin ``item_id``/``played``/``playback_position``) so watch-link
    builders never re-query.
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

    #: stable provider name (e.g. "jellyfin")
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
        """Build the watch links (e.g. a ``jellyfin`` browser URL) for a match."""

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

    def item_detail(self, item_id: str) -> Optional[dict]:
        """Rich single-item metadata for a preplay/detail view. Default ``None``."""
        return None

    # ------------------------------------- household accounts (AUTH_MULTIUSER_PLAN 1b)
    # An optional capability: only a server that OWNS accounts can manage them. Every
    # default is the safe one (nothing listed, nothing changed), so a provider without
    # this support degrades the household screen rather than breaking it.
    def list_users(self) -> list[dict]:
        """Every account on the server. Default ``[]`` (not supported)."""
        return []

    def get_user_policy(self, user_id: str) -> Optional[dict]:
        """One account's FULL policy. Default ``None`` (not supported)."""
        return None

    def create_user(self, name: str, password: str = "") -> Optional[dict]:
        """Create an account; the password is optional. Default ``None`` (not supported)."""
        return None

    def mutate_user_policy(self, user_id: str, mutate) -> Optional[dict]:
        """Read-modify-write one account's policy. Default ``None`` (not supported)."""
        return None

    def set_folder_access(self, user_id: str, library_ids: Optional[list] = None,
                          *, enable_all: bool = False) -> Optional[dict]:
        """Grant exactly these libraries to an account. Default ``None`` (not supported)."""
        return None

    def set_user_disabled(self, user_id: str, disabled: bool) -> Optional[dict]:
        """Enable/disable an account. Default ``None`` (not supported)."""
        return None

    def set_user_password(self, user_id: str, new_password: str, *,
                          reset: bool = True) -> bool:
        """Set or reset another account's password. Default ``False`` (not supported)."""
        return False

    def change_own_password(self, current_password: str, new_password: str) -> Optional[str]:
        """Change the acting identity's own password. Default: "unreachable" (not supported)."""
        return "unreachable"

    def rename_user(self, user_id: str, name: str) -> Optional[dict]:
        """Rename an account. Default ``None`` (not supported)."""
        return None

    def delete_user(self, user_id: str) -> bool:
        """Delete an account. Default ``False`` (not supported)."""
        return False

    def item_similar(self, item_id: str, limit: int = 10) -> Optional[list[dict]]:
        """\"Because you watched\" rows for one item (TMDB similarity graph).

        Returns display rows ``[{id, title, year, kind, score, poster,
        backdrop}]``, ``[]`` when the backend answers with no similar titles,
        or ``None`` when the backend can't answer for this item. Default
        ``None`` (not supported by this backend for this item).
        """
        return None

    def recently_watched(self, limit: int = 12) -> list[dict]:
        """Recently *finished* titles (most-recently-played first). Default ``[]``."""
        return []

    def library_folders(self) -> list[dict]:
        """The media server's OWN library folders (MEDIA_LIBRARIES_PLAN).

        Returns rows ``[{id, name, collection_type, path, locations}]`` where
        ``id`` is the folder's stable item id on the server (usable as a
        ``ParentId`` scope for :meth:`items_in_folder`), ``path`` is the first
        (primary) location and ``locations`` carries every path the folder
        covers. Default ``[]`` — providers that cannot enumerate folders (or are
        not configured) degrade to the empty state rather than fabricating one.
        """
        return []

    def items_in_folder(self, folder_id: str, limit: Optional[int] = None) -> list[dict]:
        """Titles inside ONE server library folder (movies + series).

        Rows use the same public item shape as :meth:`all_items` so cards/rows/
        player wiring reuse unchanged. Default ``[]`` (not supported).
        """
        return []

    def search_items(self, q: str, limit: int = 12) -> dict:
        """Global-search owned media (GLOBAL_SEARCH_PLAN Phase 1).

        Returns ``{"items": [...], "people": [...], "genres": [...]}`` where
        ``items`` are playable owned rows (movie/show/episode with playback
        facts), ``people``/``genres`` are intent hints. Default ``{}`` (not
        supported by this provider — routes degrade to TMDB discovery only).
        """
        return {}

    def items_by_person(self, person_id: str, limit: int = 6) -> list[dict]:
        """Owned titles featuring *person_id* (actor/director drill-down).
        Default ``[]`` (not supported)."""
        return []

    def mark_state(self, item_id: str, watched: bool) -> Optional[dict]:
        """Mutate watched/unwatched state; return ``{"played": bool, "play_count": int}``
        or ``None`` when the backend doesn't support marking."""
        return None

    def set_playback_position(self, item_id: str, position_ticks: int) -> bool:
        """Record a resume position for an item; ``True`` when the backend stored it.

        A proxy player (one that never becomes a session inside the media server)
        must write the item's user data directly — see the Jellyfin implementation
        for why the ``/Sessions/Playing*`` endpoints cannot work here.
        """
        return False

    # --- Subtitles (SUBTITLES_OPENSUBTITLES_PLAN §3.3) -----------------------
    def item_path(self, item_id: str) -> Optional[str]:
        """The media FILE's path as the server reports it (``None`` if unknown).

        The api runs with the media roots mounted read-write at the SAME container
        paths the server reports, so this value is directly writable from the api —
        that is what makes sidecar-``.srt`` delivery possible without a plugin.
        """
        return None

    def refresh_item(self, item_id: str) -> bool:
        """Re-index ONE item so a newly added sidecar file is picked up.

        Deliberately NOT :meth:`refresh_library`: a library-wide scan is expensive
        and CANCELS an in-flight scan (OPERATIONS.md), which is exactly how to leave
        the user's library half-indexed.
        """
        return False

    def upload_subtitle(self, item_id: str, file_name: str, content: bytes,
                        language: str = "", format: str = "") -> bool:
        """Attach a subtitle to the server directly (fallback when no sidecar write
        is possible — e.g. the media file lives outside the api's mounts)."""
        return False

    def subtitle_search_context(self, item_id: str) -> Optional[dict]:
        """The identity a subtitle SEARCH needs for an item (``None`` if unknown).

        Not the rich detail payload: provider ids (tmdb/imdb) plus, for an episode, the
        series name and season/episode numbers — exactly what keys an OpenSubtitles
        search, and nothing else.
        """
        return None


class LibraryService:
    """Unified library facade.

    Providers are views of ONE logical library (spec §9): ``find`` returns the
    first match across providers (a single AVAILABLE state). ``watch_links``
    still returns per-provider links, so the UI can offer the right "Watch on
    <server>" action for the same (one) available item.
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
        """All provider matches (e.g. the same film found twice).

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
        (pass ``find_all(...)`` to surface every matching provider's links for
        the same item). Returns ``{provider: {"available": bool, "url": str|None,
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
    # is skipped in favour of the backend that actually implements it —
    # preserving the old "first provider
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

    def item_path(self, item_id: str) -> Optional[str]:
        """The media file's path from the first provider that knows it."""
        for p in self._providers:
            try:
                path = p.item_path(item_id)
            except Exception as e:
                logger.warning("item_path failed for %s: %s", p.name, e)
                continue
            if path:
                return path
        return None

    def refresh_item(self, item_id: str) -> bool:
        """Re-index one item; ``True`` when a provider accepted it (never a scan)."""
        for p in self._providers:
            try:
                if p.refresh_item(item_id):
                    return True
            except Exception as e:
                logger.warning("refresh_item failed for %s: %s", p.name, e)
        return False

    def upload_subtitle(self, item_id: str, file_name: str, content: bytes,
                        language: str = "", format: str = "") -> bool:
        """Attach subtitle bytes via the server; ``True`` when a provider accepted it."""
        for p in self._providers:
            try:
                if p.upload_subtitle(item_id, file_name, content,
                                     language=language, format=format):
                    return True
            except Exception as e:
                logger.warning("upload_subtitle failed for %s: %s", p.name, e)
        return False

    def subtitle_search_context(self, item_id: str) -> Optional[dict]:
        """Search identity for an item, from the first provider that knows it."""
        for p in self._providers:
            try:
                context = p.subtitle_search_context(item_id)
            except Exception as e:
                logger.warning("subtitle_search_context failed for %s: %s", p.name, e)
                continue
            if context:
                return context
        return None

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

    def item_detail(self, item_id: str) -> Optional[dict]:
        """Rich single-item metadata from the first provider able to serve it."""
        for p in self._providers:
            try:
                result = p.item_detail(item_id)
            except Exception as e:
                logger.warning("item_detail failed for %s: %s", p.name, e)
                continue
            if result:
                return result
        return None

    # ----------------------------------------- household accounts (Phase 1b) — FACADE
    # The provider interface carries these (``LibraryProvider``), but the ROUTES talk to this
    # facade, so they MUST be delegated here too. Forgetting that is a silent failure with a
    # very misleading symptom: the attribute lookup raises inside the admin gate's try/except,
    # which then answers 403 "only a Jellyfin administrator can manage household accounts" —
    # telling the user they lack permission when the app simply never called the server. Cost
    # one live 403 on 2026-09-12; the wiring test at the bottom of
    # ``tests/test_admin_users_api.py`` exists to make it impossible to repeat.
    def list_users(self) -> list[dict]:
        """Every account on the server, from the first provider able to enumerate them."""
        for p in self._providers:
            try:
                rows = p.list_users()
            except Exception as e:
                logger.warning("list_users failed for %s: %s", p.name, e)
                continue
            if rows:
                return rows
        return []

    def get_user_policy(self, user_id: str) -> Optional[dict]:
        """One account's FULL policy — ``None`` means the server could not be asked."""
        for p in self._providers:
            try:
                policy = p.get_user_policy(user_id)
            except Exception as e:
                logger.warning("get_user_policy failed for %s: %s", p.name, e)
                continue
            if policy is not None:
                return policy
        return None

    def last_api_error(self) -> Optional[dict]:
        """Why the most recent account call failed, from whichever provider knows."""
        for p in self._providers:
            error = getattr(p, "last_api_error", None)
            error = error() if callable(error) else error
            if error:
                return error
        return None

    def create_user(self, name: str, password: str = "") -> Optional[dict]:
        """Create an account (password optional). ``None`` means it was not created."""
        for p in self._providers:
            try:
                created = p.create_user(name, password)
            except Exception as e:
                logger.warning("create_user failed for %s: %s", p.name, e)
                continue
            if created is not None:
                return created
        return None

    def mutate_user_policy(self, user_id: str, mutate) -> Optional[dict]:
        """Read-modify-write one account's policy (``mutate`` receives the FULL policy)."""
        for p in self._providers:
            try:
                updated = p.mutate_user_policy(user_id, mutate)
            except Exception as e:
                logger.warning("mutate_user_policy failed for %s: %s", p.name, e)
                continue
            if updated is not None:
                return updated
        return None

    def set_folder_access(self, user_id: str, library_ids=None, *,
                          enable_all: bool = False) -> Optional[dict]:
        """Grant exactly these libraries (``enable_all`` grants everything instead)."""
        for p in self._providers:
            try:
                updated = p.set_folder_access(user_id, library_ids, enable_all=enable_all)
            except Exception as e:
                logger.warning("set_folder_access failed for %s: %s", p.name, e)
                continue
            if updated is not None:
                return updated
        return None

    def set_user_disabled(self, user_id: str, disabled: bool) -> Optional[dict]:
        """Enable/disable an account (its data is untouched)."""
        for p in self._providers:
            try:
                updated = p.set_user_disabled(user_id, disabled)
            except Exception as e:
                logger.warning("set_user_disabled failed for %s: %s", p.name, e)
                continue
            if updated is not None:
                return updated
        return None

    def set_user_password(self, user_id: str, new_password: str, *, reset: bool = True) -> bool:
        """Set or RESET another account's password. ``True`` means the server accepted it."""
        for p in self._providers:
            try:
                if p.set_user_password(user_id, new_password, reset=reset):
                    return True
            except Exception as e:
                logger.warning("set_user_password failed for %s: %s", p.name, e)
                continue
        return False

    def change_own_password(self, current_password: str, new_password: str) -> Optional[str]:
        """The acting identity changes its OWN password. ``None`` = it worked.

        ⚠ The facade needs its own delegation, like every other capability: a provider-only method
        raises ``AttributeError`` on every route call and the admin gate reports that as "you are
        not an administrator" — a live wrong answer this workstream has already paid for.
        """
        for p in self._providers:
            try:
                reason = p.change_own_password(current_password, new_password)
            except Exception as e:
                logger.warning("change_own_password failed for %s: %s", p.name, e)
                continue
            if reason is None:
                return None
        return "unreachable"

    def rename_user(self, user_id: str, name: str) -> Optional[dict]:
        """Rename an account (``None`` means the server refused).

        ⚠ The FACADE needs its own delegation, not just the provider: adding a capability to
        ``LibraryProvider`` alone raises ``AttributeError`` on every route call, and the admin gate
        swallows that and reports it as "you are not an administrator" — a live wrong answer this
        workstream has already paid for once.
        """
        for p in self._providers:
            try:
                updated = p.rename_user(user_id, name)
            except Exception as e:
                logger.warning("rename_user failed for %s: %s", p.name, e)
                continue
            if updated is not None:
                return updated
        return None

    def delete_user(self, user_id: str) -> bool:
        """Delete an account. ``True`` means the server confirmed it."""
        for p in self._providers:
            try:
                if p.delete_user(user_id):
                    return True
            except Exception as e:
                logger.warning("delete_user failed for %s: %s", p.name, e)
                continue
        return False

    def item_similar(self, item_id: str, limit: int = 10) -> Optional[list[dict]]:
        """\"Because you watched\" rows from the first provider able to answer.

        ``None`` means no provider could resolve the item to similar titles
        (route maps that to 404); a (possibly empty) list is a real answer.
        """
        for p in self._providers:
            try:
                result = p.item_similar(item_id, limit=limit)
            except Exception as e:
                logger.warning("item_similar failed for %s: %s", p.name, e)
                continue
            if result is not None:
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

    def library_folders(self) -> dict:
        """Server library folders (MEDIA_LIBRARIES_PLAN).

        ``{"provider": str|None, "folders": [...]}`` — first provider able to
        enumerate real folders wins (mirrors ``all_items`` aggregation).
        """
        for p in self._providers:
            try:
                folders = p.library_folders() or []
            except Exception as e:
                logger.warning("library_folders failed for %s: %s", p.name, e)
                continue
            if folders:
                return {"provider": p.name, "folders": folders}
        return {"provider": None, "folders": []}

    def items_in_folder(self, folder_id: str, limit: Optional[int] = None) -> dict:
        """One folder's titles: ``{"provider": str|None, "folder_id": str, "items": [...]}``."""
        for p in self._providers:
            try:
                items = p.items_in_folder(folder_id, limit=limit) or []
            except Exception as e:
                logger.warning("items_in_folder failed for %s: %s", p.name, e)
                continue
            if items or p.library_folders():
                return {"provider": p.name, "folder_id": folder_id, "items": items}
        return {"provider": None, "folder_id": folder_id, "items": []}

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

    def set_playback_position(self, item_id: str, position_ticks: int) -> bool:
        """Record a resume position via the first provider that supports it.

        Returns ``True`` only when a backend confirms it stored the value — never
        "we asked" — so the caller can answer honestly instead of 204-and-forget.
        """
        for p in self._providers:
            try:
                if p.set_playback_position(item_id, position_ticks):
                    return True
            except Exception as e:
                logger.warning("set_playback_position failed for %s: %s", p.name, e)
        return False

    def search(self, q: str, limit: int = 12) -> dict:
        """Global-search owned media: ``{provider, items, people, genres}``.

        First provider that returns a real payload wins (mirrors ``all_items``);
        providers without native search (ABC default ``{}``) are skipped.
        """
        for p in self._providers:
            try:
                found = p.search_items(q, limit=limit) or {}
            except Exception as e:
                logger.warning("search_items failed for %s: %s", p.name, e)
                continue
            if found.get("items") or found.get("people") or found.get("genres"):
                return {"provider": p.name, **found}
        return {"provider": None, "items": [], "people": [], "genres": []}

    def items_by_person(self, person_id: str, limit: int = 6) -> dict:
        """Titles featuring a person: ``{provider, items}`` (first provider)."""
        for p in self._providers:
            try:
                items = p.items_by_person(person_id, limit=limit) or []
            except Exception as e:
                logger.warning("items_by_person failed for %s: %s", p.name, e)
                continue
            if items:
                return {"provider": p.name, "items": items}
        return {"provider": None, "items": []}

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