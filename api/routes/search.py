"""Search endpoint - watchlist + TMDB live search."""
import urllib.parse
from fastapi import APIRouter, Query
from api.models import SearchResponse, SearchResult
from config.settings import get_config
from services import WatchlistService

router = APIRouter()


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

    # Live TMDB search
    live = []
    live_key = cfg.has_tmdb()
    if cfg.has_tmdb():
        url = f"https://api.themoviedb.org/3/search/multi?api_key={cfg.TMDB_API_KEY}&query={urllib.parse.quote(query)}&language=en-US&page=1"
        try:
            import urllib.request, json
            with urllib.request.urlopen(url, timeout=10) as r:
                d = json.load(r)
            for result in (d.get("results") or [])[:8]:
                mtype = result.get("media_type")
                if mtype not in ("movie", "tv"):
                    continue
                live.append(SearchResult(
                    title=result.get("title") or result.get("name") or "",
                    year=int((result.get("release_date") or result.get("first_air_date") or "")[:4] or 0) or None,
                    type=mtype, tmdbId=result.get("id"),
                    poster=("https://image.tmdb.org/t/p/w342" + result["poster_path"]) if result.get("poster_path") else "",
                    overview=result.get("overview") or "", inWatchlist=False,
                    voteAverage=result.get("vote_average"), director="", cast=[]
                ))
        except Exception:
            pass

    return SearchResponse(
        watchlist=local[:6], tmdb=live, tmdbKey=live_key,
        servicesDown=not (cfg.RADARR_API_KEY and cfg.SONARR_API_KEY)
    )