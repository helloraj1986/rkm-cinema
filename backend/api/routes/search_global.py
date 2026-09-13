"""Global search endpoint — library-first, TMDB discovery when the library has no exact answer.

GLOBAL_SEARCH_PLAN: ONE intelligent search for the top-bar overlay. Answers
"do I own this?" first: owned Movie/Series/Episode rows (with playback facts +
a state-aware primary action), People/Genre/BoxSet intent hints, actor
drill-down titles, and a TMDB DISCOVER group of titles the library does not
have. Duplicate TMDB rows are suppressed by tmdb-id / exact title.

⚠ The DISCOVER group is NOT conditional on "the library found something"
(2026-09-13). It used to be gated on `strong_match`, i.e. on any owned title
that CONTAINED the query — so searching "sholay" while owning "Sholay — Special
Ops" never reached TMDB at all and the real film was invisible. The gate now
asks the only question that matters: does the library have EXACTLY this title
(`EXACT_TITLE_SCORE`)?

Additive endpoint (ADR-0001): the legacy ``/api/search`` is untouched.
"""
import logging

from fastapi import APIRouter, Query

from api.models import (
    SearchGlobalResponse, GlobalOwnedRow, GlobalHint, GlobalDiscoveryRow,
)
from config.settings import get_config
from core.cache import TTLCache
from services.global_search import (
    EXACT_TITLE_SCORE, is_duplicate_discovery, next_episode_facts, normalize_title,
    owned_state, owned_strong_match,
)
from services.library import build_library_service
from services.tmdb import TMDBService

router = APIRouter()
logger = logging.getLogger("rkm.api.search_global")

#: How many Series rows get the episodes enrich (resume/next-episode target).
SHOW_ENRICH_LIMIT = 3

#: How many external candidates the overlay shows (§ his report: "top 5–6").
DISCOVERY_LIMIT = 6

#: ⚠ The external half is cached, the LOCAL half never is. Metadata search is stable for minutes and
#: the user retypes the same query as they refine it; playback state (progress, next episode) is stale
#: in seconds, so caching the merged response would show him an old resume position. The client's
#: `staleTime` stays 15s for the same reason.
SEARCH_CACHE_TTL = 300
_search_cache: TTLCache[list] = TTLCache(default_ttl=SEARCH_CACHE_TTL)


def _tmdb_search_cached(cfg, query: str) -> list:
    """``TMDBService.search_multi`` for *query*, cached per normalised query for ``SEARCH_CACHE_TTL``.

    ``search_multi`` itself stays uncached on purpose (the legacy /api/search must read fresh), so the
    cache lives here — on the ONE path where the same query is asked repeatedly as he types. A
    transport failure raises (and is NOT cached), which the caller degrades on explicitly.
    """
    key = f"search_multi:{normalize_title(query)}"
    hit = _search_cache.get(key)
    if hit is not None:
        return hit
    rows = list(TMDBService(config=cfg).search_multi(query))
    return _search_cache.set(key, rows) or rows


def _to_owned(row: dict, next_ep: dict | None = None) -> dict:
    """Response-row shape for a raw provider row (drops internal keys)."""
    out = dict(row)
    out.pop("provider_ids", None)
    runtime = int(out.get("runtime") or 0)
    pos = int(out.get("playback_position") or 0)
    out["state"] = owned_state(row, next_ep)
    out["remaining"] = max(0, runtime - pos) if runtime > 0 else None
    if next_ep:
        out["next_episode"] = next_ep
    return out


@router.get("/search/global", response_model=SearchGlobalResponse)
def search_global(q: str = Query(default="", min_length=1)):
    """Library-first global search: owned rows + hints + deduped TMDB discovery."""
    cfg = get_config()
    query = q.strip()
    payload = {
        "query": query,
        "provider": None,
        "tmdb_key": cfg.has_tmdb(),
        "strong_match": False,
        "items": [],
        "people": [],
        "person_titles": [],
        "genres": [],
        "collections": [],
        "discovery": [],
    }
    owned_raw: list[dict] = []  # keeps provider_ids for TMDB dedupe

    service = build_library_service(cfg)
    if service is not None:
        try:
            found = service.search(query, limit=12) or {}
        except Exception as e:  # noqa: BLE001
            logger.warning("global search local failed for %r: %s", query, e)
            found = {}

        payload["provider"] = found.get("provider")
        enriched = 0
        for row in found.get("items") or []:
            next_ep = None
            if row.get("kind") == "show" and enriched < SHOW_ENRICH_LIMIT:
                enriched += 1
                try:
                    eps = (service.episodes(row["id"]) or {}).get("episodes") or []
                    next_ep = next_episode_facts(eps)
                except Exception as e:  # noqa: BLE001
                    logger.warning("episode enrich failed for %s: %s", row.get("id"), e)
            owned_raw.append(row)
            payload["items"].append(GlobalOwnedRow(**_to_owned(row, next_ep)))

        for p in found.get("people") or []:
            payload["people"].append(GlobalHint(id=str(p.get("id", "")), name=str(p.get("name", "")), kind="person"))
        for g in found.get("genres") or []:
            payload["genres"].append(GlobalHint(id=str(g.get("id", "")), name=str(g.get("name", "")), kind="genre"))
        for c in found.get("collections") or []:
            payload["collections"].append(GlobalHint(
                id=str(c.get("id", "")), name=str(c.get("name", "")), kind="collection", year=c.get("year")))

        # Actor/director drill-down: titles featuring the top Person hint.
        people = found.get("people") or []
        if people:
            try:
                person_rows = (service.items_by_person(str(people[0].get("id", "")), limit=6) or {}).get("items") or []
                for row in person_rows:
                    owned_raw.append(row)
                    payload["person_titles"].append(GlobalOwnedRow(**_to_owned(row)))
            except Exception as e:  # noqa: BLE001
                logger.warning("person titles failed for %r: %s", query, e)

        # ⚠ EXACT title only: a longer owned title that merely CONTAINS the query is a different
        # work and must not suppress the external search (see EXACT_TITLE_SCORE).
        payload["strong_match"] = owned_strong_match(owned_raw, query) >= EXACT_TITLE_SCORE

    # External discovery runs whenever the library has no EXACT answer — and never carries a row the
    # library already owns (tmdb-id, or an exact title+year).
    if cfg.has_tmdb() and not payload["strong_match"]:
        # Watchlist membership so the overlay can offer Download (not Add) for
        # titles already on the watchlist — matches the Suggest card contract.
        watchlist_tmdb: set[int] = set()
        try:
            from services.watchlist import WatchlistService
            data = WatchlistService().load()
            for e in data.pending + data.recommended:
                try:
                    if getattr(e, "tmdbId", None):
                        watchlist_tmdb.add(int(e.tmdbId))
                except (TypeError, ValueError):
                    continue
        except Exception as e:  # noqa: BLE001
            logger.warning("watchlist membership lookup failed: %s", e)
        try:
            for res in _tmdb_search_cached(cfg, query)[:DISCOVERY_LIMIT]:
                mtype = res.get("media_type")
                if mtype not in ("movie", "tv"):
                    continue
                raw_year = (res.get("release_date") or res.get("first_air_date") or "")[:4]
                candidate = {
                    "tmdb_id": int(res.get("id") or 0),
                    "media_type": mtype,
                    "title": str(res.get("title") or res.get("name") or ""),
                    "year": int(raw_year) if raw_year.isdigit() else None,
                    "poster": ("https://image.tmdb.org/t/p/w342" + res["poster_path"])
                              if res.get("poster_path") else "",
                    "overview": str(res.get("overview") or ""),
                    "in_watchlist": int(res.get("id") or 0) in watchlist_tmdb,
                }
                if candidate["tmdb_id"] and not is_duplicate_discovery(candidate, owned_raw):
                    payload["discovery"].append(GlobalDiscoveryRow(**candidate))
        except Exception as e:  # noqa: BLE001
            # Degrade to library-only, but never silently (api log shows why).
            logger.error("Live TMDB global search failed for %r: %s", query, e)

    return SearchGlobalResponse(**payload)
