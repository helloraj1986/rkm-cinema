"""Library abstraction — the media server's library as one logical library.

Spec §4/§6/§7/§8/§9: providers of the SAME logical library must collapse to one
``LibraryMatch`` / one ``AVAILABLE`` state per media item. Jellyfin is the only
provider wired today (2026-09-11); the abstraction stays so a second backend —
or a different media server — never leaks a second availability state into the
UI.
"""
from services.library.service import (
    LibraryProvider,
    LibraryMatch,
    LibraryService,
    resolve_library_identity,
)
from services.library.watch_links import WatchLink, WatchLinkResolver
from services.library.jellyfin import JellyfinLibraryProvider
from services.library.factory import build_library_service

__all__ = [
    "LibraryProvider",
    "LibraryMatch",
    "LibraryService",
    "resolve_library_identity",
    "WatchLink",
    "WatchLinkResolver",
    "JellyfinLibraryProvider",
    "build_library_service",
]