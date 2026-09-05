"""Jellyfin poster proxy endpoint — serves artwork without leaking the token."""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response
from config.settings import get_config
from services.library.factory import build_library_service

router = APIRouter()


@router.get("/jellyfin/poster")
def jellyfin_poster(id: str = Query(default=""), width: int = Query(default=500, ge=16, le=2000)):
    """Proxy a Jellyfin item's primary image so the browser can render it.

    Keeps the Jellyfin token/credential server-side: the browser only ever hits
    this same-origin /api route. Phase 1: routed through the ``LibraryService``
    ``get_poster`` capability (first provider able to serve it wins).
    """
    cfg = get_config()
    if not id:
        return Response(status_code=404)
    service = build_library_service(cfg)
    try:
        result = service.get_poster(id, width) if service is not None else None
    except Exception:
        result = None
    if not result:
        return Response(status_code=404)
    return Response(content=result["content"], media_type=result["content_type"])