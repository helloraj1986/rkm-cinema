"""End-to-end tests for recommendation → watchlist flow."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from services import RecommendationService, WatchlistService, PlexService
from services.watchlist import WatchlistEntry
from services.recommendations import Candidate


class TestRecommendationFlow:
    """Test complete recommendation pipeline."""

    def setup_method(self):
        self.reco = RecommendationService()
        self.wl = WatchlistService("/tmp/test_watchlist_e2e.json")
        import os
        if os.path.exists("/tmp/test_watchlist_e2e.json"):
            os.remove("/tmp/test_watchlist_e2e.json")

    def teardown_method(self):
        import os
        if os.path.exists("/tmp/test_watchlist_e2e.json"):
            os.remove("/tmp/test_watchlist_e2e.json")

    @patch("services.recommendations.PlexService")
    @patch("services.recommendations.TrailerService")
    @patch("services.recommendations.WatchlistService")
    def test_full_pipeline_accepts_quality_movie(self, mock_wl_class, mock_trailers_class, mock_plex_class):
        """Full pipeline should accept a movie meeting quality gates."""
        # Setup mocks
        mock_plex = Mock()
        mock_plex.has_media.return_value = False  # Not in Plex
        mock_plex_class.return_value = mock_plex

        mock_trailers = Mock()
        mock_trailers.enrich_entry.return_value = {
            "title": "The Matrix", "year": 1999, "category": "Action", "lang": "English",
            "rt": 88, "imdb": 8.7, "isSeries": False, "imdbId": "tt0133093", "tmdbId": 603,
            "cert": "R", "snippet": "A hacker discovers reality is a simulation.",
            "cast": ["Keanu Reeves"], "director": "Lana Wachowski",
            "poster": "", "trailerId": "dQw4w9WgXcQ", "trailerTitle": "Official Trailer",
            "added": "2026-01-01", "state": "pending"
        }
        mock_trailers.validate_trailer.return_value = True
        mock_trailers_class.return_value = mock_trailers

        mock_wl = Mock()
        mock_wl.find_by_imdb.return_value = None  # Not duplicate
        mock_wl_class.return_value = mock_wl

        # Create candidate meeting quality gates (IMDb 8.7 >= 7.5)
        candidate = Candidate(
            title="The Matrix", year=1999, category="Action", lang="English",
            imdb=8.7, rt=88, is_series=False, imdb_id="tt0133093", tmdb_id=603,
            director="Lana Wachowski", cast=["Keanu Reeves"],
            snippet="A hacker discovers reality is a simulation.", poster=""
        )

        # Process
        entry = self.reco.process_recommendation(candidate)

        # Should be accepted
        assert entry is not None
        assert entry.title == "The Matrix"
        assert entry.imdbId == "tt0133093"
        mock_wl.add_pending.assert_called_once()

    @patch("services.recommendations.PlexService")
    @patch("services.recommendations.WatchlistService")
    def test_full_pipeline_rejects_plex_owned(self, mock_wl_class, mock_plex_class):
        """Pipeline should reject movies already in Plex."""
        mock_plex = Mock()
        mock_plex.has_media.return_value = True  # Already in Plex
        mock_plex_class.return_value = mock_plex

        mock_wl = Mock()
        mock_wl_class.return_value = mock_wl

        candidate = Candidate(
            title="The Matrix", year=1999, category="Action", lang="English",
            imdb=8.7, rt=88, is_series=False, imdb_id="tt0133093", tmdb_id=603,
            director="Lana Wachowski", cast=["Keanu Reeves"],
            snippet="A hacker discovers reality is a simulation.", poster=""
        )

        entry = self.reco.process_recommendation(candidate)

        assert entry is None
        mock_plex.has_media.assert_called_once_with("The Matrix", 1999, False)
        mock_wl.add_pending.assert_not_called()

    @patch("services.recommendations.PlexService")
    @patch("services.recommendations.WatchlistService")
    def test_full_pipeline_rejects_watchlist_duplicate(self, mock_wl_class, mock_plex_class):
        """Pipeline should reject movies already in watchlist."""
        mock_plex = Mock()
        mock_plex.has_media.return_value = False
        mock_plex_class.return_value = mock_plex

        mock_wl = Mock()
        mock_wl.find_by_imdb.return_value = WatchlistEntry(  # Already exists
            title="The Matrix", year=1999, category="Action", lang="English",
            rt=88, imdb=8.7, isSeries=False, imdbId="tt0133093", tmdbId=603,
            cert="R", snippet="", cast=[], director="", poster="",
            trailerId="", trailerTitle="", added="2026-01-01", state="pending"
        )
        mock_wl_class.return_value = mock_wl

        candidate = Candidate(
            title="The Matrix", year=1999, category="Action", lang="English",
            imdb=8.7, rt=88, is_series=False, imdb_id="tt0133093", tmdb_id=603,
            director="Lana Wachowski", cast=["Keanu Reeves"],
            snippet="A hacker discovers reality is a simulation.", poster=""
        )

        entry = self.reco.process_recommendation(candidate)

        assert entry is None
        mock_wl.add_pending.assert_not_called()

    @patch("services.recommendations.PlexService")
    @patch("services.recommendations.WatchlistService")
    def test_full_pipeline_rejects_below_quality_gate(self, mock_wl_class, mock_plex_class):
        """Pipeline should reject movies below quality gates."""
        mock_plex = Mock()
        mock_plex.has_media.return_value = False
        mock_plex_class.return_value = mock_plex

        mock_wl = Mock()
        mock_wl_class.return_value = mock_wl

        # Below film gate (IMDb 7.0 < 7.5, RT 70 < 80)
        candidate = Candidate(
            title="Bad Movie", year=2020, category="Action", lang="English",
            imdb=7.0, rt=70, is_series=False, imdb_id="tt9999999", tmdb_id=99999,
            director="Director", cast=["Actor"],
            snippet="A bad movie.", poster=""
        )

        entry = self.reco.process_recommendation(candidate)

        assert entry is None
        mock_wl.add_pending.assert_not_called()

    def test_series_quality_gate(self):
        """Series quality gate should use series thresholds."""
        # Series: IMDb 8.0+ OR RT 85+
        # This tests the logic directly
        assert self.reco.verify_quality_gate(Candidate(
            title="Series", year=2020, category="Drama", lang="English",
            imdb=8.2, rt=80, is_series=True, imdb_id="tt1111111", tmdb_id=11111,
            director="", cast=[], snippet="", poster=""
        )) is True  # IMDb 8.2 >= 8.0

        assert self.reco.verify_quality_gate(Candidate(
            title="Series", year=2020, category="Drama", lang="English",
            imdb=7.8, rt=90, is_series=True, imdb_id="tt2222222", tmdb_id=22222,
            director="", cast=[], snippet="", poster=""
        )) is True  # RT 90 >= 85

        assert self.reco.verify_quality_gate(Candidate(
            title="Series", year=2020, category="Drama", lang="English",
            imdb=7.5, rt=80, is_series=True, imdb_id="tt3333333", tmdb_id=33333,
            director="", cast=[], snippet="", poster=""
        )) is False  # Both below series gates


if __name__ == "__main__":
    pytest.main([__file__, "-v"])