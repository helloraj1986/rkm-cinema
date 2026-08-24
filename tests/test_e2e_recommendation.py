"""End-to-end tests for recommendation → watchlist flow (DI-injected, no real LAN)."""
import os
import pytest
from unittest.mock import Mock

from services import RecommendationService
from services.watchlist import WatchlistEntry
from services.recommendations import Candidate


def make_test_wl():
    from services.watchlist import WatchlistService
    path = "/tmp/test_watchlist_e2e.json"
    if os.path.exists(path):
        os.remove(path)
    return WatchlistService(path)


class TestRecommendationFlow:
    """Test complete recommendation pipeline with injected mocks."""

    def make_reco(self, library=None, watchlist=None, trailers=None, tmdb=None, youtube=None):
        return RecommendationService(
            config=Mock(TMDB_API_KEY="k", YOUTUBE_API_KEY=""),
            library=library,
            watchlist=watchlist or Mock(),
            trailers=trailers or Mock(),
            tmdb=tmdb or Mock(),
            youtube=youtube or Mock(),
        )

    def test_full_pipeline_accepts_quality_movie(self):
        """Full pipeline accepts a movie meeting quality gates and adds it."""
        library = Mock()
        library.has.return_value = False
        watchlist = Mock()
        watchlist.find_by_imdb.return_value = None
        watchlist.find_by_tmdb.return_value = None
        trailers = Mock()
        trailers.enrich_entry.return_value = {
            "title": "The Matrix", "year": 1999, "category": "Action", "lang": "English",
            "rt": 88, "imdb": 8.7, "isSeries": False, "imdbId": "tt0133093", "tmdbId": 603,
            "cert": "R", "snippet": "A hacker discovers reality is a simulation.",
            "cast": ["Keanu Reeves"], "director": "Lana Wachowski",
            "poster": "", "trailerId": "dQw4w9WgXcQ", "trailerTitle": "Official Trailer",
            "added": "2026-01-01", "state": "pending"
        }
        trailers.validate_trailer.return_value = True
        youtube = Mock()
        youtube.has_youtube.return_value = False  # force trailer-service fallback

        reco = self.make_reco(library=library, watchlist=watchlist, trailers=trailers, youtube=youtube)
        candidate = Candidate(
            title="The Matrix", year=1999, category="Action", lang="English",
            imdb=8.7, rt=88, is_series=False, imdb_id="tt0133093", tmdb_id=603,
            director="Lana Wachowski", cast=["Keanu Reeves"],
            snippet="A hacker discovers reality is a simulation.", poster="")

        entry = reco.process_recommendation(candidate)

        assert entry is not None
        assert entry.title == "The Matrix"
        watchlist.add_pending.assert_called_once()

    def test_full_pipeline_rejects_library_owned(self):
        """An item already in the library is rejected (ownership dedupe)."""
        library = Mock()
        library.has.return_value = True
        watchlist = Mock()
        reco = self.make_reco(library=library, watchlist=watchlist)
        candidate = Candidate(
            title="The Matrix", year=1999, category="Action", lang="English",
            imdb=8.7, rt=88, is_series=False, imdb_id="tt0133093", tmdb_id=603,
            director="Lana Wachowski", cast=["Keanu Reeves"],
            snippet="A hacker discovers reality is a simulation.", poster="")

        entry = reco.process_recommendation(candidate)
        assert entry is None
        library.has.assert_called_once()
        watchlist.add_pending.assert_not_called()

    def test_full_pipeline_rejects_watchlist_duplicate(self):
        library = Mock()
        library.has.return_value = False
        watchlist = Mock()
        watchlist.find_by_imdb.return_value = WatchlistEntry(
            title="The Matrix", year=1999, category="Action", lang="English",
            rt=88, imdb=8.7, isSeries=False, imdbId="tt0133093", tmdbId=603,
            cert="R", snippet="", cast=[], director="", poster="",
            trailerId="", trailerTitle="", added="2026-01-01", state="pending")
        reco = self.make_reco(library=library, watchlist=watchlist)
        candidate = Candidate(
            title="The Matrix", year=1999, category="Action", lang="English",
            imdb=8.7, rt=88, is_series=False, imdb_id="tt0133093", tmdb_id=603,
            director="Lana Wachowski", cast=["Keanu Reeves"],
            snippet="A hacker discovers reality is a simulation.", poster="")

        entry = reco.process_recommendation(candidate)
        assert entry is None
        watchlist.add_pending.assert_not_called()

    def test_full_pipeline_rejects_below_quality_gate(self):
        library = Mock()
        library.has.return_value = False
        watchlist = Mock()
        reco = self.make_reco(library=library, watchlist=watchlist)
        candidate = Candidate(
            title="Bad Movie", year=2020, category="Action", lang="English",
            imdb=7.0, rt=70, is_series=False, imdb_id="tt9999999", tmdb_id=99999,
            director="Director", cast=["Actor"], snippet="A bad movie.", poster="")

        entry = reco.process_recommendation(candidate)
        assert entry is None
        watchlist.add_pending.assert_not_called()

    def test_series_quality_gate(self):
        reco = self.make_reco()
        assert reco.verify_quality_gate(Candidate(
            title="Series", year=2020, category="Drama", lang="English",
            imdb=8.2, rt=80, is_series=True, imdb_id="tt1111111", tmdb_id=11111,
            director="", cast=[], snippet="", poster="")) is True
        assert reco.verify_quality_gate(Candidate(
            title="Series", year=2020, category="Drama", lang="English",
            imdb=7.8, rt=90, is_series=True, imdb_id="tt2222222", tmdb_id=22222,
            director="", cast=[], snippet="", poster="")) is True
        assert reco.verify_quality_gate(Candidate(
            title="Series", year=2020, category="Drama", lang="English",
            imdb=7.5, rt=80, is_series=True, imdb_id="tt3333333", tmdb_id=33333,
            director="", cast=[], snippet="", poster="")) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
