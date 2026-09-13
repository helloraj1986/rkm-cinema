"""Reconcile command endpoint (spec §17 Phase 10).

``POST /api/reconcile`` triggers a single batch reconcile of the watchlist and
returns the freshly-derived resources. The heavy lifting lives in the
:class:`Reconciler`; this route just runs it and renders the result.

**Administrators only (Phase E, his decision 2026-09-13).** It is a whole-library write pass
against the database and the *arr services, run on the caller's behalf — administrative IN
EFFECT, even though it was only session-gated. The scheduler runs the same work through
``jobs.reconcile``, which never uses an HTTP session, so nothing internal depends on this route
staying open.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from api.models import ReconcileResponse
from api.routes.media import _snapshot_to_media
from api.session import SessionContext, require_admin_session
from services.reconciliation import Reconciler

router = APIRouter()
logger = logging.getLogger("rkm.api.reconcile")


@router.post("/reconcile", response_model=ReconcileResponse)
def reconcile_now(session: SessionContext = Depends(require_admin_session)):
    """Re-derive every watchlist entry's status/capabilities/watch in one pass."""
    result = Reconciler().compute()
    entries = [_snapshot_to_media(snap) for snap in result.snapshots.values()]
    return ReconcileResponse(
        ok=True,
        entries=entries,
        indexerIssue=result.indexer_issue,
    )