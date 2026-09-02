"""Watchlist resource endpoint (spec §17 Phase 10).

Thin route: reconciles every pending + recommended entry in one batch via the
canonical Reconciler and renders each as a complete §18 MediaResponse resource.
No business rules here.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from api.models import WatchlistResponse
from api.routes.media import _snapshot_to_media
from services.reconciliation import Reconciler

router = APIRouter()
logger = logging.getLogger("rkm.api.watchlist")


@router.get("/watchlist", response_model=WatchlistResponse)
def get_watchlist():
    """Every watchlist entry as a backend-derived §18 resource."""
    result = Reconciler().compute_cached()
    entries = [_snapshot_to_media(snap) for snap in result.snapshots.values()]
    return WatchlistResponse(entries=entries, indexerIssue=result.indexer_issue)