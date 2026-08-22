"""Tests for the Phase 13 jobs layer (jobs/{base,daily_watchlist,reconcile}.py).

Verifies: JobRunner records runs to job_runs (success + error), the daily
watchlist job feeds the RecommendationManager and records counts, the reconcile
job computes statuses without generating recommendations, and the REST run
endpoint dispatches known jobs. LAN-free — DI fakes for manager/adder/reconciler.
"""
import pytest
from unittest.mock import Mock

from domain.enums import MediaStatus, MediaType
from services.recommendation.criteria import RecommendationCandidate
from services.recommendation.ranker import RankedCandidate, rank_tuples
from jobs.base import JobRunner, JobResult


def repo_mock():
    repo = Mock()
    repo.record_job_run.return_value = None
    repo.list_job_runs.return_value = []
    return repo


class TestJobRunner:
    def test_records_success(self):
        repo = repo_mock()
        runner = JobRunner(repository=repo)
        def fn():
            return JobResult(name="x", items_processed=3, counts={"a": 1})
        res = runner.run("x", fn)
        assert res.status == "success"
        assert res.items_processed == 3
        repo.record_job_run.assert_called_once()
        kwargs = repo.record_job_run.call_args.kwargs
        assert kwargs["job_name"] == "x"
        assert kwargs["status"] == "success"
        assert kwargs["items_processed"] == 3

    def test_records_error(self):
        repo = repo_mock()
        runner = JobRunner(repository=repo)
        def fn():
            raise RuntimeError("boom")
        res = runner.run("x", fn)
        assert res.status == "error"
        assert "boom" in (res.error or "")
        kwargs = repo.record_job_run.call_args.kwargs
        assert kwargs["status"] == "error"
        assert kwargs["error"]

    def test_converts_plain_return(self):
        repo = repo_mock()
        runner = JobRunner(repository=repo)
        res = runner.run("x", lambda: 7)
        assert res.name == "x"
        assert res.items_processed == 7


class TestDailyWatchlistJob:
    def _cand(self, i):
        return RecommendationCandidate(
            media_type=MediaType.MOVIE, title=f"T{i}", year=2025,
            tmdb_id=i, tmdb_score=8.4, vote_count=1000, imdb=8.0, rt=85)

    def test_adds_survivors_and_records_counts(self):
        from jobs.daily_watchlist import DailyWatchlistJob
        mgr = Mock()

        class _Res:
            status = "success"
            candidates = 5
            passed_criteria = 4
            already_in_library = 1
            watchlist_duplicates = 0
            already_recommended = 0
            new_recommendations = 3
            recommended = [
                RankedCandidate(self._cand(1), 90.0, Mock(passed=True)),
                RankedCandidate(self._cand(2), 88.0, Mock(passed=True)),
                RankedCandidate(self._cand(3), 85.0, Mock(passed=True)),
            ]
        mgr.run.return_value = _Res()
        added = []
        def adder(cand, score):
            added.append(cand.tmdb_id)
            return True
        job = DailyWatchlistJob(manager=mgr, adder=adder)
        res = job.run()
        assert res.status == "success"
        assert res.items_processed == 3
        assert added == [1, 2, 3]
        assert res.counts["new_recommendations"] == 3
        assert res.counts["watchlist_added"] == 3

    def test_error_propagates(self):
        from jobs.daily_watchlist import DailyWatchlistJob
        mgr = Mock()
        mgr.run.return_value = Mock(status="error", error="nope")
        job = DailyWatchlistJob(manager=mgr)
        res = job.run()
        assert res.status == "error"
        assert res.error == "nope"


class TestReconcileJob:
    def test_tallies_statuses_without_recs(self):
        from jobs.reconcile import ReconcileJob
        from domain.status import MediaSnapshot
        rec = Mock()
        res = Mock(snapshots={
            "a": MediaSnapshot(media_id="movie:tmdb:1", status=MediaStatus.AVAILABLE),
            "b": MediaSnapshot(media_id="movie:tmdb:2", status=MediaStatus.DOWNLOADING),
            "c": MediaSnapshot(media_id="movie:tmdb:3", status=MediaStatus.REQUESTED),
        }, indexer_issue=None)
        rec.compute.return_value = res
        job = ReconcileJob(reconciler=rec)
        result = job.run()
        assert result.status == "success"
        assert result.items_processed == 3
        assert result.counts["available"] == 1
        assert result.counts["downloading"] == 1
        assert result.counts["requested"] == 1
        assert result.counts["indexer_issue"] is False
        rec.compute.assert_called_once()


class TestJobRunEndpoint:
    def test_unknown_job_404(self):
        from fastapi.testclient import TestClient
        import api.main
        c = TestClient(api.main.app)
        r = c.post("/api/jobs/nope/run")
        assert r.status_code == 404

    def test_dispatch_known_job(self, monkeypatch):
        from fastapi.testclient import TestClient
        import api.main
        import jobs.reconcile as reconcile_mod
        fake = lambda: JobResult(name="reconcile", status="success", items_processed=2, counts={"a": 1})
        monkeypatch.setattr(reconcile_mod, "run_reconcile", fake)
        c = TestClient(api.main.app)
        r = c.post("/api/jobs/reconcile/run")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "reconcile"
        assert body["status"] == "success"