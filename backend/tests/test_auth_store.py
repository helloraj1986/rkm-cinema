"""Session store + Jellyfin sign-in (AUTH_MULTIUSER_PLAN Phase 0).

No network and no real media drive: the Jellyfin call runs against a fake transport and
the store is pointed at ``tmp_path``. What is pinned here is everything the later phases
will ASSUME:

* what is stored is the **sha256 of the session id**, never the id itself, and the file
  is owner-only — so a leaked store file yields no usable session;
* the Jellyfin **token never leaves the server**: ``records()`` (the diagnostic shape)
  omits it, and no exception message carries the password or the response body;
* a rejected login is GENERIC — an unknown user and a wrong password are one answer;
* expiry is enforced from the RECORD, not from the cookie's Max-Age, and it slides on
  use without a disk write per request;
* a corrupt store file degrades to empty rather than locking the household out.
"""
import json
import logging
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest

from services.auth import (SESSION_TTL_SECONDS, AuthResponse, AuthUnavailableError,
                           InvalidCredentialsError, JellyfinIdentity, SessionStore,
                           authenticate_jellyfin, default_session_path, hash_session_id)

PASSWORD = "p#ss w0rd"
TOKEN = "jellyfin-token-9f2b"


class FakeConfig:
    """Only the attributes the store and the auth call read."""

    JELLYFIN_URL = "http://jellyfin:8096"
    WATCHLIST_DB_PATH = "/data/rkm/watchlist.json"


class FakeTransport:
    """Answers by URL: 200 with a real-shaped payload, or a chosen failure."""

    def __init__(self, status=200, payload=None, raises=None):
        self.status = status
        self.payload = payload if payload is not None else {
            "User": {"Id": "uid-1", "Name": "Rajeev"},
            "AccessToken": TOKEN,
        }
        self.raises = raises
        self.calls = []

    def request(self, method, url, *, headers=None, json_body=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}),
                           "json_body": dict(json_body or {})})
        if self.raises is not None:
            raise self.raises
        body = self.payload if isinstance(self.payload, (bytes, str)) else json.dumps(
            self.payload).encode("utf-8")
        return AuthResponse(status=self.status, body=body.encode("utf-8")
                            if isinstance(body, str) else body)


@pytest.fixture()
def store(tmp_path):
    def build(**kw):
        return SessionStore(path=tmp_path / "sessions.json", config=FakeConfig(), **kw)
    return build


def _raw(path):
    return (path / "sessions.json").read_text(encoding="utf-8")


# ------------------------------------------------------------------ the store
class TestSessionStore:
    def test_create_lookup_round_trip(self, tmp_path, store):
        s = store()
        session_id, record = s.create(user_id="uid-1", user_name="Rajeev", token=TOKEN)
        assert session_id and len(session_id) > 20
        assert record["user_id"] == "uid-1"
        assert record["expires"] > record["created"]

        live = s.lookup(session_id)
        assert live["user_name"] == "Rajeev"
        assert live["jellyfin_token"] == TOKEN      # the provider needs it
        assert s.count() == 1

    def test_the_stored_key_is_the_hash_not_the_session_id(self, tmp_path, store):
        """A leaked store file must yield no usable session id (plan §3.1/§8.3)."""
        s = store()
        session_id, _ = s.create(user_id="uid-1", user_name="Rajeev", token=TOKEN)
        raw = _raw(tmp_path)
        assert session_id not in raw
        assert hash_session_id(session_id) in raw

    def test_the_file_is_owner_only(self, tmp_path, store):
        """The store holds live Jellyfin tokens — 0600, not 0644."""
        s = store()
        s.create(user_id="uid-1", user_name="Rajeev", token=TOKEN)
        mode = stat.S_IMODE(os.stat(tmp_path / "sessions.json").st_mode)
        assert mode == 0o600, oct(mode)

    def test_no_temp_file_is_left_behind(self, tmp_path, store):
        s = store()
        s.create(user_id="uid-1", user_name="Rajeev", token=TOKEN)
        assert sorted(p.name for p in tmp_path.iterdir()) == ["sessions.json"]

    def test_an_unknown_or_blank_id_is_none(self, store):
        s = store()
        assert s.lookup("nope") is None
        assert s.lookup("") is None

    def test_expiry_comes_from_the_record_not_the_cookie(self, tmp_path, store):
        """A cookie can outlive its row — the row wins, and it is removed."""
        s = store()
        session_id, _ = s.create(user_id="uid-1", user_name="Rajeev", token=TOKEN,
                                 ttl_seconds=-1)
        assert s.lookup(session_id) is None
        assert s.count() == 0

    def test_revoke_is_a_real_revocation(self, store):
        s = store()
        session_id, _ = s.create(user_id="uid-1", user_name="Rajeev", token=TOKEN)
        assert s.revoke(session_id) is True
        assert s.lookup(session_id) is None
        assert s.revoke(session_id) is False        # idempotent
        assert s.count() == 0

    def test_create_prunes_expired_rows(self, tmp_path, store):
        """A login is a natural moment for hygiene."""
        s = store()
        s.create(user_id="old", user_name="Old", token="t1", ttl_seconds=-5)
        s.create(user_id="new", user_name="New", token="t2")
        assert s.count() == 1

    def test_prune_reports_how_many_went(self, tmp_path, store):
        """Age two sessions on disk: a LOGIN prunes too, so do it out of band.

        A fresh store instance is used after writing, because the mtime cache is only
        guaranteed to invalidate on a change THIS process made.
        """
        s = store()
        session_ids = [s.create(user_id=n, user_name=n, token=f"t-{n}")[0]
                       for n in ("a", "b", "c")]
        data = json.loads(_raw(tmp_path))
        for session_id in session_ids[:2]:
            data["sessions"][hash_session_id(session_id)]["expires"] = "2000-01-01T00:00:00Z"
        (tmp_path / "sessions.json").write_text(json.dumps(data), encoding="utf-8")

        assert store().prune() == 2
        assert store().count() == 1

    def test_records_never_carry_the_token(self, store):
        s = store()
        s.create(user_id="uid-1", user_name="Rajeev", token=TOKEN)
        records = s.records()
        assert len(records) == 1
        assert records[0]["user_name"] == "Rajeev"
        assert "jellyfin_token" not in records[0]
        assert TOKEN not in json.dumps(records)

    def test_a_corrupt_file_starts_empty_and_says_so(self, tmp_path, store, caplog):
        (tmp_path / "sessions.json").write_text("{ this is not json", encoding="utf-8")
        s = store()
        with caplog.at_level(logging.WARNING, logger="rkm.auth"):
            assert s.count() == 0
            assert s.lookup("anything") is None
        assert any("unreadable" in r.getMessage() for r in caplog.records)
        # the damaged file is left alone, not silently overwritten with evidence lost
        assert _raw(tmp_path) == "{ this is not json"

    def test_a_session_with_a_garbage_expiry_is_refused(self, tmp_path, store):
        s = store()
        session_id, _ = s.create(user_id="uid-1", user_name="Rajeev", token=TOKEN)
        data = json.loads(_raw(tmp_path))
        data["sessions"][hash_session_id(session_id)]["expires"] = "not-a-date"
        (tmp_path / "sessions.json").write_text(json.dumps(data), encoding="utf-8")
        assert store().lookup(session_id) is None
        assert store().count() == 0

    def test_sliding_expiry_refreshes_on_use_but_not_once_per_request(self, tmp_path, store):
        """30 days sliding — otherwise a long-lived TV browser is signed out.

        The refresh is rate-limited so the hot path stays a read.
        """
        s = store()
        session_id, _ = s.create(user_id="uid-1", user_name="Rajeev", token=TOKEN)
        key = hash_session_id(session_id)
        data = json.loads(_raw(tmp_path))
        # Still VALID (a past expiry would simply be revoked) but expiring soon, with a
        # last_seen old enough to be past the write-avoiding touch interval: using the
        # session must renew it for the whole TTL again.
        aged = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        nearly_done = (datetime.now(timezone.utc) + timedelta(minutes=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        data["sessions"][key]["last_seen"] = aged
        data["sessions"][key]["expires"] = nearly_done
        (tmp_path / "sessions.json").write_text(json.dumps(data), encoding="utf-8")

        live = store()                       # fresh instance: the file is the truth
        refreshed = live.lookup(session_id)
        assert refreshed["last_seen"] > aged
        assert refreshed["expires"] > nearly_done      # a full TTL again

        first_mtime = os.stat(tmp_path / "sessions.json").st_mtime_ns
        live.lookup(session_id)
        assert os.stat(tmp_path / "sessions.json").st_mtime_ns == first_mtime

    def test_create_refuses_a_tokenless_session(self, store):
        s = store()
        with pytest.raises(ValueError):
            s.create(user_id="uid-1", user_name="Rajeev", token="")
        with pytest.raises(ValueError):
            s.create(user_id="", user_name="Rajeev", token=TOKEN)


class TestStorePath:
    def test_sits_beside_the_watchlist(self):
        assert default_session_path("/data/rkm/watchlist.json") == \
            default_session_path("/data/rkm/watchlist.json")
        assert str(default_session_path("/data/rkm/watchlist.json")) == \
            "/data/rkm/sessions.json"

    def test_falls_back_to_the_container_default(self):
        assert str(default_session_path(None)) == "/data/rkm/sessions.json"

    def test_follows_a_moved_media_root(self):
        assert str(default_session_path("/media2/rkm/watchlist.json")) == \
            "/media2/rkm/sessions.json"

    def test_the_store_derives_it_from_the_config(self):
        assert str(SessionStore(config=FakeConfig()).path) == "/data/rkm/sessions.json"


# ------------------------------------------------------------- the Jellyfin call
class TestAuthenticateJellyfin:
    def test_a_good_login_returns_identity_and_token(self):
        transport = FakeTransport()
        identity = authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(),
                                         transport=transport)
        assert identity == JellyfinIdentity(user_id="uid-1", user_name="Rajeev",
                                            token=TOKEN)

    def test_it_uses_the_proven_header_and_endpoint(self):
        """Mirrors tools/rkm_common.py::Jellyfin._login, which is known to work."""
        transport = FakeTransport()
        authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(), transport=transport)
        call = transport.calls[0]
        assert call["method"] == "POST"
        assert call["url"] == "http://jellyfin:8096/Users/AuthenticateByName"
        assert call["headers"]["X-Emby-Authorization"].startswith("MediaBrowser ")
        assert "RKM Cinema" in call["headers"]["X-Emby-Authorization"]
        assert call["json_body"] == {"Username": "rajeev", "Pw": PASSWORD}

    def test_the_default_device_is_the_apps_own(self):
        """⚠ Empty means the WEB APP's device — the browser must keep exactly today's behaviour."""
        transport = FakeTransport()
        authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(), transport=transport)
        assert 'DeviceId="rkm-cinema-web"' in transport.calls[0]["headers"]["X-Emby-Authorization"]

    def test_a_caller_can_sign_in_on_its_OWN_device(self):
        """⚠ The whole point: Jellyfin rotates the previous token of a (device, user) pair on every
        login, so a tool signing in on the app's device would kill the browser's session (§6h)."""
        from services.auth import TOOLS_DEVICE_ID

        transport = FakeTransport()
        authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(), transport=transport,
                              device_id=TOOLS_DEVICE_ID)
        header = transport.calls[0]["headers"]["X-Emby-Authorization"]
        assert f'DeviceId="{TOOLS_DEVICE_ID}"' in header
        assert "rkm-cinema-web" not in header

    @pytest.mark.parametrize("given", [
        'rkm-tools" , DeviceId="stolen',     # a quote would break out of DeviceId="..."
        "rkm-tools\r\nX-Injected: 1",        # header injection
        "rkm tools/../../etc",               # anything else unusable
    ])
    def test_a_device_id_cannot_break_out_of_the_header(self, given):
        """The id is CLIENT-SUPPLIED text inside a header value, so it is constrained, not trusted.

        ⚠ The id's TEXT may survive — inside the quotes it is only data. What must never survive is a
        character that can END the value (a quote) or SPLIT the header (CR/LF), so those are what the
        assertions are about: exactly four quoted values, and nothing after the last one.
        """
        transport = FakeTransport()
        authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(), transport=transport,
                              device_id=given)
        header = transport.calls[0]["headers"]["X-Emby-Authorization"]
        assert header.count('"') == 8, f"a quote got through: {header!r}"
        assert "\r" not in header and "\n" not in header, f"header injection: {header!r}"
        assert header.startswith("MediaBrowser ") and header.endswith('Version="2.0"'), (
            f"something was appended after the header's own values: {header!r}")

    def test_an_unusable_device_id_never_becomes_the_apps_own(self):
        """⚠ The safe direction. Falling back to the APP's device would rotate the browser's token
        away — the exact harm `device_id` exists to prevent — so an unusable id gets its own name."""
        from services.auth import UNIDENTIFIED_DEVICE_ID

        transport = FakeTransport()
        authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(), transport=transport,
                              device_id='"""')
        header = transport.calls[0]["headers"]["X-Emby-Authorization"]
        assert f'DeviceId="{UNIDENTIFIED_DEVICE_ID}"' in header
        assert "rkm-cinema-web" not in header

    def test_whitespace_alone_is_nobody_asking_for_a_device(self):
        """A blank/whitespace id is the DEFAULT, not an unusable one: the browser is unaffected."""
        transport = FakeTransport()
        authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(), transport=transport,
                              device_id="   ")
        assert 'DeviceId="rkm-cinema-web"' in transport.calls[0]["headers"]["X-Emby-Authorization"]

    def test_a_very_long_device_id_is_truncated(self):
        from services.auth import DEVICE_ID_MAX

        transport = FakeTransport()
        authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(), transport=transport,
                              device_id="a" * 500)
        header = transport.calls[0]["headers"]["X-Emby-Authorization"]
        assert f'DeviceId="{"a" * DEVICE_ID_MAX}"' in header

    @pytest.mark.parametrize("status", [401, 403])
    def test_bad_credentials_are_generic(self, status):
        with pytest.raises(InvalidCredentialsError) as excinfo:
            authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(),
                                  transport=FakeTransport(status=status))
        assert PASSWORD not in str(excinfo.value)
        assert "rajeev" not in str(excinfo.value)

    def test_an_unknown_user_and_a_wrong_password_are_indistinguishable(self):
        """Otherwise the endpoint becomes a username oracle."""
        messages = []
        for _ in range(2):
            with pytest.raises(InvalidCredentialsError) as excinfo:
                authenticate_jellyfin("whoever", "whatever", config=FakeConfig(),
                                      transport=FakeTransport(status=401))
            messages.append(str(excinfo.value))
        assert messages[0] == messages[1]

    def test_a_5xx_is_unavailable_not_a_rejection(self):
        with pytest.raises(AuthUnavailableError):
            authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(),
                                  transport=FakeTransport(status=503))

    def test_a_200_without_a_token_is_unavailable(self):
        with pytest.raises(AuthUnavailableError):
            authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(),
                                  transport=FakeTransport(payload={"User": {"Id": "uid-1"}}))

    def test_a_non_json_body_is_unavailable(self):
        with pytest.raises(AuthUnavailableError):
            authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(),
                                  transport=FakeTransport(payload=b"<html>nope</html>"))

    def test_an_unconfigured_media_server_is_unavailable(self):
        class NoJellyfin:
            JELLYFIN_URL = ""

        with pytest.raises(AuthUnavailableError):
            authenticate_jellyfin("rajeev", PASSWORD, config=NoJellyfin())

    def test_a_network_error_never_stringifies_its_url(self):
        """A urllib error can carry the URL it called; the message must not."""
        with pytest.raises(AuthUnavailableError) as excinfo:
            authenticate_jellyfin("rajeev", PASSWORD, config=FakeConfig(),
                                  transport=FakeTransport(
                                      raises=OSError("connection refused to "
                                                     "http://jellyfin:8096/?k=secret")))
        message = str(excinfo.value)
        assert "secret" not in message and "jellyfin:8096" not in message
        assert "OSError" in message              # the CLASS is the useful part


class TestDefaults:
    def test_the_session_lives_thirty_days(self):
        assert SESSION_TTL_SECONDS == 30 * 24 * 3600
