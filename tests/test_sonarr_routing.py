"""Tests for TV series → Sonarr routing."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from services.sonarr import SonarrService, SonarrSeries, AddResult


class TestSonarrRouting:
    """Test TV series download routing to Sonarr."""

    def setup_method(self):
        self.sonarr = SonarrService()

    @patch("services.sonarr.get_config")
    @patch("services.sonarr.get_http_client")
    def test_add_series_success(self, mock_http, mock_config):
        """Test successful series addition to Sonarr."""
        mock_config.return_value.SONARR_URL = "http://test:8989"
        mock_config.return_value.SONARR_API_KEY = "key"
        mock_config.return_value.SONARR_QUALITY_PROFILE_ID = None

        mock_http.return_value.get.side_effect = [
            [{"id": 1, "name": "HD-1080p", "items": []}],  # quality profiles
            [{"id": 1, "name": "English", "path": "/tv"}],  # language profiles
            [{"path": "/tv"}],  # root folders
        ]
        mock_http.return_value.post.return_value = {
            "id": 999, "tvdbId": 81189, "title": "Breaking Bad", "year": 2008,
            "monitored": True, "qualityProfileId": 1, "languageProfileId": 1,
            "statistics": {"episodeFileCount": 0}
        }

        with patch.object(self.sonarr, 'lookup_series') as mock_lookup:
            mock_lookup.return_value = SonarrSeries(
                id=0, tvdbId=81189, title="Breaking Bad", year=2008,
                monitored=True, qualityProfileId=0, languageProfileId=0, statistics={}
            )
            with patch.object(self.sonarr, 'find_series_by_tvdb') as mock_find:
                mock_find.return_value = None
                result = self.sonarr.add_series("tt0903747")

        assert result.success is True
        assert result.state == "requested"
        assert result.series is not None
        assert result.series.title == "Breaking Bad"

    @patch("services.sonarr.get_config")
    @patch("services.sonarr.get_http_client")
    def test_add_series_duplicate(self, mock_http, mock_config):
        """Test duplicate series handling."""
        mock_config.return_value.SONARR_URL = "http://test:8989"
        mock_config.return_value.SONARR_API_KEY = "key"

        with patch.object(self.sonarr, 'lookup_series') as mock_lookup:
            mock_lookup.return_value = SonarrSeries(
                id=0, tvdbId=81189, title="Breaking Bad", year=2008,
                monitored=True, qualityProfileId=0, languageProfileId=0, statistics={}
            )
            with patch.object(self.sonarr, 'find_series_by_tvdb') as mock_find:
                mock_find.return_value = SonarrSeries(
                    id=123, tvdbId=81189, title="Breaking Bad", year=2008,
                    monitored=True, qualityProfileId=1, languageProfileId=1,
                    statistics={"episodeFileCount": 62}
                )
                result = self.sonarr.add_series("tt0903747")

        assert result.success is True
        assert result.state == "requested"
        assert "already in Sonarr" in result.message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])