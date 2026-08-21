"""Status state machine — canonical derivation of MediaStatus.

**Compatibility shim (spec §43 — no parallel implementations).** The canonical
types and the resolver now live in ``domain.status``. This module re-exports
them unchanged so existing imports (e.g. ``services/media_status.py``) keep
working during the refactor. New code should import from ``domain.status``.

Resolution order (single source of truth in ``domain.status.resolve_status``):

    Plex has media            -> AVAILABLE          (with Plex/Emby watch links)
    else *arr has file        -> DOWNLOADED
    else qBittorrent/*arr q   -> DOWNLOADING
    else *arr record exists   -> REQUESTED
    else                      -> NOT_ADDED

Library availability always wins.
"""
from __future__ import annotations

from domain.status import (  # noqa: F401  (re-exported for backward compatibility)
    WatchLinks,
    StatusFacts,
    StatusResult,
    Capabilities,
    MediaSnapshot,
    resolve_status,
    allowed_transitions,
)

__all__ = [
    "WatchLinks",
    "StatusFacts",
    "StatusResult",
    "Capabilities",
    "MediaSnapshot",
    "resolve_status",
    "allowed_transitions",
]