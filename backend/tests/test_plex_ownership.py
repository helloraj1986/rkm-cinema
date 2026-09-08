"""Tests for Plex ownership detection."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from services.plex import PlexService, PlexMovie, PlexShow


class TestPlexOwnership:
    """Test Plex ownership verification."""

    def setup_method(self):
        # Patch get_http_client at the source (core.http_client) BEFORE creating service
        self.http_patcher = patch("core.http_client.get_http_client")
        self.mock_http_client_factory = self.http_patcher.start()

        # Create a fresh MagicMock for each call to get_http_client()
        self.mock_client = MagicMock()
        self.mock_http_client_factory.return_value = self.mock_client

        # Create service AFTER patches are applied
        self.plex = PlexService()

    def teardown_method(self):
        self.http_patcher.stop()

    def _reset_mock(self):
        """Reset the mock client for a new test."""
        self.mock_client = MagicMock()
        self.mock_http_client_factory.return_value = self.mock_client
        self.plex.http = self.mock_client
        self.plex._section_cache = {}
        self.plex._section_cache_expiry = 0

    def test_has_movie_exact_match(self):
        """Test exact title + year match."""
        self._reset_mock()
        # Need enough responses for:
        # 1st has_movie: sections + section content
        # 2nd has_movie: cached sections + section content
        # 3rd has_movie: cached sections + section content
        self.mock_client.get.side_effect = [
            {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}},  # sections
            {"MediaContainer": {"Metadata": [  # section content (1st call)
                {"title": "The Matrix", "year": 1999, "ratingKey": "123", "type": "movie"},
                {"title": "Inception", "year": 2010, "ratingKey": "456", "type": "movie"},
            ]}},
            {"MediaContainer": {"Metadata": [  # section content (2nd call, cached sections)
                {"title": "The Matrix", "year": 1999, "ratingKey": "123", "type": "movie"},
                {"title": "Inception", "year": 2010, "ratingKey": "456", "type": "movie"},
            ]}},
            {"MediaContainer": {"Metadata": [  # section content (3rd call, cached sections)
                {"title": "The Matrix", "year": 1999, "ratingKey": "123", "type": "movie"},
                {"title": "Inception", "year": 2010, "ratingKey": "456", "type": "movie"},
            ]}},
        ]

        assert self.plex.has_movie("The Matrix", 1999) is True
        assert self.plex.has_movie("The Matrix", 1998) is False  # Wrong year
        assert self.plex.has_movie("Matrix", 1999) is True  # Partial match

    def test_has_show_match(self):
        """Test TV show match."""
        self._reset_mock()
        self.mock_client.get.side_effect = [
            {"MediaContainer": {"Directory": [{"key": "2", "type": "show"}]}},
            {"MediaContainer": {"Metadata": [
                {"title": "Breaking Bad", "year": 2008, "ratingKey": "789", "type": "show"},
            ]}},
            {"MediaContainer": {"Metadata": [
                {"title": "Breaking Bad", "year": 2008, "ratingKey": "789", "type": "show"},
            ]}},
        ]

        assert self.plex.has_show("Breaking Bad", 2008) is True
        assert self.plex.has_show("Breaking Bad", 2009) is False

    def test_case_insensitive_match(self):
        """Test case-insensitive matching."""
        self._reset_mock()
        # Note: First call caches sections, second call uses cached sections but still calls section content
        self.mock_client.get.side_effect = [
            {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}},  # sections (call 1)
            {"MediaContainer": {"Metadata": [  # section content (call 1)
                {"title": "The Grand Budapest Hotel", "year": 2014, "ratingKey": "1", "type": "movie"},
            ]}},
            {"MediaContainer": {"Metadata": [  # section content (call 2, cached sections)
                {"title": "The Grand Budapest Hotel", "year": 2014, "ratingKey": "1", "type": "movie"},
            ]}},
        ]

        assert self.plex.has_movie("the grand budapest hotel", 2014) is True
        assert self.plex.has_movie("GRAND BUDAPEST", 2014) is True

    def test_library_scan_cached_across_calls(self):
        """get_all_movies scans the library once, then reuses the 60s cache —
        this is what keeps /api/status from rescanning on every entry."""
        self._reset_mock()
        # Only 2 http calls total: sections + one section content fetch.
        # A second get_all_movies() must hit the cache, NOT refetch.
        self.mock_client.get.side_effect = [
            {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}},
            {"MediaContainer": {"Metadata": [
                {"title": "The Matrix", "year": 1999, "ratingKey": "123", "type": "movie"},
                {"title": "Inception", "year": 2010, "ratingKey": "456", "type": "movie"},
            ]}},
        ]
        first = self.plex.get_all_movies()
        assert len(first) == 2
        second = self.plex.get_all_movies()
        assert len(second) == 2
        # sections (1) + content (1) = 2 calls; a 3rd would be another content fetch
        assert self.mock_client.get.call_count == 2

    def test_library_cache_expiry(self):
        """After the 60s TTL the library is rescanned."""
        self._reset_mock()
        self.mock_client.get.side_effect = [
            {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}},
            {"MediaContainer": {"Metadata": [{"title": "M", "year": 2000, "ratingKey": "1", "type": "movie"}]}},
            {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}},
            {"MediaContainer": {"Metadata": [{"title": "M", "year": 2000, "ratingKey": "1", "type": "movie"}]}},
        ]
        self.plex.get_all_movies()
        self.plex.get_all_movies()           # cache hit
        self.plex._library_cache_expiry = 0  # force expiry
        self.plex.get_all_movies()           # refetch content (sections still cached 5min)
        # sections(1) + content(1) first call, then content(1) after library-expiry = 3
        assert self.mock_client.get.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])