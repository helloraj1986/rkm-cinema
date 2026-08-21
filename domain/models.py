"""Domain models — plain business objects shared across services and routes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from domain.enums import DownloadResultState, MediaStatus, MediaType


@dataclass
class DownloadResult:
    """Outcome of a download/add attempt, typed and predictable.

    ``pick`` carries the matched external IDs a caller may need to display or
    disambiguate; on an ambiguous result it is a list of candidate matches.
    """

    success: bool
    state: DownloadResultState
    message: str
    media_type: MediaType = MediaType.MOVIE
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    tvdb_id: Optional[int] = None
    title: str = ""
    year: Optional[int] = None
    candidates: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> MediaStatus:
        """Map a download outcome to an app status."""
        if self.state is DownloadResultState.REQUESTED:
            return MediaStatus.REQUESTED
        if self.state is DownloadResultState.ALREADY_EXISTS:
            return MediaStatus.AVAILABLE
        return MediaStatus.NOT_ADDED
