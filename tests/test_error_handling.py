"""Tests for error handling when services are unavailable."""
import pytest
from unittest.mock import Mock, patch
from core.exceptions import ServiceUnavailableError, ConfigurationError
from services import RadarrService, SonarrService, PlexService
from config.settings import Config


class TestErrorHandling:
    """Test error handling for unavailable services."""

    @patch("services.radarr.get_config")
    @patch("services.radarr.get_http_client")
    def test_radarr_unavailable_raises_service_error(self, mock_http, mock_config):
        """Radarr health check failure should raise ServiceUnavailableError."""
        mock_config.return_value.RADARR_URL = "http://test:7878"
        mock_config.return_value.RADARR_API_KEY = "key"

        import urllib.error
        mock_http.return_value.get.side_effect = urllib.error.URLError("Connection refused")

        radarr = RadarrService()
        with pytest.raises(ServiceUnavailableError) as exc_info:
            radarr.health_check()

        assert "radarr" in str(exc_info.value).lower()
        assert "connection refused" in str(exc_info.value).lower()

    @patch("services.sonarr.get_config")
    @patch("services.sonarr.get_http_client")
    def test_sonarr_unavailable_raises_service_error(self, mock_http, mock_config):
        """Sonarr health check failure should raise ServiceUnavailableError."""
        mock_config.return_value.SONARR_URL = "http://test:8989"
        mock_config.return_value.SONARR_API_KEY = "key"

        import urllib.error
        mock_http.return_value.get.side_effect = urllib.error.URLError("Connection refused")

        sonarr = SonarrService()
        with pytest.raises(ServiceUnavailableError) as exc_info:
            sonarr.health_check()

        assert "sonarr" in str(exc_info.value).lower()

    @patch("services.plex.get_config")
    @patch("services.plex.get_http_client")
    def test_plex_unavailable_raises_service_error(self, mock_http, mock_config):
        """Plex health check failure should raise ServiceUnavailableError."""
        mock_config.return_value.PLEX_URL = "http://test:32400"
        mock_config.return_value.PLEX_TOKEN = "token"

        import urllib.error
        mock_http.return_value.get.side_effect = urllib.error.URLError("Connection refused")

        plex = PlexService()
        with pytest.raises(ServiceUnavailableError) as exc_info:
            plex.health_check()

        assert "plex" in str(exc_info.value).lower()

    def test_missing_config_raises_validation_error(self):
        """Missing required config should be detected."""
        cfg = Config()
        # Manually clear required fields
        cfg.RADARR_API_KEY = ""
        cfg.SONARR_API_KEY = ""
        cfg.PLEX_TOKEN = ""

        missing = cfg.validate_required()
        assert "RADARR_API_KEY" in missing
        assert "SONARR_API_KEY" in missing
        assert "PLEX_TOKEN" in missing

    @patch("services.radarr.get_config")
    @patch("services.radarr.get_http_client")
    def test_radarr_timeout_handled(self, mock_http, mock_config):
        """Radarr timeout should be handled gracefully."""
        mock_config.return_value.RADARR_URL = "http://test:7878"
        mock_config.return_value.RADARR_API_KEY = "key"

        import urllib.error
        import socket
        mock_http.return_value.get.side_effect = socket.timeout("Request timed out")

        radarr = RadarrService()
        with pytest.raises(ServiceUnavailableError) as exc_info:
            radarr.get_movies()

        assert "timeout" in str(exc_info.value).lower() or "timed out" in str(exc_info.value).lower()

    @patch("services.radarr.get_config")
    @patch("services.radarr.get_http_client")
    def test_radarr_http_500_handled(self, mock_http, mock_config):
        """Radarr HTTP 500 should be handled gracefully."""
        mock_config.return_value.RADARR_URL = "http://test:7878"
        mock_config.return_value.RADARR_API_KEY = "key"

        import urllib.error
        # Create a mock HTTPError
        class MockFP:
            def read(self):
                return b'{"error": "Internal Server Error"}'
            def close(self):
                pass

        error = urllib.error.HTTPError(
            url="http://test:7878/api/v3/movie",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=MockFP()
        )
        mock_http.return_value.get.side_effect = error

        radarr = RadarrService()
        with pytest.raises(ServiceUnavailableError) as exc_info:
            radarr.get_movies()

        assert "500" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])