"""Per-viewer search preferences — SEARCH_IMPROVEMENT_PLAN Phase 5, Phase 6.

Search has two switches, and both are per PROFILE:

* **personalization** (Phase 5) — bias discovery toward the genres this viewer watches. Some people
  want a neutral search regardless of their history, and the plan is explicit that this is a
  legitimate choice rather than something to talk them out of;
* **the embedding fallback** (Phase 6) — search the library by MEANING when the string matcher found
  nothing (plan `docs/SEMANTIC_SEARCH_PLAN.md`). It is bounded by construction (it only runs when the
  string matcher failed), and it is switchable because it is the one part of search that costs CPU
  rather than a dictionary lookup.

⚠ These routes are session-scoped like every other app route (§11), and they read the PROFILE from
the session — never from the request body. A client that could name the profile it was writing to
would let one household member switch another's preference off.
"""
import logging

from fastapi import APIRouter, HTTPException

from api.models import SearchPrefsResponse, SearchPrefsUpdate
from api.session import current_session
from services.search_prefs import SearchPrefsStore

router = APIRouter()
logger = logging.getLogger("rkm.api.search_prefs")


def _viewer() -> tuple[str, str]:
    """``(profile_id, profile_name)`` for the request, from the session only."""
    ctx = current_session()
    if ctx is None:
        return "", ""
    return ctx.profile_id(), ctx.profile_name()


def _state(profile_id: str, profile_name: str, store: SearchPrefsStore) -> SearchPrefsResponse:
    """The viewer's CURRENT stored state — one reader, so GET and POST cannot disagree."""
    return SearchPrefsResponse(personalized=store.personalized(profile_id),
                               semantic=store.semantic(profile_id),
                               profile_name=profile_name)


@router.get("/search/prefs", response_model=SearchPrefsResponse)
def get_search_prefs():
    """This viewer's search preferences (the defaults when they have never chosen)."""
    profile_id, profile_name = _viewer()
    return _state(profile_id, profile_name, SearchPrefsStore())


@router.post("/search/prefs", response_model=SearchPrefsResponse)
def set_search_prefs(body: SearchPrefsUpdate):
    """Change this profile's search preferences — one of them, or both.

    ⚠ **A field the request leaves out is NOT changed** (`SearchPrefsUpdate`'s own rule). The body
    names values, never the profile; the response is always the SERVER's stored state, so the UI
    positions its switches from what is stored rather than from what it sent.
    """
    profile_id, profile_name = _viewer()
    if not profile_id:
        # The router rides SESSION_SCOPED, so this is only reachable without a
        # published identity in a direct call (a test, or a route that forgot the
        # dependency). Refuse rather than write a preference that belongs to nobody
        # and could never be read back.
        raise HTTPException(status_code=409, detail="No profile in effect for this request.")
    if body.personalized is None and body.semantic is None:
        # ⚠ Named rather than ignored: a request that changes nothing is far more likely to be a
        # client bug (a body built with the wrong key names) than an intent, and answering 200 would
        # leave that bug invisible.
        raise HTTPException(status_code=400,
                            detail="Send at least one preference to change: personalized, semantic.")
    store = SearchPrefsStore()
    try:
        if body.personalized is not None:
            store.set_personalized(profile_id, body.personalized)
        if body.semantic is not None:
            store.set_semantic(profile_id, body.semantic)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    logger.info("search prefs for %s: personalized=%s semantic=%s", profile_id,
                body.personalized, body.semantic)
    return _state(profile_id, profile_name, store)
