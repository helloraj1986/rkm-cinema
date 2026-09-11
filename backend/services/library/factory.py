"""Build a fully-wired :class:`LibraryService` from config.

The single place that decides which library backends the app uses, driven by
``config.MEDIA_SERVER`` (resolved by :func:`config.settings.resolve_media_server`):

- ``jellyfin`` (default) → Jellyfin only (the bundled self-contained stack)
- ``plex``             → Plex primary + Emby fallback (legacy, no longer deployed)
- ``emby``             → Emby only (legacy, no longer deployed)

Every call site that previously hand-wired ``LibraryService`` + provider
appends now delegates here, so one switch is consistent app-wide.

Note: config presence is checked via **attributes** (``cfg.EMBY_URL and
cfg.EMBY_API_KEY``), not the ``has_*()`` helper methods, so the factory keeps
working with the plain attribute Mocks used across the test suite.
"""
from __future__ import annotations

from typing import Optional

from config.settings import get_config, resolve_media_server
from services.library.service import LibraryService


def build_library_service(config=None, *, plex=None, http=None) -> Optional[LibraryService]:
    """Build a :class:`LibraryService` with the configured providers.

    ``plex`` may be a ``PlexService`` (legacy passthrough used by a few call
    sites); it is wrapped when present. ``http`` is a DI seam for tests. Returns
    ``None`` when the chosen backend is not configured.
    """
    cfg = config if config is not None else get_config()
    # An explicitly-supplied PlexService IS a request for the Plex backend (the legacy
    # passthrough a few call sites still use) — it must never be silently ignored in
    # favour of the default.
    backend = "plex" if plex is not None else resolve_media_server(getattr(cfg, "MEDIA_SERVER", ""))

    if backend == "jellyfin":
        if not (cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY):
            return None
        from services.library.jellyfin import JellyfinLibraryProvider
        return LibraryService(providers=[JellyfinLibraryProvider(config=cfg, http=http)])

    if backend == "emby":
        if not (cfg.EMBY_URL and cfg.EMBY_API_KEY):
            return None
        from services.library.emby import EmbyLibraryProvider
        return LibraryService(providers=[EmbyLibraryProvider(config=cfg, http=http)])

    # Default: Plex primary + Emby fallback.
    from services.library.emby import EmbyLibraryProvider
    from services.library.plex import PlexLibraryProvider

    providers = []
    if plex is not None or (cfg.PLEX_URL and cfg.PLEX_TOKEN):
        providers.append(PlexLibraryProvider(config=cfg, plex=plex, http=http))
    if cfg.EMBY_URL and cfg.EMBY_API_KEY:
        providers.append(EmbyLibraryProvider(config=cfg, http=http))
    if not providers:
        return None
    return LibraryService(providers=providers)