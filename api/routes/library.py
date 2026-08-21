"""Library endpoint - unified Plex/Emby library info.

Thin route: delegates to ``LibraryService`` (Plex primary + Emby fallback).
URL bases are owned by the library providers, not duplicated here.
"""
from fastapi import APIRouter

from api.models import LibraryResponse
from config.settings import get_config
from services import PlexLibraryProvider, EmbyLibraryProvider, LibraryService


router = APIRouter()


def _build_service() -> LibraryService:
    """Build a LibraryService wired with the configured providers."""
    cfg = get_config()
    service = LibraryService()
    if cfg.PLEX_URL and cfg.PLEX_TOKEN:
        service.add_provider(PlexLibraryProvider(config=cfg))
    if cfg.has_emby():
        service.add_provider(EmbyLibraryProvider(config=cfg))
    return service


@router.get("/library", response_model=LibraryResponse)
def get_library():
    """Plex first, Emby fallback. URL bases come from the providers."""
    cfg = get_config()
    service = _build_service()

    plex_url = PlexLibraryProvider(config=cfg)._browser_base() + "/web/index.html" \
        if (cfg.PLEX_URL and cfg.PLEX_TOKEN) else ""
    emby_url = EmbyLibraryProvider(config=cfg)._browser_base() \
        if cfg.has_emby() else ""

    # Try Plex first (richest view: counts + recents).
    if plex_url:
        try:
            plex = service.providers[0]
            counts = plex._plex.get_library_counts()
            recent = plex.recently_added(limit=8)
            return LibraryResponse(
                provider="plex", available=True, counts=counts,
                recent=recent, server="Plex",
                urls={"plex": plex_url, "emby": emby_url}
            )
        except Exception:
            pass

    # Fallback to Emby.
    if emby_url:
        try:
            emby = next((p for p in service.providers if p.name == "emby"), None)
            if emby is not None:
                counts_movie = sum(1 for _ in emby._get_items("Movie"))
                counts_show = sum(1 for _ in emby._get_items("Series"))
                return LibraryResponse(
                    provider="emby", available=True,
                    counts={"movie": counts_movie, "show": counts_show},
                    recent=emby.recently_added(limit=8), server="Emby",
                    urls={"plex": "", "emby": emby_url}
                )
        except Exception:
            pass

    return LibraryResponse(
        provider=None, available=False,
        counts={"movie": 0, "show": 0}, recent=[], server=None,
        urls={"plex": plex_url, "emby": emby_url}
    )