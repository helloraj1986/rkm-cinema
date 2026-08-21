"""Download endpoint - initiate Radarr/Sonarr download with robust movie/tv routing.

Routing rule (authoritative):
  - If the caller explicitly provides type=movie -> Radarr
  - If the caller explicitly provides type=tv    -> Sonarr
  - Otherwise, resolve the media type from the watchlist, then by querying
    both Radarr (movie) and Sonarr (series) lookups so a movie is never
    accidentally routed to Sonarr (and vice-versa).
"""
import logging
import json
import urllib.parse
import urllib.request
from fastapi import APIRouter, HTTPException

from api.models import DownloadRequest, DownloadResponse
from config.settings import get_config
from services import RadarrService, SonarrService
from services.watchlist import WatchlistService

router = APIRouter()
logger = logging.getLogger("rkm.api.download")


def _resolve_type(imdb: str, tmdb: str, requested_type: str) -> str:
    """Determine movie|tv authoritatively.

    Priority:
      1. Explicit requested type
      2. Watchlist entry isSeries
      3. Radarr lookup (movie) vs Sonarr lookup (series)
    Returns 'movie' or 'tv'.
    """
    if requested_type in ("movie", "tv"):
        return requested_type

    # Watchlist
    if imdb:
        wl = WatchlistService()
        entry = wl.find_by_imdb(imdb)
        if entry:
            return "tv" if entry.isSeries else "movie"

    cfg = get_config()

    def _lookup_radarr() -> bool:
        try:
            url = f"{cfg.RADARR_URL}/api/v3/movie/lookup?term=imdb:{imdb or tmdb}"
            headers = {"X-Api-Key": cfg.RADARR_API_KEY}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.load(r)
            items = data or []
            return bool(items and items[0].get("tmdbId"))
        except Exception:
            return False

    def _lookup_sonarr() -> bool:
        try:
            url = f"{cfg.SONARR_URL}/api/v3/series/lookup?term=imdb:{imdb or tmdb}"
            headers = {"X-Api-Key": cfg.SONARR_API_KEY}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.load(r)
            items = data or []
            return bool(items and items[0].get("tvdbId"))
        except Exception:
            return False

    # Prefer Radarr lookup first so a movie is never sent to Sonarr.
    try:
        if _lookup_radarr():
            return "movie"
        if _lookup_sonarr():
            return "tv"
    except Exception:
        pass

    # Last resort: treat as movie (Radarr) since that's the common case.
    return "movie"


@router.post("/download", response_model=DownloadResponse)
def download(req: DownloadRequest):
    """Add movie/series to Radarr or Sonarr."""
    cfg = get_config()
    imdb = (req.imdbId or "").strip()
    tmdb = str(req.tmdbId) if req.tmdbId else ""

    if not imdb and not tmdb:
        raise HTTPException(status_code=400, detail="imdbId or tmdbId required")

    media_type = _resolve_type(imdb, tmdb, (req.type or "").lower().strip())

    if media_type == "tv":
        if not cfg.SONARR_API_KEY:
            raise HTTPException(status_code=503, detail="Sonarr is not configured")
        if not imdb:
            raise HTTPException(status_code=400, detail="TV downloads need an IMDb ID")
        sonarr = SonarrService()
        result = sonarr.add_series(imdb, req.qualityProfileId,
                                   title=req.title, year=req.year)
        if not result.success:
            # If Sonarr has no match but Radarr does, the caller intended a movie.
            if "No Sonarr match" in (result.message or ""):
                r2 = RadarrService().add_movie(imdb, req.qualityProfileId)
                if r2.success:
                    return DownloadResponse(ok=True, state=r2.state, message=r2.message, service="radarr")
            raise HTTPException(status_code=502, detail=result.message)
        return DownloadResponse(
            ok=True, state=result.state, message=result.message, service="sonarr"
        )
    else:
        if not cfg.RADARR_API_KEY:
            raise HTTPException(status_code=503, detail="Radarr is not configured")
        radarr = RadarrService()

        if not imdb:
            # tmdbId-only path: resolve imdb via Radarr lookup.
            try:
                url = f"{cfg.RADARR_URL}/api/v3/movie/lookup?term=tmdb:{req.tmdbId}"
                headers = {"X-Api-Key": cfg.RADARR_API_KEY}
                rq = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(rq, timeout=20) as r:
                    data = json.load(r)
                m = (data or [{}])[0] if isinstance(data, list) else None
                if not m or not m.get("imdbId"):
                    raise HTTPException(status_code=404, detail="No Radarr match for this title")
                imdb = m["imdbId"]
            except HTTPException:
                raise
            except Exception as ex:
                raise HTTPException(status_code=502, detail=f"Radarr unavailable: {ex}")

        result = radarr.add_movie(imdb, req.qualityProfileId,
                                  title=req.title, year=req.year)
        if not result.success:
            # If Radarr has no match but Sonarr does, the caller intended a series.
            if "No Radarr match" in (result.message or ""):
                r2 = SonarrService().add_series(imdb, req.qualityProfileId)
                if r2.success:
                    return DownloadResponse(ok=True, state=r2.state, message=r2.message, service="sonarr")
            raise HTTPException(status_code=404 if "Multiple Radarr matches" in (result.message or "") else 502,
                                detail=result.message)
        return DownloadResponse(
            ok=True, state=result.state, message=result.message, service="radarr"
        )
