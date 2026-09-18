"""Per-viewer search preferences — SEARCH_IMPROVEMENT_PLAN Phase 5.

Search personalization (biasing discovery rows toward the genres this viewer
actually watches) is ON by default and switchable per PROFILE. Some people want a
neutral search regardless of their history, and the plan is explicit that this is
a legitimate choice rather than something to talk them out of.

⚠ These two routes are session-scoped like every other app route (§11), and they
read the PROFILE from the session — never from the request body. A client that
could name the profile it was writing to would let one household member switch
another's preference off.
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


@router.get("/search/prefs", response_model=SearchPrefsResponse)
def get_search_prefs():
    """This viewer's search preferences (the default when they have never chosen)."""
    profile_id, profile_name = _viewer()
    store = SearchPrefsStore()
    return SearchPrefsResponse(personalized=store.personalized(profile_id),
                               profile_name=profile_name)


@router.post("/search/prefs", response_model=SearchPrefsResponse)
def set_search_prefs(body: SearchPrefsUpdate):
    """Switch taste-biased ranking on or off for this profile."""
    profile_id, profile_name = _viewer()
    if not profile_id:
        # The router rides SESSION_SCOPED, so this is only reachable without a
        # published identity in a direct call (a test, or a route that forgot the
        # dependency). Refuse rather than write a preference that belongs to nobody
        # and could never be read back.
        raise HTTPException(status_code=409, detail="No profile in effect for this request.")
    store = SearchPrefsStore()
    try:
        row = store.set_personalized(profile_id, body.personalized)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    logger.info("search personalization for %s set to %s", profile_id, row.get("personalized"))
    return SearchPrefsResponse(personalized=bool(row.get("personalized")),
                               profile_name=profile_name)
