"""Watch-link resolver (spec §10 / §11).

Library match
    → provider-specific watch-link resolver
    → WatchLink

A ``WatchLink`` captures the *capability* to watch a given available item on one
provider. The spec §10 shape the API returns is::

    {
      "watch": {
        "plex":  {"available": true,  "url": "..."},
        "emby":  {"available": false, "url": null, "error": "no browser url"}
      }
    }

Failure containment (the key rule of §10):

    Do not let a failed watch-link resolver change AVAILABLE -> NOT_REQUESTED.
    Watch-link failure is a capability problem, not a media availability problem.

Availability is decided *independently* by ``domain/state_machine.resolve_status``
from the library ``find()`` result. ``WatchLinkResolver`` therefore swallows any
exception a provider's ``build_watch_link`` raises and emits
``WatchLink(available=False, error=...)`` — so a broken provider can only hide a
button, never downgrade the item's state.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from services.library.service import LibraryMatch, LibraryService

logger = logging.getLogger("rkm.library.watch_links")


@dataclass
class WatchLink:
    """One provider's watch capability for an available item (spec §10)."""

    provider: str
    available: bool
    url: Optional[str] = None
    error: Optional[str] = None
    #: Provider-native item id (e.g. the Jellyfin ``item_id``) used for in-app
    #: playback through the same-origin /api stream proxy. Optional; absent for
    #: providers whose playback is deep-link-only (Plex/Emby).
    item_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialise in the exact spec §10 shape (plus optional ``item_id``)."""
        d = {
            "available": self.available,
            "url": self.url,
            "error": self.error,
        }
        if self.item_id:
            d["item_id"] = self.item_id
        return d


class WatchLinkResolver:
    """Build the ``watch`` map for one available item across all providers.

    Failure-safe: a provider that can't produce a link yields
    ``{"available": False, "url": None, "error": ...}``; it never raises, and a
    failure here never changes the item's media availability (which is resolved
    separately from the library ``find()``).
    """

    def __init__(self, service: "LibraryService"):
        self._service = service

    def resolve(self, matches) -> dict:
        """Resolve watch links for one available item.

        ``matches`` is a single :class:`LibraryMatch` or an iterable of them
        (use ``LibraryService.find_all`` to surface both Plex and Emby links for
        the same item). Returns the spec §10 ``watch`` map keyed by provider.
        """
        watch: dict = {}
        if not matches:
            return watch
        match_list = list(matches) if isinstance(matches, (list, tuple)) else [matches]
        for match in match_list:
            link = self._build_one(match)
            watch[link.provider] = link.to_dict()
        return watch

    # ------------------------------------------------------------------ internals
    def _build_one(self, match: "LibraryMatch") -> WatchLink:
        for provider in self._service.providers:
            if provider.name != match.provider:
                continue
            try:
                built = provider.build_watch_link(match)
            except Exception as e:  # noqa: BLE001 - containment is the whole point
                logger.warning("watch link failed for %s: %s", provider.name, e)
                return WatchLink(provider=provider.name, available=False, url=None, error=str(e))
            url = self._pick_url(built)
            if url:
                logger.info("watch link available on %s", provider.name)
                item_id = (match.metadata or {}).get("item_id") or None
                return WatchLink(provider=provider.name, available=True, url=url, item_id=item_id)
            # Builder returned but no usable URL — a soft no, not an exception.
            return WatchLink(provider=provider.name, available=False, url=None)
        # No provider matched this match's name (should not happen) — soft no.
        return WatchLink(provider=match.provider, available=False, url=None)

    @staticmethod
    def _pick_url(built: dict) -> Optional[str]:
        """Pull the single URL out of a provider build_watch_link() result.

        Providers return ``{"plex_url": ...}`` / ``{"emby_url": ...}`` (or a
        bare ``{"url": ...}``). We take the first string that actually looks
        like an http(s) URL so the resolver is agnostic to a provider's exact
        dict key and rejects empty/None values.
        """
        if not isinstance(built, dict):
            return None
        for value in built.values():
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
        return None