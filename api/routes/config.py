"""Config endpoint - public-safe configuration."""
from fastapi import APIRouter
from api.models import ConfigResponse
from config.settings import get_config
from services import RadarrService, SonarrService
from services.library import PlexLibraryProvider
from services.watchlist import WatchlistService

router = APIRouter()


@router.get("/config", response_model=ConfigResponse)
def get_config_endpoint():
    """Public-safe config (no secrets)."""
    cfg = get_config()

    # Service health booleans only
    radarr_ok = bool(cfg.RADARR_API_KEY) and RadarrService().health_check()
    sonarr_ok = bool(cfg.SONARR_API_KEY) and SonarrService().health_check()
    plex_ok = bool(cfg.PLEX_URL and cfg.PLEX_TOKEN) and PlexLibraryProvider(config=cfg).health()

    # Watchlist metadata
    try:
        wl = WatchlistService()
        data = wl.load()
        updated = data.updated
        hero_mode = data.hero_mode
        rotation = data.rotation
    except Exception:
        updated = ""
        hero_mode = "auto"
        rotation = []

    return ConfigResponse(
        updated=updated,
        heroMode=hero_mode,
        rotation=rotation,
        services={
            "radarr": radarr_ok,
            "sonarr": sonarr_ok,
            "tmdb": cfg.has_tmdb(),
            "plex": plex_ok,
            "jellyfin": cfg.has_jellyfin(),
        }
    )