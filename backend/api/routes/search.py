"""Search endpoint - watchlist + TMDB live search."""
import logging
from fastapi import APIRouter, Query
from api.models import SearchResponse, SearchResult
from config.settings import get_config
from services import WatchlistService
from services.tmdb import TMDBService

router = APIRouter()
logger = logging.getLogger("rkm.api.search")


@router.get("/search", response_model=SearchResponse)
def search(q: str = Query(default="", min_length=1)):
    """Search watchlist and TMDB."""
    cfg = get_config()
    query = q.strip()
    ql = query.lower()

    wl = WatchlistService()
    data = wl.load()

    # Local watchlist matches
    local = []
    for entry in data.pending + data.recommended:
        hay = " ".join([
            entry.title, entry.category, entry.director,
            entry.snippet, " ".join(entry.cast or []),
            str(entry.year),
        ]).lower()
        if ql in hay:
            local.append(SearchResult(
                title=entry.title, year=entry.year, type="tv" if entry.isSeries else "movie",
                imdbId=entry.imdbId, tmdbId=entry.tmdbId, poster=entry.poster or "",
                inWatchlist=True, director=entry.director, cast=entry.cast[:3], snippet=entry.snippet or ""
            ))

    # Live TMDB search. Uses the shared TMDBService/HTTPClient path (RKM
    # User-Agent + Accept headers, retries) — the same path /api/suggest and
    # every other TMDB call uses. A hand-rolled raw urllib call here carried no
    # such headers and was rejected by TMDB's edge from the deployed container,
    # silently returning empty results (bare `except: pass`).
    live = []
    live_key = cfg.has_tmdb()
    if cfg.has_tmdb():
        try:
            for result in TMDBService(config=cfg).search_multi(query)[:8]:
                mtype = result.get("media_type")
                live.append(SearchResult(
                    title=result.get("title") or result.get("name") or "",
                    year=int((result.get("release_date") or result.get("first_air_date") or "")[:4] or 0) or None,
                    type=mtype, imdbId="", tmdbId=result.get("id"),
                    poster=("https://image.tmdb.org/t/p/w342" + result["poster_path"]) if result.get("poster_path") else "",
                    snippet=result.get("overview") or "", inWatchlist=False,
                    voteAverage=result.get("vote_average"), director="", cast=[]
                ))
        except Exception as e:
            # Degrade to watchlist-only (contract shape is unchanged) but never
            # silently: the api log should show why live search is empty.
            logger.error("Live TMDB search failed for %r: %s", query, e)

    return SearchResponse(
        watchlist=local[:6], tmdb=live, tmdbKey=live_key,
        servicesDown=not (cfg.RADARR_API_KEY and cfg.SONARR_API_KEY)
    )
