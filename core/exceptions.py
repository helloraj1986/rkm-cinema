"""Custom exception hierarchy for RKM Watchlist."""
from typing import Optional


class RKMError(Exception):
    """Base exception for all RKM Watchlist errors."""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.details = details or {}


class ConfigurationError(RKMError):
    """Missing or invalid configuration."""
    pass


class ServiceUnavailableError(RKMError):
    """External service is unreachable or returned an error."""
    def __init__(self, service: str, message: str, status_code: Optional[int] = None):
        super().__init__(f"{service}: {message}")
        self.service = service
        self.status_code = status_code


# --- Phase 14: typed per-service errors (spec §28). One failed service must
# never destroy the whole response — callers catch the specific type and keep
# other providers working.
class PlexUnavailableError(ServiceUnavailableError):
    def __init__(self, message: str = "Plex is unreachable", status_code: Optional[int] = None):
        super().__init__("Plex", message, status_code)

class EmbyUnavailableError(ServiceUnavailableError):
    def __init__(self, message: str = "Emby is unreachable", status_code: Optional[int] = None):
        super().__init__("Emby", message, status_code)

class RadarrUnavailableError(ServiceUnavailableError):
    def __init__(self, message: str = "Radarr is unreachable", status_code: Optional[int] = None):
        super().__init__("Radarr", message, status_code)

class SonarrUnavailableError(ServiceUnavailableError):
    def __init__(self, message: str = "Sonarr is unreachable", status_code: Optional[int] = None):
        super().__init__("Sonarr", message, status_code)

class QBittorrentUnavailableError(ServiceUnavailableError):
    def __init__(self, message: str = "qBittorrent is unreachable", status_code: Optional[int] = None):
        super().__init__("qBittorrent", message, status_code)

class TMDBUnavailableError(ServiceUnavailableError):
    def __init__(self, message: str = "TMDB is unreachable", status_code: Optional[int] = None):
        super().__init__("TMDB", message, status_code)


class AmbiguousMediaError(RKMError):
    """Multiple media matched a request; an explicit choice is required."""
    def __init__(self, candidates: list, message: str = "Multiple matches — pick one"):
        super().__init__(message)
        self.candidates = candidates


class NotFoundError(RKMError):
    """Resource not found."""
    def __init__(self, resource: str, identifier: str):
        super().__init__(f"{resource} not found: {identifier}")
        self.resource = resource
        self.identifier = identifier


class MediaNotFoundError(NotFoundError):
    """A requested media item could not be resolved to an external provider."""
    pass


class DuplicateError(RKMError):
    """Duplicate resource detected."""
    def __init__(self, resource: str, identifier: str):
        super().__init__(f"{resource} already exists: {identifier}")
        self.resource = resource
        self.identifier = identifier


class ValidationError(RKMError):
    """Input validation failed."""
    def __init__(self, field: str, value: any, reason: str):
        super().__init__(f"Validation failed for {field}={value}: {reason}")
        self.field = field
        self.value = value
        self.reason = reason


class MetadataError(RKMError):
    """Metadata enrichment or validation failed."""
    pass


class TrailerError(MetadataError):
    """Trailer validation or enrichment failed."""
    pass


class WatchlistError(RKMError):
    """Watchlist operation failed."""
    pass


class DownloadError(RKMError):
    """Download initiation or tracking failed."""
    def __init__(self, service: str, imdb_id: str, message: str):
        super().__init__(f"Download failed ({service}, {imdb_id}): {message}")
        self.service = service
        self.imdb_id = imdb_id


class StateTransitionError(RKMError):
    """Invalid state transition attempted."""
    def __init__(self, from_state: str, to_state: str, imdb_id: str):
        super().__init__(f"Invalid state transition {from_state} -> {to_state} for {imdb_id}")
        self.from_state = from_state
        self.to_state = to_state
        self.imdb_id = imdb_id