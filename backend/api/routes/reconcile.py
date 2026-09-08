"""Reconcile command endpoint (spec §17 Phase 10).

``POST /api/reconcile`` triggers a single batch reconcile of the watchlist and
returns the freshly-derived resources. The heavy lifting lives in the
:class:`Reconciler`; this route just runs it and renders the result.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from api.models import ReconcileResponse
from api.routes.media import _snapshot_to_media
from services.reconciliation import Reconciler

router = APIRouter()
logger = logging.getLogger("rkm.api.reconcile")


@router.post("/reconcile", response_model=ReconcileResponse)
def reconcile_now():
    """Re-derive every watchlist entry's status/capabilities/watch in one pass."""
    result = Reconciler().compute()
    entries = [_snapshot_to_media(snap) for snap in result.snapshots.values()]
    return ReconcileResponse(
        ok=True,
        entries=entries,
        indexerIssue=result.indexer_issue,
    )