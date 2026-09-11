"""Subtitle store + subtitle endpoints (SUBTITLES_OPENSUBTITLES_PLAN Phase 3).

No network and no real media drive: the library and the OpenSubtitles client are fakes,
and the store is pointed at ``tmp_path``. What is pinned here:

* preferences and usage are DIFFERENT things — prefs are per item and keep an IDENTITY
  (indices are positional), usage is per subtitle and is what ranks results;
* "off" is not "forgotten" — a disabled preference keeps its record;
* a corrupt store file degrades to empty instead of taking the feature down;
* a vendor failure degrades the SEARCH route only: local tracks still come back and
  playback is never blocked, while an action the user asked for surfaces a real error.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.routes.jellyfin_subtitles as subs_route
from api.main import app
from services.opensubtitles import (OpenSubtitlesClient, QuotaExhaustedError,
                                    TransportResponse, UnsupportedFormatError)
from services.subtitle_store import SubtitleStore, default_store_path, usage_key
from services.subtitles import merge_subtitle_rows, rank_results, search_keywords

SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"
TRACKS = [{"index": 0, "name": "English", "language": "eng"},
          {"index": 1, "name": "English (SDH)", "language": "eng"}]


class FakeLib:
    """Only the surface the subtitle routes/services use."""

    def __init__(self, tracks=None, context=None, path="/data/Movies/Film.2009.mp4"):
        self.tracks = TRACKS if tracks is None else tracks
        self.context = context or {"type": "Movie", "name": "Film", "year": 2009,
                                   "tmdb_id": 1234}
        self.path = path
        self.refreshes, self.uploads, self.scans = [], [], 0

    def item_path(self, item_id):
        return self.path

    def refresh_item(self, item_id):
        self.refreshes.append(item_id)
        return True

    def refresh_library(self):  # pragma: no cover - asserted never called
        self.scans += 1
        return True

    def upload_subtitle(self, item_id, file_name, content, language="", format=""):
        self.uploads.append((item_id, file_name))
        return True

    def playback_info(self, item_id):
        return {"subtitles": list(self.tracks), "media_source_id": "ms1"}

    def subtitle_search_context(self, item_id):
        return dict(self.context)


class RouteTransport:
    """A transport that answers by URL instead of by call order.

    Order-based scripting made these tests fragile (a select route that legitimately
    fetches a download link consumed the search stub), and a wrong order produced a
    confusing 400 instead of the behaviour under test. Routing on the URL keeps each
    fake honest: search stubs answer ``/subtitles``, download stubs answer
    ``/download``, and the pre-signed link returns the subtitle bytes.
    """

    def __init__(self, search=None, download=None, content=SRT, search_status=200,
                 download_status=200):
        self.search, self.download, self.content = search, download, content
        self.search_status, self.download_status = search_status, download_status
        self.calls = []

    def request(self, method, url, *, headers=None, params=None, json_body=None, timeout=None):
        self.calls.append((method, url, params, headers or {}))
        if url.endswith("/subtitles"):
            body = self.search if self.search is not None else SEARCH
            return TransportResponse(status=self.search_status, headers={},
                                     body=json.dumps(body).encode())
        if url.endswith("/download"):
            body = self.download if self.download is not None else DOWNLOAD
            return TransportResponse(status=self.download_status, headers={},
                                     body=json.dumps(body).encode())
        return TransportResponse(status=200, headers={}, body=self.content)


def ok_client(transport=None):
    """A real OpenSubtitlesClient over a fake transport (no network, ever)."""
    cfg = SimpleNamespace(OPENSUBTITLES_API_KEY="k" * 8, OPENSUBTITLES_USERNAME=None,
                          OPENSUBTITLES_PASSWORD=None, OPENSUBTITLES_LANGUAGES="en")
    cfg.has_opensubtitles = lambda: True
    cfg.has_opensubtitles_login = lambda: False
    cfg.opensubtitles_languages = lambda: ["en"]
    return OpenSubtitlesClient(config=cfg, transport=transport or RouteTransport())


def row(status=200, body=None):
    return TransportResponse(status=status, headers={},
                             body=json.dumps(body if body is not None else {}).encode())


SEARCH = {"data": [{"attributes": {
    "subtitle_id": "111", "language": "en", "download_count": 10, "format": "eng-full",
    "release": "Film.2009.WEB-DL", "files": [{"file_id": 111, "file_name": "Film.2009.WEB-DL.srt"}],
    "feature_details": {"title": "Film", "year": 2009}}}]}
DOWNLOAD = {"link": "https://dl.example/x?sig=1", "file_name": "Film.2009.WEB-DL.srt",
            "remaining": 3, "reset_time_utc": "2026-09-13T00:00:00Z"}


@pytest.fixture()
def store(tmp_path):
    return SubtitleStore(path=tmp_path / "rkm" / "subtitles.json")


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """A client wired to fakes, with the store pointed at tmp_path."""
    cfg = SimpleNamespace(WATCHLIST_DB_PATH=str(tmp_path / "rkm" / "watchlist.json"),
                          OPENSUBTITLES_LANGUAGES="en")
    cfg.has_opensubtitles = lambda: True
    cfg.opensubtitles_languages = lambda: ["en"]
    lib = FakeLib()
    monkeypatch.setattr(subs_route, "get_config", lambda: cfg)
    monkeypatch.setattr(subs_route, "build_library_service", lambda cfg=None: lib)
    transport = RouteTransport()
    monkeypatch.setattr(subs_route, "build_opensubtitles_client",
                        lambda cfg=None: ok_client(transport))
    c = TestClient(app)
    c.fake_lib = lib
    c.cfg = cfg
    return c


# ----------------------------------------------------------------------- the store
class TestStoreBasics:
    def test_an_absent_store_is_empty_not_an_error(self, store):
        assert store.load() == {"prefs": {}, "usage": {}}
        assert store.preference("ITEM") is None
        assert store.usage_count("os:111") == 0

    def test_the_store_lives_beside_the_watchlist(self):
        assert default_store_path("/data/rkm/watchlist.json") == Path("/data/rkm/subtitles.json")
        assert default_store_path(None) == Path("/data/rkm/subtitles.json")

    def test_usage_keys_accept_both_forms(self):
        assert usage_key("os:123456") == "123456"
        assert usage_key("123456") == "123456"

    def test_a_preference_records_an_identity_not_an_index(self, store):
        rec = store.set_preference("ITEM", subtitle_id="os:111", language="en",
                                   display_title="Film.2009.WEB-DL")
        assert rec["subtitle_id"] == "os:111" and rec["disabled"] is False
        assert "index" not in rec
        assert store.preference("ITEM")["display_title"] == "Film.2009.WEB-DL"

    def test_a_preference_write_is_atomic_and_leaves_no_temp(self, store):
        store.set_preference("ITEM", subtitle_id="os:1", language="en")
        assert store.path.exists()
        assert list(store.path.parent.glob("*.rkm-tmp")) == []

    def test_a_corrupt_store_degrades_to_empty_and_does_not_crash(self, store):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("{not json at all", encoding="utf-8")
        assert store.load() == {"prefs": {}, "usage": {}}
        assert store.preference("ITEM") is None
        # the damaged file is left alone until something is actually written
        assert store.path.read_text(encoding="utf-8") == "{not json at all"

    def test_a_corrupt_store_can_still_be_written_to(self, store):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("garbage", encoding="utf-8")
        store.set_preference("ITEM", subtitle_id="os:9", language="en")
        assert store.preference("ITEM")["subtitle_id"] == "os:9"


class TestUsage:
    def test_usage_increments_per_subtitle(self, store):
        assert store.record_use("ITEM", subtitle_id="os:111", language="en") == 1
        assert store.record_use("ITEM", subtitle_id="os:111", language="en") == 2
        assert store.usage_count("os:111") == 2
        assert store.usage_count("111") == 2          # both forms are one counter

    def test_usage_is_global_across_items(self, store):
        store.record_use("ITEM_A", subtitle_id="os:111", language="en")
        store.record_use("ITEM_B", subtitle_id="os:111", language="en")
        assert store.usage_count("os:111") == 2

    def test_usage_records_when_and_where(self, store):
        store.record_use("ITEM", subtitle_id="os:111", language="en",
                         display_title="Film.2009")
        data = store.load()["usage"]["111"]
        assert data["media_id"] == "ITEM" and data["last_used"].endswith("Z")
        assert store.last_used("os:111").endswith("Z")

    def test_usage_counts_map_for_ranking(self, store):
        store.record_use("A", subtitle_id="os:1", language="en")
        store.record_use("A", subtitle_id="os:2", language="en")
        store.record_use("A", subtitle_id="os:2", language="en")
        assert store.usage_counts() == {"os:1": 1, "os:2": 2}


class TestDisableIsNotForget:
    def test_disable_keeps_the_choice(self, store):
        store.set_preference("ITEM", subtitle_id="os:111", language="en",
                             display_title="Film.2009")
        store.disable("ITEM")
        pref = store.preference("ITEM")
        assert pref["disabled"] is True
        assert pref["subtitle_id"] == "os:111"        # re-enabling is one tap

    def test_re_enabling_restores_it(self, store):
        store.set_preference("ITEM", subtitle_id="os:111", language="en")
        store.disable("ITEM")
        store.set_preference("ITEM", subtitle_id="os:111", language="en")
        assert store.preference("ITEM")["disabled"] is False

    def test_clear_forgets_entirely(self, store):
        store.set_preference("ITEM", subtitle_id="os:111", language="en")
        assert store.clear_preference("ITEM") is True
        assert store.preference("ITEM") is None
        assert store.clear_preference("ITEM") is False


class TestResolvePreference:
    def test_resolves_the_stored_identity_to_a_current_index(self, store):
        store.set_preference("ITEM", subtitle_id="os:111", language="en",
                             display_title="English (SDH)")
        assert store.preferred_subtitle("ITEM", TRACKS)["index"] == 1

    def test_a_disabled_preference_resolves_to_nothing(self, store):
        store.set_preference("ITEM", subtitle_id="os:111", language="en")
        store.disable("ITEM")
        assert store.preferred_subtitle("ITEM", TRACKS) is None

    def test_no_preference_is_none(self, store):
        assert store.preferred_subtitle("ITEM", TRACKS) is None

    def test_an_unmatched_identity_applies_nothing(self, store):
        """Never silently substitute a different subtitle for the chosen one."""
        store.set_preference("ITEM", subtitle_id="os:111", language="fr",
                             display_title="Some.Other.Release")
        assert store.preferred_subtitle("ITEM", TRACKS) is None

    def test_the_resolved_row_carries_the_usage_count(self, store):
        store.set_preference("ITEM", subtitle_id="os:111", language="en",
                             display_title="English")
        store.record_use("ITEM", subtitle_id="os:111", language="en")
        store.record_use("ITEM", subtitle_id="os:111", language="en")
        assert store.preferred_subtitle("ITEM", TRACKS)["used_count"] == 2


# ------------------------------------------------------------------ pure helpers
class TestRanking:
    def test_our_usage_beats_the_providers_popularity(self):
        a = SimpleNamespace(subtitle_id="os:1", download_count=999)
        b = SimpleNamespace(subtitle_id="os:2", download_count=1)
        assert [r.subtitle_id for r in rank_results([a, b], {"os:2": 3})] == ["os:2", "os:1"]

    def test_ties_fall_back_to_download_count_then_identity(self):
        a = SimpleNamespace(subtitle_id="os:1", download_count=5)
        b = SimpleNamespace(subtitle_id="os:2", download_count=50)
        assert [r.subtitle_id for r in rank_results([a, b], {})] == ["os:2", "os:1"]

    def test_rows_put_local_tracks_first_and_mark_the_active_one(self):
        remote = [SimpleNamespace(subtitle_id="os:111", provider="opensubtitles",
                                  language="en", display_title="Film.2009.WEB-DL",
                                  download_count=10, hearing_impaired=False, format="srt",
                                  vendor_format="eng-full", year=2009)]
        rows = merge_subtitle_rows(TRACKS, remote, counts={"os:111": 4}, active_index=1)
        assert [r["provider"] for r in rows] == ["local", "local", "opensubtitles"]
        assert rows[1]["active"] is True and rows[0]["active"] is False
        assert rows[2]["used_count"] == 4 and rows[2]["index"] is None

    def test_episodes_search_by_series_title_and_numbers(self):
        assert search_keywords({"type": "Episode", "series_name": "Chernobyl", "year": 2019,
                                "season": 1, "episode": 1, "tmdb_id": 999}) == {
            "title": "Chernobyl", "year": 2019, "season": 1, "episode": 1}

    def test_movies_prefer_ids_then_fall_back_to_the_title(self):
        assert search_keywords({"type": "Movie", "tmdb_id": 5, "name": "x"}) == {"tmdb_id": 5}
        assert search_keywords({"type": "Movie", "imdb_id": "tt1"}) == {"imdb_id": "tt1"}
        assert search_keywords({"type": "Movie", "name": "Some Film", "year": 2001}) == {
            "title": "Some Film", "year": 2001}


# ----------------------------------------------------------------------- endpoints
class TestSearchRoute:
    def test_local_tracks_come_back_even_with_no_result(self, client):
        client.fake_lib.tracks = TRACKS
        r = client.get("/api/jellyfin/subtitle-search?id=ITEM")
        assert r.status_code == 200
        body = r.json()
        assert body["local_count"] == 2 and body["remote_count"] == 1
        assert [row["provider"] for row in body["results"]] == ["local", "local", "opensubtitles"]
        assert body["enabled"] is True and body["language"] == "en"

    def test_a_vendor_failure_degrades_the_search_not_the_request(self, monkeypatch, client):
        monkeypatch.setattr(subs_route, "build_opensubtitles_client",
                            lambda cfg=None: ok_client(RouteTransport(search_status=429)))
        r = client.get("/api/jellyfin/subtitle-search?id=ITEM")
        assert r.status_code == 200           # playback must never be blocked
        body = r.json()
        assert body["local_count"] == 2 and body["remote_count"] == 0
        assert "limit" in body["warning"].lower()

    def test_a_missing_item_id_is_404(self, client):
        assert client.get("/api/jellyfin/subtitle-search").status_code == 404

    def test_no_credential_field_is_ever_returned(self, client):
        payload = client.get("/api/jellyfin/subtitle-search?id=ITEM").text.lower()
        for token in ("api_key", "api-key", "password", "token"):
            assert token not in payload


class TestSelectRoute:
    def test_select_delivers_persists_and_counts(self, client):
        r = client.post("/api/jellyfin/subtitle-select",
                        json={"item_id": "ITEM", "file_id": 111, "language": "en",
                              "display_title": "Film.2009.WEB-DL"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True and body["used_count"] == 1
        assert body["delivered"] in ("sidecar", "upload")
        assert body["preferred_subtitle"]["language"] == "en"
        # ... and it is really in the store on disk
        stored = json.loads((Path(client.cfg.WATCHLIST_DB_PATH).parent
                             / "subtitles.json").read_text(encoding="utf-8"))
        assert stored["prefs"]["ITEM"]["subtitle_id"] == "os:111"
        assert stored["usage"]["111"]["count"] == 1

    def test_selecting_twice_keeps_counting_usage(self, client):
        for _ in range(2):
            client.post("/api/jellyfin/subtitle-select",
                        json={"item_id": "ITEM", "file_id": 111, "language": "en"})
        body = client.get("/api/jellyfin/subtitle-search?id=ITEM").json()
        remote = [r for r in body["results"] if not r["local"]]
        assert remote[0]["used_count"] == 2

    def test_select_without_ids_is_400(self, client):
        assert client.post("/api/jellyfin/subtitle-select", json={"item_id": "ITEM"}).status_code == 400
        assert client.post("/api/jellyfin/subtitle-select", json={"file_id": 1}).status_code == 400

    def test_a_quota_failure_is_429_with_a_message(self, monkeypatch, client):
        monkeypatch.setattr(subs_route, "build_opensubtitles_client",
                            lambda cfg=None: ok_client(RouteTransport(download_status=429)))
        r = client.post("/api/jellyfin/subtitle-select",
                        json={"item_id": "ITEM", "file_id": 111, "language": "en"})
        assert r.status_code == 429 and "limit" in r.json()["detail"].lower()

    def test_a_bad_format_is_400_not_500(self, monkeypatch, client):
        monkeypatch.setattr(subs_route, "build_opensubtitles_client",
                            lambda cfg=None: ok_client(RouteTransport(
                                download={**DOWNLOAD, "file_name": "x.idx"})))
        r = client.post("/api/jellyfin/subtitle-select",
                        json={"item_id": "ITEM", "file_id": 111, "language": "en"})
        assert r.status_code == 400


class TestDisableRoute:
    def test_disable_then_search_reports_it(self, client):
        client.post("/api/jellyfin/subtitle-select",
                    json={"item_id": "ITEM", "file_id": 111, "language": "en"})
        r = client.post("/api/jellyfin/subtitle-disable", json={"item_id": "ITEM"})
        assert r.status_code == 200 and r.json()["disabled"] is True
        body = client.get("/api/jellyfin/subtitle-search?id=ITEM").json()
        assert body["disabled"] is True and body["preferred_subtitle"] is None

    def test_disable_without_an_item_is_400(self, client):
        assert client.post("/api/jellyfin/subtitle-disable", json={}).status_code == 400


class TestPlaybackInfoAdditive:
    def test_playback_info_carries_the_preferred_subtitle(self, client, monkeypatch):
        from api.routes import jellyfin_tracks as tracks_route
        monkeypatch.setattr(tracks_route, "get_config", lambda: SimpleNamespace(
            JELLYFIN_URL="http://jellyfin:8096", JELLYFIN_API_KEY="k",
            WATCHLIST_DB_PATH=client.cfg.WATCHLIST_DB_PATH))
        monkeypatch.setattr(tracks_route, "build_library_service",
                            lambda cfg=None: client.fake_lib)
        client.post("/api/jellyfin/subtitle-select",
                    json={"item_id": "ITEM", "file_id": 111, "language": "en",
                          "display_title": "English (SDH)"})
        body = client.get("/api/jellyfin/playback-info?id=ITEM").json()
        assert body["subtitles"] and "preferred_subtitle" in body
        assert body["preferred_subtitle"]["index"] == 1

    def test_playback_info_still_works_with_no_store(self, client, monkeypatch):
        from api.routes import jellyfin_tracks as tracks_route
        monkeypatch.setattr(tracks_route, "get_config", lambda: SimpleNamespace(
            JELLYFIN_URL="http://jellyfin:8096", JELLYFIN_API_KEY="k",
            WATCHLIST_DB_PATH=client.cfg.WATCHLIST_DB_PATH))
        monkeypatch.setattr(tracks_route, "build_library_service",
                            lambda cfg=None: client.fake_lib)
        body = client.get("/api/jellyfin/playback-info?id=ITEM").json()
        assert body["preferred_subtitle"] is None
