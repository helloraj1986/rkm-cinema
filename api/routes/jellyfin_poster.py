"""Jellyfin poster proxy endpoint — serves artwork without leaking the token."""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response
from config.settings import get_config
from services.library import JellyfinLibraryProvider

router = APIRouter()


@router.get("/jellyfin/poster")
def jellyfin_poster(id: str = Query(default=""), width: int = Query(default=500, ge=16, le=2000)):
    """Proxy a Jellyfin item's primary image so the browser can render it.

    Keeps the Jellyfin token/credential server-side: the browser only ever hits
    this same-origin /api route.
    """
    cfg = get_config()
    if not id:
        return Response(status_code=404)
    try:
        result = JellyfinLibraryProvider(config=cfg).get_poster(id, width)
    except Exception:
        result = None
    if not result:
        return Response(status_code=404)
    return Response(content=result["content"], media_type=result["content_type"])