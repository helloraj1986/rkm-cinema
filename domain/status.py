"""Canonical status resolver (spec §12 Phase 6, §13 Phase 7).

This module is the SINGLE source of truth for status derivation. It is **pure** —
it operates on :class:`StatusFacts` and never performs HTTP calls. The
resolver's job is to turn a bag of externally-gathered facts into a
:class:`StatusResult` (what the API/UI render today) and, for the Phase 7
reconciler, a :class:`MediaSnapshot` carrying ``status`` + ``capabilities`` +
``watch_links``.

Resolution priority (spec §12) — library availability always wins:

    in_library            -> AVAILABLE   (with watch links)
    else downloading      -> DOWNLOADING
    else acquisition req  -> REQUESTED
    else downloaded       -> DOWNLOADED
    else                  -> NOT_REQUESTED

``domain.state_machine`` is kept strictly as a backwards-compatible import
shim that re-exports everything from here per spec §43 (no parallel
implementations). Import from this module going forward.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from domain.enums import MediaType, MediaStatus

__all__ = [
    "WatchLinks",
    "StatusFacts",
    "StatusResult",
    "Capabilities",
    "MediaSnapshot",
    "resolve_status",
    "allowed_transitions",
]


@dataclass
class WatchLinks:
    """Watch capabilities for an available item. URLs are backend-derived."""

    plex_available: bool = False
    plex_url: str = ""
    plex_key: str = ""            # numeric Plex ratingKey for the item
    emby_available: bool = False
    emby_url: str = ""


@dataclass
class StatusFacts:
    """External facts needed to resolve a single title's status.

    Every field is optional and "unknown" by default so callers only supply
    what they actually know. ``None``/empty means "no evidence".
    """

    media_type: MediaType = MediaType.MOVIE
    in_plex: bool = False
    plex_links: WatchLinks = field(default_factory=WatchLinks)
    arr_has_file: bool = False
    arr_queue_active: bool = False
    arr_record_exists: bool = False
    qbit_active: bool = False       # downloading in qBittorrent
    qbit_done: bool = False         # fully downloaded in qBittorrent
    arr_queue_percent: Optional[int] = None
    qbit_percent: Optional[int] = None
    qbit_speed: Optional[float] = None
    qbit_eta: Optional[int] = None
    qbit_state: str = ""
    qbit_name: str = ""
    indexer_issue: Optional[str] = None

    @property
    def detail(self) -> str:
        """Human-readable detail for the resolved state."""
        if self.in_plex:
            return "Available in Plex"
        if self.qbit_done:
            return "Downloaded — awaiting import"
        if self.qbit_active:
            return "Active in qBittorrent"
        if self.arr_queue_active:
            return "Downloading"
        if self.arr_has_file:
            return "In library"
        if self.arr_record_exists:
            if self.indexer_issue:
                return "Waiting — search indexers down"
            return "Requested"
        return ""


@dataclass
class StatusResult:
    """Resolved status plus every action/URL the UI may need."""

    state: MediaStatus
    service: str = ""                     # the *arr service responsible
    detail: str = ""
    plexUrl: str = ""
    embyUrl: str = ""
    plexKey: Optional[str] = None
    progress: Optional[int] = None
    speed: Optional[float] = None
    eta: Optional[int] = None
    qbitState: str = ""
    qbitName: str = ""


@dataclass
class Capabilities:
    """Which user actions are available for a resolved status (spec §13)."""

    can_download: bool = False
    can_watch: bool = False

    @classmethod
    def from_status(cls, status: MediaStatus) -> "Capabilities":
        return cls(
            can_download=status in (MediaStatus.NOT_ADDED, MediaStatus.REQUESTED, MediaStatus.AMBIGUOUS),
            can_watch=status is MediaStatus.AVAILABLE,
        )


@dataclass
class MediaSnapshot:
    """Canonical per-item object consumed by API routes (spec §13 Phase 7).

    One item -> one status + capabilities + watch links. Routes render this,
    never re-derive the state machine.
    """

    media_id: str = ""
    status: MediaStatus = MediaStatus.NOT_ADDED
    capabilities: Capabilities = field(default_factory=Capabilities)
    watch_links: dict = field(default_factory=dict)
    detail: str = ""
    service: str = ""

    @classmethod
    def from_result(cls, result: StatusResult, *, media_id: str = "",
                    watch_links: Optional[dict] = None) -> "MediaSnapshot":
        return cls(
            media_id=media_id,
            status=result.state,
            capabilities=Capabilities.from_status(result.state),
            watch_links=watch_links or {},
            detail=result.detail,
            service=result.service,
        )


def resolve_status(facts: StatusFacts) -> StatusResult:
    """Derive the canonical MediaStatus and watch capabilities from facts.

    This is the single authoritative implementation of the status resolver.
    It is pure: no HTTP, no side effects. Library availability always wins
    (spec §12) — a watch-link failure is a *capability* problem and must never
    flip an available title to NOT_REQUESTED (spec §10).
    """
    mt = facts.media_type
    service = mt.arr_service

    # 1. Plex is the source of truth for availability.
    if facts.in_plex:
        return StatusResult(
            state=MediaStatus.AVAILABLE,
            service=service,
            detail="Available in Plex",
            plexUrl=facts.plex_links.plex_url,
            embyUrl=facts.plex_links.emby_url,
            plexKey=facts.plex_links.plex_key or None,
        )

    # 2. *arr reports a file on disk (not yet surfaced in Plex).
    if facts.arr_has_file:
        return StatusResult(
            state=MediaStatus.DOWNLOADED,
            service=service,
            detail="In library",
            plexUrl=facts.plex_links.plex_url,
            embyUrl=facts.plex_links.emby_url,
        )

    # 3. Down / downloading.
    if facts.qbit_active:
        return StatusResult(
            state=MediaStatus.DOWNLOADING,
            service=service,
            detail="Active in qBittorrent",
            progress=facts.qbit_percent,
            speed=facts.qbit_speed,
            eta=facts.qbit_eta,
            qbitState=facts.qbit_state,
            qbitName=facts.qbit_name,
        )
    if facts.qbit_done:
        return StatusResult(
            state=MediaStatus.DOWNLOADED,
            service=service,
            detail="Downloaded — awaiting import",
            progress=100,
            speed=facts.qbit_speed,
            eta=facts.qbit_eta,
            qbitState=facts.qbit_state,
            qbitName=facts.qbit_name,
        )
    if facts.arr_queue_active:
        return StatusResult(
            state=MediaStatus.DOWNLOADING,
            service=service,
            progress=facts.arr_queue_percent,
        )

    # 4. Requested (record exists in *arr).
    if facts.arr_record_exists:
        detail = "Waiting — search indexers down" if facts.indexer_issue else "Requested"
        return StatusResult(
            state=MediaStatus.REQUESTED,
            service=service,
            detail=detail,
        )

    # 5. Nothing anywhere.
    return StatusResult(state=MediaStatus.NOT_ADDED, service=service)


def allowed_transitions(current: MediaStatus, target: MediaStatus) -> bool:
    """Explicitly encode which lifecycle transitions are permitted.

    Kept deliberately conservative: at minimum every forward transition is
    allowed, plus any transition TO available (Plex is authoritative).
    """
    order = [
        MediaStatus.NOT_ADDED,
        MediaStatus.REQUESTED,
        MediaStatus.DOWNLOADING,
        MediaStatus.DOWNLOADED,
        MediaStatus.AVAILABLE,
        MediaStatus.RECOMMENDED,
    ]
    if current == target:
        return True
    if target == MediaStatus.AVAILABLE:
        return True
    try:
        return order.index(target) >= order.index(current)
    except ValueError:
        return True