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
        self.renames = []
        self.deleted = []
        self.error = None
        #: Set by a test to make the policy read FAIL (the server could not be asked).
        self.fail_policy = False
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
        if self.fail_policy:
            # The server could not be asked (unreachable / refusing the app's credential).
            # The fake says so the way the real provider does: None + a last_api_error.
            self.error = {"method": "GET", "path": f"/Users/{user_id}", "status": 401}
            return None
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
        # The FACADE's shape, not the provider's: `LibraryService.library_folders()` returns
        # {"provider": …, "folders": [...]}. The fake must mirror what the routes REALLY receive,
        # or a route that cannot read it passes every test and 500s in production (it did).
        return {"provider": "jellyfin", "folders": [dict(f) for f in self.folders]}

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

    def set_user_password(self, user_id, new_password):
        self.passwords.append({"user_id": user_id, "new_password": new_password})
        return True

    def rename_user(self, user_id, name):
        """Mirror what the route RECEIVES (the facade's row shape), not the provider's."""
        self.renames.append((user_id, name))
        for user in self.users:
            if user["id"] == user_id:
                user["name"] = name
                return dict(user)
        return None

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
    # The rename route writes the new name into the SESSION it is answering (otherwise the chip
    # keeps showing the old one). That writer must be the isolated store too, or the test would
    # reach into the real one.
    monkeypatch.setattr(admin_route, "default_session_store", lambda config=None: store)
    monkeypatch.setattr(session_mod.get_config(), "RKM_AUTH_REQUIRED", "false")
    return SimpleNamespace(client=TestClient(app), library=library, store=store)


def sign_in(env, user_id=ADMIN_ID):
    session_id, _ = env.store.create(user_id=user_id, user_name=user_id, token="jf-token")
    env.client.cookies.set(SESSION_COOKIE, session_id)
    return session_id


class TestTheCheckCannotLie:
    """503 vs 403 — the distinction that cost a live false accusation on 2026-09-12.

    The gate answers three different things: not signed in (401), not an administrator (403),
    and *could not ask the server* (503). Reporting the third as the second tells a signed-in
    administrator they lack permission, and sends them to the Jellyfin dashboard to "fix" a
    permission that was never the problem.
    """

    def test_an_unconfigured_media_server_is_503_not_403(self, env, monkeypatch):
        sign_in(env)
        monkeypatch.setattr(session_mod, "build_library_service", lambda *a, **k: None)
        r = env.client.get("/api/admin/users")
        assert r.status_code == 503
        assert "Could not reach the media server" in r.json()["detail"]

    def test_a_failed_policy_read_is_503_not_403(self, env):
        sign_in(env)
        env.library.fail_policy = True
        r = env.client.get("/api/admin/users")
        assert r.status_code == 503
        assert env.library.created == []

    def test_a_genuinely_demoted_admin_is_still_403(self, env):
        sign_in(env)
        for user in env.library.users:
            if user["id"] == ADMIN_ID:
                user["is_admin"] = False
        r = env.client.get("/api/admin/users")
        assert r.status_code == 403
        assert "administrator" in r.json()["detail"]


class TestFactoryWiring:
    """The seam that would have caught the live 403 — and did not exist.

    The route tests ABOVE replace ``build_library_service`` outright, and the provider tests
    build ``JellyfinLibraryProvider`` directly. Neither of them can notice that the object the
    routes actually receive is ``LibraryService``, a FACADE — so when the household methods were
    added to the provider only, every route call raised ``AttributeError``, the admin gate's
    try/except swallowed it, and the user was told they were not an administrator. These tests
    build the REAL thing from config and go through the facade.
    """

    def _service(self, monkeypatch, *, policy=None, users=None):
        from config.settings import get_config
        from services.library.factory import build_library_service

        cfg = get_config()
        monkeypatch.setattr(cfg, "JELLYFIN_URL", "http://jellyfin.test", raising=False)
        monkeypatch.setattr(cfg, "JELLYFIN_API_KEY", "test-key-not-a-secret", raising=False)
        service = build_library_service(cfg)
        assert service is not None, "the factory must build a service for a configured server"
        calls: list[tuple] = []

        def fake_api(method, path, body=None):
            calls.append((method, path, body))
            if path == "/Users":
                return True, users
            if path.startswith("/Users/"):
                return True, {"Policy": policy}
            return True, {}

        monkeypatch.setattr(service.providers[0], "_api", fake_api)
        return service, calls

    def test_the_facade_the_routes_use_exposes_every_household_method(self, monkeypatch):
        service, _ = self._service(monkeypatch)
        for name in ("list_users", "get_user_policy", "create_user", "mutate_user_policy",
                     "set_folder_access", "set_user_disabled", "set_user_password",
                     "rename_user", "delete_user", "last_api_error"):
            assert callable(getattr(service, name, None)), (
                f"LibraryService (the object the routes actually receive) is missing {name}(): "
                f"the route would raise AttributeError, the admin gate would swallow it, and the "
                f"user would be told they are not an administrator")

    def test_a_rename_sends_the_whole_account_not_just_a_name(self, monkeypatch):
        """The Policy trap — the reason a rename is not `{"Name": …}`.

        ``/Users/{id}/Policy`` REPLACES all 47 policy fields (already paid for once), and the
        server's own ``UserDto`` carries a ``Policy``. If ``POST /Users`` shares those semantics, a
        name-only body would wipe ``IsAdministrator`` — a LOCKOUT, the exact thing the user warned
        about. So the body carries the id, the name and the policy the server just reported, which
        is correct under EITHER semantics.
        """
        policy = {"IsAdministrator": True, "IsDisabled": False, "EnableAllFolders": False,
                  "EnabledFolders": ["f1"]}
        service, _ = self._service(monkeypatch, policy=policy)
        calls = []

        def fake_api(method, path, body=None):
            calls.append((method, path, body))
            if method == "GET":
                return True, {"Id": "u1", "Name": "admin", "Policy": policy}
            return True, {"Id": "u1", "Name": "Rajeev", "Policy": policy}

        monkeypatch.setattr(service.providers[0], "_api", fake_api)
        row = service.rename_user("u1", "Rajeev")
        assert row["name"] == "Rajeev", "the row comes from the server's answer"

        method, path, body = calls[-1]
        assert method == "POST"
        assert path == "/Users?userId=u1", (
            "the target is a QUERY parameter — measured from the server's own contract; the path "
            "form 404s")
        assert body["Name"] == "Rajeev"
        assert body["Policy"] == policy, (
            "the policy must travel back: under replace-wholesale semantics a name-only body would "
            "strip IsAdministrator")
        assert body["Id"] == "u1"
        assert "HasPassword" not in body, "a rename must have no way to touch a password"

    def test_a_rename_the_server_refuses_is_None_never_a_success(self, monkeypatch):
        service, _ = self._service(monkeypatch)
        monkeypatch.setattr(service.providers[0], "_api",
                            lambda *a, **k: (False, {"status": 403}))
        assert service.rename_user("u1", "Rajeev") is None

    def test_a_blank_name_never_reaches_the_server(self, monkeypatch):
        service, _ = self._service(monkeypatch)
        calls = []
        monkeypatch.setattr(service.providers[0], "_api",
                            lambda *a, **k: (calls.append(a), (True, {}))[1])
        assert service.rename_user("u1", "   ") is None
        assert calls == []

    def test_the_household_calls_work_through_the_facade(self, monkeypatch):
        """`list_users` and the policy read the gate depends on, end to end."""
        service, calls = self._service(
            monkeypatch,
            policy={"IsAdministrator": True, "IsDisabled": False, "EnableAllFolders": True},
            users=[{"Id": "u1", "Name": "admin", "Policy": {"IsAdministrator": True}}])
        rows = service.list_users()
        assert [r["name"] for r in rows] == ["admin"]
        assert rows[0]["is_admin"] is True and rows[0]["id"] == "u1"
        assert service.get_user_policy("u1") == {
            "IsAdministrator": True, "IsDisabled": False, "EnableAllFolders": True}
        assert [c[1] for c in calls] == ["/Users", "/Users/u1"]

    def test_a_refused_policy_read_reports_no_error_on_the_facade(self, monkeypatch):
        """`last_api_error()` must survive the facade too — the route's `warning` reads it."""
        service, _ = self._service(monkeypatch)
        assert service.last_api_error() is None


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

    def test_a_provider_shaped_list_is_also_accepted(self, env):
        """`library_folders()` is a dict on the facade and a list on the provider.

        The route must read BOTH: this failed in production on 2026-09-12 with
        `'str' object has no attribute 'get'` (500) because the facade's dict was iterated as if
        it were the provider's list. Pinned from both sides so neither shape can be "simplified"
        away.
        """
        sign_in(env)
        env.library.library_folders = lambda: [dict(f) for f in env.library.folders]
        r = env.client.get("/api/admin/libraries")
        assert r.status_code == 200
        assert [lib["name"] for lib in r.json()["libraries"]] == ["Movies", "TV Shows"]

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

    def _provider(self, policy, *, has_password=True):
        provider = JellyfinLibraryProvider(config=SimpleNamespace(
            JELLYFIN_URL="http://jellyfin:8096", JELLYFIN_API_KEY="key"))
        calls = []

        def fake_api(method, path, body=None):
            calls.append({"method": method, "path": path, "body": body})
            if method == "GET":
                return True, {"Id": "uid-1", "Name": "Guest", "Policy": dict(policy),
                              "HasPassword": has_password}
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

    def test_the_password_write_uses_the_working_shape_and_proves_itself(self):
        """Measured against Jellyfin 10.11.11 on 2026-09-12 — the shape matters more than it looks.

        `ResetPassword: true` answers **204, sets nothing, and CLEARS a password that existed**;
        the shape that really writes is `ResetPassword: false` (the administrator's own privilege
        is what authorises a reset, not the flag). That is what made "Set a password" on the
        Household screen report success and change nothing.

        So the flag is not a parameter any more — this test pins that it cannot come back — and a
        2xx alone is NOT accepted as success: the provider re-reads the account and reports True
        only when a password is really there.
        """
        provider, calls = self._provider({})
        assert provider.set_user_password("uid-1", "new-pw") is True
        assert calls[0]["path"] == "/Users/Password?userId=uid-1"
        assert calls[0]["body"] == {"CurrentPw": "", "NewPw": "new-pw", "ResetPassword": False}
        assert calls[1]["method"] == "GET", "the write must be confirmed, not assumed"

    def test_a_204_that_stored_nothing_is_not_success(self):
        """The exact live failure: accepted, reported OK, and the account still had no password."""
        provider, _ = self._provider({}, has_password=False)
        assert provider.set_user_password("uid-1", "new-pw") is False

    def test_an_empty_password_is_never_sent(self):
        provider, calls = self._provider({})
        assert provider.set_user_password("uid-1", "") is False
        assert calls == []

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


class TestRename:
    """Phase 2 (ADMIN_CREDENTIALS_PLAN.md §6): the ROLE is not the NAME.

    A person is identified by their id everywhere that matters, so a rename must change the LABEL
    and nothing else — not access, not a password, not anybody's watch state. These tests hold that
    line, and hold the two things a rename can silently get wrong: renaming to a name somebody else
    already has, and leaving the CURRENT session showing the old name.
    """

    def test_a_blank_name_is_refused_before_the_server_is_touched(self, env):
        sign_in(env)
        r = env.client.post(f"/api/admin/users/{MEMBER_ID}/rename", json={"name": "   "})
        assert r.status_code == 400
        assert env.library.renames == []

    def test_a_name_another_account_already_has_is_refused(self, env):
        """Jellyfin would allow it; the household would then have two 'admin' rows."""
        sign_in(env)
        r = env.client.post(f"/api/admin/users/{MEMBER_ID}/rename", json={"name": "aDmIn"})
        assert r.status_code == 409
        assert "already" in r.json()["detail"].lower()
        assert env.library.renames == []

    def test_a_rename_answers_with_what_the_server_now_holds(self, env):
        sign_in(env)
        r = env.client.post(f"/api/admin/users/{MEMBER_ID}/rename", json={"name": "Geetanjali"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user"]["name"] == "Geetanjali"
        assert body["was"] == "Guest"
        assert env.library.renames == [(MEMBER_ID, "Geetanjali")]

    def test_the_name_is_trimmed(self, env):
        sign_in(env)
        env.client.post(f"/api/admin/users/{MEMBER_ID}/rename", json={"name": "  Geetanjali  "})
        assert env.library.renames == [(MEMBER_ID, "Geetanjali")]

    def test_renaming_to_the_same_name_is_an_idempotent_no_op(self, env):
        """A double click must be neither an error nor a second write."""
        sign_in(env)
        r = env.client.post(f"/api/admin/users/{MEMBER_ID}/rename", json={"name": "Guest"})
        assert r.status_code == 200 and r.json()["user"]["name"] == "Guest"
        assert env.library.renames == [], "an identical name must not reach the server"

    def test_an_unknown_id_is_a_404(self, env):
        sign_in(env)
        r = env.client.post("/api/admin/users/nope/rename", json={"name": "X"})
        assert r.status_code == 404
        assert env.library.renames == []

    def test_a_refused_rename_is_a_502_and_never_a_false_success(self, env, monkeypatch):
        sign_in(env)
        monkeypatch.setattr(env.library, "rename_user", lambda user_id, name: None)
        r = env.client.post(f"/api/admin/users/{MEMBER_ID}/rename", json={"name": "Geetanjali"})
        assert r.status_code == 502
        assert "refused" in r.json()["detail"].lower()

    def test_the_current_session_follows_the_rename(self, env):
        """The chip reads the SESSION's stored name — the rename must update it, or the header
        keeps naming the account the old way until a profile is re-selected."""
        session_id = sign_in(env)
        env.store.set_profile(session_id, user_id=ADMIN_ID, user_name="admin", token="t")
        r = env.client.post(f"/api/admin/users/{ADMIN_ID}/rename", json={"name": "Rajeev"})
        assert r.status_code == 200, r.text
        row = env.store.lookup(session_id)
        assert row["user_name"] == "Rajeev", "the owner name is stale"
        assert row["profile_user_name"] == "Rajeev", "the profile name is stale"

    def test_renaming_an_OTHER_account_leaves_this_session_alone(self, env):
        session_id = sign_in(env)
        env.client.post(f"/api/admin/users/{MEMBER_ID}/rename", json={"name": "Geetanjali"})
        row = env.store.lookup(session_id)
        assert row["user_name"] == ADMIN_ID
        assert row.get("profile_user_name", "") == ""

    def test_it_needs_an_administrator(self, env):
        """The gate is shared with every other household route — 401 anonymous, 403 a member."""
        assert env.client.post(f"/api/admin/users/{MEMBER_ID}/rename",
                               json={"name": "X"}).status_code == 401
        sign_in(env, user_id=MEMBER_ID)
        assert env.client.post(f"/api/admin/users/{ADMIN_ID}/rename",
                               json={"name": "X"}).status_code == 403
        assert env.library.renames == []

    def test_a_rename_never_touches_a_password(self, env):
        """It cannot be a back door to credentials — asserted, not assumed."""
        sign_in(env)
        env.client.post(f"/api/admin/users/{MEMBER_ID}/rename", json={"name": "Geetanjali"})
        assert env.library.passwords == []
