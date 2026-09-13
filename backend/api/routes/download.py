"""Download endpoint - initiates Radarr/Sonarr download with robust routing.

Thin route: validates the request, delegates to DownloadService (which owns the
movie/tv resolver and cross-service fallback), and returns a typed response.

**Administrators only (Phase E, his decision 2026-09-13).** This is the legacy ``/download``
command path — a *arr action that adds and starts a download on the server's own indexers and
quality profiles. The UI asks for a title through ``POST /api/media/{id}/request`` instead (that
one stays member-facing: requesting a title is the point of the app), so nothing a member can
click reaches this route. ``require_admin_session`` is strict even while ``RKM_AUTH_REQUIRED`` is
false — see ``api/session.py``.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException

from api.models import DownloadRequest, DownloadResponse
from api.session import SessionContext, require_admin_session
from domain.enums import DownloadResultState
from services.download import DownloadService

router = APIRouter()
logger = logging.getLogger("rkm.api.download")


@router.post("/download", response_model=DownloadResponse)
def download(req: DownloadRequest,
             session: SessionContext = Depends(require_admin_session)):
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
