"""Media status service — backwards-compatible shim over the Phase 7 reconciler.

Phase 7 moved all fact-gathering + snapshot emission into
:class:`services.reconciliation.Reconciler`. This module now keeps the legacy
``MediaStatusService`` / ``StatusSnapshot`` names so existing imports and
pre-Phase-7 tests stay green (spec §43 — no parallel implementation): it wraps
a :class:`Reconciler` and re-derives the legacy ``StatusResult`` shape from the
canonical :class:`MediaSnapshot` via ``snapshot_to_status_result``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from domain.status import StatusResult
from services.reconciliation import Reconciler, snapshot_to_status_result

logger = logging.getLogger("rkm.media_status")

__all__ = ["MediaStatusService", "StatusSnapshot"]


@dataclass
class StatusSnapshot:
    """All per-entry status results plus the current indexer issue.

    Retained as a legacy wrapper around the reconciler's canonical snapshots.
    """

    results: dict[str, StatusResult]
    indexer_issue: Optional[str] = None


class MediaStatusService:
    """Legacy facade over :class:`Reconciler` (Phase 7 canonical source).

    ``compute_statuses()`` reconciles every watchlist entry through the
    reconciler and maps each :class:`MediaSnapshot` back to the legacy
    ``StatusResult`` shape. The reconciler's own ``compute()`` yields the
    canonical :class:`MediaSnapshot` objects routes should consume going forward.
    """

    def __init__(self, *, watchlist=None, library=None, plex=None, radarr=None,
                 sonarr=None, qbit=None, config=None):
        self._reconciler = Reconciler(
            watchlist=watchlist, library=library, plex=plex, radarr=radarr,
            sonarr=sonarr, qbit=qbit, config=config)
        # Expose the library seam for backward-compat introspection (the legacy
        # direct PlexService member is gone).
        self._library = self._reconciler._library
        # A thin facade only — every consumer funnels through the reconciler.
        logger.debug("MediaStatusService delegating to Reconciler")

    def compute_statuses(self) -> "StatusSnapshot":
        """Return a StatusSnapshot for every pending/recommended entry."""
        result = self._reconciler.compute()
        results = {
            imdb_id: snapshot_to_status_result(snap)
            for imdb_id, snap in result.snapshots.items()
        }
        return StatusSnapshot(results=results, indexer_issue=result.indexer_issue)