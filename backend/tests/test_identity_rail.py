"""The identity RAIL (plan `ADMIN_CREDENTIALS_PLAN.md` §6f) — a request that arrived as somebody
must never act as a stranger.

**The bug this exists for (measured 2026-09-12).** `POST /api/auth/profile/password` lives on the
auth router, which is deliberately NOT session-scoped (`api/main.py::SESSION_SCOPED` — sign-in must
work signed out). The route resolved the session from the request, then called the provider without
publishing it, so the provider fell back to:

* the **app's API key** for the credential (elevated ⇒ the write SUCCEEDED), and
* `_user_id()`'s historical lookup, **the first account in `/Users` order**,

and the change landed on a DIFFERENT PERSON while the screen reported success. It looked
intermittent because the "first account" moves as profiles are created and removed.

**The rail.** `session_context_from_request` — the ONE place a cookie becomes a session — records
the session it resolved. The identity helpers (`acting_media_token`, `acting_user_id`,
`acting_profile_is_owner`) then refuse to fall back in that state: `UnpublishedIdentityError`,
before any URL is built, so the wrong write never reaches the media server. `owner_media_token` is
the deliberate exception (its fallback IS the administrator's own credential, and every call it
serves is server administration).

**What must NOT change** (and is asserted here): no request context at all — the provisioner, the
scheduler's jobs, every tool, the unit tests — and a request that arrived as NOBODY (a signed-out
visitor, which `RKM_AUTH_REQUIRED=false` makes normal) both keep today's behaviour exactly.

**Why this file drives the REAL provider and the REAL routes.** The substitute identity only exists
in the real provider's fallbacks; a fake library can never reproduce it (`plan §6e`). So the media
server is stubbed at the `urllib` layer and everything above it — routers, session store,
contextvars, provider, URL building — is the shipped code.
"""
from __future__ import annotations

import ast
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from api import session as session_mod
from api.main import app
from api.routes import auth as auth_route
from api.session import (
    SessionContext,
    UnpublishedIdentityError,
    acting_media_token,
    acting_profile_is_owner,
    acting_user_id,
    resolved_route,
    resolved_session_from_request,
)
from services.auth import SESSION_COOKIE, SessionStore
from services.library.jellyfin import JellyfinLibraryProvider

APP_KEY = "app-key-ADMIN"
OWNER_ID = "uid-admin"
OWNER_TOKEN = "token-uid-admin"
PROFILE_ID = "uid-kid"
PROFILE_TOKEN = "token-uid-kid"
#: `"the first account in /Users order"` — in production the administrator, and the reason the
#: bug looked intermittent: as profiles are created and removed, this one moves. Deliberately NOT
#: the profile the session below selects, so a fallback is visible.
FIRST_ID = "uid-first"
STRANGER_ID = FIRST_ID
STRANGER_TOKEN = "token-uid-first"

#: Jellyfin's own `/Users` rows, in the order the stub returns them. `FIRST_ID` is first.
SERVER_USERS = [
    {"Id": STRANGER_ID, "Name": "Meenu", "HasPassword": True, "LastLoginDate": "",
     "Policy": {"IsAdministrator": False, "IsDisabled": False, "EnableAllFolders": True,
                "EnabledFolders": []}},
    {"Id": PROFILE_ID, "Name": "Kid", "HasPassword": False, "LastLoginDate": "",
     "Policy": {"IsAdministrator": False, "IsDisabled": False, "EnableAllFolders": False,
                "EnabledFolders": ["f1"]}},
    {"Id": OWNER_ID, "Name": "admin", "HasPassword": True, "LastLoginDate": "",
     "Policy": {"IsAdministrator": True, "IsDisabled": False, "EnableAllFolders": True,
                "EnabledFolders": []}},
]


def _config(**over):
    base = dict(JELLYFIN_URL="http://jellyfin.test:8096", JELLYFIN_API_KEY=APP_KEY,
                JELLYFIN_BROWSER_URL="", JELLYFIN_SCAN_TTL=60, media_libraries=[],
                media_library_warnings=[], RKM_AUTH_REQUIRED="false")
    base.update(over)
    ns = SimpleNamespace(**base)
    ns.auth_required = lambda: str(ns.RKM_AUTH_REQUIRED).lower() == "true"
    return ns


def _context(*, profile: bool) -> SessionContext:
    """A signed-in session, optionally with somebody else's profile selected."""
    return SessionContext(
        session_id="sid", user_id=OWNER_ID, user_name="admin", token=OWNER_TOKEN,
        profile_user_id=PROFILE_ID if profile else "",
        profile_user_name="Kid" if profile else "",
        profile_token=PROFILE_TOKEN if profile else "",
    )


@pytest.fixture()
def arrived_as_somebody():
    """A request that RESOLVED a session and published nothing — the rail's one bad state.

    Set through the module's own recorder (its public seam), and undone afterwards so it cannot
    leak into another test.
    """
    token = session_mod.set_resolved_session(_context(profile=True),
                                             "POST /api/auth/profile/password")
    yield _context(profile=True)
    session_mod.reset_resolved_session(token)


class _Response:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()
        self.status = 200
        self.headers = {"Content-Type": "application/json"}

    def read(self, *_a):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class StubMediaServer:
    """The media server, at the `urllib` layer, recording every call it is asked for.

    Deliberately NOT a fake library. The substitute identity the rail exists to remove is created
    by the REAL provider's fallbacks, so only the real provider can prove they are gone — and the
    URL is the only place the credential and the target id are both visible.
    """

    def __init__(self):
        #: Every call: {url, path, token, user_ids, body}.
        self.calls: list[dict] = []

    # -- assertions the tests read ----------------------------------------
    @property
    def urls(self) -> list[str]:
        return [c["url"] for c in self.calls]

    def urls_since(self, n: int) -> list[str]:
        return [c["url"] for c in self.calls[n:]]

    def calls_since(self, n: int) -> list[dict]:
        return self.calls[n:]

    def named_user_ids(self, since: int = 0) -> set[str]:
        """Every Jellyfin user id the calls acted on, from the PATH and the query alike."""
        found: set[str] = set()
        for call in self.calls[since:]:
            found |= set(call["user_ids"])
        return found

    # -- what the app sees ------------------------------------------------
    def __call__(self, url, *a, **kw):
        full = getattr(url, "full_url", None) or str(url)
        parts = urllib.parse.urlsplit(full)
        query = urllib.parse.parse_qs(parts.query)
        segments = [s for s in parts.path.split("/") if s]
        target = [s for s in segments[1:2]] if segments[:1] == ["Users"] else []
        if target and target[0] in ("Password", "AuthenticateByName", "New"):
            target = []          # `/Users/Password?userId=` names its target in the QUERY
        self.calls.append({
            "url": full,
            "path": parts.path,
            "token": (query.get("api_key") or [""])[0],
            "user_ids": set(target) | set(query.get("userId") or []),
            "body": _body_of(url),
        })
        if parts.path.endswith("/Users/AuthenticateByName"):
            name = _username_of(url)
            row = next((u for u in SERVER_USERS if u["Name"] == name), None)
            if row is None:
                raise urllib.error.HTTPError(full, 401, "Unauthorized", {}, None)
            return _Response({"User": {"Id": row["Id"], "Name": row["Name"]},
                              "AccessToken": f"token-{row['Id']}"})
        if parts.path == "/Users":
            return _Response(SERVER_USERS)
        if parts.path.startswith("/Users/"):
            row = next((u for u in SERVER_USERS if u["Id"] == segments[1]), None)
            return _Response(row or {})
        if parts.path == "/Library/VirtualFolders":
            return _Response([{"ItemId": "f1", "Name": "Movies", "CollectionType": "movies",
                               "Locations": ["/data/Movies"]}])
        if parts.path == "/UserViews":
            return _Response({"Items": [{"Id": "f1", "Name": "Movies"}]})
        return _Response({"Items": []})


def _body_of(url) -> dict:
    raw = getattr(url, "data", None)
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _username_of(url) -> str:
    return str(_body_of(url).get("Username") or _body_of(url).get("username") or "")


# ------------------------------------------------------------------ 1. the rail, unit by unit

class TestTheRail:
    """Three states, three answers — and only the third one is an error."""

    def test_a_request_that_resolved_a_session_may_not_fall_back(self, arrived_as_somebody):
        for helper in (lambda: acting_media_token(_config()),
                       lambda: acting_user_id(),
                       lambda: acting_profile_is_owner()):
            with pytest.raises(UnpublishedIdentityError):
                helper()

    def test_the_refusal_names_the_route_and_the_account(self, arrived_as_somebody):
        """Diagnosable from the log alone — this is the session's ONLY evidence."""
        with pytest.raises(UnpublishedIdentityError) as excinfo:
            acting_user_id()
        message = str(excinfo.value)
        assert "POST /api/auth/profile/password" in message
        assert PROFILE_ID in message, "the account that arrived must be named, not just 'somebody'"

    def test_no_request_context_at_all_is_unchanged(self):
        """The fail-safe: the provisioner, the scheduler's jobs and every tool live here."""
        assert acting_media_token(_config()) == APP_KEY
        assert acting_user_id() == ""
        assert acting_profile_is_owner() is True

    def test_a_request_that_arrived_as_nobody_is_unchanged(self):
        """With `RKM_AUTH_REQUIRED=false` an anonymous request is a normal request, not a bug."""
        token = session_mod.set_resolved_session(None, "GET /api/library")
        try:
            assert acting_media_token(_config()) == APP_KEY
            assert acting_user_id() == ""
            assert acting_profile_is_owner() is True
        finally:
            session_mod.reset_resolved_session(token)

    def test_the_owner_token_is_deliberately_not_guarded(self, arrived_as_somebody):
        """Account administration runs AS the administrator, so its fallback is not a stranger.

        Refusing here would break the household routes on a routine request; the fallback is the
        app's own key, which is the credential those calls are made as by definition.
        """
        from api.session import owner_media_token

        assert owner_media_token(_config()) == APP_KEY

    def test_resolving_a_session_records_it(self, tmp_path, monkeypatch):
        """The wiring half: a REAL request through the REAL resolver marks itself.

        Everything else here sets the marker by hand, so without this test the rail could be
        perfectly tested while `session_context_from_request` never actually recorded anything.
        """
        store = SessionStore(path=tmp_path / "sessions.json")
        sid, _ = store.create(user_id=OWNER_ID, user_name="admin", token=OWNER_TOKEN)
        store.set_profile(sid, user_id=PROFILE_ID, user_name="Kid", token=PROFILE_TOKEN)
        monkeypatch.setattr(session_mod, "session_store", lambda config=None: store)
        request = Request({"type": "http", "method": "POST", "path": "/api/auth/profile/password",
                           "scheme": "http", "server": ("testserver", 80),
                           "headers": [(b"cookie", f"{SESSION_COOKIE}={sid}".encode())]})
        try:
            context = session_mod.session_context_from_request(request)
            assert context is not None and context.profile_id() == PROFILE_ID
            assert resolved_session_from_request() is context
            assert resolved_route() == "POST /api/auth/profile/password", (
                "the route is recorded so the ERROR can say which route forgot to publish")
        finally:
            session_mod.set_resolved_session(None)

    def test_an_unknown_cookie_is_not_a_stranger(self, tmp_path, monkeypatch):
        """A stale cookie resolves to nothing — that is a signed-out visitor, not a wiring bug."""
        store = SessionStore(path=tmp_path / "sessions.json")
        monkeypatch.setattr(session_mod, "session_store", lambda config=None: store)
        request = Request({"type": "http", "method": "GET", "path": "/api/library",
                           "scheme": "http", "server": ("testserver", 80),
                           "headers": [(b"cookie", f"{SESSION_COOKIE}=gone".encode())]})
        try:
            assert session_mod.session_context_from_request(request) is None
            assert acting_media_token(_config()) == APP_KEY
        finally:
            session_mod.set_resolved_session(None)


# ------------------------------------------------- 2. the provider, with its real fallbacks

class TestTheProviderNeverActsAsAStranger:
    """The bug at the provider, where it actually lived."""

    def test_the_first_account_fallback_is_refused_and_nothing_is_sent(self, arrived_as_somebody,
                                                                      monkeypatch):
        provider = JellyfinLibraryProvider(config=_config())
        server = StubMediaServer()
        monkeypatch.setattr(urllib.request, "urlopen", server)

        with pytest.raises(UnpublishedIdentityError):
            provider.change_own_password("old-pw", "new-pw")

        assert server.calls == [], (
            "the write REACHED the media server. Without the rail this is how a change meant for "
            "one profile lands on whichever account is first in /Users order — reported success "
            "included.")

    def test_the_first_account_fallback_still_works_with_no_request_at_all(self, monkeypatch):
        """The counterweight, and it is load-bearing: the provisioner, the scheduler and every
        tool resolve the administrator this way. The rail must not touch them."""
        provider = JellyfinLibraryProvider(config=_config())
        server = StubMediaServer()
        monkeypatch.setattr(urllib.request, "urlopen", server)
        assert provider._user_id() == FIRST_ID, (
            "with no request context the historical lookup must be byte-identical to before")
        assert server.calls and server.calls[0]["token"] == APP_KEY

    def test_an_account_administration_call_is_never_made_as_the_profile(self, monkeypatch):
        """`/Users*` is administrator-only on the server, so the credential must be the owner's.

        For a session with a MEMBER's profile selected, acting on the member's token earns a 403
        and the screen is told "there are no profiles on this server".
        """
        published = session_mod.set_current_session(_context(profile=True))
        try:
            provider = JellyfinLibraryProvider(config=_config())
            server = StubMediaServer()
            monkeypatch.setattr(urllib.request, "urlopen", server)
            provider.list_users()
            provider.get_user_policy(OWNER_ID)
        finally:
            session_mod.reset_current_session(published)

        assert server.calls, "nothing was asked of the server — the test proves nothing"
        for call in server.calls:
            assert call["token"] == OWNER_TOKEN, (
                f"{call['path']} was made as {call['token']!r} — account administration must run as "
                "the administrator, or the media server refuses it")
            assert call["token"] != PROFILE_TOKEN

    def test_an_unknown_credential_is_a_loud_error(self, monkeypatch):
        provider = JellyfinLibraryProvider(config=_config())
        monkeypatch.setattr(urllib.request, "urlopen", StubMediaServer())
        with pytest.raises(ValueError):
            provider._api("GET", "/Users", credential="whatever")

    def test_the_facade_does_not_dress_the_rail_up_as_a_server_failure(self):
        """Measured while building this: the rail fired correctly, and the facade then answered the
        screen *"the media server refused the password change"* — blaming the server for our own
        mis-wiring. The facade contains PROVIDER failures; this one must travel out."""
        from services.library.service import LibraryService

        class Refusing:
            name = "jellyfin"

            def change_own_password(self, current_password, new_password):
                raise UnpublishedIdentityError("a route called the provider as nobody")

        with pytest.raises(UnpublishedIdentityError):
            LibraryService(providers=[Refusing()]).change_own_password("old", "new")


class TestOnlyTheSelfChangeActsAsTheProfile:
    """A structural backstop for the one call that MUST use the acting identity."""

    def test_no_other_provider_call_reaches_for_the_acting_credential(self):
        """`change_own_password` is the only caller, and for a reason: the media server decides a
        self-change by the token that asks, so on the owner credential the old password would stop
        being checked at all (an escalation) — and every other `_api` caller is administration,
        which a member's token may not do."""
        src = Path(__file__).resolve().parent.parent / "services" / "library" / "jellyfin.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        acting_callers: set[str] = set()
        for function in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for node in ast.walk(function):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Attribute) and func.attr == "_api"):
                    continue
                for kw in node.keywords:
                    if kw.arg == "credential" and getattr(kw.value, "value", None) == "acting":
                        acting_callers.add(function.name)
        assert acting_callers == {"change_own_password"}, (
            "these provider methods make a Jellyfin call as the ACTING identity: "
            f"{sorted(acting_callers)}. Only the self-service password change may — everything "
            "else is server administration and must use the owner's credential (`_api`'s default).")


# ----------------------------------------------------- 3. every auth route, over real HTTP

def _auth_client(tmp_path, monkeypatch):
    """The real app over HTTP with a stub media server, signed in and on a profile.

    Everything between the cookie and the URL is shipped code: the routers, the session store,
    `session_context_from_request`, both contextvars, the real provider and its URL building.
    """
    store = SessionStore(path=tmp_path / "sessions.json")
    server = StubMediaServer()
    cfg = _config()
    monkeypatch.setattr(session_mod, "session_store", lambda config=None: store)
    monkeypatch.setattr(auth_route, "default_session_store", lambda config=None: store)
    monkeypatch.setattr(auth_route, "get_config", lambda: cfg)
    monkeypatch.setattr(urllib.request, "urlopen", server)

    client = TestClient(app)
    signed_in = client.post("/api/auth/login", json={"username": "admin", "password": "admin-pw"})
    assert signed_in.status_code == 200, signed_in.text
    chosen = client.post("/api/auth/profile", json={"user_id": PROFILE_ID, "password": ""})
    assert chosen.status_code == 200, chosen.text
    return SimpleNamespace(client=client, server=server, store=store, cfg=cfg)


@pytest.fixture()
def signed_in(tmp_path, monkeypatch):
    return _auth_client(tmp_path, monkeypatch)


class TestNoAuthRouteActsAsAStranger:
    """`/api/auth/*` is the ONE router with no `require_session`, and it is where the bug lived.

    So every route on it is driven with a LIVE cookie — one with somebody's profile selected — and
    the assertion is the general shape of the bug: **no request may act on a Jellyfin user id the
    session did not choose.** A first-account fallback names `uid-first`, which nothing here may
    ever legitimately touch.
    """

    ROUTES = [
        ("get", "/api/auth/profiles", None),
        ("post", "/api/auth/profile", {"user_id": PROFILE_ID, "password": ""}),
        ("post", "/api/auth/profile/password",
         {"current_password": "", "new_password": "new-pw"}),
        ("get", "/api/auth/me", None),
        ("post", "/api/auth/logout", None),
        ("post", "/api/auth/login", {"username": "admin", "password": "admin-pw"}),
    ]

    @pytest.mark.parametrize("verb,path,body", ROUTES)
    def test_it_never_acts_on_an_account_the_session_did_not_choose(self, signed_in, verb, path,
                                                                   body):
        before = len(signed_in.server.calls)
        response = getattr(signed_in.client, verb)(path, **({"json": body} if body else {}))
        assert response.status_code != 500, (
            f"{verb.upper()} {path} failed outright: {response.text}. If this is the identity rail, "
            "the route resolved a session and never published it (plan §6f).")

        named = signed_in.server.named_user_ids(since=before)
        assert named <= {PROFILE_ID, OWNER_ID}, (
            f"{verb.upper()} {path} acted on {sorted(named)} while the session had {PROFILE_ID} "
            "selected. That is the 2026-09-12 bug: a resolved session, an unpublished identity, and "
            "a write that lands on whichever account the server lists first.")

    def test_the_password_write_names_the_profile_and_carries_its_own_credential(self, signed_in):
        """The route that was wrong, asserted the other way round — and by URL, not by status."""
        before = len(signed_in.server.calls)
        response = signed_in.client.post("/api/auth/profile/password",
                                         json={"current_password": "", "new_password": "new-pw"})
        assert response.status_code == 200, response.text
        writes = [c for c in signed_in.server.calls_since(before)
                  if c["path"] == "/Users/Password"]
        assert writes, "the change never reached the media server"
        assert writes[0]["user_ids"] == {PROFILE_ID}, (
            "the write must target the PROFILE in effect, not whatever account happens to be first")
        assert writes[0]["token"] == PROFILE_TOKEN, (
            "and it must act with the PROFILE's own credential — on the app's key the old password "
            "stops being checked entirely")

    def test_the_picker_still_lists_accounts_while_a_member_is_selected(self, signed_in):
        """"There are no profiles on this server" is what a member's token earns from `/Users`.

        The credential here is the ADMINISTRATOR's — the app's own key, because this route
        deliberately does not publish a session (it resolves one only to answer 401 honestly, and
        publishing would swap the server's folder LIST for the previous profile's own views, which
        is the list `select_profile` maps its grant ids against). Either way it must never be the
        selected profile's: the server answers `/Users` to an administrator only.
        """
        before = len(signed_in.server.calls)
        body = signed_in.client.get("/api/auth/profiles").json()
        assert [p["name"] for p in body["profiles"]] == ["Meenu", "Kid", "admin"]
        listings = [c for c in signed_in.server.calls_since(before) if c["path"] == "/Users"]
        assert listings, "listing accounts never reached the media server"
        for call in listings:
            assert call["token"] in (OWNER_TOKEN, APP_KEY), (
                f"listing accounts ran as {call['token']!r} — it is administrator-only on the "
                "server, so it must use the administrator's own credential")
            assert call["token"] != PROFILE_TOKEN

    def test_forgetting_to_publish_fires_the_rail_instead_of_writing(self, signed_in, monkeypatch):
        """THE historical bug, reproduced on purpose.

        This is what `POST /api/auth/profile/password` did before 14c06bf: resolve the session,
        then call the provider without publishing it. Without the rail the write SUCCEEDED — on the
        wrong account. With it, the call never reaches the media server.

        The evidence is gathered BEFORE asserting (and printed in the failure message) so that
        deleting the rail reproduces the 2026-09-12 report verbatim: a write on the app's own
        elevated key, aimed at whichever account the server lists first.
        """
        monkeypatch.setattr(auth_route, "set_current_session", lambda context: None)
        monkeypatch.setattr(auth_route, "reset_current_session", lambda token: None)

        before = len(signed_in.server.calls)
        fired: Optional[BaseException] = None
        try:
            signed_in.client.post("/api/auth/profile/password",
                                  json={"current_password": "", "new_password": "new-pw"})
        except UnpublishedIdentityError as exc:      # TestClient re-raises the route's exception
            fired = exc

        after = signed_in.server.calls_since(before)
        writes = [c for c in after if c["path"] == "/Users/Password"]
        named = signed_in.server.named_user_ids(since=before)
        assert fired is not None, (
            "the rail did NOT fire, so the write went through: "
            + "; ".join(f"{c['path']} on {c['token']!r} targeting {sorted(c['user_ids'])}"
                        for c in after)
            + f" — the session had {PROFILE_ID} selected")
        assert not writes, "the password write reached the media server with nothing published"
        assert named == set(), (
            "and no call named ANY account — the old code named the first one in /Users order, "
            f"which here is {STRANGER_ID}")
