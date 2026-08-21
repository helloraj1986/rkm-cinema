"""Status endpoint - per-title download state computation.

Thin route: calls MediaStatusService and converts the domain StatusResult
into the API response model. All status logic lives in the domain state
machine via services/media_status.py.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter

from api.models import StatusEntry, StatusResponse
from services.media_status import MediaStatusService

router = APIRouter()
logger = logging.getLogger("rkm.api.status")


@router.get("/status", response_model=StatusResponse)
def get_status():
    """Per-title download state computed by the domain state machine."""
    svc = MediaStatusService()
    snapshot = svc.compute_statuses()

    statuses = {}
    for imdb, r in snapshot.results.items():
        statuses[imdb] = StatusEntry(
            state=r.state.value,
            service=r.service,
            detail=r.detail,
            progress=r.progress,
            speed=r.speed,
            eta=r.eta,
            qbitState=r.qbitState,
            qbitName=r.qbitName,
            plexKey=r.plexKey,
            plexUrl=r.plexUrl,
            embyUrl=r.embyUrl,
        )

    return StatusResponse(statuses=statuses, indexerIssue=snapshot.indexer_issue)
