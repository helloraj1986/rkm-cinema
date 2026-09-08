"""Tests for trailer validation."""
import pytest
from unittest.mock import Mock, patch
from services.trailers import TrailerService, TrailerInfo


class TestTrailerValidation:
    """Test trailer ID validation and enrichment."""

    def setup_method(self):
        self.trailers = TrailerService()

    def test_validate_trailer_valid_id(self):
        """Valid YouTube IDs should pass."""
        valid_ids = [
            "dQw4w9WgXcQ",  # Standard
            "abc123def45",  # Alphanumeric
            "AbCdEfGhIjK",  # Mixed case
            "video-id_12",  # With hyphen and underscore
        ]
        for tid in valid_ids:
            assert self.trailers.validate_trailer(tid) is True, f"Should be valid: {tid}"

    def test_validate_trailer_invalid_id(self):
        """Invalid YouTube IDs should fail."""
        invalid_ids = [
            "",  # Empty
            "short",  # Too short
            "dQw4w9WgXcQQ",  # Too long (12 chars)
            "dQw4w9WgXc!",  # Special char
            "dQw4w9WgXc.",  # Dot
            "dQw4w9WgXc ",  # Space
            None,  # None
        ]
        for tid in invalid_ids:
            assert self.trailers.validate_trailer(tid) is False, f"Should be invalid: {tid}"

    @patch("services.trailers.get_config")
    @patch("services.trailers.get_http_client")
    def test_enrich_entry_preserves_existing_trailer(self, mock_http, mock_config):
        """Enrichment should not overwrite existing valid trailer."""
        mock_config.return_value.TVDB_API_KEY = None
        mock_config.return_value.TMDB_API_KEY = None

        entry = {
            "title": "Test Movie",
            "year": 2020,
            "imdbId": "tt1234567",
            "tmdbId": 12345,
            "isSeries": False,
            "trailerId": "dQw4w9WgXcQ",
            "trailerTitle": "Existing Trailer",
        }

        enriched = self.trailers.enrich_entry(entry)
        assert enriched["trailerId"] == "dQw4w9WgXcQ"
        assert enriched["trailerTitle"] == "Existing Trailer"

    @patch("services.trailers.get_config")
    @patch("services.trailers.get_http_client")
    def test_enrich_entry_replaces_invalid_trailer(self, mock_http, mock_config):
        """Enrichment should replace invalid trailer ID."""
        mock_config.return_value.TVDB_API_KEY = None
        mock_config.return_value.TMDB_API_KEY = None

        entry = {
            "title": "Test Movie",
            "year": 2020,
            "imdbId": "tt1234567",
            "tmdbId": 12345,
            "isSeries": False,
            "trailerId": "invalid_id",
            "trailerTitle": "Bad Trailer",
        }

        enriched = self.trailers.enrich_entry(entry)
        assert enriched["trailerId"] == ""
        assert enriched["trailerTitle"] == ""

    @patch("services.trailers.get_config")
    @patch("services.trailers.get_http_client")
    def test_extract_youtube_id(self, mock_http, mock_config):
        """Test YouTube ID extraction from various URL formats."""
        mock_config.return_value.TVDB_API_KEY = None
        mock_config.return_value.TMDB_API_KEY = None

        test_cases = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "dQw4w9WgXcQ"),
            ("not a url", None),
            ("", None),
        ]

        for url, expected in test_cases:
            result = self.trailers._extract_youtube_id(url)
            assert result == expected, f"URL: {url} -> expected {expected}, got {result}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])