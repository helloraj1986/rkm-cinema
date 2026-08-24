"""Tests for the Phase 12 recommendation engine (services/recommendation/).

Covers: criteria engine (config-driven PASS/FAIL + reasons + score), generator
(candidate normalization), ranker, manager pipeline (library/watchlist/history
exclusions + persistence). LAN-free — TMDB and repo are DI-injected fakes.
"""
import pytest
from unittest.mock import Mock

from domain.enums import MediaType
from services.recommendation.criteria import (
    CriteriaEngine, CriteriaResult, RecommendationCandidate,
)
from services.recommendation.generator import CandidateGenerator
from services.recommendation.ranker import rank, rank_tuples
from services.recommendation.manager import RecommendationManager

# A representative criteria dict (mirrors config/recommendations.yaml).
CRITERIA = {
    "recommendations": {
        "movies": {
            "min_tmdb_rating": 7.5, "min_vote_count": 500, "years": [],
            "genres": {"include": [], "exclude": ["horror"]},
            "min_imdb": 7.5, "min_rt": 80, "rt_any": True, "score_weight": 1.0,
        },
        "series": {
            "min_tmdb_rating": 8.0, "min_vote_count": 200, "years": [],
            "genres": {"include": [], "exclude": []},
            "min_imdb": 8.0, "min_rt": 85, "rt_any": True, "score_weight": 1.0,
        },
        "score": {"tmdb_weight": 0.6, "imdb_weight": 0.3, "recent_bonus": 0.1},
    }
}


def cand(movie=True, title="X", year=2025, tmdb=1, ts=8.4, vc=10000,
         imdb=8.2, rt=90, genres=None):
    return RecommendationCandidate(
        media_type=MediaType.MOVIE if movie else MediaType.TV,
        title=title, year=year, tmdb_id=tmdb, imdb_id="tt" + str(tmdb),
        tmdb_score=ts, vote_count=vc, imdb=imdb, rt=rt, genres=genres or ["drama"])


def engine():
    e = CriteriaEngine()
    e.load_from_dict(CRITERIA)
    return e


class TestCriteriaEngine:
    def test_pass_with_reasons_and_score(self):
        r = engine().evaluate(cand())
        assert r.passed is True
        assert r.score > 50
        assert any("TMDB rating" in x for x in r.reasons)
        assert any("Vote count" in x for x in r.reasons)

    def test_fail_low_tmdb_rating(self):
        r = engine().evaluate(cand(ts=6.0))
        assert r.passed is False
        assert r.score < 50

    def test_fail_excluded_genre(self):
        r = engine().evaluate(cand(genres=["horror"]))
        assert r.passed is False
        assert any("Excluded genre" in x for x in r.reasons)

    def test_fail_imdb_rt_both_below_gate(self):
        # movies: needs imdb>=7.5 OR rt>=80; this fails both.
        r = engine().evaluate(cand(ts=8.5, imdb=6.0, rt=20))
        assert r.passed is False
        assert any("IMDb" in x and "RT" in x for x in r.reasons)

    def test_series_gate(self):
        # series: imdb>=8.0 OR rt>=85
        e = engine()
        assert e.evaluate(cand(movie=False, imdb=8.2, rt=70)).passed is True
        assert e.evaluate(cand(movie=False, imdb=7.5, rt=80)).passed is False

    def test_unknown_tmdb_score_does_not_fail(self):
        # legacy candidates carry tmdb_score=0 (unknown) -> not enforced.
        r = engine().evaluate(cand(ts=0, imdb=8.2, rt=90))
        assert r.passed is True

    def test_imdb_rt_both_unknown_skips_anchor(self):
        """A TMDB-discover candidate (imdb=0 AND rt=0) passes on TMDB alone.

        The IMDb/RT anchor is a real gate ONLY when the scores are known;
        when both are unknown (TMDB-discover case) the candidate is scored on
        its TMDB rating (spec §22).
        """
        r = engine().evaluate(cand(ts=8.0, vc=1000, imdb=0, rt=0, genres=None))
        assert r.passed is True
        # a genuinely low-TMDB discover candidate still fails on tmdb
        low = engine().evaluate(cand(ts=6.0, vc=1000, imdb=0, rt=0, genres=None))
        assert low.passed is False


class TestCandidateGenerator:
    def test_normalizes_tmdb_movie_shape(self):
        raw = [{"id": 603, "title": "The Matrix", "release_date": "1999-03-31",
                "vote_average": 8.7, "vote_count": 20000, "genre_ids": [878]}]
        gen = CandidateGenerator(source_fn=lambda mt, cat, n: raw)
        out = gen.candidates(media_type=MediaType.MOVIE)
        assert len(out) == 1
        assert out[0].title == "The Matrix"
        assert out[0].year == 1999
        assert out[0].tmdb_score == 8.7
        assert out[0].genres == ["878"]

    def test_normalizes_tv_shape(self):
        raw = [{"id": 9, "name": "Breaking Bad", "first_air_date": "2008-01-20",
                "vote_average": 9.3, "vote_count": 30000}]
        gen = CandidateGenerator(source_fn=lambda mt, cat, n: raw)
        out = gen.candidates(media_type=MediaType.TV)
        assert out[0].title == "Breaking Bad"
        assert out[0].media_type is MediaType.TV

    def test_skips_invalid_candidates(self):
        gen = CandidateGenerator(source_fn=lambda mt, cat, n: [{}, {"id": 1, "title": "G", "vote_average": "x"}])
        # empty dict has no keys -> still yields a candidate with empty title; only
        # malformed that raise are skipped. Assert no exception and no crash.
        out = gen.candidates(media_type=MediaType.MOVIE)
        assert isinstance(out, list)

    def test_discover_maps_genre_ids_to_names(self):
        """TMDB discover returns numeric genre_ids; the generator must map them
        to names so name-based criteria (exclude horror) fire on this path."""
        raw = [{"id": 1, "title": "The Thing", "release_date": "1982-01-01",
                "vote_average": 8.2, "vote_count": 1000, "genre_ids": [27, 878]}]

        class _FakeDiscover:
            def genre_names(self):
                return {878: "Science Fiction", 27: "Horror", 12: "Adventure"}

            def _request(self, *a, **k):
                return {"results": raw}

        out = CandidateGenerator._discover_tmdb(_FakeDiscover(), "discover/movie", 10)
        assert out[0]["genres"] == ["Horror", "Science Fiction"]


class TestRanker:
    def test_ranks_by_score_desc(self):
        c1, c2 = cand(tmdb=1, ts=8.0), cand(tmdb=2, ts=9.0)
        r1, r2 = CriteriaResult(passed=True, score=80), CriteriaResult(passed=True, score=95)
        ranked = rank([(c1, r1), (c2, r2)])
        assert ranked[0].candidate.tmdb_id == 2
        assert ranked[0].score == 95

    def test_rank_tuples(self):
        ranked = rank_tuples([(cand(tmdb=1), CriteriaResult(True, 70)),
                              (cand(tmdb=2), CriteriaResult(True, 90))])
        assert ranked[0][1] == 90


class TestRecommendationManager:
    def test_pipeline_excludes_library_watchlist_history(self):
        generator = CandidateGenerator(source_fn=lambda mt, cat, n: [
            {"id": i, "title": f"T{i}", "release_date": "2025",
             "vote_average": 8.5, "vote_count": 1000, "genre_ids": ["drama"],
             "imdb": 8.0, "rt": 85}
            for i in range(1, 6)])
        library = Mock()
        library.has.return_value = False
        watchlist = Mock()
        watchlist.find_by_imdb.return_value = None
        watchlist.find_by_tmdb.return_value = None
        history = Mock()
        history.list_recommendation_history.return_value = [
            {"media_id": "movie:tmdb:3"}]  # tmdb_id 3 already recommended
        m = RecommendationManager(generator=generator, criteria=engine(),
                                  library=library, watchlist=watchlist, history=history)
        res = m.run(media_type=MediaType.MOVIE, count=5)
        assert res.candidates == 5
        assert res.already_recommended == 1
        assert res.new_recommendations == 4
        assert res.passed_criteria == 5

    def test_library_exclusion(self):
        generator = CandidateGenerator(source_fn=lambda mt, cat, n: [
            {"id": 1, "title": "Owned", "release_date": "2025",
             "vote_average": 8.5, "vote_count": 1000, "genre_ids": ["drama"],
             "imdb": 8.0, "rt": 85}])
        library = Mock()
        library.has.return_value = True
        watchlist = Mock(); watchlist.find_by_imdb.return_value = None; watchlist.find_by_tmdb.return_value = None
        history = Mock(); history.list_recommendation_history.return_value = []
        m = RecommendationManager(generator=generator, criteria=engine(),
                                  library=library, watchlist=watchlist, history=history)
        res = m.run(media_type=MediaType.MOVIE, count=1)
        assert res.already_in_library == 1
        assert res.new_recommendations == 0
        library.has.assert_called_once()

    def test_watchlist_exclusion(self):
        """§30: a candidate already on the active watchlist (pending) is excluded."""
        generator = CandidateGenerator(source_fn=lambda mt, cat, n: [
            {"id": 1, "title": "Pending", "release_date": "2025",
             "vote_average": 8.5, "vote_count": 1000, "genre_ids": ["drama"],
             "imdb_id": "tt9999999", "imdb": 8.0, "rt": 85}])
        library = Mock(); library.has.return_value = False
        watchlist = Mock()
        watchlist.find_by_imdb.return_value = {"media_id": "movie:tmdb:1"}  # already pending
        watchlist.find_by_tmdb.return_value = None
        history = Mock(); history.list_recommendation_history.return_value = []
        m = RecommendationManager(generator=generator, criteria=engine(),
                                  library=library, watchlist=watchlist, history=history)
        res = m.run(media_type=MediaType.MOVIE, count=1)
        assert res.watchlist_duplicates == 1
        assert res.new_recommendations == 0

    def test_persists_history(self):
        generator = CandidateGenerator(source_fn=lambda mt, cat, n: [
            {"id": i, "title": f"T{i}", "release_date": "2025",
             "vote_average": 8.5, "vote_count": 1000, "genre_ids": ["drama"],
             "imdb": 8.0, "rt": 85}
            for i in range(1, 4)])
        library = Mock(); library.has.return_value = False
        watchlist = Mock(); watchlist.find_by_imdb.return_value = None; watchlist.find_by_tmdb.return_value = None
        history = Mock(); history.list_recommendation_history.return_value = []
        m = RecommendationManager(generator=generator, criteria=engine(),
                                  library=library, watchlist=watchlist, history=history)
        res = m.run(media_type=MediaType.MOVIE, count=3, max_persist=2)
        assert res.new_recommendations == 3
        calls = history.record_recommendation.call_count
        assert calls == 2  # max_persist caps history writes
        # each recorded media_id is canonical and carries a score
        kwargs = history.record_recommendation.call_args_list[0].kwargs
        assert kwargs["media_id"].startswith("movie:tmdb:")
        assert kwargs["score"] > 0


class TestRepoHistory:
    def test_sqlite_record_and_list(self, tmp_path):
        from infrastructure.database.db import Database
        from infrastructure.database.repository import SqliteWatchlistRepository
        db = Database(path=str(tmp_path / "rec.db"))
        repo = SqliteWatchlistRepository(db=db)
        repo.record_recommendation(media_id="movie:tmdb:1", decision="recommended", score=88.0,
                                   payload={"title": "X"})
        repo.record_recommendation(media_id="movie:tmdb:2", decision="recommended", score=91.0)
        rows = repo.list_recommendation_history(limit=10)
        ids = [r["media_id"] for r in rows]
        assert "movie:tmdb:1" in ids and "movie:tmdb:2" in ids
        # idempotent re-record updates last_seen, not a duplicate row
        repo.record_recommendation(media_id="movie:tmdb:1", decision="accepted", score=95.0)
        rows = repo.list_recommendation_history(limit=10)
        assert sum(1 for r in rows if r["media_id"] == "movie:tmdb:1") == 1
        row1 = next(r for r in rows if r["media_id"] == "movie:tmdb:1")
        assert row1["score"] == 95.0