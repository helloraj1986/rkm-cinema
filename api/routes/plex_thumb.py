"""Plex thumbnail proxy endpoint - exposes artwork without leaking the token."""
from __future__ import annotations

import logging
from fastapi import APIRouter, Query
from fastapi.responses import Response, JSONResponse
from config.settings import get_config
from services.library import PlexLibraryProvider

router = APIRouter()
logger = logging.getLogger("rkm.api.plex_thumb")


@router.get("/plex/thumb")
def plex_thumb(path: str = Query(default=""), width: int = Query(default=500, ge=16, le=2000)):
    """Proxy a Plex thumbnail so the browser can render it (token stays server-side)."""
    cfg = get_config()
    if not (cfg.PLEX_URL and cfg.PLEX_TOKEN) or not path:
        return Response(status_code=404)
    try:
        plex = PlexLibraryProvider(config=cfg)
        result = plex.get_thumb(path, width)
    except Exception:
        result = None
    if not result:
        return Response(status_code=404)
    return Response(content=result["content"], media_type=result["content_type"])
