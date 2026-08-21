"""Tests for movie → Radarr routing."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from services.radarr import RadarrService, RadarrMovie, AddResult


class TestRadarrRouting:
    """Test movie download routing to Radarr."""

    def setup_method(self):
        self.radarr = RadarrService()

    @patch("services.radarr.get_config")
    @patch("services.radarr.get_http_client")
    def test_add_movie_success(self, mock_http, mock_config):
        """Test successful movie addition to Radarr."""
        mock_config.return_value.RADARR_URL = "http://test:7878"
        mock_config.return_value.RADARR_API_KEY = "key"
        mock_config.return_value.RADARR_QUALITY_PROFILE_ID = None

        # Mock responses
        mock_http.return_value.get.side_effect = [
            [{"id": 1, "name": "HD-1080p", "items": []}],  # quality profiles
            [{"path": "/movies"}],  # root folders
        ]
        mock_http.return_value.post.return_value = {
            "id": 999, "tmdbId": 603, "title": "The Matrix", "year": 1999,
            "hasFile": False, "monitored": True, "qualityProfileId": 1
        }

        # Mock lookup
        with patch.object(self.radarr, 'lookup_movie') as mock_lookup:
            mock_lookup.return_value = RadarrMovie(
                id=0, tmdbId=603, title="The Matrix", year=1999,
                hasFile=False, monitored=True, qualityProfileId=0
            )
            with patch.object(self.radarr, 'find_movie_by_tmdb') as mock_find:
                mock_find.return_value = None
                result = self.radarr.add_movie("tt0133093")

        assert result.success is True
        assert result.state == "requested"
        assert result.movie is not None
        assert result.movie.title == "The Matrix"

    @patch("services.radarr.get_config")
    @patch("services.radarr.get_http_client")
    def test_add_movie_duplicate(self, mock_http, mock_config):
        """Test duplicate movie handling."""
        mock_config.return_value.RADARR_URL = "http://test:7878"
        mock_config.return_value.RADARR_API_KEY = "key"

        with patch.object(self.radarr, 'lookup_movie') as mock_lookup:
            mock_lookup.return_value = RadarrMovie(
                id=0, tmdbId=603, title="The Matrix", year=1999,
                hasFile=False, monitored=True, qualityProfileId=0
            )
            with patch.object(self.radarr, 'find_movie_by_tmdb') as mock_find:
                mock_find.return_value = RadarrMovie(
                    id=123, tmdbId=603, title="The Matrix", year=1999,
                    hasFile=True, monitored=True, qualityProfileId=1
                )
                result = self.radarr.add_movie("tt0133093")

        assert result.success is True
        assert result.state == "requested"
        assert "already in Radarr" in result.message

    @patch("services.radarr.get_config")
    @patch("services.radarr.get_http_client")
    def test_add_movie_no_match(self, mock_http, mock_config):
        """Test movie not found in Radarr."""
        mock_config.return_value.RADARR_URL = "http://test:7878"
        mock_config.return_value.RADARR_API_KEY = "key"

        with patch.object(self.radarr, 'lookup_movie') as mock_lookup:
            mock_lookup.return_value = None
            result = self.radarr.add_movie("tt9999999")

        assert result.success is False
        assert result.state == "unavailable"
        assert "No Radarr match" in result.message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])