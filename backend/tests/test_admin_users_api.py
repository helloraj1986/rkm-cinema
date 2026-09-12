"""Household accounts — provider + routes (AUTH_MULTIUSER_PLAN Phase 1b).

No network and no real account is ever created here: the provider's HTTP layer is replaced by
a recorder, and the routes are driven through the REAL app with a fake provider and a fake
session store. What is pinned:

* these routes are session-STRICT while the rest of the app is deliberately unenforced, and
  an administrator check that is asked of the SERVER every time (no cached flag);
* the policy write is READ-MODIFY-WRITE — Jellyfin replaces all 47 fields, so a partial body
  would silently reset permissions (the trap the probe found);
* a **password-less** account is a supported, deliberate state, and it is never an admin;
* passwords never reach a response body or a log record;
* the rails: no self-delete, no deleting the last administrator, no delete without the name
  typed out.
"""
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.routes.admin_users as admin_route
import api.session as session_mod
from api.main import app
from api.session import SessionContext
from services.auth import SESSION_COOKIE, SessionStore
from services.library.jellyfin import JellyfinLibraryProvider

ADMIN_ID = "uid-admin"
MEMBER_ID = "uid-member"
PASSWORD = "s3cret-pw"


class FakeLibrary:
    """Only the surface the household routes use. Records every mutation."""

    def __init__(self, users=None, folders=None):
        # COPIES of the dicts, not just of the list: a test that demotes or edits an
        # account must not reach through a shared module-level default into every later
        # test (it did — the admin check then failed for the admin in 19 tests at once).
        source = DEFAULT_USERS if users is None else users
        self.users = [dict(u) for u in source]
        folder_source = DEFAULT_FOLDERS if folders is None else folders
        self.folders = [dict(f) for f in folder_source]
        self.created = []
        self.folder_access = []
        self.disabled = []
        self.passwords = []
        self.deleted = []
        self.error = None
        self.next_id = "uid-new"
        #: Lets a test make the LISTING empty (or refused) while the signed-in account is
        #: still resolvable — the gate reads one account, the screen lists them all.
        self.list_users_override = None

    # --- reads
    def list_users(self):
        if self.list_users_override is not None:
            return [dict(u) for u in self.list_users_override]
        return [dict(u) for u in self.users]

    def get_user_policy(self, user_id):
        for user in self.users:
            if user["id"] == user_id:
                # The ADMIN check reads this: the server's own word, per request.
                return {"IsAdministrator": bool(user.get("is_admin")),
                        "IsDisabled": bool(user.get("disabled")),
                        "EnableAllFolders": bool(user.get("enable_all_folders")),
                        "EnabledFolders": list(user.get("enabled_folders") or []),
                        "EnableMediaPlayback": True, "MaxParentalRating": 18}
        return None

    def library_folders(self):
        return [dict(f) for f in self.folders]

    def last_api_error(self):
        return self.error

    # --- writes
    def create_user(self, name, password=""):
        if name.lower() == "explode":
            return None
        self.created.append({"name": name, "password": password})
        row = {"id": self.next_id, "name": name, "is_admin": False, "disabled": False,
               "has_password": bool(password), "enable_all_folders": False,
               "enabled_folders": [], "last_login": ""}
        self.users.append(row)
        return dict(row)

    def set_folder_access(self, user_id, library_ids=None, *, enable_all=False):
        self.folder_access.append({"user_id": user_id, "ids": list(library_ids or []),
                                   "enable_all": enable_all})
        for user in self.users:
            if user["id"] == user_id:
                user["enable_all_folders"] = bool(enable_all)
                user["enabled_folders"] = [] if enable_all else list(library_ids or [])
                return dict(user)
        return None

    def set_user_disabled(self, user_id, disabled):
        self.disabled.append({"user_id": user_id, "disabled": bool(disabled)})
        for user in self.users:
            if user["id"] == user_id:
                user["disabled"] = bool(disabled)
                return dict(user)
        return None

    def set_user_password(self, user_id, new_password, *, reset=True):
        self.passwords.append({"user_id": user_id, "new_password": new_password})
        return True

    def delete_user(self, user_id):
        self.deleted.append(user_id)
        self.users = [u for u in self.users if u["id"] != user_id]
        return True


DEFAULT_USERS = [
    {"id": ADMIN_ID, "name": "admin", "is_admin": True, "disabled": False,
     "has_password": True, "enable_all_folders": True, "enabled_folders": [],
     "last_login": "2026-09-12T07:25:10Z"},
    {"id": MEMBER_ID, "name": "Guest", "is_admin": False, "disabled": False,
     "has_password": False, "enable_all_folders": False,
     "enabled_folders": ["f1"], "last_login": ""},
]
DEFAULT_FOLDERS = [
    {"id": "f1", "name": "Movies", "collection_type": "movies", "path": "/data/Movies"},
    {"id": "f2", "name": "TV Shows", "collection_type": "tvshows",
     "path": "/media2/TV Shows"},
]
HOUSEHOLD_PATHS = ("/api/admin/users", "/api/admin/libraries")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """The real app, a fake provider, an isolated session store."""
    library = FakeLibrary()
    store = SessionStore(path=tmp_path / "sessions.json")

    monkeypatch.setattr(admin_route, "build_library_service", lambda cfg: library)
    monkeypatch.setattr(session_mod, "build_library_service", lambda cfg: library)
    monkeypatch.setattr(session_mod, "session_store", lambda config=None: store)
    monkeypatch.setattr(session_mod.get_config(), "RKM_AUTH_REQUIRED", "false")
    return SimpleNamespace(client=TestClient(app), library=library, store=store)


def sign_in(env, user_id=ADMIN_ID):
    session_id, _ = env.store.create(user_id=user_id, user_name=user_id, token="jf-token")
    env.client.cookies.set(SESSION_COOKIE, session_id)
    return session_id


class TestAccessControl:
    """These routes are strict in a world where nothing else is."""

    def test_an_anonymous_caller_is_refused_even_while_unenforced(self, env):
        assert env.client.get("/api/admin/users").status_code == 401
        assert env.client.get("/api/admin/libraries").status_code == 401
        assert env.client.post("/api/admin/users", json={"name": "X"}).status_code == 401
        assert env.client.post(f"/api/admin/users/{MEMBER_ID}/policy",
                               json={"disabled": True}).status_code == 401
        assert env.client.post(f"/api/admin/users/{MEMBER_ID}/password",
                               json={"new_password": "x"}).status_code == 401
        assert env.client.request("DELETE", f"/api/admin/users/{MEMBER_ID}",
                                  json={"confirm_name": "Guest"}).status_code == 401
        assert env.library.created == [] and env.library.deleted == []

    def test_a_signed_in_non_administrator_is_refused(self, env):
        sign_in(env, MEMBER_ID)
        r = env.client.get("/api/admin/users")
        assert r.status_code == 403
        assert "administrator" in r.json()["detail"].lower()
        assert env.library.created == []

    def test_the_administrator_check_is_asked_of_the_server_every_time(self, env):
        """Demote the account mid-session: the very next call must be refused."""
        sign_in(env, ADMIN_ID)
        assert env.client.get("/api/admin/users").status_code == 200
        for user in env.library.users:
            if user["id"] == ADMIN_ID:
                user["is_admin"] = False
        assert env.client.get("/api/admin/users").status_code == 403


class TestListing:
    def test_the_household_lists_without_any_secret(self, env):
        sign_in(env)
        r = env.client.get("/api/admin/users")
        assert r.status_code == 200
        body = r.json()
        assert body["signed_in_as"] == ADMIN_ID
        names = [u["name"] for u in body["users"]]
        assert names == ["admin", "Guest"]
        assert body["users"][1]["has_password"] is False
        assert "password" not in r.text.lower().replace("has_password", "")

    def test_the_libraries_are_the_tick_box_list(self, env):
        sign_in(env)
        body = env.client.get("/api/admin/libraries").json()
        assert [lib["name"] for lib in body["libraries"]] == ["Movies", "TV Shows"]
        assert body["libraries"][0]["id"] == "f1"

    def test_an_empty_listing_says_why_instead_of_looking_empty(self, env):
        """A refused listing must not read as "there are no accounts"."""
        sign_in(env)
        env.library.list_users_override = []          # the SERVER answered with nothing
        env.library.error = {"method": "GET", "path": "/Users", "status": 403}
        body = env.client.get("/api/admin/users").json()
        assert body["users"] == []
        assert "refused" in body["warning"].lower()


class TestCreate:
    def test_a_member_can_be_created_without_a_password(self, env):
        """The user's decision (1c): no password, sign in with the username alone."""
        sign_in(env)
        r = env.client.post("/api/admin/users", json={"name": "Raj", "library_ids": ["f1"]})
        assert r.status_code == 200, r.text
        assert env.library.created == [{"name": "Raj", "password": ""}]
        assert env.library.folder_access == [{"user_id": "uid-new", "ids": ["f1"],
                                             "enable_all": False}]
        body = r.json()
        assert body["user"]["is_admin"] is False      # never an admin, ever
        assert body["user"]["has_password"] is False
        assert body["granted"] == ["f1"]

    def test_omitting_the_library_list_grants_every_library(self, env):
        """The chosen default (2a): a new member gets the admin's own access."""
        sign_in(env)
        r = env.client.post("/api/admin/users", json={"name": "Raj"})
        assert r.status_code == 200
        assert env.library.folder_access[0]["enable_all"] is True
        assert r.json()["granted"] == ["f1", "f2"]

    def test_an_empty_library_list_grants_nothing(self, env):
        sign_in(env)
        env.client.post("/api/admin/users", json={"name": "Raj", "library_ids": []})
        assert env.library.folder_access[0] == {"user_id": "uid-new", "ids": [],
                                               "enable_all": False}

    def test_a_blank_name_is_refused(self, env):
        sign_in(env)
        assert env.client.post("/api/admin/users", json={"name": "   "}).status_code == 400
        assert env.library.created == []

    def test_a_duplicate_name_is_refused_case_insensitively(self, env):
        sign_in(env)
        r = env.client.post("/api/admin/users", json={"name": "guest"})
        assert r.status_code == 409
        assert env.library.created == []

    def test_a_server_that_creates_nothing_is_reported_honestly(self, env):
        sign_in(env)
        r = env.client.post("/api/admin/users", json={"name": "explode"})
        assert r.status_code == 502
        assert "did not create" in r.json()["detail"]


class TestPolicyAndPassword:
    def test_library_access_and_disable_are_independent(self, env):
        sign_in(env)
        r = env.client.post(f"/api/admin/users/{MEMBER_ID}/policy",
                            json={"library_ids": ["f2"]})
        assert r.status_code == 200
        assert env.library.folder_access == [{"user_id": MEMBER_ID, "ids": ["f2"],
                                             "enable_all": False}]
        assert env.library.disabled == []          # omitted field = left alone
        assert r.json()["user"]["enabled_folders"] == ["f2"]

    def test_disabling_alone_leaves_folders_alone(self, env):
        sign_in(env)
        env.client.post(f"/api/admin/users/{MEMBER_ID}/policy", json={"disabled": True})
        assert env.library.disabled == [{"user_id": MEMBER_ID, "disabled": True}]
        assert env.library.folder_access == []

    def test_a_unknown_account_is_a_404_not_a_silent_noop(self, env):
        sign_in(env)
        assert env.client.post("/api/admin/users/nope/policy",
                               json={"disabled": True}).status_code == 404
        assert env.library.disabled == []

    def test_a_password_can_be_set_but_never_read(self, env):
        sign_in(env)
        r = env.client.post(f"/api/admin/users/{MEMBER_ID}/password",
                            json={"new_password": PASSWORD})
        assert r.status_code == 200
        assert env.library.passwords == [{"user_id": MEMBER_ID, "new_password": PASSWORD}]
        assert r.json() == {"ok": True}
        assert PASSWORD not in r.text

    def test_an_empty_password_is_refused_here(self, env):
        """An account is CREATED without one; this route is not how it is emptied."""
        sign_in(env)
        r = env.client.post(f"/api/admin/users/{MEMBER_ID}/password", json={"new_password": ""})
        assert r.status_code == 400
        assert env.library.passwords == []


class TestDeleteRails:
    def test_deleting_yourself_is_refused(self, env):
        sign_in(env)
        r = env.client.request("DELETE", f"/api/admin/users/{ADMIN_ID}",
                               json={"confirm_name": "admin"})
        assert r.status_code == 400
        assert "signed in as" in r.json()["detail"]
        assert env.library.deleted == []

    def test_another_administrator_can_be_deleted(self, env):
        """The rail is about the LAST administrator, not about administrators in general."""
        env.library.users.append({"id": "uid-other-admin", "name": "other", "is_admin": True,
                                  "disabled": False, "has_password": True,
                                  "enable_all_folders": True, "enabled_folders": [],
                                  "last_login": ""})
        sign_in(env, ADMIN_ID)
        r = env.client.request("DELETE", "/api/admin/users/uid-other-admin",
                               json={"confirm_name": "other"})
        assert r.status_code == 200
        assert env.library.deleted == ["uid-other-admin"]

    def test_deleting_the_only_administrator_is_refused(self, env):
        """What a user actually hits when there is one admin left: the SELF rail.

        The route ALSO has a last-administrator check, and it is a genuine backstop — but
        with the gate in place (the caller must be an enabled administrator) any non-self
        admin target inevitably has the caller as company, so it cannot fire from here. The
        self rail is what protects the last administrator, and this pins it.
        """
        sign_in(env, ADMIN_ID)
        r = env.client.request("DELETE", f"/api/admin/users/{ADMIN_ID}",
                               json={"confirm_name": "admin"})
        assert r.status_code == 400
        assert env.library.deleted == []

    def test_a_disabled_administrator_cannot_manage_anything(self, env):
        """A disabled account cannot use the server, so it must not be able to manage it."""
        for user in env.library.users:
            if user["id"] == ADMIN_ID:
                user["disabled"] = True
        sign_in(env, ADMIN_ID)
        assert env.client.get("/api/admin/users").status_code == 403
        assert env.library.created == []

    def test_the_name_must_be_typed_out(self, env):
        sign_in(env)
        r = env.client.request("DELETE", f"/api/admin/users/{MEMBER_ID}",
                               json={"confirm_name": "Someone Else"})
        assert r.status_code == 400
        assert "Guest" in r.json()["detail"]
        assert env.library.deleted == []

    def test_a_confirmed_delete_goes_through(self, env):
        sign_in(env)
        r = env.client.request("DELETE", f"/api/admin/users/{MEMBER_ID}",
                               json={"confirm_name": "guest"})   # case-insensitive on purpose
        assert r.status_code == 200
        assert env.library.deleted == [MEMBER_ID]
        assert r.json()["name"] == "Guest"


class TestNoSecretLeaks:
    def test_no_response_or_log_line_carries_a_password(self, env, caplog):
        sign_in(env)
        with caplog.at_level(logging.DEBUG):
            create = env.client.post("/api/admin/users",
                                     json={"name": "Raj", "password": PASSWORD})
            change = env.client.post(f"/api/admin/users/{MEMBER_ID}/password",
                                     json={"new_password": PASSWORD + "-2"})
        log_text = " ".join(r.getMessage() for r in caplog.records)
        for text in (create.text, change.text, log_text):
            assert PASSWORD not in text
            assert PASSWORD + "-2" not in text


class TestProviderPolicyWrite:
    """The provider-level trap: the policy is REPLACED wholesale, so writes must merge."""

    def _provider(self, policy):
        provider = JellyfinLibraryProvider(config=SimpleNamespace(
            JELLYFIN_URL="http://jellyfin:8096", JELLYFIN_API_KEY="key"))
        calls = []

        def fake_api(method, path, body=None):
            calls.append({"method": method, "path": path, "body": body})
            if method == "GET":
                return True, {"Id": "uid-1", "Name": "Guest", "Policy": dict(policy)}
            return True, {}

        provider._api = fake_api
        return provider, calls

    def test_a_folder_grant_posts_the_whole_policy_back(self):
        existing = {"IsAdministrator": False, "IsDisabled": False, "EnableAllFolders": True,
                    "EnabledFolders": [], "EnableMediaPlayback": True, "MaxParentalRating": 18,
                    "EnableRemoteControlOfOtherUsers": False}
        provider, calls = self._provider(existing)
        result = provider.set_folder_access("uid-1", ["f1", "f2"])

        assert result is not None
        posted = calls[-1]
        assert posted["method"] == "POST"
        assert posted["path"] == "/Users/uid-1/Policy"
        # the change…
        assert posted["body"]["EnabledFolders"] == ["f1", "f2"]
        assert posted["body"]["EnableAllFolders"] is False
        # …and everything the request did NOT mention survives untouched
        assert posted["body"]["EnableMediaPlayback"] is True
        assert posted["body"]["MaxParentalRating"] == 18
        assert posted["body"]["IsAdministrator"] is False

    def test_disabling_merges_too(self):
        existing = {"IsDisabled": False, "EnableMediaPlayback": True, "EnabledFolders": ["f1"]}
        provider, calls = self._provider(existing)
        provider.set_user_disabled("uid-1", True)
        assert calls[-1]["body"]["IsDisabled"] is True
        assert calls[-1]["body"]["EnableMediaPlayback"] is True
        assert calls[-1]["body"]["EnabledFolders"] == ["f1"]

    def test_a_failed_read_means_no_write_at_all(self):
        """Without the current policy a merge is impossible — so nothing is sent."""
        provider, calls = self._provider({})
        provider._api = lambda method, path, body=None: (False, {"status": 403})
        assert provider.set_folder_access("uid-1", ["f1"]) is None
        assert calls == []

    def test_the_password_route_uses_the_query_form(self):
        provider, calls = self._provider({})
        provider.set_user_password("uid-1", "new-pw")
        assert calls[-1]["path"] == "/Users/Password?userId=uid-1"
        assert calls[-1]["body"] == {"CurrentPw": "", "NewPw": "new-pw", "ResetPassword": True}

    def test_creating_without_a_password_omits_the_key_entirely(self):
        """`Password: ""` is a different request from omitting it."""
        provider, calls = self._provider({})
        provider.create_user("Guest")
        assert calls[-1] == {"method": "POST", "path": "/Users/New",
                             "body": {"Name": "Guest"}}

    def test_creating_with_a_password_sends_it_once(self):
        provider, calls = self._provider({})
        provider.create_user("Guest", "pw-123")
        assert calls[-1]["body"] == {"Name": "Guest", "Password": "pw-123"}


class TestContract:
    def test_the_household_paths_are_in_the_contract(self):
        paths = app.openapi()["paths"]
        for path in HOUSEHOLD_PATHS:
            assert path in paths, path
        assert "/api/admin/users/{user_id}/policy" in paths
        assert "/api/admin/users/{user_id}/password" in paths
        assert "/api/admin/users/{user_id}" in paths

    def test_no_admin_RESPONSE_model_carries_a_password(self):
        """A caller SUPPLIES a password (the request schema has one); nothing ever returns
        one — the contract is public documentation, and a response field would invite one."""
        import json as _json

        for path, operations in app.openapi()["paths"].items():
            if not path.startswith("/api/admin"):
                continue
            for method, operation in operations.items():
                for status, response in (operation.get("responses") or {}).items():
                    body = _json.dumps(response.get("content") or {})
                    assert "password" not in body.lower(), (path, method, status)
