"""Build a fully-wired :class:`LibraryService` from config.

The single place that decides which library backend the app uses. Since
2026-09-11 there is exactly ONE: **Jellyfin** — the bundled self-contained
stack. The retired ``plex``/``emby`` provider branches (and the legacy
``plex=`` passthrough seam) are gone; the deployment path that could select
them was removed with `chore/retire-prod-stack`.

``config.MEDIA_SERVER`` no longer selects a backend here. It is still accepted
and reported (``config.settings.resolve_media_server`` maps any blank or
retired value to ``jellyfin``) so an un-updated `.env` keeps deploying, but
the code never wires a second provider: a name lookup kept "for symmetry" is
exactly how a wrong backend gets selected again.

Every call site that previously hand-wired ``LibraryService`` + provider
appends now delegates here, so one decision is consistent app-wide.
"""
from __future__ import annotations

from typing import Optional

from config.settings import get_config
from services.library.service import LibraryService


def build_library_service(config=None, *, http=None) -> Optional[LibraryService]:
    """Build the Jellyfin-backed :class:`LibraryService`.

    ``http`` is a DI seam for tests. Returns ``None`` when Jellyfin is not
    configured (no URL or no API key). That is a legitimate state for a fresh
    install until the provisioner writes the API key, and every caller already
    treats ``None`` as "the library is not available".
    """
    cfg = config if config is not None else get_config()
    if not (cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY):
        return None
    from services.library.jellyfin import JellyfinLibraryProvider
    return LibraryService(providers=[JellyfinLibraryProvider(config=cfg, http=http)])
