"""Jellyfin item-detail endpoint — Plex-style preplay metadata.

One additive same-origin route that unlocks the ~90% of a Plex preplay screen
Jellyfin already stores (docs/PLEX_UI_PLAN.md §1): synopsis, genres, ratings,
studios, cast/credits, backdrop facts and play state. Mirrors
``jellyfin_poster.py`` / ``jellyfin_tracks.py``: the Jellyfin credential stays
server-side; the browser only ever sees the normalised detail payload.

- ``GET /api/jellyfin/detail?id=`` — driven by the ``LibraryService``
  ``item_detail`` capability (first provider able to answer wins); returns the
  player-ready preplay shape (or 404/503 when there is nothing to show).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from config.settings import get_config
from services.library.factory import build_library_service

router = APIRouter()
logger = logging.getLogger("rkm.api.jellyfin_detail")


@router.get("/jellyfin/detail")
def jellyfin_detail(id: str = Query(default="")):
    """Rich preplay metadata for one library item (movie/series/episode)."""
    cfg = get_config()
    if not (cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY):
        raise HTTPException(status_code=503, detail="Jellyfin not configured")
    if not id:
        raise HTTPException(status_code=404, detail="Missing item id")
    service = build_library_service(cfg)
    try:
        detail = service.item_detail(id) if service is not None else None
    except Exception as e:  # noqa: BLE001 - a provider failure is a soft miss
        logger.warning("jellyfin detail(%s) failed: %s", id, e)
        detail = None
    if not detail:
        raise HTTPException(status_code=404, detail="No detail for item")
    return JSONResponse(detail)
