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

⚠ SEARCH_IMPROVEMENT_PLAN Phase 2: that last gate is now GONE TOO. `strong_match`
is still computed and returned (it is part of the frozen contract and it honestly
answers "you already have this"), but it no longer decides whether the external
half runs — because a gate is exactly what made search read as "two separate
searches stapled together". Owning *The Matrix* used to hide *The Matrix
Resurrections* and *The Animatrix* completely.

Discovery now always runs when TMDB is configured, and `rank_all()` interleaves
every source on ONE continuous scale with a score-based ownership PREFERENCE
(`OWNED_BONUS`) rather than a cutoff. The response carries the result as
`results`; the older per-source arrays (`items`, `discovery`, `people`, …) are
unchanged, so a client that predates this keeps working byte-for-byte.

⚠ PERFORMANCE NOTE — the plan's "fire the TMDB call without blocking on it":
this route is SYNCHRONOUS (FastAPI runs it in a worker thread), so there is no
honest way to attach a result that arrives after the response is built. What is
implemented instead is the cache that makes the round-trip disappear for exactly
the case the plan cared about — the user retyping the same query as they refine
it (`_tmdb_search_cached`, keyed on the normalised query). Making it genuinely
non-blocking needs an async route and a background task; that is NOT done here
and should not be assumed.

Additive endpoint (ADR-0001): the legacy ``/api/search`` is untouched.
"""
import logging

from fastapi import APIRouter, Query

from api.models import (
    SearchGlobalResponse, GlobalOwnedRow, GlobalHint, GlobalDiscoveryRow, UnifiedResult,
)
from config.settings import get_config
from core.cache import TTLCache
from services.global_search import (
    EXACT_TITLE_SCORE, is_duplicate_discovery, next_episode_facts, normalize_title,
    owned_state, owned_strong_match,
)
from services.library import build_library_service
from services.search.ranking import rank_all
from services.tmdb import TMDBService
from services.watchlist import WatchlistService

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


def _watchlist_rows() -> list[dict]:
    """Every acquisition-queue entry, as plain dicts, for ranking.

    ⚠ Loaded on EVERY search (it is a small local JSON read). It answers two
    questions the response needs — "is this candidate already requested?" for the
    discovery rows, and "does the queue itself match?" for the ranked list — and a
    second, lazily-loaded copy is how those two answers would drift apart.

    ⚠ ``WatchlistService`` is imported at MODULE level (not inside this function)
    so a test can patch it. A function-local import is invisible to
    ``patch.object(module, "WatchlistService")``, which made the route's tests read
    the developer's real ``watchlist.json`` while appearing to stub it — every
    route assertion was quietly running against live data.
    """
    try:
        data = WatchlistService().load()
    except Exception as e:  # noqa: BLE001
        logger.warning("watchlist lookup failed: %s", e)
        return []
    return [e.to_dict() for e in (data.pending + data.recommended)]


def _tmdb_ids(rows: list[dict]) -> set[int]:
    out: set[int] = set()
    for e in rows:
        try:
            if e.get("tmdbId"):
                out.add(int(e["tmdbId"]))
        except (TypeError, ValueError):
            continue
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
        "results": [],
    }
    owned_raw: list[dict] = []  # keeps provider_ids for TMDB dedupe
    hints: dict[str, list[dict]] = {"person": [], "genre": [], "collection": []}
    watchlist_raw = _watchlist_rows()

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
            hints["person"].append({"id": str(p.get("id", "")), "name": str(p.get("name", "")), "kind": "person"})
            payload["people"].append(GlobalHint(id=str(p.get("id", "")), name=str(p.get("name", "")), kind="person"))
        for g in found.get("genres") or []:
            hints["genre"].append({"id": str(g.get("id", "")), "name": str(g.get("name", "")), "kind": "genre"})
            payload["genres"].append(GlobalHint(id=str(g.get("id", "")), name=str(g.get("name", "")), kind="genre"))
        for c in found.get("collections") or []:
            hint = {"id": str(c.get("id", "")), "name": str(c.get("name", "")), "kind": "collection", "year": c.get("year")}
            hints["collection"].append(hint)
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

        # ⚠ EXACT title only, and now INFORMATIONAL: a longer owned title that merely CONTAINS the
        # query is a different work (see EXACT_TITLE_SCORE) — but it no longer suppresses anything.
        payload["strong_match"] = owned_strong_match(owned_raw, query) >= EXACT_TITLE_SCORE

    # ⚠ NO GATE on strong_match (Phase 2). The external half runs whenever TMDB is configured; the
    # only thing that keeps a row out is dedupe — it must never offer to acquire what he already has.
    if cfg.has_tmdb():
        watchlist_tmdb = _tmdb_ids(watchlist_raw)
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

    payload["results"] = _ranked(query, owned_raw, watchlist_raw, payload, hints)
    return SearchGlobalResponse(**payload)


def _ranked(query: str, owned_raw: list[dict], watchlist_raw: list[dict],
            payload: dict, hints: dict[str, list[dict]]) -> list[UnifiedResult]:
    """One ranked list across every source (SEARCH_IMPROVEMENT_PLAN Phase 2).

    ⚠ Discovery rows are passed as the MODELS already built for ``payload`` (so the
    ranked entry and the legacy array can never disagree about what was found) and
    converted back with ``model_dump()``. Dedupe therefore runs twice — once when
    the array is built, once inside ``rank_all`` — which is deliberate: the two
    have different inputs (the array is deduped against owned only, the ranked list
    also skips anything the queue already covers) and a single shared pass would
    have to lie about one of them.
    """
    try:
        ranked = rank_all(
            query,
            owned=owned_raw,
            watchlist=watchlist_raw,
            discovery=[d.model_dump() for d in payload["discovery"]],
            hints=hints,
        )
    except Exception as e:  # noqa: BLE001
        # ⚠ Ranking is additive: if it fails, the response still carries the
        # per-source arrays a pre-Phase-2 client reads. Never fail a search over it.
        logger.error("unified ranking failed for %r: %s", query, e)
        return []
    return [UnifiedResult(**row.to_dict()) for row in ranked]
