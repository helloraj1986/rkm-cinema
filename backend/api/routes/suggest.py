"""Suggest endpoint — user-defined filters → TMDB discover → recommendations.

POST /api/suggest accepts filter criteria (genres, year range, rating, media type)
and returns TMDB-discovered candidates that pass the criteria engine. This powers
the "Suggest" tab in the frontend where users can explore what to watch.
"""
from __future__ import annotations

import logging
from typing import Optional, List
from fastapi import APIRouter
from pydantic import BaseModel, Field

from config.settings import get_config

router = APIRouter()
logger = logging.getLogger("rkm.api.suggest")

# TMDB genre ID → name mapping (movies + TV combined)
MOVIE_GENRES = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Sci-Fi", 53: "Thriller",
    10752: "War", 37: "Western",
}

TV_GENRES = {
    10759: "Action & Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    10762: "Kids", 9648: "Mystery", 10764: "Reality",
    10765: "Sci-Fi & Fantasy", 10767: "Talk", 10768: "War & Politics",
    37: "Western",
}

# Reverse maps: name → id
MOVIE_GENRE_IDS = {v: k for k, v in MOVIE_GENRES.items()}
TV_GENRE_IDS = {v: k for k, v in TV_GENRES.items()}
# Combined for the UI
ALL_GENRE_NAMES = sorted(set(list(MOVIE_GENRES.values()) + list(TV_GENRES.values())))


class SuggestRequest(BaseModel):
    """User-defined filter criteria for suggest."""
    media_type: str = "all"          # "all" | "movie" | "tv"
    genres: List[str] = Field(default_factory=list)  # e.g. ["Action", "Sci-Fi"]
    year_from: Optional[int] = None  # e.g. 2020
    year_to: Optional[int] = None    # e.g. 2025
    min_rating: float = 6.0          # minimum TMDB vote_average (0-10)
    sort_by: str = "popularity.desc" # popularity.desc | vote_average.desc | primary_release_date.desc
    count: int = 20                  # max results per type (1-50)
    include_owned: bool = False      # include titles already in Plex


class SuggestResult(BaseModel):
    """One suggested title."""
    tmdb_id: int
    title: str
    year: Optional[int] = None
    media_type: str                  # "movie" | "tv"
    tmdb_score: float = 0.0
    vote_count: int = 0
    genres: List[str] = Field(default_factory=list)
    overview: str = ""
    poster: str = ""
    backdrop: str = ""
    in_watchlist: bool = False
    in_library: bool = False


class SuggestResponse(BaseModel):
    """POST /api/suggest response."""
    results: List[SuggestResult]
    total: int
    filters: dict
    genres_available: List[str]


@router.post("/suggest/add")
def suggest_add(req: SuggestRequest) -> dict:
    """Add a TMDB-discovered title to the watchlist as a pending entry."""
    return {"ok": False, "message": "Not implemented"}


@router.post("/suggest/add/{tmdb_id}")
def suggest_add_one(tmdb_id: int, media_type: str = "movie") -> dict:
    """Add a single TMDB title to the watchlist as a pending entry."""
    from services.recommendations import RecommendationService, Candidate
    from services.watchlist import WatchlistService

    cfg = get_config()
    svc = RecommendationService(config=cfg)

    # Check if already in watchlist
    wl = WatchlistService()
    data = wl.load()
    for e in (data.pending or []) + (data.recommended or []):
        if e.tmdbId == tmdb_id:
            return {"ok": True, "message": "Already in watchlist", "already": True,
                    "title": getattr(e, "title", ""),
                    "entry": e.to_dict() if hasattr(e, "to_dict") else None}

    # Fetch details from TMDB
    from services.tmdb import TMDBService
    tmdb = TMDBService(config=cfg)

    try:
        if media_type == "tv":
            details = tmdb.get_show_details(tmdb_id)
        else:
            details = tmdb.get_movie_details(tmdb_id)
    except Exception as e:
        return {"ok": False, "message": f"TMDB lookup failed: {e}"}

    if not details:
        return {"ok": False, "message": "TMDB lookup returned no data"}

    # Build Candidate
    title = details.get("title") or details.get("name") or ""
    year = details.get("year") or 0
    genres = details.get("genres", [])
    is_series = media_type == "tv"

    candidate = Candidate(
        title=title,
        year=year,
        category=genres[0] if genres else "Other",
        lang="English",
        imdb=0.0,  # will be enriched
        rt=0,
        is_series=is_series,
        imdb_id=details.get("imdb_id", ""),
        tmdb_id=tmdb_id,
        director=details.get("director", ""),
        cast=details.get("cast", []),
        snippet=details.get("overview", ""),
        poster=details.get("poster", ""),
        tmdb_score=details.get("tmdb_score", 0.0),
        vote_count=0,
    )

    # Enrich and add
    try:
        enriched = svc.enrich_metadata(candidate)
        svc.add_to_watchlist(enriched)
        return {"ok": True, "message": f"Added {title} to watchlist", "title": title,
                "entry": enriched.entry.to_dict()}
    except Exception as e:
        return {"ok": False, "message": f"Failed to add: {e}"}


class SuggestDetail(BaseModel):
    """Full TMDB detail for one suggested title (card click → detail modal)."""
    ok: bool = True
    id: int
    media_type: str                  # "movie" | "tv"
    title: str = ""
    year: Optional[int] = None
    overview: str = ""
    genres: List[str] = Field(default_factory=list)
    runtime: int = 0
    cert: str = ""
    cast: List[str] = Field(default_factory=list)
    director: str = ""
    tmdb_score: float = 0.0
    vote_count: int = 0
    poster: str = ""
    backdrop: str = ""
    imdb_id: str = ""
    imdb_rating: float = 0.0


@router.get("/suggest/detail/{tmdb_id}", response_model=SuggestDetail)
def suggest_detail(tmdb_id: int, media_type: str = "movie") -> SuggestDetail:
    """Return full TMDB metadata + IMDb rating for one title (on-demand, cached).

    Powers the card-click detail modal (IMDb rating + synopsis). Fetches fresh
    from TMDB on demand so the grid's /api/suggest stays light (it would
    otherwise need one IMDb lookup per result).
    """
    from services.tmdb import TMDBService

    cfg = get_config()
    tmdb = TMDBService(config=cfg)

    try:
        if media_type == "tv":
            details = tmdb.get_show_details(tmdb_id)
        else:
            details = tmdb.get_movie_details(tmdb_id)
    except Exception as e:
        return SuggestDetail(ok=False, id=tmdb_id, media_type=media_type, title=_err_title(e))

    if not details:
        return SuggestDetail(ok=False, id=tmdb_id, media_type=media_type)

    imdb_id = details.get("imdb_id", "") or ""
    imdb_rating = 0.0
    if imdb_id and imdb_id.startswith("tt"):
        try:
            imdb_rating = float(tmdb.get_imdb_rating(imdb_id) or 0)
        except Exception:
            imdb_rating = 0.0

    return SuggestDetail(
        ok=True,
        id=tmdb_id,
        media_type=media_type,
        title=details.get("title") or details.get("name") or "",
        year=details.get("year") or None,
        overview=details.get("overview") or "",
        genres=details.get("genres") or [],
        runtime=int(details.get("runtime") or 0),
        cert=details.get("cert") or "",
        cast=details.get("cast") or [],
        director=details.get("director") or "",
        tmdb_score=float(details.get("tmdb_score") or 0),
        vote_count=int(details.get("vote_count") or 0),
        poster=details.get("poster") or "",
        backdrop=details.get("backdrop") or "",
        imdb_id=imdb_id,
        imdb_rating=imdb_rating,
    )


def _err_title(exc: Exception) -> str:
    return f"TMDB lookup failed: {exc}"


@router.post("/suggest", response_model=SuggestResponse)
def suggest(req: SuggestRequest) -> SuggestResponse:
    """Discover titles matching user-defined filters via TMDB."""
    cfg = get_config()
    count = max(1, min(50, req.count))

    # Build TMDB discover params
    tmdb_params = _build_tmdb_params(req)

    # Fetch from TMDB
    raw_results = _fetch_tmdb(cfg, tmdb_params, req.media_type, count)

    # Deduplicate by TMDB ID
    seen_ids = set()
    deduped = []
    for item in raw_results:
        tid = item.get("id")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            deduped.append(item)

    # Check watchlist/library membership
    watchlist_ids = _get_watchlist_ids()
    library_titles = _get_library_titles()

    # Build results
    results = []
    for item in deduped:
        media_type = _detect_type(item)
        year = _extract_year(item, media_type)
        genres = _extract_genres(item)

        # Check library by title+year
        title_lower = (item.get("title") or item.get("name") or "").lower().strip()
        in_library = (title_lower, year) in library_titles or (title_lower, None) in library_titles

        # Skip items already in library (user already owns them)
        if in_library:
            continue

        results.append(SuggestResult(
            tmdb_id=item.get("id", 0),
            title=item.get("title") or item.get("name") or "",
            year=year,
            media_type=media_type,
            tmdb_score=item.get("vote_average", 0.0),
            vote_count=item.get("vote_count", 0),
            genres=genres,
            overview=item.get("overview", ""),
            poster=_build_poster_url(item.get("poster_path")),
            backdrop=_build_poster_url(item.get("backdrop_path"), size="w1280"),
            in_watchlist=f"tmdb:{item.get('id')}" in watchlist_ids,
            in_library=in_library,
        ))

    # Interleave movies and TV for balanced display
    movies = [r for r in results if r.media_type == "movie"]
    tvs = [r for r in results if r.media_type == "tv"]
    interleaved = []
    mi, ti = 0, 0
    while mi < len(movies) or ti < len(tvs):
        if mi < len(movies):
            interleaved.append(movies[mi]); mi += 1
        if ti < len(tvs):
            interleaved.append(tvs[ti]); ti += 1

    return SuggestResponse(
        results=interleaved[:count],
        total=len(results),
        filters={
            "media_type": req.media_type,
            "genres": req.genres,
            "year_from": req.year_from,
            "year_to": req.year_to,
            "min_rating": req.min_rating,
            "sort_by": req.sort_by,
        },
        genres_available=ALL_GENRE_NAMES,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_tmdb_params(req: SuggestRequest) -> dict:
    """Convert user filters into TMDB discover API params."""
    params = {
        "sort_by": req.sort_by,
        "page": 1,
        "include_adult": "false",
    }

    # Rating filter
    if req.min_rating > 0:
        params["vote_average.gte"] = req.min_rating

    # Year range
    if req.year_from:
        params["primary_release_date.gte"] = f"{req.year_from}-01-01"
    if req.year_to:
        params["primary_release_date.lte"] = f"{req.year_to}-12-31"

    # Genre filter (map names → TMDB IDs)
    genre_ids = []
    for g in req.genres:
        gid = MOVIE_GENRE_IDS.get(g) or TV_GENRE_IDS.get(g)
        if gid:
            genre_ids.append(str(gid))
    if genre_ids:
        params["with_genres"] = ",".join(genre_ids)

    return params


def _fetch_tmdb(cfg, params: dict, media_type: str, count: int) -> list:
    """Fetch from TMDB discover for movies, TV, or both."""
    from services.tmdb import TMDBService
    tmdb = TMDBService(config=cfg)

    results = []
    endpoints = []
    if media_type == "movie":
        endpoints = ["discover/movie"]
    elif media_type == "tv":
        endpoints = ["discover/tv"]
    else:
        endpoints = ["discover/movie", "discover/tv"]

    for endpoint in endpoints:
        try:
            # Clone params and fix for the specific endpoint
            ep_params = dict(params)

            # TV uses first_air_date, not primary_release_date
            if endpoint == "discover/tv":
                for old_key in ("primary_release_date.gte", "primary_release_date.lte"):
                    if old_key in ep_params:
                        new_key = old_key.replace("primary_release_date", "first_air_date")
                        ep_params[new_key] = ep_params.pop(old_key)

                # TV genre IDs are different — remap by name similarity
                if "with_genres" in ep_params:
                    genre_names = [g.strip() for g in ep_params["with_genres"].split(",")]
                    tv_ids = []
                    for gid_str in genre_names:
                        gid = int(gid_str)
                        name = MOVIE_GENRES.get(gid, "")
                        tv_gid = TV_GENRE_IDS.get(name)
                        if not tv_gid and name:
                            for tv_name, tv_id in TV_GENRE_IDS.items():
                                if name.lower() in tv_name.lower():
                                    tv_gid = tv_id
                                    break
                        tv_ids.append(str(tv_gid) if tv_gid else gid_str)
                    ep_params["with_genres"] = ",".join(tv_ids)

            data = tmdb._request(endpoint, ep_params)
            items = (data or {}).get("results", [])[:count]

            # Map genre IDs to names
            names = tmdb.genre_names()
            for item in items:
                ids = item.get("genre_ids") or []
                if ids and names:
                    item["genres"] = [names.get(int(i), str(i)) for i in ids]

            results.extend(items)
        except Exception as e:
            logger.warning("suggest: TMDB fetch failed for %s: %s", endpoint, e)

    return results


def _detect_type(item: dict) -> str:
    """Detect if item is movie or TV from TMDB response shape."""
    if "first_air_date" in item or "name" in item:
        return "tv"
    return "movie"


def _extract_year(item: dict, media_type: str) -> Optional[int]:
    """Extract release year from TMDB item."""
    date_str = item.get("release_date") or item.get("first_air_date") or ""
    if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
        return int(date_str[:4])
    return None


def _extract_genres(item: dict) -> List[str]:
    """Extract genre names from TMDB item."""
    return [str(g) for g in (item.get("genres") or [])]


def _build_poster_url(path: Optional[str], size: str = "w500") -> str:
    """Build full poster URL from TMDB path."""
    if not path:
        return ""
    return f"https://image.tmdb.org/t/p/{size}{path}"


def _get_watchlist_ids() -> set:
    """Get set of tmdb IDs currently in the watchlist."""
    try:
        from services.watchlist import WatchlistService
        wl = WatchlistService()
        data = wl.load()
        ids = set()
        for e in (data.pending or []) + (data.recommended or []):
            if e.tmdbId:
                ids.add(f"tmdb:{e.tmdbId}")
            if e.imdbId:
                ids.add(f"imdb:{e.imdbId}")
        return ids
    except Exception:
        return set()


def _get_library_ids() -> set:
    """Get set of tmdb IDs currently in Plex library.

    Plex GUIDs are internal (plex://...) so we can't extract TMDB IDs directly.
    Instead, we return an empty set and rely on title+year matching in the
    caller. The library check is done via a separate function.
    """
    return set()


def _get_library_titles() -> set:
    """Get normalized (title_lower, year) tuples from Plex library for dedup."""
    try:
        from services.plex import PlexService
        from config.settings import get_config
        cfg = get_config()
        if not cfg.PLEX_URL or not cfg.PLEX_TOKEN:
            return set()

        plex = PlexService(config=cfg)
        titles = set()

        for m in plex.get_all_movies():
            t = (m.title or "").lower().strip()
            y = m.year or 0
            if t:
                titles.add((t, y))
                titles.add((t, None))  # year-agnostic

        for s in plex.get_all_shows():
            t = (s.title or "").lower().strip()
            y = s.year or 0
            if t:
                titles.add((t, y))
                titles.add((t, None))

        return titles
    except Exception as e:
        logger.warning("suggest: failed to get library titles: %s", e)
        return set()
