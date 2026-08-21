"""Domain enums — canonical vocabulary for media types and lifecycle states."""
from __future__ import annotations

import enum


class MediaType(str, enum.Enum):
    """Whether a title is a movie or a TV series."""

    MOVIE = "movie"
    TV = "tv"

    @classmethod
    def from_request(cls, value: str | None) -> "MediaType | None":
        """Parse a raw API/frontend type string (case-insensitive)."""
        if not value:
            return None
        v = str(value).strip().lower()
        if v in ("movie", "film", "radarr"):
            return cls.MOVIE
        if v in ("tv", "series", "show", "sonarr"):
            return cls.TV
        return None

    @property
    def arr_service(self) -> str:
        """The *arr service that manages this media type."""
        return "sonarr" if self is MediaType.TV else "radarr"


class MediaStatus(str, enum.Enum):
    """Application-level lifecycle state of a watchlist entry.

    A title can only ever be in one of these states. The canonical resolver in
    ``domain.status`` derives ``MediaStatus`` from the external
    (Plex/*arr/qBittorrent) facts — it is the one source of truth. ``ERROR`` and
    ``AMBIGUOUS`` are the spec §12 recommended statuses; they are declared now
    (reserved) and produced by the resolver in later phases.
    """

    NOT_ADDED = "not_added"
    REQUESTED = "requested"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    AVAILABLE = "available"
    RECOMMENDED = "recommended"
    ERROR = "error"
    AMBIGUOUS = "ambiguous"


class DownloadResultState(str, enum.Enum):
    """Outcome of an add/download attempt (service-level)."""

    REQUESTED = "requested"          # added to *arr, download queued
    ALREADY_EXISTS = "already_exists"
    UNAVAILABLE = "unavailable"      # looked up but could not be added
    AMBIGUOUS = "ambiguous"          # multiple matches, needs user choice
