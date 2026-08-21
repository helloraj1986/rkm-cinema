"""Tests for error handling when services are unavailable.

Uses injectable config/http (DI) so tests never touch the real LAN.
"""
import pytest
from unittest.mock import Mock
import urllib.error
import socket

from core.exceptions import ServiceUnavailableError, ConfigurationError
from core.http_client import HTTPError, NetworkError
from services import RadarrService, SonarrService, PlexService
from config.settings import Config


def make_radarr(http):
    c = Mock()
    c.RADARR_URL = "http://radarr.test:7878"
    c.RADARR_API_KEY = "key"
    return RadarrService(config=c, http=http)


def make_sonarr(http):
    c = Mock()
    c.SONARR_URL = "http://sonarr.test:8989"
    c.SONARR_API_KEY = "key"
    return SonarrService(config=c, http=http)


def make_plex(http):
    c = Mock()
    c.PLEX_URL = "http://plex.test:32400"
    c.PLEX_TOKEN = "token"
    return PlexService(config=c, http=http)


class TestErrorHandling:
    """Test error handling for unavailable services."""

    def test_radarr_unavailable_raises_service_error(self):
        """Radarr connection failure: health_check degrades to False; get_movies raises."""
        http = Mock()
        http.get.side_effect = NetworkError("http://radarr.test", "Connection refused")
        radarr = make_radarr(http)
        # health_check is a probe: returns False, does not crash the app.
        assert radarr.health_check() is False
        with pytest.raises(ServiceUnavailableError) as exc_info:
            radarr.get_movies()
        assert "radarr" in str(exc_info.value).lower()
        assert "connection refused" in str(exc_info.value).lower()

    def test_sonarr_unavailable_raises_service_error(self):
        """Sonarr connection failure: health_check degrades; get_series raises."""
        http = Mock()
        http.get.side_effect = NetworkError("http://sonarr.test", "Connection refused")
        sonarr = make_sonarr(http)
        assert sonarr.health_check() is False
        with pytest.raises(ServiceUnavailableError) as exc_info:
            sonarr.get_series()
        assert "sonarr" in str(exc_info.value).lower()

    def test_plex_unavailable_raises_service_error(self):
        """Plex connection failure: health_check degrades; get_library_counts not crash."""
        http = Mock()
        http.get.side_effect = NetworkError("http://plex.test", "Connection refused")
        plex = make_plex(http)
        assert plex.health_check() is False

    def test_missing_config_raises_validation_error(self):
        """Missing required config should be detected."""
        cfg = Config()
        cfg.RADARR_API_KEY = ""
        cfg.SONARR_API_KEY = ""
        cfg.PLEX_TOKEN = ""
        missing = cfg.validate_required()
        assert "RADARR_API_KEY" in missing
        assert "SONARR_API_KEY" in missing
        assert "PLEX_TOKEN" in missing

    def test_radarr_timeout_handled(self):
        """Radarr timeout should be handled gracefully."""
        http = Mock()
        http.get.side_effect = NetworkError("http://radarr.test", "timed out")
        radarr = make_radarr(http)
        with pytest.raises(ServiceUnavailableError) as exc_info:
            radarr.get_movies()
        assert "timeout" in str(exc_info.value).lower() or "timed out" in str(exc_info.value).lower()

    def test_radarr_http_500_handled(self):
        """Radarr HTTP 500 should be handled gracefully."""
        http = Mock()
        http.get.side_effect = HTTPError(500, "http://radarr.test/api/v3/movie", "Server Error")
        radarr = make_radarr(http)
        with pytest.raises(ServiceUnavailableError) as exc_info:
            radarr.get_movies()
        assert "500" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
