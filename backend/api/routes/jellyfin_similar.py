"""Jellyfin \"Because you watched\" — TMDB similar titles endpoint.

One additive same-origin route (docs/SIMILAR_TITLES_PLAN.md): given a Jellyfin
library item id, resolve its ``ProviderIds.Tmdb`` server-side, query TMDB's
similarity graph, and return compact display rows. The Jellyfin + TMDB keys
stay server-side; the browser only ever sees the normalised ``{similar:[…]}``
payload (poster/backdrop are public TMDB CDN URLs — no proxy needed).

- ``GET /api/jellyfin/similar?id=<item>&limit=10`` — driven by the
  ``LibraryService`` ``item_similar`` capability (first provider able to answer
  wins); 404 when the item can't be resolved to TMDB similarity (missing/not a
  movie or series/no TMDB id), 503 when Jellyfin isn't configured, mirroring
  the ``jellyfin_detail`` route's semantics.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from config.settings import get_config
from services.library.factory import build_library_service

router = APIRouter()
logger = logging.getLogger("rkm.api.jellyfin_similar")


@router.get("/jellyfin/similar")
def jellyfin_similar(id: str = Query(default=""), limit: int = Query(default=10, ge=1, le=30)):
    """\"Because you watched <title>\" rows for one library item (movie/series)."""
    cfg = get_config()
    if not (cfg.JELLYFIN_URL and cfg.JELLYFIN_API_KEY):
        raise HTTPException(status_code=503, detail="Jellyfin not configured")
    if not id:
        raise HTTPException(status_code=404, detail="Missing item id")
    service = build_library_service(cfg)
    try:
        similar = service.item_similar(id, limit=limit) if service is not None else None
    except Exception as e:  # noqa: BLE001 - a provider failure is a soft miss
        logger.warning("jellyfin similar(%s) failed: %s", id, e)
        similar = None
    if similar is None:
        raise HTTPException(status_code=404, detail="No similar titles for item")
    return JSONResponse({"similar": similar})
