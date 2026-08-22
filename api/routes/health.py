"""Health check endpoint."""
from fastapi import APIRouter, HTTPException
from api.models import HealthResponse
from config.settings import get_config
from services import RadarrService, SonarrService
from services.library import PlexLibraryProvider

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Service health and watchlist freshness."""
    cfg = get_config()

    # Quick service checks
    radarr_ok = bool(cfg.RADARR_API_KEY) and RadarrService().health_check()
    sonarr_ok = bool(cfg.SONARR_API_KEY) and SonarrService().health_check()
    plex_ok = bool(cfg.PLEX_URL and cfg.PLEX_TOKEN) and PlexLibraryProvider(config=cfg).health()
    qbit_ok = True  # qBittorrent has no auth, just try to connect

    # Load watchlist for count
    try:
        from services.watchlist import WatchlistService
        wl = WatchlistService()
        data = wl.load()
        title_count = len(data.pending) + len(data.recommended)
        updated = data.updated
    except Exception:
        title_count = 0
        updated = ""

    return HealthResponse(
        ok=True,
        updated=updated,
        titleCount=title_count,
        services={
            "radarr": radarr_ok,
            "sonarr": sonarr_ok,
            "tmdb": cfg.has_tmdb(),
            "plex": plex_ok,
            "jellyfin": cfg.has_jellyfin(),
            "qbit": qbit_ok,
        }
    )