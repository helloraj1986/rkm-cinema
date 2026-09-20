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
from services.subtitles import (auto_pick_basis, auto_pick_blocked, auto_pick_candidate,
                                auto_pick_language, auto_pick_shortfall, has_local_track_in,
                                merge_subtitle_rows, normalise_auto_pick_settings,
                                rank_results, search_keywords)

SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"
TRACKS = [{"index": 0, "name": "English", "language": "eng"},
          {"index": 1, "name": "English (SDH)", "language": "eng"}]


class FakeLib:
    """Only the surface the subtitle routes/services use."""

    def __init__(self, tracks=None, context=None, path="/data/Movies/Film.2009.mp4",
                 audio=None):
        self.tracks = TRACKS if tracks is None else tracks
        # ⚠ The item's OWN audio language, which the auto-pick's exclusion reads
        # (`auto_pick_skip_audio`, his decision 2). ``None`` = Jellyfin told us nothing.
        self.audio = audio
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
        info = {"subtitles": list(self.tracks), "media_source_id": "ms1"}
        if self.audio is not None:
            info["audio"] = list(self.audio)
        return info

    def subtitle_search_context(self, item_id):
        return dict(self.context)


class RouteTransport:
    """A transport that answers by URL instead of by call order.

    Order-based scripting made these tests fragile (a select route that legitimately
    fetches a download link consumed the search stub), and a wrong order produced a
    confusing 400 instead of the behaviour under test. Routing on the URL keeps each
    fake honest: search stubs answer ``/subtitles``, download stubs answer
    ``/download``, and the pre-signed link returns the subtitle bytes.

    ⚠ ``/login`` and ``/infos/user`` answer too, because the auto-pick asks the ACCOUNT
    for its allowance before it spends a download (SUBTITLE_AUTOPICK_PLAN §2, gate 5).
    """

    def __init__(self, search=None, download=None, content=SRT, search_status=200,
                 download_status=200, remaining=3, allowed=20):
        self.search, self.download, self.content = search, download, content
        self.search_status, self.download_status = search_status, download_status
        self.remaining, self.allowed = remaining, allowed
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
        if url.endswith("/login"):
            return TransportResponse(status=200, headers={},
                                     body=json.dumps({"token": "jwt-token"}).encode())
        if url.endswith("/infos/user"):
            return TransportResponse(status=200, headers={}, body=json.dumps({
                "data": {"allowed_downloads": self.allowed,
                         "remaining_downloads": self.remaining,
                         "level": "Bronze"}}).encode())
        return TransportResponse(status=200, headers={}, body=self.content)

    def count(self, suffix: str) -> int:
        """How many requests this transport saw for a URL ending — the cheap-order proof."""
        return len([1 for _, url, _, _ in self.calls if url.endswith(suffix)])


def ok_client(transport=None, login=False):
    """A real OpenSubtitlesClient over a fake transport (no network, ever).

    ⚠ ``login=True`` is the ACCOUNT tier, and it is what makes the quota KNOWABLE before a
    download: without a login `/infos/user` is unavailable and the allowance is only
    reported on a download, which is exactly the state that answers ``quota_unknown``.
    """
    cfg = SimpleNamespace(OPENSUBTITLES_API_KEY="k" * 8,
                          OPENSUBTITLES_USERNAME="rajeev" if login else None,
                          OPENSUBTITLES_PASSWORD="p" * 8 if login else None,
                          OPENSUBTITLES_LANGUAGES="en")
    cfg.has_opensubtitles = lambda: True
    cfg.has_opensubtitles_login = lambda: bool(login)
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
        assert store.load() == {"prefs": {}, "usage": {}, "settings": {}}
        assert store.preference("ITEM") is None
        assert store.usage_count("os:111") == 0
        # ⚠ The DEFAULTS of a store that has never been written: auto-pick ON (his decision),
        # nothing excluded.
        assert store.settings() == {"auto_pick": True, "auto_pick_skip_audio": []}

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
        assert store.load() == {"prefs": {}, "usage": {}, "settings": {}}
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
        remote = [SimpleNamespace(subtitle_id="os:111", file_id=111, provider="opensubtitles",
                                  language="en", display_title="Film.2009.WEB-DL",
                                  download_count=10, hearing_impaired=False, format="srt",
                                  vendor_format="eng-full", year=2009)]
        rows = merge_subtitle_rows(TRACKS, remote, counts={"os:111": 4}, active_index=1)
        assert [r["provider"] for r in rows] == ["local", "local", "opensubtitles"]
        assert rows[1]["active"] is True and rows[0]["active"] is False
        assert rows[2]["used_count"] == 4 and rows[2]["index"] is None
        # the provider file id rides along so a client need not parse "os:<id>"
        assert rows[2]["file_id"] == 111 and rows[0]["file_id"] is None

    def test_the_row_the_user_chose_is_the_one_marked_active(self):
        """MEASURED LIVE 2026-09-12 (user report): a download succeeded, the track was
        attached, and the row the user had clicked still looked unselected — remote rows
        were hard-coded `active: False`, so only the derived local track could ever show
        the tick, and that row is not in the panel until the player reloads its tracks.
        """
        remote = [SimpleNamespace(subtitle_id="os:682960", file_id=682960,
                                  provider="opensubtitles", language="en",
                                  display_title="3 Deewarein (2003)", download_count=10,
                                  hearing_impaired=False, format="srt",
                                  vendor_format="srt", year=2003)]
        rows = merge_subtitle_rows(TRACKS, remote, counts={"os:682960": 1},
                                   active_index=0, active_subtitle_id="os:682960")
        chosen = [r for r in rows if r["subtitle_id"] == "os:682960"][0]
        assert chosen["active"] is True
        # exactly one row is ticked: the delivery of that choice is the SAME subtitle,
        # so the local track it resolved to must not light up as a second selection
        assert [r for r in rows if r["active"]] == [chosen]
        assert [r["active"] for r in rows if r["local"]] == [False, False]

    def test_a_stored_choice_still_marks_its_row_when_no_track_matches(self):
        """The file may be gone or re-indexed: the choice is still the user's choice."""
        remote = [SimpleNamespace(subtitle_id="os:5", file_id=5, provider="opensubtitles",
                                  language="en", display_title="Some.Release", download_count=1,
                                  hearing_impaired=False, format="srt",
                                  vendor_format="srt", year=2019)]
        rows = merge_subtitle_rows(TRACKS, remote, active_index=None,
                                   active_subtitle_id="os:5")
        assert [r["active"] for r in rows] == [False, False, True]

    def test_with_no_remote_choice_the_local_track_keeps_the_tick(self):
        rows = merge_subtitle_rows(TRACKS, [], active_index=1)
        assert [r["active"] for r in rows] == [False, True]

    def test_episodes_search_by_series_title_and_numbers(self):
        assert search_keywords({"type": "Episode", "series_name": "Chernobyl", "year": 2019,
                                "season": 1, "episode": 1, "tmdb_id": 999}) == {
            "title": "Chernobyl", "year": 2019, "season": 1, "episode": 1}

    def test_movies_prefer_ids_then_fall_back_to_the_title(self):
        assert search_keywords({"type": "Movie", "tmdb_id": 5, "name": "x"}) == {"tmdb_id": 5}
        assert search_keywords({"type": "Movie", "imdb_id": "tt1"}) == {"imdb_id": "tt1"}
        assert search_keywords({"type": "Movie", "name": "Some Film", "year": 2001}) == {
            "title": "Some Film", "year": 2001}


class DeadTransport:
    """Every request fails the way a dead network fails."""

    def __init__(self, exc=None):
        self.exc = exc or OSError("connection refused")
        self.calls = 0

    def request(self, method, url, *, headers=None, params=None, json_body=None, timeout=None):
        self.calls += 1
        raise self.exc


def dead_client(exc=None):
    cfg = SimpleNamespace(OPENSUBTITLES_API_KEY="k" * 8, OPENSUBTITLES_USERNAME=None,
                          OPENSUBTITLES_PASSWORD=None, OPENSUBTITLES_LANGUAGES="en")
    cfg.has_opensubtitles = lambda: True
    cfg.has_opensubtitles_login = lambda: False
    cfg.opensubtitles_languages = lambda: ["en"]
    return OpenSubtitlesClient(config=cfg, transport=DeadTransport(exc))


def unconfigured_client():
    """A client with no API key — it refuses locally, without a request."""
    cfg = SimpleNamespace(OPENSUBTITLES_API_KEY=None, OPENSUBTITLES_USERNAME=None,
                          OPENSUBTITLES_PASSWORD=None, OPENSUBTITLES_LANGUAGES="en")
    cfg.has_opensubtitles = lambda: False
    cfg.has_opensubtitles_login = lambda: False
    cfg.opensubtitles_languages = lambda: ["en"]
    return OpenSubtitlesClient(config=cfg)


# ------------------------------------------------------- failure paths (Phase 5)
class TestFailurePaths:
    """The rule the plan states as criterion 10: a subtitle problem degrades the FEATURE,
    never the app. Playback, seeking and the item's own subtitles must keep working while
    OpenSubtitles is unreachable, misconfigured, out of quota, or answering nonsense.
    """

    def _search(self, client, **kw):
        return client.get("/api/jellyfin/subtitle-search?id=abc&language=en", **kw)

    def test_a_dead_network_is_a_warning_and_the_local_tracks_still_come_back(
            self, monkeypatch, client):
        monkeypatch.setattr(subs_route, "build_opensubtitles_client",
                            lambda cfg=None: dead_client())
        r = self._search(client)
        assert r.status_code == 200                      # never a 500, never a broken panel
        body = r.json()
        assert body["enabled"] is True                   # configured — the VENDOR is down
        assert body["remote_count"] == 0
        assert body["warning"]
        local = [row for row in body["results"] if row["local"]]
        assert [row["index"] for row in local] == [0, 1]  # own subtitles untouched, usable
        assert [row["display_title"] for row in local] == ["English", "English (SDH)"]

    def test_a_vendor_payload_we_did_not_expect_does_not_500_the_listing(
            self, monkeypatch, client):
        # A shape change (or a parser bug) is not a typed OpenSubtitlesError. The listing
        # is passive, so it must STILL degrade to the local tracks.
        monkeypatch.setattr(subs_route, "build_opensubtitles_client",
                            lambda cfg=None: dead_client(ValueError("unexpected payload")))
        r = self._search(client)
        assert r.status_code == 200
        assert r.json()["warning"] and r.json()["remote_count"] == 0
        assert any(row["local"] for row in r.json()["results"])

    def test_a_search_never_asks_the_vendor_when_it_is_not_configured(
            self, monkeypatch, client):
        client.cfg.has_opensubtitles = lambda: False
        dead = dead_client()
        monkeypatch.setattr(subs_route, "build_opensubtitles_client", lambda cfg=None: dead)
        r = self._search(client)
        assert r.status_code == 200
        assert r.json()["enabled"] is False
        assert "OPENSUBTITLES_API_KEY" in r.json()["warning"]
        assert dead.transport.calls == 0                 # refused locally, no request spent
        assert any(row["local"] for row in r.json()["results"])

    def test_select_without_a_key_is_503_and_names_the_setting(self, monkeypatch, client):
        monkeypatch.setattr(subs_route, "build_opensubtitles_client",
                            lambda cfg=None: unconfigured_client())
        r = client.post("/api/jellyfin/subtitle-select",
                        json={"item_id": "abc", "file_id": 111, "language": "en"})
        assert r.status_code == 503                      # NOT 500
        assert "OPENSUBTITLES_API_KEY" in r.json()["detail"]

    def test_select_while_the_network_is_down_is_502(self, monkeypatch, client):
        monkeypatch.setattr(subs_route, "build_opensubtitles_client",
                            lambda cfg=None: dead_client())
        r = client.post("/api/jellyfin/subtitle-select",
                        json={"item_id": "abc", "file_id": 111, "language": "en"})
        assert r.status_code == 502 and r.json()["detail"]
        # nothing was attached and no preference was invented
        assert client.fake_lib.uploads == []
        assert client.fake_lib.refreshes == []

    def test_turning_subtitles_off_works_with_the_vendor_down(self, monkeypatch, client):
        # No client is involved in this one — proving "off" stays available offline.
        monkeypatch.setattr(subs_route, "build_opensubtitles_client",
                            lambda cfg=None: dead_client())
        r = client.post("/api/jellyfin/subtitle-disable", json={"item_id": "abc"})
        assert r.status_code == 200 and r.json()["disabled"] is True

    def test_a_leftover_quota_counter_is_reported_on_the_row_not_as_an_error(
            self, monkeypatch, client):
        # Quota exhaustion is a STATE, not a failure of the listing: the panel still lists
        # everything (so the user can see what they have) and says how many are left.
        monkeypatch.setattr(subs_route, "build_opensubtitles_client",
                            lambda cfg=None: ok_client(RouteTransport(search_status=429)))
        r = self._search(client)
        assert r.status_code == 200
        assert r.json()["warning"]


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


# =====================================================================================
# THE AUTO-PICK (SUBTITLE_AUTOPICK_PLAN §2 — his decision, 2026-09-21)
#
# *"apply the most downloaded subtitle automatically by default .. user can choose to off it
# later"*. Four decisions came with it: fire on FIRST PLAY when the title has no subtitle of
# its own in that language (and spend nothing when the quota is 0 OR unknown); a GLOBAL switch
# + per-title `Off` + a per-language exclusion; the FIRST entry of the configured list as the
# language; and NEVER a hearing-impaired track.
#
# ⚠ The rule has two halves and the ORDER between them is itself a claim: every gate knowable
# locally must answer BEFORE a single request is made. `transport.count("/subtitles") == 0` is
# how these tests hold that — a blocked title that still searched would be handing a
# metered account to a rule that had already declined.
# =====================================================================================

def os_row(file_id: int, download_count: int, *, language="en", hi=False, release="", local=False):
    """One OpenSubtitles result, in the WIRE shape (`attributes`/`files`)."""
    name = release or f"Film.2009.{file_id}"
    return {"attributes": {
        "subtitle_id": str(file_id), "language": language, "download_count": download_count,
        "format": "srt", "release": name, "hearing_impaired": hi,
        "files": [{"file_id": file_id, "file_name": f"{name}.srt"}],
        "feature_details": {"title": "Film", "year": 2009}}}


def search_payload(*rows):
    return {"data": list(rows)}


#: ⚠ THREE results, and the ordering of them is the test: the highest count (5000) is an SDH
#: track, so an auto-pick that took "the most downloaded" literally would take the one his
#: decision 4 forbids.
THREE_RESULTS = search_payload(
    os_row(111, 10, release="Film.2009.WEB-DL"),
    os_row(222, 900, release="Film.2009.BluRay.x264-MOST"),
    os_row(333, 5000, hi=True, release="Film.2009.SDH"),
)
SDH_ONLY = search_payload(os_row(333, 5000, hi=True, release="Film.2009.SDH"))


class TestAutoPickRules:
    """The pure half — no store, no network. Each of these is a sentence from §2."""

    def test_the_language_is_the_first_entry_of_the_configured_list(self):
        assert auto_pick_language(["en", "hi"]) == "en"
        assert auto_pick_language(["Hindi", "en"]) == "hi"     # normalised, not literal
        assert auto_pick_language([]) == "en"                  # the fallback, never blank

    def test_the_switch_defaults_on_and_a_stored_false_is_off(self):
        assert normalise_auto_pick_settings({})["auto_pick"] is True
        assert normalise_auto_pick_settings({"auto_pick": False})["auto_pick"] is False

    def test_the_skip_list_is_normalised_so_English_means_en(self):
        s = normalise_auto_pick_settings({"auto_pick_skip_audio": ["English", "eng", "EN", ""]})
        assert s["auto_pick_skip_audio"] == ["en"]

    def test_an_item_whose_own_subtitle_is_eng_matches_the_en_auto_pick(self):
        # ⚠ Jellyfin says `eng`, OpenSubtitles says `en`: a literal comparison would download
        # a second English subtitle over a film that already has one.
        assert has_local_track_in([{"language": "eng"}], "en") is True
        assert has_local_track_in([{"language": "hin"}], "en") is False
        assert has_local_track_in([], "en") is False

    def test_the_candidate_is_the_top_of_the_panel_ranking(self):
        rows = [SimpleNamespace(subtitle_id="os:1", language="en", hearing_impaired=False,
                                download_count=10, file_id=1),
                SimpleNamespace(subtitle_id="os:2", language="en", hearing_impaired=False,
                                download_count=900, file_id=2)]
        assert auto_pick_candidate(rows, language="en").subtitle_id == "os:2"

    def test_our_own_usage_beats_the_provider_popularity(self):
        rows = [SimpleNamespace(subtitle_id="os:1", language="en", hearing_impaired=False,
                                download_count=10, file_id=1),
                SimpleNamespace(subtitle_id="os:2", language="en", hearing_impaired=False,
                                download_count=900, file_id=2)]
        got = auto_pick_candidate(rows, language="en", counts={"os:1": 1})
        assert got.subtitle_id == "os:1"
        assert auto_pick_basis(got, {"os:1": 1}) == "used-before"
        assert auto_pick_basis(got, {}) == "most-downloaded"

    def test_a_hearing_impaired_track_is_never_the_pick(self):
        rows = [SimpleNamespace(subtitle_id="os:1", language="en", hearing_impaired=True,
                                download_count=9999, file_id=1)]
        assert auto_pick_candidate(rows, language="en") is None            # his decision 4
        assert auto_pick_candidate(rows, language="en", allow_sdh=True) is not None

    def test_a_title_already_chosen_is_blocked_before_anything_else(self):
        assert auto_pick_blocked(settings={}, stored_preference={"subtitle_id": "os:1"},
                                 tracks=[], audio_language="", language="en") == "already_chosen"
        assert auto_pick_blocked(settings={}, stored_preference={"disabled": True},
                                 tracks=[], audio_language="", language="en") == "title_off"
        assert auto_pick_blocked(settings={"auto_pick": False}, stored_preference=None,
                                 tracks=[], audio_language="", language="en") == "disabled"
        assert auto_pick_blocked(settings={}, stored_preference=None,
                                 tracks=[{"language": "eng"}], audio_language="",
                                 language="en") == "has_local_track"
        assert auto_pick_blocked(settings={"auto_pick_skip_audio": ["English"]},
                                 stored_preference=None, tracks=[], audio_language="eng",
                                 language="en") == "audio_excluded"
        assert auto_pick_blocked(settings={}, stored_preference=None, tracks=[],
                                 audio_language="hin", language="en") == ""

    def test_the_quota_and_the_candidate_are_the_last_two_gates(self):
        candidate = object()
        assert auto_pick_shortfall(remaining=None, candidate=candidate) == "quota_unknown"
        assert auto_pick_shortfall(remaining=0, candidate=candidate) == "quota_exhausted"
        assert auto_pick_shortfall(remaining=3, candidate=None) == "no_candidate"
        assert auto_pick_shortfall(remaining=3, candidate=candidate) == ""
        # ⚠ A garbage value is UNKNOWN, not "plenty": the honest answer is the one that
        # spends nothing.
        assert auto_pick_shortfall(remaining="?", candidate=candidate) == "quota_unknown"


class TestAutoPickSettings:
    """The store's `settings` block, and the trap it was written around."""

    def test_settings_default_to_on_with_nothing_excluded(self, store):
        assert store.settings() == {"auto_pick": True, "auto_pick_skip_audio": []}

    def test_a_settings_write_survives_a_preference_write(self, store):
        # ⚠⚠ THE TRAP: `_mutate` writes back what `load()` returned, so a block `load()` did
        # not carry would be ERASED by the next subtitle the user chose — and nothing about
        # that write would look wrong.
        store.update_settings(auto_pick=False)
        store.set_preference("ITEM", subtitle_id="os:1", language="en")
        assert store.settings()["auto_pick"] is False
        store.record_use("ITEM", subtitle_id="os:1", language="en")
        assert store.settings()["auto_pick"] is False
        assert json.loads(store.path.read_text(encoding="utf-8"))["settings"]["auto_pick"] is False

    def test_the_update_is_partial_so_one_control_cannot_reset_the_other(self, store):
        store.update_settings(auto_pick_skip_audio=["en"])
        assert store.settings()["auto_pick"] is True          # untouched
        store.update_settings(auto_pick=False)
        assert store.settings()["auto_pick_skip_audio"] == ["en"]   # untouched

    def test_the_skip_list_is_stored_as_iso_codes(self, store):
        store.update_settings(auto_pick_skip_audio=["English", "HIN"])
        assert store.settings()["auto_pick_skip_audio"] == ["en", "hi"]


class TestAutoPickRoute:
    """`POST /subtitle-auto` — the rule, composed in the order that costs nothing first."""

    def _wire(self, monkeypatch, tmp_path, *, tracks=None, audio=None, login=True,
              transport=None, remaining=3):
        cfg = SimpleNamespace(WATCHLIST_DB_PATH=str(tmp_path / "rkm" / "watchlist.json"),
                              OPENSUBTITLES_LANGUAGES="en")
        cfg.has_opensubtitles = lambda: True
        cfg.opensubtitles_languages = lambda: ["en"]
        lib = FakeLib(tracks=tracks, audio=audio)
        transport = transport or RouteTransport(search=THREE_RESULTS, remaining=remaining)
        monkeypatch.setattr(subs_route, "get_config", lambda: cfg)
        monkeypatch.setattr(subs_route, "build_library_service", lambda cfg=None: lib)
        monkeypatch.setattr(subs_route, "build_opensubtitles_client",
                            lambda cfg=None: ok_client(transport, login=login))
        c = TestClient(app)
        c.fake_lib, c.cfg, c.transport = lib, cfg, transport
        return c

    def test_a_fresh_title_is_given_the_best_result_and_remembers_it(self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=[], audio=[{"language": "eng"}])
        r = c.post("/api/jellyfin/subtitle-auto", json={"item_id": "ITEM"})
        assert r.status_code == 200
        body = r.json()
        assert body["decision"] == "apply" and body["ok"] is True
        # ⚠ NOT 333 (5000 downloads) — that one is hearing-impaired.
        assert body["applied"]["subtitle_id"] == "os:222"
        assert body["applied"]["basis"] == "most-downloaded"
        assert body["used_count"] == 1
        # ⚠ The delivery really happened, and the choice is in the STORE — which is the half
        # that must survive: the fake library does not gain a track (nothing did the attach),
        # so `preferred_subtitle` resolving to an index is only meaningful on a real stack.
        assert c.fake_lib.uploads and c.fake_lib.refreshes == ["ITEM"]
        stored = json.loads((Path(c.cfg.WATCHLIST_DB_PATH).parent / "subtitles.json")
                            .read_text(encoding="utf-8"))
        assert stored["prefs"]["ITEM"]["subtitle_id"] == "os:222"
        assert stored["prefs"]["ITEM"]["disabled"] is False
        # ⚠ REMEMBERED, exactly as a hand pick is: this is what makes it cost ONE download
        # per title, ever — the second play finds a stored choice and the rule stands down.
        assert c.transport.count("/download") == 1
        second = c.post("/api/jellyfin/subtitle-auto", json={"item_id": "ITEM"}).json()
        assert second["decision"] == "already_chosen" and second["applied"] is None
        assert c.transport.count("/download") == 1

    def test_the_api_asks_the_account_before_it_spends_a_download(self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=[], login=True)
        c.post("/api/jellyfin/subtitle-auto", json={"item_id": "ITEM"})
        assert c.transport.count("/infos/user") == 1

    def test_an_anonymous_key_cannot_promise_a_download_so_nothing_is_attempted(
            self, monkeypatch, tmp_path):
        # His decision 1: 0 OR UNKNOWN quota → no attempt. Without a login the allowance is
        # only reported ON a download, so the api cannot promise this one will succeed.
        c = self._wire(monkeypatch, tmp_path, tracks=[], login=False)
        body = c.post("/api/jellyfin/subtitle-auto", json={"item_id": "ITEM"}).json()
        assert body["decision"] == "quota_unknown"
        assert body["reason"] and "OpenSubtitles" in body["reason"]
        assert c.transport.count("/download") == 0
        assert c.fake_lib.uploads == [] and c.fake_lib.refreshes == []
        assert body["applied"] is None

    def test_a_known_zero_quota_is_reported_and_spends_nothing(self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=[], login=True, remaining=0)
        body = c.post("/api/jellyfin/subtitle-auto", json={"item_id": "ITEM"}).json()
        assert body["decision"] == "quota_exhausted" and body["remaining_downloads"] == 0
        assert c.transport.count("/download") == 0

    def test_the_switch_off_and_the_exclusions_never_reach_the_vendor(self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=[], audio=[{"language": "eng"}])
        assert c.post("/api/jellyfin/subtitle-settings",
                      json={"auto_pick": False}).json()["settings"]["auto_pick"] is False
        body = c.post("/api/jellyfin/subtitle-auto", json={"item_id": "ITEM"}).json()
        assert body["decision"] == "disabled"
        assert c.transport.count("/subtitles") == 0        # ⚠ the ORDER: nothing was spent

        c.post("/api/jellyfin/subtitle-settings", json={"auto_pick": True,
                                                        "auto_pick_skip_audio": ["English"]})
        body = c.post("/api/jellyfin/subtitle-auto", json={"item_id": "ITEM"}).json()
        assert body["decision"] == "audio_excluded"
        assert c.transport.count("/subtitles") == 0

    def test_a_title_with_its_own_english_subtitle_is_left_alone(self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=TRACKS)   # language `eng`
        body = c.post("/api/jellyfin/subtitle-auto", json={"item_id": "ITEM"}).json()
        assert body["decision"] == "has_local_track"
        assert c.transport.count("/subtitles") == 0
        assert body["preferred_subtitle"] is None

    def test_a_per_title_off_is_a_choice_the_auto_pick_respects(self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=[])
        c.post("/api/jellyfin/subtitle-disable", json={"item_id": "ITEM"})
        body = c.post("/api/jellyfin/subtitle-auto", json={"item_id": "ITEM"}).json()
        assert body["decision"] == "title_off"
        assert c.transport.count("/subtitles") == 0

    def test_an_sdh_only_answer_is_no_candidate_not_a_compromise(self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=[],
                       transport=RouteTransport(search=SDH_ONLY))
        body = c.post("/api/jellyfin/subtitle-auto", json={"item_id": "ITEM"}).json()
        assert body["decision"] == "no_candidate"
        assert c.transport.count("/download") == 0

    def test_a_vendor_outage_is_a_decision_and_never_a_500(self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=[])
        monkeypatch.setattr(subs_route, "build_opensubtitles_client",
                            lambda cfg=None: dead_client())
        r = c.post("/api/jellyfin/subtitle-auto", json={"item_id": "ITEM"})
        assert r.status_code == 200
        assert r.json()["decision"] == "unavailable" and r.json()["detail"]

    def test_a_failed_download_leaves_no_preference_behind(self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=[],
                       transport=RouteTransport(search=THREE_RESULTS, download_status=429))
        body = c.post("/api/jellyfin/subtitle-auto", json={"item_id": "ITEM"}).json()
        assert body["applied"] is None and body["decision"] in ("quota_exhausted", "unavailable")
        assert SubtitleStore(path=Path(c.cfg.WATCHLIST_DB_PATH).parent
                             / "subtitles.json").preference("ITEM") is None

    def test_it_is_a_400_without_an_item_id(self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=[])
        assert c.post("/api/jellyfin/subtitle-auto", json={}).status_code == 400

    def test_the_settings_route_round_trips_what_it_stored(self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=[])
        body = c.get("/api/jellyfin/subtitle-settings").json()
        assert body["settings"] == {"auto_pick": True, "auto_pick_skip_audio": []}
        assert body["language"] == "en" and body["enabled"] is True
        c.post("/api/jellyfin/subtitle-settings", json={"auto_pick": False,
                                                        "auto_pick_skip_audio": ["en"]})
        again = c.get("/api/jellyfin/subtitle-settings").json()
        assert again["settings"] == {"auto_pick": False, "auto_pick_skip_audio": ["en"]}

    def test_the_search_listing_carries_the_badge_the_pick_and_the_settings(
            self, monkeypatch, tmp_path):
        # ⚠ ONE payload for the badge, the settings row and the list: a client that had to ask
        # twice could render them disagreeing.
        c = self._wire(monkeypatch, tmp_path, tracks=[])
        body = c.get("/api/jellyfin/subtitle-search?id=ITEM").json()
        assert body["auto"]["subtitle_id"] == "os:222"       # not the SDH one
        assert body["auto"]["basis"] == "most-downloaded"
        assert body["auto"]["blocked"] == ""
        assert body["settings"]["auto_pick"] is True
        assert body["auto_language"] == "en"

    def test_the_badge_says_used_before_when_our_own_count_put_it_first(
            self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=[])
        store = SubtitleStore(path=Path(c.cfg.WATCHLIST_DB_PATH).parent / "subtitles.json")
        store.record_use("OTHER", subtitle_id="os:111", language="en")
        body = c.get("/api/jellyfin/subtitle-search?id=ITEM").json()
        assert body["auto"]["subtitle_id"] == "os:111"
        assert body["auto"]["basis"] == "used-before"

    def test_a_title_that_has_already_been_chosen_reports_the_block_on_the_listing(
            self, monkeypatch, tmp_path):
        c = self._wire(monkeypatch, tmp_path, tracks=[])
        c.post("/api/jellyfin/subtitle-select",
               json={"item_id": "ITEM", "file_id": 222, "language": "en"})
        body = c.get("/api/jellyfin/subtitle-search?id=ITEM").json()
        assert body["auto"]["blocked"] == "already_chosen"
        assert body["auto"]["reason"]
