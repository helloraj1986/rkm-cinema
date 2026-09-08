"""Config endpoint - public-safe configuration."""
from fastapi import APIRouter
from api.models import ConfigResponse
from config.settings import get_config
from services.acquisition import build_acquisition_service
from services.library import build_library_service
from services.watchlist import WatchlistService

router = APIRouter()


@router.get("/config", response_model=ConfigResponse)
def get_config_endpoint():
    """Public-safe config (no secrets)."""
    cfg = get_config()

    # Service health booleans only — health/profile queries go through the
    # acquisition facade, no caller branches on Radarr/Sonarr directly (§43).
    acq = build_acquisition_service(config=cfg)
    acq_health = acq.health()
    radarr_ok = bool(cfg.RADARR_API_KEY) and acq_health.get("radarr", False)
    sonarr_ok = bool(cfg.SONARR_API_KEY) and acq_health.get("sonarr", False)
    backend = (cfg.MEDIA_SERVER or "plex").lower()
    acq_lib = build_library_service(cfg)
    backend_ok = bool(acq_lib and acq_lib.providers and acq_lib.providers[0].health())
    plex_ok = bool(backend == "plex") and backend_ok
    jellyfin_ok = bool(backend == "jellyfin") and backend_ok
    emby_ok = bool(backend == "emby") and backend_ok

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
            "jellyfin": jellyfin_ok,
            "emby": emby_ok,
        }
    )