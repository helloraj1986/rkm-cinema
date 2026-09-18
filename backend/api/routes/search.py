"""Search endpoint - watchlist + TMDB live search.

⚠ SEARCH_IMPROVEMENT_PLAN Phases 1–2 changed how the WATCHLIST half matches.

It used to build one lower-cased string out of six fields and ask
``query in hay``. That is a substring test with no notion of relevance: a hit in
``snippet`` counted exactly as much as a hit in ``title``, ``"the dark knght"``
found nothing at all, and the result order was whatever the watchlist file
happened to be in. It now goes through the shared scorer
(:mod:`services.search.scoring`) so it is typo-tolerant, weighted, and RANKED —
the same rules the library half uses, which is the point of having one scorer.

⚠ The TMDB half is deliberately NOT filtered by score. TMDB ran the search and
its own relevance is not our business to second-guess: a typed query like
``"tom hanks 90s"`` scores low against every title yet is exactly the kind of
search this endpoint should answer. Rows are ORDERED by our score, never dropped.
"""
import logging
from fastapi import APIRouter, Query
from api.models import SearchResponse, SearchResult
from config.settings import get_config
from services import WatchlistService
from services.search.query_parser import parse_query
from services.search.scoring import row_fields, score_item
from services.tmdb import TMDBService

router = APIRouter()
logger = logging.getLogger("rkm.api.search")

#: How many watchlist rows the response carries (unchanged from before).
WATCHLIST_LIMIT = 6

#: How many live TMDB rows the response carries (unchanged from before).
TMDB_LIMIT = 8

#: ⚠ Rows below this are DROPPED rather than ranked. It replaces the old
#: substring test's implicit "either it contained the query or it did not":
#: 0.2 keeps a real hit in any single field (a synopsis-only hit lands at 0.25)
#: while cutting the scores that only exist because one short token of a long
#: synopsis happened to appear. It is a NOISE floor, not a relevance bar.
MIN_WATCHLIST_SCORE = 0.2


def watchlist_fields(entry) -> dict:
    """The searchable surface of a watchlist entry, in one place.

    ⚠ ``category`` is deliberately included as a GENRE and not as a title: the
    old joined-string test let a hit on the rotation category ("Thriller") look
    exactly like a hit on the film's name.
    """
    row = entry.to_dict() if hasattr(entry, "to_dict") else dict(entry)
    fields = row_fields(row)
    fields["genre"] = [*(row.get("genres") or []), row.get("category") or ""]
    return fields


def _tmdb_candidate(result: dict) -> dict:
    """One live TMDB row, in the provider row shape the scorer understands."""
    raw_year = (result.get("release_date") or result.get("first_air_date") or "")[:4]
    return {
        "title": result.get("title") or result.get("name") or "",
        "year": int(raw_year) if raw_year.isdigit() else None,
        "media_type": result.get("media_type"),
        "tmdb_id": result.get("id"),
        "poster": ("https://image.tmdb.org/t/p/w342" + result["poster_path"])
                  if result.get("poster_path") else "",
        "overview": result.get("overview") or "",
        "vote_average": result.get("vote_average"),
    }


@router.get("/search", response_model=SearchResponse)
def search(q: str = Query(default="", min_length=1)):
    """Search the watchlist and TMDB, ranked by continuous relevance."""
    cfg = get_config()
    # ⚠ Parse BEFORE matching (Phase 3): "tom hanks movies 1994" is a person, a
    # type and a year — matched as one literal string it finds nothing, because
    # that string appears in no title anywhere.
    parsed = parse_query(q.strip())
    query = parsed.scoring_query

    wl = WatchlistService()
    data = wl.load()

    # ---- Local watchlist matches: SCORED and ranked (Phase 1/2), not substring-tested.
    scored_local = []
    for entry in data.pending + data.recommended:
        scored = score_item(query, watchlist_fields(entry), item_year=entry.year, item=entry,
                            query_year=parsed.year, query_year_range=parsed.year_range)
        if scored.score >= MIN_WATCHLIST_SCORE:
            scored_local.append(scored)
    scored_local.sort(key=lambda s: -s.score)

    local: list[SearchResult] = []
    for scored in scored_local[:WATCHLIST_LIMIT]:
        entry = scored.item
        local.append(SearchResult(
            title=entry.title, year=entry.year, type="tv" if entry.isSeries else "movie",
            imdbId=entry.imdbId, tmdbId=entry.tmdbId, poster=entry.poster or "",
            inWatchlist=True, director=entry.director, cast=(entry.cast or [])[:3],
            snippet=entry.snippet or "", score=scored.score,
            matchedFields=scored.matched_fields,
        ))

    # ---- Live TMDB search. Uses the shared TMDBService/HTTPClient path (RKM
    # User-Agent + Accept headers, retries) — the same path /api/suggest and
    # every other TMDB call uses. A hand-rolled raw urllib call here carried no
    # such headers and was rejected by TMDB's edge from the deployed container,
    # silently returning empty results (bare `except: pass`).
    live: list[SearchResult] = []
    live_key = cfg.has_tmdb()
    if live_key:
        try:
            scored_live = []
            for result in TMDBService(config=cfg).search_multi(
                    query, media_type=parsed.media_type)[:TMDB_LIMIT]:
                candidate = _tmdb_candidate(result)
                scored = score_item(query, row_fields(candidate), item_year=candidate["year"],
                                    query_year=parsed.year, query_year_range=parsed.year_range)
                scored_live.append((scored, candidate))
            # ⚠ Stable sort: TMDB's own order is the tie-break, so a row it ranked
            # first is never demoted by our scorer failing to see the match.
            scored_live.sort(key=lambda t: -t[0].score)
            for scored, candidate in scored_live:
                live.append(SearchResult(
                    title=candidate["title"], year=candidate["year"],
                    type=candidate["media_type"], imdbId="", tmdbId=candidate["tmdb_id"],
                    poster=candidate["poster"], snippet=candidate["overview"], inWatchlist=False,
                    voteAverage=candidate["vote_average"], director="", cast=[],
                    score=scored.score, matchedFields=scored.matched_fields,
                ))
        except Exception as e:
            # Degrade to watchlist-only (contract shape is unchanged) but never
            # silently: the api log should show why live search is empty.
            logger.error("Live TMDB search failed for %r: %s", query, e)

    return SearchResponse(
        watchlist=local, tmdb=live, tmdbKey=live_key,
        servicesDown=not (cfg.RADARR_API_KEY and cfg.SONARR_API_KEY)
    )
