"""Auth endpoints + the session seam (AUTH_MULTIUSER_PLAN Phase 0).

The REAL app, with the session store pointed at ``tmp_path`` and the Jellyfin call
faked: no network, no ``/data`` write. What is pinned here:

* the browser gets ONE opaque ``HttpOnly`` cookie and nothing else — not the Jellyfin
  token, not the password, and no secret in any response body or log record;
* a rejected sign-in is a generic 401 with no cookie, so the route is not a username
  oracle;
* logout REVOKES server-side — replaying the same cookie afterwards is a 401;
* **the contextvar seam works through a real request**: a sync endpoint sees the
  session its dependency published. That is the whole mechanism Phase 3 relies on, and
  it silently fails if ``require_session`` is ever turned into a sync ``def``;
* nothing is enforced in Phase 0, while ``RKM_AUTH_REQUIRED=true`` really does 401.
"""
import logging
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import api.routes.auth as auth_route
import api.session as session_mod
from api.main import app
from api.session import current_session, require_session
from services.auth import (SESSION_COOKIE, AuthUnavailableError, InvalidCredentialsError,
                           JellyfinIdentity, SessionStore)

PASSWORD = "p#ss w0rd"
TOKEN = "jellyfin-token-9f2b"
AUTH_PATHS = ("/api/auth/login", "/api/auth/logout", "/api/auth/me")


@pytest.fixture()
def api(tmp_path, monkeypatch):
    """The real app with the store isolated and Jellyfin replaced by a fake."""
    store = SessionStore(path=tmp_path / "sessions.json")
    seen = {}

    def fake_auth(username, password, *, config=None, transport=None):
        seen["username"], seen["password"] = username, password
        if username != "rajeev" or password != PASSWORD:
            raise InvalidCredentialsError("Incorrect username or password")
        return JellyfinIdentity(user_id="uid-1", user_name="Rajeev", token=TOKEN)

    monkeypatch.setattr(auth_route, "authenticate_jellyfin", fake_auth)
    monkeypatch.setattr(auth_route, "default_session_store", lambda config=None: store)
    monkeypatch.setattr(session_mod, "session_store", lambda config=None: store)
    # Since PLEX_PROFILE_AUTH_PLAN Phase A, a login ALSO has to be an administrator: this fixture
    # declares "the account this fake returns is an admin" so these tests stay about the SESSION
    # mechanics. The refusals themselves are pinned in test_profile_auth_api.py.
    monkeypatch.setattr(auth_route, "admin_status", lambda cfg, uid: True)
    return SimpleNamespace(client=TestClient(app), store=store, seen=seen)


def _login(client, password=PASSWORD, username="rajeev"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


class TestLogin:
    def test_a_good_login_returns_the_user_and_an_opaque_cookie(self, api):
        r = _login(api.client)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["user"] == {"id": "uid-1", "name": "Rajeev"}
        assert body["expires"]

        cookie = r.headers["set-cookie"]
        lowered = cookie.lower()
        assert cookie.startswith(f"{SESSION_COOKIE}=")
        assert "httponly" in lowered              # no XSS token theft
        assert "samesite=lax" in lowered          # survives a top-level navigation
        assert "path=/" in lowered
        assert "max-age=2592000" in lowered       # 30 days, matching the store
        assert "secure" not in lowered            # tailnet is plain http
        assert TOKEN not in cookie                # opaque id, never the token

    def test_the_browser_never_receives_the_jellyfin_token(self, api):
        r = _login(api.client)
        assert TOKEN not in r.text
        session_id = api.client.cookies.get(SESSION_COOKIE)
        assert session_id and session_id != TOKEN
        assert api.store.count() == 1
        # the token IS stored server-side, because the provider must act as the user
        assert api.store.lookup(session_id)["jellyfin_token"] == TOKEN

    def test_credentials_are_passed_through_untouched_and_never_stored(self, api):
        _login(api.client)
        assert api.seen == {"username": "rajeev", "password": PASSWORD}
        # The display name is kept (the UI shows it); the CREDENTIAL is not stored
        # anywhere — what identifies the session on disk is the sha256 of the id.
        raw = api.store.path.read_text(encoding="utf-8")
        assert PASSWORD not in raw
        assert "Rajeev" in raw

    def test_a_wrong_password_is_a_generic_401_with_no_cookie(self, api):
        r = _login(api.client, password="wrong")
        assert r.status_code == 401
        assert "set-cookie" not in {k.lower() for k in r.headers}
        assert "wrong" not in r.text
        assert api.store.count() == 0

    def test_an_unknown_user_and_a_wrong_password_read_identically(self, api):
        unknown = _login(api.client, username="nobody")
        wrong = _login(api.client, username="rajeev", password="wrong")
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json() == wrong.json()

    def test_a_jellyfin_outage_is_a_503_not_a_500(self, api, monkeypatch):
        def dead(*a, **kw):
            raise AuthUnavailableError("could not reach the media server (URLError)")

        monkeypatch.setattr(auth_route, "authenticate_jellyfin", dead)
        r = _login(api.client)
        assert r.status_code == 503
        assert "set-cookie" not in {k.lower() for k in r.headers}
        assert api.store.count() == 0


class TestMeAndLogout:
    def test_me_is_401_before_signing_in(self, api):
        r = api.client.get("/api/auth/me")
        assert r.status_code == 401

    def test_me_reports_who_is_signed_in(self, api):
        _login(api.client)
        r = api.client.get("/api/auth/me")
        assert r.status_code == 200
        assert r.json()["user"] == {"id": "uid-1", "name": "Rajeev"}
        assert TOKEN not in r.text

    def test_me_does_not_care_whether_enforcement_is_on(self, api, monkeypatch):
        """"signed out" and "not enforced yet" are different states (the guard asks)."""
        monkeypatch.setattr(session_mod.get_config(), "RKM_AUTH_REQUIRED", "false")
        assert api.client.get("/api/auth/me").status_code == 401
        monkeypatch.setattr(session_mod.get_config(), "RKM_AUTH_REQUIRED", "true")
        assert api.client.get("/api/auth/me").status_code == 401

    def test_logout_revokes_server_side(self, api):
        """Replaying the very same cookie afterwards must fail."""
        _login(api.client)
        session_id = api.client.cookies.get(SESSION_COOKIE)

        r = api.client.post("/api/auth/logout")
        assert r.status_code == 200
        assert r.json() == {"ok": True, "revoked": True}
        assert "max-age=0" in r.headers["set-cookie"].lower()

        replay = api.client.get("/api/auth/me",
                                headers={"Cookie": f"{SESSION_COOKIE}={session_id}"})
        assert replay.status_code == 401
        assert api.store.count() == 0

    def test_logout_without_a_session_is_harmless(self, api):
        r = api.client.post("/api/auth/logout")
        assert r.status_code == 200
        assert r.json()["revoked"] is False

    def test_a_bogus_cookie_is_not_a_session(self, api):
        api.client.cookies.set(SESSION_COOKIE, "not-a-real-session")
        assert api.client.get("/api/auth/me").status_code == 401


class TestNoSecretReachesTheBrowserOrTheLog:
    def test_no_response_body_carries_a_secret(self, api):
        bodies = [
            _login(api.client).text,
            api.client.get("/api/auth/me").text,
            api.client.post("/api/auth/logout").text,
        ]
        for body in bodies:
            assert TOKEN not in body and PASSWORD not in body

    def test_no_log_record_carries_a_secret(self, api, caplog):
        with caplog.at_level(logging.DEBUG):
            _login(api.client)
            api.client.get("/api/auth/me")
            api.client.post("/api/auth/logout")
        text = " ".join(r.getMessage() for r in caplog.records)
        assert TOKEN not in text
        assert PASSWORD not in text


class TestContract:
    def test_the_three_auth_paths_are_in_the_contract(self):
        paths = app.openapi()["paths"]
        for path in AUTH_PATHS:
            assert path in paths, path

    def test_me_is_documented_as_a_session_user(self):
        schema = app.openapi()["paths"]["/api/auth/me"]["get"]
        ref = schema["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/MeResponse")


class TestSessionSeam:
    """The contextvar the Jellyfin provider will read (Phase 3).

    Driven through a REAL request on a probe app that uses the real dependency, so this
    fails if ``require_session`` ever becomes a sync ``def`` (a sync dependency runs in a
    worker thread whose copied context is discarded — the provider would then quietly
    fall back to the admin token and every user would share one identity again).
    """

    def _probe(self, monkeypatch, store, *, required, authenticated, cookie=None):
        probe = FastAPI()

        @probe.get("/probe")
        def probe_route(session=Depends(require_session)):   # noqa: B008 - FastAPI idiom
            live = current_session()
            return {
                "dependency_user": getattr(session, "user_name", None),
                "context_user": getattr(live, "user_name", None),
                "context_token": getattr(live, "token", None),
            }

        monkeypatch.setattr(session_mod, "session_store", lambda config=None: store)
        monkeypatch.setattr(session_mod.get_config(), "RKM_AUTH_REQUIRED",
                            "true" if required else "false")

        client = TestClient(probe)
        if authenticated:
            session_id, _ = store.create(user_id="uid-1", user_name="Rajeev", token=TOKEN)
            client.cookies.set(SESSION_COOKIE, session_id)
        elif cookie:
            client.cookies.set(SESSION_COOKIE, cookie)
        return client.get("/probe")

    def test_a_signed_in_request_publishes_the_session_to_the_endpoint(self, tmp_path, monkeypatch):
        store = SessionStore(path=tmp_path / "sessions.json")
        r = self._probe(monkeypatch, store, required=True, authenticated=True)
        assert r.status_code == 200, r.text
        assert r.json() == {"dependency_user": "Rajeev",
                            "context_user": "Rajeev",
                            "context_token": TOKEN}

    def test_with_enforcement_off_a_stranger_is_not_an_error(self, tmp_path, monkeypatch):
        """Phase 0's whole promise: behave exactly as the app did before auth."""
        store = SessionStore(path=tmp_path / "sessions.json")
        r = self._probe(monkeypatch, store, required=False, authenticated=False)
        assert r.status_code == 200
        assert r.json() == {"dependency_user": None, "context_user": None,
                            "context_token": None}

    def test_with_enforcement_on_a_stranger_is_401(self, tmp_path, monkeypatch):
        store = SessionStore(path=tmp_path / "sessions.json")
        r = self._probe(monkeypatch, store, required=True, authenticated=False)
        assert r.status_code == 401

    def test_a_bogus_cookie_is_anonymous_not_a_crash(self, tmp_path, monkeypatch):
        store = SessionStore(path=tmp_path / "sessions.json")
        r = self._probe(monkeypatch, store, required=False, authenticated=False,
                        cookie="nonsense")
        assert r.status_code == 200
        assert r.json()["context_user"] is None
