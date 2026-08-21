"""Tests for TV series → Sonarr routing (uses injectable DI, no real LAN)."""
import pytest
from unittest.mock import Mock
from services.sonarr import SonarrService, SonarrSeries, AddResult


def make_config(**over):
    c = Mock()
    c.SONARR_URL = "http://sonarr.test:8989"
    c.SONARR_API_KEY = "key"
    c.SONARR_QUALITY_PROFILE_ID = None
    for k, v in over.items():
        setattr(c, k, v)
    return c


def make_http():
    h = Mock()
    h.get.return_value = []
    return h


class TestSonarrRouting:
    """Test series download routing to Sonarr."""

    def test_add_series_success(self):
        svc = SonarrService(config=make_config(), http=make_http())
        svc.get_quality_profiles = Mock(return_value=[Mock(id=1, name="HD-1080p", items=[])])
        svc.get_language_profiles = Mock(return_value=[Mock(id=1, name="English")])
        svc.get_root_folders = Mock(return_value=[Mock(path="/tv")])
        svc.lookup_series = Mock(return_value=SonarrSeries(
            id=0, tvdbId=81189, title="Breaking Bad", year=2008,
            monitored=True, qualityProfileId=0, languageProfileId=0, statistics={}))
        svc.find_series_by_tvdb = Mock(return_value=None)
        svc._post = Mock(return_value={
            "id": 999, "tvdbId": 81189, "title": "Breaking Bad", "year": 2008,
            "monitored": True, "qualityProfileId": 1, "languageProfileId": 1,
            "statistics": {"episodeFileCount": 0}})

        result = svc.add_series("tt0903747")

        assert result.success is True
        assert result.state == "requested"
        assert result.series is not None
        assert result.series.title == "Breaking Bad"

    def test_add_series_duplicate(self):
        svc = SonarrService(config=make_config(), http=make_http())
        svc.lookup_series = Mock(return_value=SonarrSeries(
            id=0, tvdbId=81189, title="Breaking Bad", year=2008,
            monitored=True, qualityProfileId=0, languageProfileId=0, statistics={}))
        svc.find_series_by_tvdb = Mock(return_value=SonarrSeries(
            id=123, tvdbId=81189, title="Breaking Bad", year=2008,
            monitored=True, qualityProfileId=1, languageProfileId=1,
            statistics={"episodeFileCount": 62}))

        result = svc.add_series("tt0903747")

        assert result.success is True
        assert result.state == "requested"
        assert "already in Sonarr" in result.message

    def test_add_series_title_fallback(self):
        """Stale IMDB -> title search resolves correct series."""
        svc = SonarrService(config=make_config(), http=make_http())
        svc.lookup_series = Mock(return_value=None)
        svc.search_series = Mock(return_value=[SonarrSeries(
            id=0, tvdbId=403294, title="The Bear", year=2022,
            monitored=True, qualityProfileId=0, languageProfileId=0, statistics={}, imdbId="tt10157119")])
        svc.get_quality_profiles = Mock(return_value=[Mock(id=1, name="HD-1080p", items=[])])
        svc.get_language_profiles = Mock(return_value=[Mock(id=1, name="English")])
        svc.get_root_folders = Mock(return_value=[Mock(path="/tv")])
        svc.find_series_by_tvdb = Mock(return_value=None)
        svc._post = Mock(return_value={
            "id": 1, "tvdbId": 403294, "title": "The Bear", "year": 2022,
            "monitored": True, "qualityProfileId": 1, "languageProfileId": 1,
            "statistics": {"episodeFileCount": 0}})

        result = svc.add_series("tt10157119", title="The Bear", year=2022)

        assert result.success is True
        assert result.series.tvdbId == 403294

    def test_add_series_ambiguous(self):
        """Multiple distinct title matches, no exact -> ambiguous, not silent guess."""
        svc = SonarrService(config=make_config(), http=make_http())
        svc.lookup_series = Mock(return_value=None)
        svc.search_series = Mock(return_value=[
            SonarrSeries(id=0, tvdbId=1, title="Candyman: Farewell to the Flesh", year=1995,
                         monitored=True, qualityProfileId=0, languageProfileId=0, statistics={}),
            SonarrSeries(id=0, tvdbId=2, title="Candyman (2021 Reimagining)", year=2021,
                         monitored=True, qualityProfileId=0, languageProfileId=0, statistics={}),
        ])
        result = svc.add_series("tt0000000", title="Candyman", year=1990)
        assert result.success is False
        assert result.state == "ambiguous"
        assert "Multiple Sonarr matches" in result.message

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
