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


class NotFoundError(RKMError):
    """Resource not found."""
    def __init__(self, resource: str, identifier: str):
        super().__init__(f"{resource} not found: {identifier}")
        self.resource = resource
        self.identifier = identifier


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