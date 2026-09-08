"""Tests for movie → Radarr routing.

Services take injectable ``config``/``http`` so these tests never touch the
real LAN — they pass fakes directly (spec: external APIs must be mockable).
"""
import pytest
from unittest.mock import Mock, MagicMock
from services.radarr import RadarrService, RadarrMovie, AddResult


def make_config(**over):
    c = Mock()
    c.RADARR_URL = "http://radarr.test:7878"
    c.RADARR_API_KEY = "key"
    c.RADARR_QUALITY_PROFILE_ID = None
    for k, v in over.items():
        setattr(c, k, v)
    return c


def make_http():
    h = Mock()
    # default: no exception, returns empty list for lookups
    h.get.return_value = []
    return h


class TestRadarrRouting:
    """Test movie download routing to Radarr."""

    def test_add_movie_success(self):
        """Test successful movie addition to Radarr."""
        svc = RadarrService(config=make_config(), http=make_http())
        svc.get_quality_profiles = Mock(return_value=[Mock(id=1, name="HD-1080p", items=[])])
        svc.get_root_folders = Mock(return_value=[Mock(path="/movies")])
        svc.lookup_movie = Mock(return_value=RadarrMovie(
            id=0, tmdbId=603, title="The Matrix", year=1999,
            hasFile=False, monitored=True, qualityProfileId=0))
        svc.find_movie_by_tmdb = Mock(return_value=None)
        svc._post = Mock(return_value={
            "id": 999, "tmdbId": 603, "title": "The Matrix", "year": 1999,
            "hasFile": False, "monitored": True, "qualityProfileId": 1})

        result = svc.add_movie("tt0133093")

        assert result.success is True
        assert result.state == "requested"
        assert result.movie is not None
        assert result.movie.title == "The Matrix"

    def test_add_movie_duplicate(self):
        """Test duplicate movie handling."""
        svc = RadarrService(config=make_config(), http=make_http())
        svc.lookup_movie = Mock(return_value=RadarrMovie(
            id=0, tmdbId=603, title="The Matrix", year=1999,
            hasFile=False, monitored=True, qualityProfileId=0))
        svc.find_movie_by_tmdb = Mock(return_value=RadarrMovie(
            id=123, tmdbId=603, title="The Matrix", year=1999,
            hasFile=True, monitored=True, qualityProfileId=1))

        result = svc.add_movie("tt0133093")

        assert result.success is True
        assert result.state == "requested"
        assert "already in Radarr" in result.message

    def test_add_movie_no_match(self):
        """Test movie not found in Radarr."""
        svc = RadarrService(config=make_config(), http=make_http())
        svc.lookup_movie = Mock(return_value=None)

        result = svc.add_movie("tt9999999")

        assert result.success is False
        assert result.state == "unavailable"
        assert "No Radarr match" in result.message

    def test_add_movie_title_fallback(self):
        """Stale IMDB -> title+year search fallback resolves correctly."""
        svc = RadarrService(config=make_config(), http=make_http())
        svc.lookup_movie = Mock(return_value=None)  # imdb lookup fails
        svc.search_movies = Mock(return_value=[RadarrMovie(
            id=0, tmdbId=467244, title="The Zone of Interest", year=2023,
            hasFile=False, monitored=True, qualityProfileId=0, imdbId="tt7160372")])
        svc.get_quality_profiles = Mock(return_value=[Mock(id=1, name="HD-1080p", items=[])])
        svc.get_root_folders = Mock(return_value=[Mock(path="/movies")])
        svc.find_movie_by_tmdb = Mock(return_value=None)
        svc._post = Mock(return_value={
            "id": 1, "tmdbId": 467244, "title": "The Zone of Interest", "year": 2023,
            "hasFile": False, "monitored": True, "qualityProfileId": 1})

        result = svc.add_movie("tt2197033", title="The Zone of Interest", year=2023)

        assert result.success is True
        assert result.movie.tmdbId == 467244

    def test_add_movie_ambiguous(self):
        """Multiple title matches -> ambiguous message, not silent guess."""
        svc = RadarrService(config=make_config(), http=make_http())
        svc.lookup_movie = Mock(return_value=None)
        svc.search_movies = Mock(return_value=[
            RadarrMovie(id=0, tmdbId=1, title="Candyman", year=1992,
                        hasFile=False, monitored=True, qualityProfileId=0),
            RadarrMovie(id=0, tmdbId=2, title="Candyman", year=2021,
                        hasFile=False, monitored=True, qualityProfileId=0),
        ])

        result = svc.add_movie("tt9999999", title="Candyman", year=1995)

        assert result.success is False
        assert result.state == "ambiguous"
        assert "Multiple Radarr matches" in result.message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
