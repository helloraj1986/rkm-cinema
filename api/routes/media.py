"""Media resource endpoints (spec §17/§18 Phase 10).

Resource-oriented media API replacing the generic ``/download`` command path.
The route is thin: it delegates to the canonical reconciler (for the one-item
resource) and the idempotent ``request_media`` command (for requests). It never
re-derives status, capabilities, or watch links.

Endpoints
---------
- ``GET  /api/media/{media_id}``      -> one complete MediaResponse (§18)
- ``POST /api/media/{media_id}/request`` -> idempotent acquisition request (§15)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api.models import (
    AcquisitionModel,
    CapabilitiesModel,
    MediaResponse,
    RequestMediaResponse,
    WatchEntryModel,
)
from application.commands.request_media import request_media
from domain.enums import MediaType, RequestMediaState
from domain.status import MediaSnapshot
from services.reconciliation import Reconciler

router = APIRouter()
logger = logging.getLogger("rkm.api.media")


def _snapshot_to_media(snap: MediaSnapshot) -> MediaResponse:
    """Render a reconciler MediaSnapshot as the canonical §18 resource."""
    watch: dict[str, WatchEntryModel] = {}
    for provider, info in (snap.watch_links or {}).items():
        watch[provider] = WatchEntryModel(
            available=bool(info.get("available")),
            url=info.get("url"),
            error=info.get("error"),
        )
    acquisition = None
    if snap.service:
        acquisition = AcquisitionModel(provider=snap.service, status=snap.status.value)
    return MediaResponse(
        id=snap.media_id or "",
        title=snap.title,
        year=snap.year,
        type="tv" if snap.media_type is MediaType.TV else "movie",
        status=snap.status.value,
        capabilities=CapabilitiesModel(
            can_download=snap.capabilities.can_download,
            can_watch=snap.capabilities.can_watch,
        ),
        watch=watch,
        acquisition=acquisition,
        detail=snap.detail or None,
        progress=snap.progress,
    )


@router.get("/media/{media_id}", response_model=MediaResponse)
def get_media(media_id: str):
    """One complete, backend-derived resource for a canonical media_id."""
    snap = Reconciler().get_snapshot(media_id)
    return _snapshot_to_media(snap)


@router.post("/media/{media_id}/request", response_model=RequestMediaResponse)
def request_media_endpoint(media_id: str):
    """Idempotently add a canonical media_id to the right *arr backend.

    The canonical request path is ``request_media`` (application layer). This
    route only maps result states to typed HTTP responses.
    """
    result = request_media(media_id)

    # Idempotent good outcomes (AVAILABLE / ALREADY_REQUESTED / REQUESTED).
    if result.success:
        return RequestMediaResponse(
            ok=True,
            state=result.state.value,
            message=result.message,
            mediaId=result.media_id,
            service=result.service,
            candidates=result.candidates,
        )

    # Typed failure mapping (§15 vocabulary).
    state = result.state
    if state is RequestMediaState.NOT_CONFIGURED:
        raise HTTPException(status_code=503, detail=result.message)
    if state is RequestMediaState.PROVIDER_UNAVAILABLE:
        raise HTTPException(status_code=502, detail=result.message)
    if state is RequestMediaState.AMBIGUOUS:
        raise HTTPException(
            status_code=409,
            detail={
                "message": result.message,
                "candidates": result.candidates,
            },
        )
    # Unexpected -> 500.
    raise HTTPException(status_code=500, detail=result.message or "request failed")