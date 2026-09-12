"""Plex-style profile auth (PLEX_PROFILE_AUTH_PLAN Phase A) — the refusals, pinned.

Every test here is about a RULE, not a happy path: who may open a session, who may select which
profile, what a shared device may not reach, and what survives a restart. The fakes mirror what the
routes really receive (`LibraryService`'s shapes — a dict from `library_folders()`), because getting
that wrong is how a 39-test suite once passed while production 403'd the administrator.

No network and no real account is touched: `authenticate_jellyfin` is replaced, the session store
points at `tmp_path`, and the provider is a fake.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import admin_users as admin_route
from api.routes import auth as auth_route
from api import session as session_mod
from services.auth import SESSION_COOKIE, InvalidCredentialsError, JellyfinIdentity, SessionStore

ADMIN_PW = "admin-pw"
LOCKED_PW = "locked-pw"

USERS = [
    {"id": "uid-admin", "name": "admin", "is_admin": True, "disabled": False,
     "has_password": True, "enable_all_folders": True, "enabled_folders": [],
     "last_login": "2026-09-12T07:25:10Z"},
    {"id": "uid-kid", "name": "Kid", "is_admin": False, "disabled": False,
     "has_password": False, "enable_all_folders": False, "enabled_folders": ["f1"],
     "last_login": ""},
    {"id": "uid-locked", "name": "Locked", "is_admin": False, "disabled": False,
     "has_password": True, "enable_all_folders": False, "enabled_folders": ["f2"],
     "last_login": ""},
    {"id": "uid-off", "name": "Off", "is_admin": False, "disabled": True,
     "has_password": False, "enable_all_folders": True, "enabled_folders": [], "last_login": ""},
]

FOLDERS = [
    {"id": "f1", "name": "Movies", "collection_type": "movies", "path": "/data/Movies"},
    {"id": "f2", "name": "TV Shows", "collection_type": "tvshows", "path": "/media2/TV Shows"},
]

PASSWORDS = {"admin": ADMIN_PW, "Locked": LOCKED_PW}


def _authenticate(users, seen):
    """The app's own login call, faked — including Jellyfin's real permissiveness.

    Jellyfin succeeds for an account with NO password whatever is supplied (there is nothing to
    compare against); a password-protected account must match. Both branches are modelled here so a
    test cannot pass against a fake that is kinder than reality.
    """
    def fake_auth(username, password, *, config=None, transport=None):
        seen.setdefault("attempts", []).append((username, password))
        for user in users:
            if user["name"] != username:
                continue
            if user["has_password"] and password != PASSWORDS.get(username, ""):
                raise InvalidCredentialsError("Incorrect username or password")
            return JellyfinIdentity(user_id=user["id"], user_name=user["name"],
                                    token=f"token-{user['id']}")
        raise InvalidCredentialsError("Incorrect username or password")

    return fake_auth


@pytest.fixture()
def api(tmp_path, monkeypatch):
    store = SessionStore(path=tmp_path / "sessions.json")
    users = [dict(u) for u in USERS]
    folders = [dict(f) for f in FOLDERS]
    seen: dict = {}
    revoked: list[str] = []

    class FakeLibrary:
        """What the routes really get: the FACADE's shapes."""

        def __init__(self):
            #: Every (current, new) pair the route handed the provider, in order.
            self.password_changes: list[tuple[str, str]] = []

        def list_users(self):
            return [dict(u) for u in users]

        def library_folders(self):
            # A DICT — the facade's shape, not the provider's list. See the module docstring.
            return {"provider": "jellyfin", "folders": [dict(f) for f in folders]}

        def get_user_policy(self, user_id):
            for user in users:
                if user["id"] == user_id:
                    return {"IsAdministrator": bool(user["is_admin"]),
                            "IsDisabled": bool(user["disabled"])}
            return None

        def change_own_password(self, current_password, new_password):
            self.password_changes.append((current_password, new_password))
            return seen.pop("password_reason", None)

        def last_api_error(self):
            return None

    library = FakeLibrary()

    monkeypatch.setattr(auth_route, "authenticate_jellyfin", _authenticate(users, seen))
    monkeypatch.setattr(auth_route, "default_session_store", lambda config=None: store)
    monkeypatch.setattr(auth_route, "build_library_service", lambda *a, **k: library)

    def fake_admin_status(cfg, user_id):
        """The real rule, over the fake users — so a member's credential really is refused."""
        for user in users:
            if user["id"] == user_id:
                return bool(user["is_admin"]) and not bool(user["disabled"])
        return False

    monkeypatch.setattr(auth_route, "admin_status", fake_admin_status)
    monkeypatch.setattr(auth_route, "revoke_jellyfin_session",
                        lambda token, **kw: revoked.append(token) or True)
    monkeypatch.setattr(admin_route, "build_library_service", lambda *a, **k: library)
    monkeypatch.setattr(session_mod, "session_store", lambda config=None: store)
    monkeypatch.setattr(session_mod, "build_library_service", lambda *a, **k: library)
    monkeypatch.setattr(session_mod.get_config(), "RKM_AUTH_REQUIRED", "false")

    return SimpleNamespace(client=TestClient(app), store=store, users=users, folders=folders,
                           seen=seen, revoked=revoked, library=library)


def _sign_in(api, username="admin", password=ADMIN_PW):
    return api.client.post("/api/auth/login", json={"username": username, "password": password})


def _select(api, user_id, password=""):
    return api.client.post("/api/auth/profile", json={"user_id": user_id, "password": password})


class TestTheServerLoginIsAdminOnly:
    """Decision 2 (2026-09-12): a member's credential opens nothing of its own."""

    def test_the_administrator_signs_in(self, api):
        r = _sign_in(api)
        assert r.status_code == 200, r.text
        assert r.json()["user"] == {"id": "uid-admin", "name": "admin"}
        assert api.store.count() == 1

    def test_a_members_credential_is_refused_and_creates_no_session(self, api):
        r = api.client.post("/api/auth/login", json={"username": "Locked", "password": LOCKED_PW})
        assert r.status_code == 403
        assert "administrator" in r.json()["detail"].lower()
        assert api.store.count() == 0
        assert SESSION_COOKIE not in api.client.cookies

    def test_the_token_we_refuse_to_use_is_revoked(self, api):
        """A live token left behind is a credential nothing in the app can see or expire."""
        api.client.post("/api/auth/login", json={"username": "Locked", "password": LOCKED_PW})
        assert api.revoked == ["token-uid-locked"]

    def test_an_unverifiable_admin_check_is_a_503_not_a_refusal(self, api, monkeypatch):
        monkeypatch.setattr(auth_route, "admin_status", lambda cfg, uid: None)
        r = _sign_in(api)
        assert r.status_code == 503
        assert "Could not reach the media server" in r.json()["detail"]
        assert api.store.count() == 0


class TestProfiles:
    def test_the_list_needs_a_session(self, api):
        r = api.client.get("/api/auth/profiles")
        assert r.status_code == 401

    def test_the_administrator_sees_every_profile_with_its_locks(self, api):
        _sign_in(api)
        body = api.client.get("/api/auth/profiles").json()
        by_name = {p["name"]: p for p in body["profiles"]}
        assert set(by_name) == {"admin", "Kid", "Locked", "Off"}
        assert by_name["admin"]["is_admin"] is True
        assert by_name["Kid"]["has_password"] is False
        assert by_name["Locked"]["has_password"] is True
        assert by_name["Off"]["disabled"] is True
        # With no profile chosen, the profile in effect IS the owner's.
        assert body["current"]["id"] == "uid-admin"

    def test_an_empty_list_says_why(self, api, monkeypatch):
        _sign_in(api)
        monkeypatch.setattr(api.library, "list_users", lambda: [])
        monkeypatch.setattr(api.library, "last_api_error", lambda: {"status": 403})
        body = api.client.get("/api/auth/profiles").json()
        assert body["profiles"] == []
        assert "403" in body["warning"]


class TestThePickerCanTellNothingHasBeenChosenYet:
    """Phase B's ONE server-side trigger (added while building the picker).

    `profile_id()` falls back to the OWNER, so a fresh sign-in and "the administrator picked
    themselves" send an identical `profile` payload. Without this flag the picker could only guess
    from a locally-remembered click — and a reload, or the user's other device, would be the guess.
    """

    def test_a_fresh_sign_in_has_no_profile_chosen(self, api):
        _sign_in(api)
        me = api.client.get("/api/auth/me").json()
        assert me["profile_selected"] is False
        # The OWNER still fills `profile` in — which is exactly why the flag has to exist.
        assert me["profile"]["id"] == "uid-admin"

    def test_choosing_a_profile_sets_it(self, api):
        _sign_in(api)
        _select(api, "uid-kid")
        me = api.client.get("/api/auth/me").json()
        assert me["profile_selected"] is True
        assert me["profile"]["id"] == "uid-kid"

    def test_the_profile_list_says_whether_one_was_chosen(self, api):
        """The picker must not label the owner's FALLBACK profile as the current choice."""
        _sign_in(api)
        assert api.client.get("/api/auth/profiles").json()["profile_selected"] is False
        _select(api, "uid-kid")
        body = api.client.get("/api/auth/profiles").json()
        assert body["profile_selected"] is True
        assert body["current"]["id"] == "uid-kid"


class TestProfileSelection:
    def test_a_passwordless_profile_opens_with_nothing_typed(self, api):
        _sign_in(api)
        r = _select(api, "uid-kid")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["profile"]["id"] == "uid-kid"
        assert body["profile"]["name"] == "Kid"
        # Its granted library, resolved to a NAME (grant ids mean nothing to a person).
        assert body["libraries"] == [{"id": "f1", "name": "Movies"}]
        assert api.seen["attempts"][-1] == ("Kid", "")

    def test_the_selected_profile_is_what_the_session_acts_as(self, api):
        _sign_in(api)
        _select(api, "uid-kid")
        me = api.client.get("/api/auth/me").json()
        assert me["user"]["id"] == "uid-admin"        # the owner is unchanged
        assert me["profile"]["id"] == "uid-kid"       # the profile is what media runs as
        assert me["on_own_profile"] is False

    def test_the_owner_token_survives_so_the_administrator_can_come_back(self, api):
        _sign_in(api)
        session_id = api.client.cookies.get(SESSION_COOKIE)
        before = api.store.lookup(session_id)["jellyfin_token"]
        _select(api, "uid-kid")
        after = api.store.lookup(session_id)
        assert after["jellyfin_token"] == before == "token-uid-admin"
        assert after["profile_token"] == "token-uid-kid"

    def test_the_profile_survives_a_restart(self, api, tmp_path):
        """A fresh store instance reads the file — which is the whole point of writing it."""
        _sign_in(api)
        _select(api, "uid-kid")
        from_file = SessionStore(path=tmp_path / "sessions.json")
        record = from_file.records()[0]
        assert record["profile_user_id"] == "uid-kid"
        assert record["profile_user_name"] == "Kid"

    def test_a_protected_profile_needs_its_own_password(self, api):
        _sign_in(api)
        assert _select(api, "uid-locked").status_code == 401
        assert _select(api, "uid-locked", "wrong").status_code == 401
        assert _select(api, "uid-locked", LOCKED_PW).status_code == 200

    def test_a_disabled_profile_is_refused(self, api):
        _sign_in(api)
        r = _select(api, "uid-off")
        assert r.status_code == 403
        assert "disabled" in r.json()["detail"].lower()

    def test_an_unknown_profile_is_a_404(self, api):
        _sign_in(api)
        assert _select(api, "uid-nope").status_code == 404

    def test_selection_needs_a_session(self, api):
        assert _select(api, "uid-kid").status_code == 401

    def test_nothing_returns_a_password_or_a_token(self, api):
        _sign_in(api)
        text = _select(api, "uid-locked", LOCKED_PW).text
        assert LOCKED_PW not in text
        assert "token-uid" not in text
        assert "jellyfin_token" not in text


class TestTheSharedDeviceRule:
    """Decision 3 (2026-09-12): the device holds the administrator's session, so admin access is
    refused while somebody else's profile is selected — and getting back in is password-checked."""

    def test_admin_routes_are_refused_while_another_profile_is_selected(self, api):
        _sign_in(api)
        assert api.client.get("/api/admin/users").status_code == 200   # on their own profile
        _select(api, "uid-kid")
        r = api.client.get("/api/admin/users")
        assert r.status_code == 403
        assert "Switch back" in r.json()["detail"]

    def test_switching_back_to_the_administrator_needs_the_password(self, api):
        _sign_in(api)
        _select(api, "uid-kid")
        assert _select(api, "uid-admin").status_code == 401             # no password offered
        assert _select(api, "uid-admin", "wrong").status_code == 401    # the wrong one
        r = _select(api, "uid-admin", ADMIN_PW)
        assert r.status_code == 200
        assert r.json()["profile"]["is_admin"] is True
        assert api.client.get("/api/auth/me").json()["on_own_profile"] is True
        assert api.client.get("/api/admin/users").status_code == 200

    def test_a_blank_attempt_never_lands_on_the_administrator_profile(self, api):
        """A blank attempt is refused even when the account has no password of its own: the rule is
        about the PROFILE (decision 3), so entry can never happen by accident. Documented limit:
        with no password set, Jellyfin accepts any supplied value (nothing to compare against), so
        a deliberate non-empty attempt DOES succeed — which is why the Household screen nudges the
        administrator to set a real one."""
        for user in api.users:
            if user["id"] == "uid-admin":
                user["has_password"] = False
        _sign_in(api)
        assert _select(api, "uid-admin").status_code == 401
        assert _select(api, "uid-admin", "anything-at-all").status_code == 200


class TestChangeMyOwnPassword:
    """Phase 3 (ADMIN_CREDENTIALS_PLAN.md §6): a person changes their OWN password.

    The rails exist because this screen sits in every profile's sidebar: it must be impossible for
    it to become an escalation path (changing somebody ELSE's password) or a way to REMOVE a
    profile's protection on a shared device.
    """

    def test_it_needs_a_session(self, api):
        r = api.client.post("/api/auth/profile/password",
                            json={"current_password": "old", "new_password": "new"})
        assert r.status_code == 401
        assert api.library.password_changes == [], "nothing may be attempted unsigned"

    def test_the_target_is_the_profile_never_a_client_supplied_id(self, api):
        """The provider method takes NO user id at all — the acting identity IS the target.

        That is a structural rail: there is no parameter a caller could fill in with somebody
        else's account, so "change my own" cannot be turned into "change theirs".
        """
        _sign_in(api)
        _select(api, "uid-kid")
        r = api.client.post("/api/auth/profile/password",
                            json={"current_password": "", "new_password": "kid-new-pw",
                                  "user_id": "uid-admin"})
        assert r.status_code == 200, r.text          # an extra field is ignored, not obeyed
        assert api.library.password_changes == [("", "kid-new-pw")]

    def test_an_empty_new_password_is_refused(self, api):
        """An account is CREATED without a password, not emptied afterwards — the same rule the
        household reset route states. Otherwise anyone at a shared device could strip the lock off
        the profile they are sitting on.

        ⚠ Only a TRULY empty value is refused. A whitespace-only password is a footgun, but the
        media server accepts it, and forbidding it here would be a second implementation of the
        server's contract — the trap that once made a password-LESS account unusable. The next test
        pins that distinction so a future "tidy-up" cannot quietly add the rule.
        """
        _sign_in(api)
        _select(api, "uid-kid")
        r = api.client.post("/api/auth/profile/password",
                            json={"current_password": "whatever", "new_password": ""})
        assert r.status_code == 400
        assert "not emptied" in r.json()["detail"]
        assert api.library.password_changes == []

    def test_a_whitespace_only_password_is_allowed_because_the_server_allows_it(self, api):
        _sign_in(api)
        _select(api, "uid-kid")
        r = api.client.post("/api/auth/profile/password",
                            json={"current_password": "", "new_password": "   "})
        assert r.status_code == 200, r.text
        assert api.library.password_changes == [("", "   ")]

    def test_a_wrong_current_password_is_a_generic_401(self, api):
        _sign_in(api)
        _select(api, "uid-kid")
        api.seen["password_reason"] = "wrong-password"
        r = api.client.post("/api/auth/profile/password",
                            json={"current_password": "typo", "new_password": "new-pw"})
        assert r.status_code == 401
        detail = r.json()["detail"]
        assert "current password" in detail.lower()
        assert "typo" not in detail and "new-pw" not in detail, (
            "the message must never echo either password")

    def test_a_server_refusal_that_is_not_a_typo_is_a_502(self, api):
        """`unreachable` covers "could not ask" and "refused for another reason" — neither is the
        user's typo, and saying so would send them hunting a password that was correct."""
        _sign_in(api)
        _select(api, "uid-kid")
        api.seen["password_reason"] = "unreachable"
        r = api.client.post("/api/auth/profile/password",
                            json={"current_password": "right", "new_password": "new-pw"})
        assert r.status_code == 502
        assert "refused" in r.json()["detail"].lower()

    def test_a_successful_change_says_nothing_but_ok(self, api):
        _sign_in(api)
        _select(api, "uid-kid")
        r = api.client.post("/api/auth/profile/password",
                            json={"current_password": "old-pw", "new_password": "new-pw"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert "new-pw" not in r.text and "old-pw" not in r.text

    def test_an_unbuildable_provider_is_a_503_not_a_refusal(self, api, monkeypatch):
        _sign_in(api)
        _select(api, "uid-kid")
        monkeypatch.setattr(auth_route, "build_library_service", lambda *a, **k: None)
        r = api.client.post("/api/auth/profile/password",
                            json={"current_password": "old", "new_password": "new"})
        assert r.status_code == 503
        assert "media server" in r.json()["detail"]

    def test_the_administrator_changes_their_own_password_too(self, api):
        """On the administrator's own profile the same route changes THEIR password — no separate
        admin path is needed, and no old password is bypassed either."""
        _sign_in(api)
        r = api.client.post("/api/auth/profile/password",
                            json={"current_password": ADMIN_PW, "new_password": "fresh"})
        assert r.status_code == 200, r.text
        assert api.library.password_changes == [(ADMIN_PW, "fresh")]

    def test_nothing_secret_reaches_the_logs(self, api, caplog):
        """The route logs the OUTCOME and the profile id — never a value."""
        import logging

        _sign_in(api)
        _select(api, "uid-kid")
        with caplog.at_level(logging.INFO):
            api.client.post("/api/auth/profile/password",
                            json={"current_password": "old-secret", "new_password": "new-secret"})
        text = caplog.text
        assert "old-secret" not in text and "new-secret" not in text
        assert "auth.password changed" in text


class TestTheProvidersOwnPasswordCall:
    """The payload and the failure taxonomy, at the provider — where they are easy to get wrong."""

    def _provider(self, monkeypatch, *, answers):
        from services.library.jellyfin import JellyfinLibraryProvider

        provider = JellyfinLibraryProvider(config=SimpleNamespace(
            JELLYFIN_URL="http://jellyfin.test", JELLYFIN_API_KEY="app-key",
            JELLYFIN_BROWSER_URL=""))
        calls = []

        def fake_api(method, path, body=None):
            calls.append((method, path, body))
            return answers.pop(0)

        monkeypatch.setattr(provider, "_api", fake_api)
        monkeypatch.setattr(provider, "_user_id", lambda: "uid-kid")
        return provider, calls

    def test_the_self_change_never_uses_the_admin_reset_flag(self, monkeypatch):
        """`ResetPassword: true` is the administrator's path (no old password needed). On a
        self-service screen it would be an escalation — so it must be False, always."""
        provider, calls = self._provider(monkeypatch, answers=[(True, {})])
        assert provider.change_own_password("old-pw", "new-pw") is None
        method, path, body = calls[0]
        assert method == "POST"
        assert path == "/Users/Password?userId=uid-kid", (
            "the target is the ACTING identity, as a query parameter")
        assert body == {"CurrentPw": "old-pw", "NewPw": "new-pw", "ResetPassword": False}

    def test_a_401_or_403_is_the_current_password_being_wrong(self, monkeypatch):
        for status in (401, 403):
            provider, _ = self._provider(monkeypatch, answers=[(False, {"status": status})])
            provider._last_api_error = {"status": status}
            assert provider.change_own_password("typo", "new-pw") == "wrong-password"

    def test_anything_else_is_an_honest_unreachable(self, monkeypatch):
        for status in (500, 502, None):
            provider, _ = self._provider(monkeypatch, answers=[(False, {"error": "boom"})])
            provider._last_api_error = {"status": status} if status else {"error": "OSError"}
            assert provider.change_own_password("old", "new") == "unreachable"

    def test_a_blank_new_password_never_reaches_the_server(self, monkeypatch):
        provider, calls = self._provider(monkeypatch, answers=[])
        assert provider.change_own_password("old", "  ".strip()) == "unreachable"
        assert calls == []
