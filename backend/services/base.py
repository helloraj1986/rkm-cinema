"""Base service class with common patterns.

Services are designed for dependency injection: ``config`` and ``http`` are
injectable at construction so unit tests can pass fakes without ever touching
the real LAN. When omitted they default to the process-wide singletons, which
is what the running app uses.
"""
from __future__ import annotations

import logging
from abc import ABC
from typing import Optional

from config.settings import Config, get_config
from core.http_client import HTTPClient, get_http_client, HTTPError, NetworkError
from core.exceptions import ServiceUnavailableError


class BaseService(ABC):
    """Base class for all external service integrations."""

    def __init__(self, service_name: str, *, config: Optional[Config] = None,
                 http: Optional[HTTPClient] = None):
        self.service_name = service_name
        self.config = config if config is not None else get_config()
        self.http = http if http is not None else get_http_client()
        self.logger = logging.getLogger(f"rkm.{service_name}")

    def _handle_http_error(self, operation: str, error: Exception) -> None:
        """Convert HTTP errors to service exceptions."""
        if isinstance(error, HTTPError):
            raise ServiceUnavailableError(
                self.service_name,
                f"{operation} failed: HTTP {error.status_code}",
                status_code=error.status_code
            ) from error
        elif isinstance(error, NetworkError):
            raise ServiceUnavailableError(
                self.service_name,
                f"{operation} failed: network error - {error.reason}"
            ) from error
        else:
            raise ServiceUnavailableError(
                self.service_name,
                f"{operation} failed: {error}"
            ) from error

    def _radarr_headers(self) -> dict:
        return {"X-Api-Key": self.config.RADARR_API_KEY}

    def _sonarr_headers(self) -> dict:
        return {"X-Api-Key": self.config.SONARR_API_KEY}

    def _plex_params(self) -> dict:
        return {"X-Plex-Token": self.config.PLEX_TOKEN}

    def health_check(self) -> bool:
        """Override in subclass."""
        raise NotImplementedError
