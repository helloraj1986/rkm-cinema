"""Library abstraction - unified Plex/Emby library providers.

Spec §4/§6/§7/§8/§9: Plex and Emby are providers of the SAME logical library.
The application must present one ``LibraryMatch`` / one ``AVAILABLE`` state per
media item, never "Plex available" and "Emby available" as two states.
"""
from services.library.service import (
    LibraryProvider,
    LibraryMatch,
    LibraryService,
    resolve_library_identity,
)
from services.library.watch_links import WatchLink, WatchLinkResolver
from services.library.plex import PlexLibraryProvider
from services.library.emby import EmbyLibraryProvider
from services.library.jellyfin import JellyfinLibraryProvider
from services.library.factory import build_library_service

__all__ = [
    "LibraryProvider",
    "LibraryMatch",
    "LibraryService",
    "resolve_library_identity",
    "WatchLink",
    "WatchLinkResolver",
    "PlexLibraryProvider",
    "EmbyLibraryProvider",
    "JellyfinLibraryProvider",
    "build_library_service",
]