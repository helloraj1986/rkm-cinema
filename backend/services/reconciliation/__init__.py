"""Reconciliation package (spec §13 Phase 7).

The reconciler is the canonical fact-gathering + snapshot layer. Given a media
identity / an element of the watchlist it gathers facts from the external
systems (LibraryService, *arr services, qBittorrent) and emits a single
:class:`MediaSnapshot` via the pure ``domain.status.resolve_status`` resolver.

API routes consume the snapshot as the canonical object and never re-derive
the state machine themselves.
"""
from services.reconciliation.reconciler import (
    Reconciler,
    ReconcileResult,
    snapshot_to_status_result,
)

__all__ = ["Reconciler", "ReconcileResult", "snapshot_to_status_result"]