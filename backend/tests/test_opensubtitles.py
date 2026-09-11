"""OpenSubtitles client tests (SUBTITLES_OPENSUBTITLES_PLAN Phase 1).

The plan is explicit: **no live calls in this suite**. Every test drives a fake
transport that records the request and replays a scripted response, so the suite costs
zero downloads and zero quota — the one live download the plan allows happens in
Phase 2, deliberately, against the real stack.

Two behaviours here are worth more than the happy path:

* the **quota** is never guessed — ``remaining``/``allowed_downloads`` are read from
  the API at runtime, and a 429 is classified as "quota spent" vs "slow down" from the
  body, because the advice differs completely;
* a **download POST is never retried** (it may already have been charged) while an
  idempotent GET is retried exactly once.
"""
import json
from types import SimpleNamespace

import pytest

from services.opensubtitles import (AuthFailedError, DownloadedSubtitle, NotConfiguredError,
                                    NoResultsError, OpenSubtitlesClient, OpenSubtitlesError,
                                    QuotaExhaustedError, RateLimitedError, TransportError,
                                    TransportResponse, UnsupportedFormatError, _imdb_digits,
                                    _looks_like_quota, format_supported, safe_url)

API_KEY = "k" * 32
PASSWORD = "p#ss w0rd-secret"
LOGIN_TOKEN = "jwt-token-that-must-never-be-logged"
DOWNLOAD_LINK = "https://dl.opensubtitles.com/download/abc?token=SECRET-TOKEN-IN-QUERY"


# ------------------------------------------------------------------ fake transport
class FakeTransport:
    """Scripted, recording transport — the unit-test stand-in for the network."""

    def __init__(self, *responses):
        self.calls = []
        self._responses = list(responses)

    def request(self, method, url, *, headers=None, params=None, json_body=None, timeout=None):
        self.calls.append(SimpleNamespace(method=method, url=url, headers=dict(headers or {}),
                                          params=params, json_body=json_body, timeout=timeout))
        if not self._responses:
            return TransportResponse(status=200, headers={}, body=b"{}")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    @property
    def last(self):
        return self.calls[-1]

    def calls_to(self, method):
        return [c for c in self.calls if c.method == method]


def resp(status=200, body=None, headers=None):
    raw = json.dumps(body if body is not None else {}).encode("utf-8")
    return TransportResponse(status=status, headers=headers or {}, body=raw)


def raw_resp(status=200, body=b"1\n00:00:01,000 --> 00:00:02,000\nhello\n", headers=None):
    return TransportResponse(status=status, headers=headers or {}, body=body)


SEARCH_PAYLOAD = {
    "total_count": 2,
    "data": [
        {"type": "subtitle", "attributes": {
            "subtitle_id": "111", "language": "en", "download_count": 4242,
            # ⚠ the vendor's `format` is FREE TEXT, not an extension (live 2026-09-12:
            # eng-sdh / eng-full / x265-heteam / 23). The extension comes from file_name.
            "hearing_impaired": False, "format": "eng-full", "release": "Movie.2019.1080p.WEB-DL",
            "files": [{"file_id": 111, "file_name": "Movie.2019.1080p.WEB-DL.srt"}],
            "feature_details": {"title": "The Movie", "year": 2019, "imdb_id": 133093}}},
        {"type": "subtitle", "attributes": {
            "subtitle_id": "222", "language": "en", "download_count": 7,
            "hearing_impaired": True, "format": "srt", "release": "Movie.2019.HI",
            "files": [{"file_id": 222, "file_name": "Movie.2019.HI.srt"}],
            "feature_details": {"title": "The Movie", "year": 2019}}},
        # unusable row (no file) must be dropped, never fabricated into a result
        {"type": "subtitle", "attributes": {"subtitle_id": "333", "files": []}},
    ],
}

DOWNLOAD_PAYLOAD = {
    "link": DOWNLOAD_LINK, "file_name": "Movie.2019.1080p.WEB-DL.srt", "requests": 1,
    "remaining": 4, "message": "ok", "reset_time_utc": "2026-09-13T00:00:00Z",
}


def client(*responses, login=True, clock=None, config=None):
    """A client with a fake transport and (by default) an account login configured."""
    if config is None:
        cfg = SimpleNamespace(OPENSUBTITLES_API_KEY=API_KEY, OPENSUBTITLES_LANGUAGES="en,hi",
                              OPENSUBTITLES_USERNAME="rajeev" if login else None,
                              OPENSUBTITLES_PASSWORD=PASSWORD if login else None,
                              OPENSUBTITLES_ENABLED="auto")
        cfg.has_opensubtitles = lambda: bool(cfg.OPENSUBTITLES_API_KEY)
        cfg.has_opensubtitles_login = lambda: bool(cfg.OPENSUBTITLES_USERNAME
                                                   and cfg.OPENSUBTITLES_PASSWORD)
        cfg.opensubtitles_languages = lambda: ["en", "hi"]
    else:
        cfg = config
    t = FakeTransport(*responses)
    kwargs = {"config": cfg, "transport": t}
    if clock is not None:
        kwargs["clock"] = clock
    return OpenSubtitlesClient(**kwargs), t


# ------------------------------------------------------------------------- search
class TestSearch:
    def test_success_parses_rows_into_storable_identities(self):
        c, t = client(resp(body=SEARCH_PAYLOAD))
        rows = c.search(tmdb_id=603)
        assert [r.file_id for r in rows] == [111, 222]
        assert rows[0].subtitle_id == "os:111"          # the identity we persist
        assert rows[0].display_title == "Movie.2019.1080p.WEB-DL"
        assert rows[0].download_count == 4242
        assert rows[1].hearing_impaired is True

    def test_the_free_text_vendor_format_never_becomes_the_extension(self):
        """Live finding: `attributes.format` is a label, not a file type.

        Reading it as an extension mislabels every result ("eng-full"), and anything
        that then branches on the format would be branching on prose.
        """
        c, _ = client(resp(body=SEARCH_PAYLOAD))
        row = c.search(tmdb_id=603)[0]
        assert row.format == "srt"                 # from files[0].file_name
        assert row.vendor_format == "eng-full"     # the vendor's own label, display-only

    def test_the_row_without_a_file_is_dropped(self):
        c, _ = client(resp(body=SEARCH_PAYLOAD))
        rows = c.search(tmdb_id=603)
        assert 333 not in [r.file_id for r in rows]

    def test_an_empty_result_is_not_an_error(self):
        c, _ = client(resp(body={"total_count": 0, "data": []}))
        assert c.search(imdb_id="tt0133093") == []

    def test_search_is_not_metered_so_no_download_call_happens(self):
        c, t = client(resp(body=SEARCH_PAYLOAD))
        c.search(tmdb_id=603)
        assert t.calls_to("POST") == []

    def test_the_api_key_and_a_descriptive_user_agent_are_always_sent(self):
        c, t = client(resp(body=SEARCH_PAYLOAD))
        c.search(tmdb_id=603)
        assert t.last.headers["Api-Key"] == API_KEY
        assert "RKM Cinema" in t.last.headers["User-Agent"]
        assert t.last.headers["Accept"] == "application/json"

    def test_languages_default_from_config(self):
        c, t = client(resp(body=SEARCH_PAYLOAD))
        c.search(tmdb_id=603)
        assert t.last.params["languages"] == "en,hi"

    def test_explicit_languages_win(self):
        c, t = client(resp(body=SEARCH_PAYLOAD))
        c.search(tmdb_id=603, languages=["ta"])
        assert t.last.params["languages"] == "ta"


class TestSearchKeying:
    """Priority: tmdb_id → imdb_id → title+year(+season/episode)."""

    def test_tmdb_id_wins(self):
        c, t = client(resp(body=SEARCH_PAYLOAD))
        c.search(tmdb_id=603, imdb_id="tt0133093", title="The Matrix", year=1999)
        assert t.last.params == {"languages": "en,hi", "tmdb_id": 603}

    def test_imdb_id_used_when_there_is_no_tmdb_id(self):
        c, t = client(resp(body=SEARCH_PAYLOAD))
        c.search(imdb_id="tt0133093")
        assert t.last.params["imdb_id"] == 133093      # numeric, per the vendor's API
        assert "query" not in t.last.params

    def test_a_bad_imdb_id_falls_through_to_the_title(self):
        c, t = client(resp(body=SEARCH_PAYLOAD))
        c.search(imdb_id="tt-not-an-id", title="The Matrix", year=1999)
        assert t.last.params["query"] == "The Matrix"
        assert t.last.params["year"] == 1999

    def test_an_episode_search_carries_season_and_episode(self):
        c, t = client(resp(body=SEARCH_PAYLOAD))
        c.search(title="3 Body Problem", year=2024, season=1, episode=4)
        assert (t.last.params["season_number"], t.last.params["episode_number"]) == (1, 4)

    def test_search_without_any_identity_is_a_clear_error(self):
        c, _ = client()
        with pytest.raises(OpenSubtitlesError):
            c.search()

    def test_imdb_digits_helper(self):
        assert _imdb_digits("tt0133093") == 133093
        assert _imdb_digits("133093") == 133093
        assert _imdb_digits("") is None
        assert _imdb_digits(None) is None
        assert _imdb_digits("tt-nope") is None


# ---------------------------------------------------------------------- failures
class TestErrorTaxonomy:
    def test_not_configured_is_not_a_crash(self):
        cfg = SimpleNamespace(OPENSUBTITLES_API_KEY=None)
        cfg.has_opensubtitles = lambda: False
        cfg.opensubtitles_languages = lambda: ["en"]
        cfg.has_opensubtitles_login = lambda: False
        c, t = client(config=cfg)
        with pytest.raises(NotConfiguredError):
            c.search(tmdb_id=1)
        assert t.calls == []                       # nothing left the machine

    def test_a_bad_api_key_is_reported_without_echoing_it(self):
        c, _ = client(resp(status=401, body={"message": "Unauthorized"}))
        with pytest.raises(AuthFailedError) as e:
            c.search(tmdb_id=603)
        assert "OPENSUBTITLES_API_KEY" in str(e.value)
        assert API_KEY not in str(e.value)

    def test_a_403_names_the_credential_that_is_at_fault(self):
        c, _ = client(resp(status=403, body={"message": "Forbidden"}))
        with pytest.raises(AuthFailedError):
            c.search(tmdb_id=603)

    def test_a_bad_login_is_an_auth_failure_not_a_stack_trace(self):
        c, _ = client(resp(status=401, body={"message": "Invalid credentials"}))
        with pytest.raises(AuthFailedError) as e:
            c.login()
        assert PASSWORD not in str(e.value)
        assert LOGIN_TOKEN not in str(e.value)

    @pytest.mark.parametrize("status,replays", [(400, 1), (500, 2)])
    def test_a_token_in_an_error_body_never_reaches_the_message(self, status, replays):
        """Error payloads are sanitised — an API body can echo request fields."""
        c, _ = client(*[resp(status=status, body={"token": LOGIN_TOKEN, "message": "boom"})]
                      * replays)
        with pytest.raises(OpenSubtitlesError) as e:
            c.search(tmdb_id=603)
        assert LOGIN_TOKEN not in str(e.value)

    def test_a_rate_limit_carries_retry_after(self):
        c, _ = client(resp(status=429, body={"message": "Too many requests"},
                           headers={"retry-after": "30"}))
        with pytest.raises(RateLimitedError) as e:
            c.search(tmdb_id=603)
        assert e.value.retry_after == 30

    def test_a_429_about_the_allowance_is_quota_exhaustion(self):
        c, _ = client(resp(status=429, body={"message": "You have exceeded the limit of "
                                                        "downloads allowed_downloads"},
                           headers={"retry-after": "60"}))
        with pytest.raises(QuotaExhaustedError):
            c.search(tmdb_id=603)

    def test_a_429_after_a_zero_remaining_download_is_quota_exhaustion(self):
        """No guessing: the API's own last `remaining` decides."""
        c, _ = client(resp(body={**DOWNLOAD_PAYLOAD, "remaining": 0}), raw_resp(),
                      resp(status=429, body={"message": "rate limited"},
                           headers={"retry-after": "60"}), login=False)
        c.download(111)
        assert c.last_quota() == 0
        with pytest.raises(QuotaExhaustedError):
            c.download(222)

    def test_an_upstream_5xx_is_a_transport_error(self):
        c, t = client(resp(status=502, body={"message": "bad gateway"}),
                      resp(status=502, body={"message": "bad gateway"}))
        with pytest.raises(TransportError):
            c.search(tmdb_id=603)
        assert len(t.calls_to("GET")) == 2          # GET is retried exactly once

    def test_no_results_body_maps_to_no_results(self):
        c, _ = client(resp(status=406, body={"message": "No results found"}))
        with pytest.raises(NoResultsError):
            c.search(tmdb_id=603)

    def test_quota_classifier_is_keyword_based_on_the_body(self):
        assert _looks_like_quota("You have exceeded the limit of allowed_downloads")
        assert _looks_like_quota("daily quota reached")
        assert not _looks_like_quota("too many requests")


# ---------------------------------------------------------------------- transport
class TestRetryPolicy:
    def test_a_get_is_retried_once_on_a_network_error_then_succeeds(self):
        c, t = client(TransportError("timeout"), resp(body=SEARCH_PAYLOAD))
        rows = c.search(tmdb_id=603)
        assert [r.file_id for r in rows] == [111, 222]
        assert len(t.calls_to("GET")) == 2

    def test_a_network_error_survives_as_a_transport_error_after_the_retry(self):
        c, t = client(TransportError("dns"), TransportError("dns"))
        with pytest.raises(TransportError):
            c.search(tmdb_id=603)
        assert len(t.calls_to("GET")) == 2

    def test_a_download_post_is_never_retried(self):
        """It may already have been charged — a retry spends a second download."""
        c, t = client(resp(body=DOWNLOAD_PAYLOAD), login=False)
        c.download(111)                                  # lazy login is skipped (no login)
        posts = t.calls_to("POST")
        assert len(posts) == 1
        assert posts[0].json_body == {"file_id": 111}

    def test_a_network_error_on_the_download_post_does_not_re_send(self):
        c, t = client(TransportError("connection reset"), login=False)
        with pytest.raises(TransportError):
            c.download(111)
        assert len(t.calls_to("POST")) == 1


# ----------------------------------------------------------------------- download
class TestDownload:
    def test_success_returns_bytes_and_the_quota_the_api_reported(self):
        c, t = client(resp(body=DOWNLOAD_PAYLOAD), raw_resp(), login=False)
        got = c.download(111)
        assert isinstance(got, DownloadedSubtitle)
        assert got.content.startswith(b"1\n00:00:01")
        assert got.file_name.endswith(".srt")
        assert got.remaining == 4
        assert got.reset_time_utc == "2026-09-13T00:00:00Z"
        assert c.last_quota() == 4

    def test_the_download_link_is_fetched_without_the_api_key(self):
        """The link is pre-signed; the CDN must never see the credential."""
        c, t = client(resp(body=DOWNLOAD_PAYLOAD), raw_resp(), login=False)
        c.download(111)
        link_call = t.calls[-1]
        assert link_call.url == DOWNLOAD_LINK
        assert "Api-Key" not in link_call.headers
        assert "Authorization" not in link_call.headers
        assert "RKM Cinema" in link_call.headers["User-Agent"]

    def test_a_dead_link_is_no_results(self):
        c, _ = client(resp(body=DOWNLOAD_PAYLOAD), raw_resp(status=410), login=False)
        with pytest.raises(NoResultsError):
            c.download(111)

    def test_an_empty_body_is_no_results_not_a_zero_byte_file(self):
        c, _ = client(resp(body=DOWNLOAD_PAYLOAD), raw_resp(body=b""), login=False)
        with pytest.raises(NoResultsError):
            c.download(111)

    def test_a_missing_link_is_no_results(self):
        c, _ = client(resp(body={"remaining": 3}), login=False)
        with pytest.raises(NoResultsError):
            c.download(111)

    @pytest.mark.parametrize("name", ["Movie.2019.zip", "Movie.idx", "Movie.sub"])
    def test_non_text_formats_are_rejected_before_any_bytes_are_fetched(self, name):
        c, t = client(resp(body={**DOWNLOAD_PAYLOAD, "file_name": name}), login=False)
        with pytest.raises(UnsupportedFormatError):
            c.download(111)
        assert len(t.calls) == 1                    # no link fetch, no quota spent

    def test_format_supported_helper(self):
        assert format_supported("x.srt") and format_supported("x.vtt")
        assert format_supported("x.ass") and format_supported("x.ssa")
        assert not format_supported("x.sub") and not format_supported("x.zip")
        assert not format_supported("noextension")


class TestLogin:
    def test_the_jwt_is_cached_across_calls(self):
        c, t = client(resp(body={"token": LOGIN_TOKEN}),
                      resp(body=DOWNLOAD_PAYLOAD), raw_resp(),
                      resp(body=DOWNLOAD_PAYLOAD), raw_resp())
        c.download(111)
        c.download(111)
        assert len([x for x in t.calls if x.url.endswith("/login")]) == 1

    def test_an_expired_jwt_triggers_exactly_one_re_login(self):
        c, t = client(
            resp(body={"token": LOGIN_TOKEN}),               # lazy login, call 1
            resp(body=DOWNLOAD_PAYLOAD), raw_resp(),
            resp(status=401, body={"message": "expired"}),   # call 2: token expired
            resp(body={"token": LOGIN_TOKEN}),               # ONE re-login
            resp(body=DOWNLOAD_PAYLOAD), raw_resp(),         # retried download + bytes
        )
        assert c.download(111).remaining == 4
        assert c.download(111).remaining == 4
        assert len([x for x in t.calls if x.url.endswith("/login")]) == 2

    def test_the_login_post_sends_the_account_but_never_the_key_in_the_body(self):
        c, t = client(resp(body={"token": LOGIN_TOKEN}))
        c.login()
        call = t.calls[-1]
        assert call.json_body == {"username": "rajeev", "password": PASSWORD}
        assert call.headers["Api-Key"] == API_KEY

    def test_a_configured_login_is_taken_before_the_download_is_attempted(self):
        """The JWT is fetched first — a bare 401 on /download wastes a request."""
        c, t = client(resp(body={"token": LOGIN_TOKEN}),
                      resp(body=DOWNLOAD_PAYLOAD), raw_resp())
        c.download(111)
        assert t.calls[0].url.endswith("/login")
        assert t.calls[1].url.endswith("/download")
        assert t.calls[1].headers["Authorization"] == f"Bearer {LOGIN_TOKEN}"
        assert t.calls[1].headers["Api-Key"] == API_KEY

    def test_a_failed_login_stops_before_any_download_is_spent(self):
        c, t = client(resp(status=401, body={"message": "bad credentials"}))
        with pytest.raises(AuthFailedError):
            c.download(111)
        assert not [x for x in t.calls if x.url.endswith("/download")]

    def test_anonymous_key_only_download_carries_no_authorization(self):
        c, t = client(resp(body=DOWNLOAD_PAYLOAD), raw_resp(), login=False)
        c.download(111)
        assert all("Authorization" not in c_.headers for c_ in t.calls)

    def test_anonymous_login_is_refused_with_a_clear_message(self):
        c, t = client(login=False)
        with pytest.raises(NotConfiguredError):
            c.login()
        assert t.calls == []

    def test_the_token_is_reused_until_its_ttl_expires(self):
        now = {"t": 1000.0}
        c, t = client(resp(body={"token": LOGIN_TOKEN}), resp(body={"token": "second"}),
                      clock=lambda: now["t"])
        assert c.login() == LOGIN_TOKEN
        now["t"] += 60
        assert c.login() == LOGIN_TOKEN                       # cached
        now["t"] += 13 * 3600                                 # past the TTL
        assert c.login() == "second"


# -------------------------------------------------------------------------- quota
class TestQuota:
    def test_user_info_reads_the_real_numbers(self):
        c, t = client(resp(body={"token": LOGIN_TOKEN}),
                      resp(body={"data": {"allowed_downloads": 20, "remaining_downloads": 18,
                                          "level": "Sub leecher", "vip": False}}))
        info = c.user_info()
        assert (info.allowed, info.remaining, info.level) == (20, 18, "Sub leecher")
        assert info.exhausted is False
        assert t.last.url.endswith("/infos/user")
        assert t.last.headers["Authorization"] == f"Bearer {LOGIN_TOKEN}"

    def test_user_info_is_none_for_an_anonymous_setup(self):
        """``/infos/user`` needs a JWT — key-only must degrade, not explode."""
        c, t = client(login=False)
        assert c.user_info() is None
        assert t.calls == []

    def test_user_info_is_none_when_the_account_lookup_fails(self):
        c, _ = client(resp(body={"token": LOGIN_TOKEN}),
                      resp(status=403, body={"message": "nope"}))
        assert c.user_info() is None

    def test_user_info_is_none_when_the_login_itself_fails(self):
        c, _ = client(resp(status=401, body={"message": "bad credentials"}))
        assert c.user_info() is None

    def test_user_info_reports_exhaustion(self):
        c, _ = client(resp(body={"token": LOGIN_TOKEN}),
                      resp(body={"data": {"allowed_downloads": 5, "remaining_downloads": 0}}))
        assert c.user_info().exhausted is True

    def test_anonymous_quota_is_learned_from_the_last_download(self):
        c, _ = client(resp(body={**DOWNLOAD_PAYLOAD, "remaining": 1}), raw_resp(), login=False)
        assert c.last_quota() is None
        c.download(111)
        assert c.last_quota() == 1


# ---------------------------------------------------------------------- redaction
class TestRedaction:
    def test_safe_url_strips_the_query_string(self):
        assert safe_url(DOWNLOAD_LINK) == "https://dl.opensubtitles.com/download/abc"
        assert safe_url("https://x/y") == "https://x/y"

    def test_logs_never_contain_the_password_token_or_link(self, caplog):
        caplog.set_level("DEBUG", logger="rkm.opensubtitles")
        c, _ = client(resp(body={"token": LOGIN_TOKEN}),
                      resp(body=DOWNLOAD_PAYLOAD), raw_resp())
        c.download(111)
        text = caplog.text
        assert "Movie.2019.1080p.WEB-DL.srt" in text       # the useful line IS logged
        for secret in (PASSWORD, LOGIN_TOKEN, "SECRET-TOKEN-IN-QUERY", API_KEY):
            assert secret not in text, f"{secret!r} leaked into the log"

    def test_the_link_is_never_logged_even_when_the_fetch_fails(self, caplog):
        caplog.set_level("DEBUG", logger="rkm.opensubtitles")
        c, _ = client(resp(body=DOWNLOAD_PAYLOAD), TransportError("boom"), login=False)
        with pytest.raises(TransportError):
            c.download(111)
        assert "SECRET-TOKEN-IN-QUERY" not in caplog.text


class TestConfigurationSurface:
    def test_is_configured_follows_the_api_key(self):
        c, _ = client()
        assert c.is_configured() is True
        c2, _ = client(config=SimpleNamespace(OPENSUBTITLES_API_KEY=""))
        assert c2.is_configured() is False

    def test_languages_come_from_config(self):
        c, _ = client()
        assert c.languages() == ["en", "hi"]

    def test_a_configured_build_constructs_the_real_client(self):
        from services.opensubtitles import build_opensubtitles_client
        assert isinstance(build_opensubtitles_client(config=SimpleNamespace(
            OPENSUBTITLES_API_KEY=API_KEY)), OpenSubtitlesClient)
