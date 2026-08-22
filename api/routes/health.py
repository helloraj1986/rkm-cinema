"""Health check endpoint."""
from fastapi import APIRouter
from api.models import HealthResponse
from config.settings import get_config
from services.acquisition import build_acquisition_service
from services.library import PlexLibraryProvider

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Service health and watchlist freshness."""
    cfg = get_config()

    # Quick service checks — through the acquisition facade (§43), no direct
    # Radarr/Sonarr branches. qBittorrent has no auth, just mark available.
    acq = build_acquisition_service(config=cfg)
    acq_health = acq.health()
    radarr_ok = bool(cfg.RADARR_API_KEY) and acq_health.get("radarr", False)
    sonarr_ok = bool(cfg.SONARR_API_KEY) and acq_health.get("sonarr", False)
    plex_ok = bool(cfg.PLEX_URL and cfg.PLEX_TOKEN) and PlexLibraryProvider(config=cfg).health()
    qbit_ok = True

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