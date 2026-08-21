"""Tests for download status detection."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from services import RadarrService, SonarrService, PlexService, WatchlistService
from services.watchlist import WatchlistEntry


class TestDownloadStatus:
    """Test download status computation."""

    def setup_method(self):
        self.wl = WatchlistService("/tmp/test_watchlist_status.json")
        import os
        if os.path.exists("/tmp/test_watchlist_status.json"):
            os.remove("/tmp/test_watchlist_status.json")

    def teardown_method(self):
        import os
        if os.path.exists("/tmp/test_watchlist_status.json"):
            os.remove("/tmp/test_watchlist_status.json")

    @patch("services.radarr.get_config")
    @patch("services.radarr.get_http_client")
    @patch("services.plex.get_config")
    @patch("services.plex.get_http_client")
    def test_status_available_when_radarr_hasfile_and_plex_has_it(self, mock_plex_http, mock_plex_config, mock_radarr_http, mock_radarr_config):
        """Status should be 'available' when Radarr hasFile AND Plex has it."""
        # Setup Radarr
        mock_radarr_config.return_value.RADARR_URL = "http://test:7878"
        mock_radarr_config.return_value.RADARR_API_KEY = "key"
        mock_radarr_http.return_value.get.side_effect = [
            [{"id": 1, "tmdbId": 603, "title": "The Matrix", "year": 1999, "hasFile": True, "monitored": True, "qualityProfileId": 1}],  # movies
            [],  # queue
        ]

        # Setup Plex
        mock_plex_config.return_value.PLEX_URL = "http://test:32400"
        mock_plex_config.return_value.PLEX_TOKEN = "token"
        mock_plex_http.return_value.get.side_effect = [
            {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}},
            {"MediaContainer": {"Metadata": [{"title": "The Matrix", "year": 1999, "ratingKey": "123", "type": "movie"}]}},
        ]

        # Create entry
        entry = WatchlistEntry(
            title="The Matrix", year=1999, category="Action", lang="English",
            rt=88, imdb=8.7, isSeries=False, imdbId="tt0133093", tmdbId=603,
            cert="R", snippet="", cast=[], director="", poster="", trailerId="", trailerTitle="", added="2026-01-01", state="pending"
        )
        wl = WatchlistService("/tmp/test_watchlist_status.json")
        import os
        if os.path.exists("/tmp/test_watchlist_status.json"):
            os.remove("/tmp/test_watchlist_status.json")
        data = wl.load()
        data.pending.append(entry)
        wl.save(data)

        # Compute status via the logic in status.py
        from api.routes.status import get_status
        from config.settings import get_config
        import config.settings
        config.settings._CONFIG_INSTANCE = None  # Reset singleton

        with patch("api.routes.status.get_config") as mock_cfg:
            mock_cfg.return_value = Mock(
                RADARR_URL="http://test:7878",
                RADARR_API_KEY="key",
                SONARR_URL="http://test:8989",
                SONARR_API_KEY="key",
                PLEX_URL="http://test:32400",
                PLEX_TOKEN="token",
                QBITTORRENT_URL="http://test:1701",
                RADARR_QUALITY_PROFILE_ID=None,
                SONARR_QUALITY_PROFILE_ID=None,
                has_tmdb=lambda: False,
                has_jellyfin=lambda: False,
            )

            # This is an integration test - would need full API setup
            # For now, test the components separately
            pass

    @patch("services.radarr.get_config")
    @patch("services.radarr.get_http_client")
    def test_radarr_has_file_detection(self, mock_http, mock_config):
        """Test Radarr has_file detection."""
        mock_config.return_value.RADARR_URL = "http://test:7878"
        mock_config.return_value.RADARR_API_KEY = "key"

        radarr = RadarrService()
        mock_http.return_value.get.return_value = [
            {"id": 1, "tmdbId": 603, "title": "The Matrix", "year": 1999, "hasFile": True, "monitored": True, "qualityProfileId": 1},
        ]

        assert radarr.has_file(603) is True
        assert radarr.has_file(999) is False

    @patch("config.settings.get_config")
    @patch("core.http_client.get_http_client")
    def test_sonarr_has_episodes_detection(self, mock_get_http_client, mock_get_config):
        """Test Sonarr has_episodes detection."""
        mock_get_config.return_value.SONARR_URL = "http://test:8989"
        mock_get_config.return_value.SONARR_API_KEY = "key"

        # For tracking what to return for each call - use a mutable object that persists
        call_state = {'count': 0}

        def mock_get_side_effect(url, headers=None, params=None):
            call_state['count'] += 1
            print(f"[TEST MOCK] HTTP call #{call_state['count']}: {url}")
            if url.endswith("/series") and not params:  # Series list call
                if call_state['count'] == 1:
                    # First call: get series list (first has_episodes) - with episodes
                    print("[TEST MOCK] Returning series list with 62 episodes")
                    return [
                        {"id": 1, "tvdbId": 81189, "title": "Breaking Bad", "year": 2008,
                         "monitored": True, "qualityProfileId": 1, "languageProfileId": 1,
                         "statistics": {"episodeFileCount": 62}},
                    ]
                elif call_state['count'] == 2:
                    # Second call: get series list (second has_episodes) - without episodes
                    print("[TEST MOCK] Returning series list with 0 episodes")
                    return [
                        {"id": 1, "tvdbId": 81189, "title": "Breaking Bad", "year": 2008,
                         "monitored": True, "qualityProfileId": 1, "languageProfileId": 1,
                         "statistics": {"episodeFileCount": 0}},
                    ]
                else:
                    # Fallback
                    print(f"[TEST MOCK] Unexpected series list call #{call_state['count']}, returning empty list")
                    return []
            else:
                # For any other calls (like specific series data), return empty
                print(f"[TEST MOCK] Non-series-list call #{call_state['count']}: {url}, returning []")
                return []

        mock_get_http_client.return_value.get.side_effect = mock_get_side_effect

        sonarr = SonarrService()
        print(f"[TEST] Created SonarrService, about to call has_episodes")
        result1 = sonarr.has_episodes(81189)
        print(f"[TEST] First has_episodes result: {result1}")
        assert result1 is True
        print(f"[TEST] First has_episodes passed, about to call second")
        result2 = sonarr.has_episodes(81189)
        print(f"[TEST] Second has_episodes result: {result2}")
        assert result2 is False

if __name__ == "__main__":
    pytest.main([__file__, "-v"])