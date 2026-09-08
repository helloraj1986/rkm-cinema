"""Watchlist resource endpoint (spec §17 Phase 10).

Thin route: reconciles every pending + recommended entry in one batch via the
canonical Reconciler and renders each as a complete §18 MediaResponse resource.
No business rules here.

Also serves the rich-entry parity source (`GET /watchlist/entries`), a live
replacement for the static dashboard-data.json the legacy SPA used.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from api.models import WatchlistEntriesResponse, WatchlistResponse
from api.routes.media import _snapshot_to_media
from services.dashboard import to_rich_entry
from services.reconciliation import Reconciler
from services.watchlist import WatchlistService

router = APIRouter()
logger = logging.getLogger("rkm.api.watchlist")


@router.get("/watchlist", response_model=WatchlistResponse)
def get_watchlist():
    """Every watchlist entry as a backend-derived §18 resource."""
    result = Reconciler().compute_cached()
    entries = [_snapshot_to_media(snap) for snap in result.snapshots.values()]
    return WatchlistResponse(entries=entries, indexerIssue=result.indexer_issue)


@router.get("/watchlist/entries", response_model=WatchlistEntriesResponse)
def get_watchlist_entries():
    """Every watchlist entry in the rich display shape (legacy-parity source).

    Reads the authoritative store through the same seam as the dashboard
    generator and maps with the shared ``services.dashboard.to_rich_entry`` —
    one mapper for the API and the static rebuild.
    """
    data = WatchlistService().load()
    entries = [to_rich_entry(e) for e in (data.pending or []) + (data.recommended or [])]
    return WatchlistEntriesResponse(updated=data.updated, entries=entries)