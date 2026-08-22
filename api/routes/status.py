"""Status endpoint - per-title download state computation.

Thin route: drives the Phase 7 :class:`Reconciler` and renders the canonical
:class:`MediaSnapshot` (spec §13) into the API response model. All status
logic lives in the reconciler + ``domain.status`` resolver; the route never
re-derives the state machine.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter

from api.models import StatusEntry, StatusResponse
from services.reconciliation import Reconciler

router = APIRouter()
logger = logging.getLogger("rkm.api.status")


@router.get("/status", response_model=StatusResponse)
def get_status():
    """Per-title download state computed by the reconciler's snapshots."""
    result = Reconciler().compute()

    statuses = {}
    for imdb, snap in result.snapshots.items():
        plex = (snap.watch_links or {}).get("plex") or {}
        emby = (snap.watch_links or {}).get("emby") or {}
        statuses[imdb] = StatusEntry(
            state=snap.status.value,
            service=snap.service,
            detail=snap.detail,
            progress=snap.progress,
            speed=snap.speed,
            eta=snap.eta,
            qbitState=snap.qbitState,
            qbitName=snap.qbitName,
            plexKey=snap.plexKey,
            plexUrl=plex.get("url") or "",
            embyUrl=emby.get("url") or "",
        )

    return StatusResponse(statuses=statuses, indexerIssue=result.indexer_issue)