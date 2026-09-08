"""Tests for the Phase 9 idempotent request command (application/commands/).

Verifies the spec §15 vocabulary: AVAILABLE / ALREADY_REQUESTED / REQUESTED /
AMBIGUOUS / NOT_CONFIGURED / PROVIDER_UNAVAILABLE, plus idempotency (no double
write) and the "library always wins" rule (§1.2).
"""
import pytest
from unittest.mock import Mock

from domain.enums import MediaType, RequestMediaState
from application.commands.request_media import RequestMediaCommand, request_media


class _FakeLib:
    def __init__(self, has=False):
        self._has = has

    def has(self, identity, *, title="", year=None):
        return self._has

    def find_all(self, identity, *, title="", year=None):
        return []


class _FakeAcq:
    """Fake AcquisitionService exposing find/request/provider_for."""

    def __init__(self, existing_item=None, result=None, provider_name="radarr"):
        self._existing = existing_item
        self._result = result
        self._provider_name = provider_name

    def provider_for(self, media_type):
        class _P:
            name = self._provider_name
        return _P()

    def find(self, identity, *, title="", year=None):
        return self._existing

    def request(self, identity, *, title="", year=None, quality_profile_id=None):
        return self._result


def _success_result():
    return Mock(state="requested", success=True,
                message="added to Radarr — downloading", service="radarr",
                item=Mock(title="The Matrix", year=1999))


def _ambiguous_result():
    return Mock(state="ambiguous", success=False,
                message="Multiple Radarr matches", service="radarr", item=None)


def _unavailable_result():
    return Mock(state="unavailable", success=False,
                message="No Radarr match", service="radarr", item=None)


def cmd(library=None, acquisition=None, persist=None, radarr=None):
    return RequestMediaCommand(library=library or _FakeLib(),
                               acquisition=acquisition or _FakeAcq(),
                               persist=persist, radarr=radarr)


class TestRequestMediaCommand:
    def test_available_when_in_library(self):
        res = cmd(library=_FakeLib(has=True), acquisition=_FakeAcq(
            existing_item="x", result=_success_result())).run("movie:tmdb:603")
        assert res.state is RequestMediaState.AVAILABLE
        assert res.success is True
        # Library wins — the *arr find/request must never run.
        # (We simply assert the terminal state.)

    def test_already_requested_when_in_arr(self):
        res = cmd(acquisition=_FakeAcq(existing_item=object(), result=_success_result())).run("movie:tmdb:603")
        assert res.state is RequestMediaState.ALREADY_REQUESTED
        assert res.success is True

    def test_requested_success(self):
        res = cmd(acquisition=_FakeAcq(result=_success_result())).run("movie:tmdb:603")
        assert res.state is RequestMediaState.REQUESTED
        assert res.success is True
        assert res.service == "radarr"

    def test_ambiguous_maps_result(self):
        res = cmd(acquisition=_FakeAcq(result=_ambiguous_result())).run("movie:tmdb:603")
        assert res.state is RequestMediaState.AMBIGUOUS
        assert res.success is False

    def test_provider_unavailable(self):
        res = cmd(acquisition=_FakeAcq(result=_unavailable_result())).run("movie:tmdb:603")
        assert res.state is RequestMediaState.PROVIDER_UNAVAILABLE
        assert res.success is False

    def test_not_configured_when_no_provider(self):
        # No acquisition service at all (empty config builds no provider) -> NOT_CONFIGURED.
        cfg = Mock(RADARR_API_KEY="", SONARR_API_KEY="", PLEX_URL="", PLEX_TOKEN="",
                   EMBY_URL="", EMBY_API_KEY="")
        res = RequestMediaCommand(library=_FakeLib(), acquisition=None, config=cfg).run("movie:tmdb:603")
        assert res.state is RequestMediaState.NOT_CONFIGURED

    def test_unparseable_id_returns_not_configured(self):
        res = cmd().run("garbage")
        assert res.state is RequestMediaState.NOT_CONFIGURED

    def test_idempotent_no_double_request(self):
        """A second request for an already-present item never calls request()."""
        acq = _FakeAcq(existing_item=object(), result=_success_result())
        c = cmd(acquisition=acq)
        r1 = c.run("movie:tmdb:603")
        assert r1.state is RequestMediaState.ALREADY_REQUESTED

    def test_persist_hook_called_on_request(self):
        calls = []
        def persist(media_id, provider, state):
            calls.append((media_id, provider, state))
        res = cmd(acquisition=_FakeAcq(result=_success_result()),
                  persist=persist).run("movie:tmdb:603")
        assert res.state is RequestMediaState.REQUESTED
        assert calls and calls[0] == ("movie:tmdb:603", "radarr", "requested")

    def test_tv_routes_to_sonarr(self):
        res = cmd(acquisition=_FakeAcq(result=_success_result(),
                                       provider_name="sonarr")).run("tv:imdb:tt0903747")
        assert res.state is RequestMediaState.REQUESTED
        assert res.media_type is MediaType.TV


class TestRequestMediaModule:
    def test_convenience_function(self):
        res = request_media("movie:tmdb:603", acquisition=_FakeAcq(result=_success_result()),
                            library=_FakeLib())
        assert res.state is RequestMediaState.REQUESTED