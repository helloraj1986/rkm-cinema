"""Download endpoint - initiates Radarr/Sonarr download with robust routing.

Thin route: validates the request, delegates to DownloadService (which owns the
movie/tv resolver and cross-service fallback), and returns a typed response.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

from api.models import DownloadRequest, DownloadResponse
from domain.enums import DownloadResultState
from services.download import DownloadService

router = APIRouter()
logger = logging.getLogger("rkm.api.download")


@router.post("/download", response_model=DownloadResponse)
def download(req: DownloadRequest):
    """Add movie/series to Radarr or Sonarr via the download service."""
    result = DownloadService().download(
        imdb_id=req.imdbId,
        tmdb_id=req.tmdbId,
        requested_type=(req.type or ""),
        quality_profile_id=req.qualityProfileId,
        title=req.title,
        year=req.year,
    )

    if not result.success:
        status = 502
        if result.state is DownloadResultState.AMBIGUOUS:
            status = 404
        elif "not configured" in result.message.lower():
            status = 503
        raise HTTPException(status_code=status, detail=result.message)

    return DownloadResponse(
        ok=True,
        state=result.state.value,
        message=result.message,
        service=result.media_type.arr_service,
    )
