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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from domain.enums import MediaType
from domain.identity import MediaIdentity

logger = logging.getLogger("rkm.library")


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


class LibraryService:
    """Unified library facade.

    Providers are views of ONE logical library (spec §9): ``find`` returns the
    first match across providers (a single AVAILABLE state). ``watch_links``
    still returns per-provider links so the UI can offer "Watch on Plex" and
    "Watch on Emby" for the same (one) available item.
    """

    def __init__(self, providers: Optional[list[LibraryProvider]] = None):
        self._providers: list[LibraryProvider] = providers or []

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
        """Return the FIRST match across providers (single logical library)."""
        for provider in self._providers:
            try:
                match = provider.find(identity, title=title, year=year)
            except Exception as e:
                logger.warning("library provider %s find failed: %s", provider.name, e)
                match = None
            if match is not None:
                logger.info("library: %s FOUND %s (%s)",
                            provider.name, identity.media_id, match.provider_item_id)
                return match
        logger.info("library: no provider has %s", identity.media_id)
        return None

    def has(self, identity: MediaIdentity, *, title: str = "", year: Optional[int] = None) -> bool:
        """True if ANY provider has the item (single AVAILABLE gate)."""
        return self.find(identity, title=title, year=year) is not None

    def find_all(self, identity: MediaIdentity, *, title: str = "", year: Optional[int] = None) -> list[LibraryMatch]:
        """All provider matches (e.g. same film in Plex and Emby).

        Defensive like :meth:`find`: a failing provider is skipped with a warning
        so one broken backend can't block the whole reconciler.
        """
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