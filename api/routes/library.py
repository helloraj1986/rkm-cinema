"""Library endpoint - Plex/Emby library info."""
from fastapi import APIRouter
from api.models import LibraryResponse
from config.settings import get_config
from services import PlexService

router = APIRouter()


@router.get("/library", response_model=LibraryResponse)
def get_library():
    """Plex first, Emby/Jellyfin fallback."""
    cfg = get_config()

    # Try Plex first
    if cfg.PLEX_URL and cfg.PLEX_TOKEN:
        try:
            plex = PlexService()
            counts = plex.get_library_counts()
            recent = plex.get_recently_added(limit=8)
            return LibraryResponse(
                provider="plex", available=True, counts=counts,
                recent=recent, server="Plex",
                urls={"plex": "https://app.plex.tv/desktop",
                      "emby": "https://rkm-hp.tail8d5e8.ts.net:8096/web/index.html"}
            )
        except Exception:
            pass

    # Fallback to Emby/Jellyfin
    if cfg.has_emby() or cfg.has_jellyfin():
        try:
            base = cfg.EMBY_URL or cfg.JELLYFIN_URL
            key = cfg.EMBY_API_KEY or cfg.JELLYFIN_API_KEY
            import urllib.request, json
            url = f"{base}/Items/Counts?api_key={key}"
            with urllib.request.urlopen(url, timeout=8) as r:
                d = json.load(r)
            return LibraryResponse(
                provider="emby", available=True,
                counts={"movie": d.get("MovieCount", 0), "show": d.get("SeriesCount", 0)},
                recent=[], server="Emby",
                urls={"plex": "", "emby": "https://rkm-hp.tail8d5e8.ts.net:8096/web/index.html"}
            )
        except Exception:
            pass

    return LibraryResponse(
        provider=None, available=False,
        counts={"movie": 0, "show": 0}, recent=[], server=None,
        urls={"plex": "https://app.plex.tv/desktop",
              "emby": "https://rkm-hp.tail8d5e8.ts.net:8096/web/index.html"}
    )