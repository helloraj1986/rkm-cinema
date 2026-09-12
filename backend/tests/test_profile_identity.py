"""Phase C (PLEX_PROFILE_AUTH_PLAN §7 row C) — the profile identity, threaded and pinned.

Three kinds of test, each earning its place:

1. **THE SEAM, unit by unit.** ONE rule decides a media credential
   (``api.session.acting_media_token``) and one decides the user id. No request context must mean
   *exactly* today's behaviour — every tool, the provisioner, the scheduler and the bootstrap
   depend on that, and it is what makes the change safe to ship.
2. **THE GUARD — `test_no_media_url_carries_the_administrators_credential`.** Every public media
   method of the provider is driven with a PROFILE selected, and EVERY url it builds must carry
   that profile's token. A missed call site is silent: the member simply sees the administrator's
   library and watch state, with no error anywhere. Two calls are the administrator's on purpose
   (both non-content — see ``ADMIN_BY_DESIGN``) and are asserted the other way round.
3. **THE WIRING, over real HTTP.** The contextvar has to survive the round trip through the
   router-level dependency in ``api/main.py`` — before Phase C ``require_session`` was referenced by
   no route at all, so nothing published it and the provider could not have seen a profile even
   with the threading in place. Each route family is exercised through the app's own TestClient.

No network: ``urllib.request.urlopen`` is replaced, the session store points at ``tmp_path``, and
the provider is given a fake config.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import session as session_mod
from api.session import (
    SessionContext,
    acting_media_token,
    acting_profile_is_owner,
    acting_user_id,
    set_current_session,
)
from api.routes import auth as auth_route
from services.auth import (
    SESSION_COOKIE,
    InvalidCredentialsError,
    JellyfinIdentity,
    SessionStore,
)
from services.library.media_libraries import visible_libraries

APP_KEY = "app-key-ADMIN"
OWNER_TOKEN = "owner-token"
PROFILE_TOKEN = "profile-token-KID"
OWNER_ID = "uid-admin"
PROFILE_ID = "uid-kid"

#: The two Jellyfin calls that are deliberately the ADMINISTRATOR's, and why: reading the server's
#: library LIST (display metadata for a profile's own views — never its content) and triggering a
#: library-wide SCAN (server-wide maintenance, requires elevation). Both return no item and no
#: watch state, so neither can leak one profile's data into another.
ADMIN_BY_DESIGN = ("/Library/VirtualFolders", "/Library/Refresh")


def _context(*, profile: bool) -> SessionContext:
    """A signed-in session, optionally with somebody else's profile selected."""
    return SessionContext(
        session_id="sid", user_id=OWNER_ID, user_name="admin", token=OWNER_TOKEN,
        profile_user_id=PROFILE_ID if profile else "",
        profile_user_name="Kid" if profile else "",
        profile_token=PROFILE_TOKEN if profile else "",
    )


@pytest.fixture()
def as_owner():
    """Run the body with the administrator browsing as THEMSELVES."""
    token = set_current_session(_context(profile=False))
    yield
    session_mod.reset_current_session(token)


@pytest.fixture()
def as_profile():
    """Run the body with somebody else's profile selected."""
    token = set_current_session(_context(profile=True))
    yield
    session_mod.reset_current_session(token)


def _config(**over):
    base = dict(JELLYFIN_URL="http://jellyfin.test:8096", JELLYFIN_API_KEY=APP_KEY,
                JELLYFIN_BROWSER_URL="", media_libraries=[], media_library_warnings=[],
                RKM_AUTH_REQUIRED="false")
    base.update(over)
    ns = SimpleNamespace(**base)
    # The real Config answers this by reading its own flag; the stand-in must too, or
    # `require_session` raises instead of deciding (and hides whatever the test was checking).
    ns.auth_required = lambda: str(getattr(ns, "RKM_AUTH_REQUIRED", "false")).lower() == "true"
    return ns


class _Recorder:
    """A stand-in for ``urllib.request.urlopen`` that records every url it is asked for.

    Returns the smallest payload each caller tolerates (an empty ``Items`` wrapper), so the
    methods run their full URL-building path without needing a fixture per endpoint.
    """

    def __init__(self, payload=None):
        self.urls: list[str] = []
        self._payload = payload

    def __call__(self, url, *a, **kw):
        # A ``urllib.request.Request`` (the POST/PUT/DELETE call sites) stringifies to an object
        # repr, so read the url off it — otherwise the assertion below would compare against
        # "<urllib.request.Request object at 0x…>" and pass or fail for the wrong reason.
        self.urls.append(getattr(url, "full_url", None) or str(url))
        payload = self._payload if self._payload is not None else {"Items": []}
        return _FakeResponse(json.dumps(payload).encode())


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body
        self.status = 200
        self.headers = {"Content-Type": "application/json"}

    def read(self, *_a):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


# ------------------------------------------------------------------ 1. the seam, unit by unit

class TestTheSeam:
    def test_no_request_context_is_the_app_key(self):
        """The fail-safe: the provisioner, the scheduler and every tool live here."""
        assert acting_media_token(_config()) == APP_KEY
        assert acting_user_id() == ""
        assert acting_profile_is_owner() is True

    def test_the_owner_browses_as_themselves(self, as_owner):
        assert acting_media_token(_config()) == OWNER_TOKEN
        assert acting_user_id() == OWNER_ID
        assert acting_profile_is_owner() is True

    def test_a_selected_profile_is_what_acts(self, as_profile):
        """The whole of Phase C in one assertion: the token AND the id are the profile's."""
        assert acting_media_token(_config()) == PROFILE_TOKEN
        assert acting_user_id() == PROFILE_ID
        assert acting_profile_is_owner() is False

    def test_a_session_with_no_profile_still_acts_as_the_owner(self):
        """A Phase 0/1 session (or one created before a profile was chosen) must not break."""
        ctx = SessionContext(session_id="sid", user_id=OWNER_ID, user_name="admin", token="t")
        assert ctx.profile_id() == OWNER_ID and ctx.acting_token() == "t"

    def test_the_config_is_never_needed_when_a_session_exists(self, as_profile):
        """A session's token must not depend on the app key being present."""
        assert acting_media_token(_config(JELLYFIN_API_KEY=None)) == PROFILE_TOKEN


# ------------------------------------------------- 2. the guard: no content call uses the admin key

def _media_calls():
    """Every public provider method that talks to Jellyfin, as (name, caller)."""
    from services.library.jellyfin import JellyfinLibraryProvider

    def fresh():
        return JellyfinLibraryProvider(config=_config())

    return [
        ("all_items", lambda p: p.all_items()),
        ("recently_added", lambda p: p.recently_added()),
        ("library_folders", lambda p: p.library_folders()),
        ("items_in_folder", lambda p: p.items_in_folder("folder-1")),
        ("continue_watching", lambda p: p.continue_watching()),
        ("episodes", lambda p: p.episodes("series-1")),
        ("recently_watched", lambda p: p.recently_watched()),
        ("search_items", lambda p: p.search_items("dune")),
        ("items_by_person", lambda p: p.items_by_person("person-1")),
        ("mark_state", lambda p: p.mark_state("item-1", True)),
        ("mark_state_off", lambda p: p.mark_state("item-1", False)),
        ("set_playback_position", lambda p: p.set_playback_position("item-1", 100)),
        ("get_poster", lambda p: p.get_poster("item-1")),
        ("playback_info", lambda p: p.playback_info("item-1")),
        ("item_detail", lambda p: p.item_detail("item-1")),
        ("item_similar", lambda p: p.item_similar("item-1")),
        ("item_path", lambda p: p.item_path("item-1")),
        ("refresh_item", lambda p: p.refresh_item("item-1")),
        ("subtitle_search_context", lambda p: p.subtitle_search_context("item-1")),
        ("upload_subtitle", lambda p: p.upload_subtitle("item-1", "a.srt", b"x")),
        ("refresh_library", lambda p: p.refresh_library()),
        ("list_users", lambda p: p.list_users()),
        ("get_user_policy", lambda p: p.get_user_policy("uid-1")),
    ], fresh


class TestNoMediaCallUsesTheAdministratorsCredential:
    """The guard for the failure this phase exists to prevent — and it is a SILENT one."""

    @pytest.mark.parametrize("name", [c[0] for c in _media_calls()[0]])
    def test_every_url_built_carries_the_profile(self, name, as_profile, monkeypatch):
        calls, fresh = _media_calls()
        method = dict(calls)[name]
        recorder = _Recorder()
        monkeypatch.setattr(urllib.request, "urlopen", recorder)
        method(fresh())  # must not raise, whatever the fake server answers

        assert recorder.urls, f"{name} made no request at all — the test proves nothing"
        for url in recorder.urls:
            if any(path in url for path in ADMIN_BY_DESIGN):
                assert (f"api_key={OWNER_TOKEN}" in url or f"api_key={APP_KEY}" in url), (
                    f"{name}: {url} — an administrator-only call must use the administrator's own "
                    "credential (an empty or profile credential is refused by Jellyfin)")
                assert f"api_key={PROFILE_TOKEN}" not in url, (
                    f"{name}: {url} — a member's token was used for an administrator-only call")
                continue
            assert f"api_key={PROFILE_TOKEN}" in url, (
                f"{name}: {url} was NOT made as the selected profile. A member would see the "
                "administrator's library and watch state.")
            assert APP_KEY not in url and OWNER_TOKEN not in url, (
                f"{name}: {url} leaked the administrator's credential into a content call")

    @pytest.mark.parametrize("name", [c[0] for c in _media_calls()[0]])
    def test_without_a_session_everything_still_uses_the_app_key(self, name, monkeypatch):
        """The fail-safe side: no request context ⇒ byte-identical behaviour to before Phase C."""
        calls, fresh = _media_calls()
        method = dict(calls)[name]
        recorder = _Recorder()
        monkeypatch.setattr(urllib.request, "urlopen", recorder)
        method(fresh())
        assert recorder.urls
        for url in recorder.urls:
            assert f"api_key={APP_KEY}" in url, f"{name}: {url} did not use the app key"
            assert PROFILE_TOKEN not in url

    def test_the_user_scoped_endpoints_name_the_profile_not_the_administrator(self, as_profile,
                                                                             monkeypatch):
        """Jellyfin takes the user id in the PATH, so a wrong id is a 404, not a leak — but it is
        still a broken app. Every user-scoped url must name the profile."""
        calls, fresh = _media_calls()
        recorder = _Recorder()
        monkeypatch.setattr(urllib.request, "urlopen", recorder)
        for name, method in calls:
            method(fresh())
        # Only the paths Jellyfin scopes to "the user the caller is": the media endpoints. An
        # explicit target id (`/Users/{id}` for the household routes) legitimately names somebody
        # else — the administrator is asking about them.
        # The USER-SCOPED media calls, which is a narrower set than "mentions a user":
        #   /Users/{uid}/Items…, /Users/{uid}/PlayedItems…  → the caller's own media and state
        #   /UserViews?userId={uid}                          → the caller's own libraries
        # Artwork/PlaybackInfo name no user (the token authorises them — the guard above pins
        # those), and a bare `/Users/{id}` is the HOUSEHOLD route asking about somebody else.
        scoped = [u for u in recorder.urls
                  if ("/Users/" in u and ("/Items" in u or "/PlayedItems" in u))
                  or "/UserViews" in u]
        assert scoped, "no user-scoped call was made — the test proves nothing"
        for url in scoped:
            # /Users/{uid}/Items… takes the user in the PATH; /UserViews?userId= in the query.
            named = (f"/Users/{PROFILE_ID}/" in url) or (f"userId={PROFILE_ID}" in url)
            assert named, f"{url} was scoped to the wrong user"
            assert f"/Users/{OWNER_ID}/" not in url and f"userId={OWNER_ID}" not in url

    def test_the_provider_has_exactly_one_gateway_to_the_credential(self):
        """A structural backstop for the behavioural guard above.

        Any NEW call site that reaches for ``config.JELLYFIN_API_KEY`` directly would bypass the
        seam — and would keep doing so silently for every request that has a profile. The only
        legitimate mention left is ``_configured()`` ("is the media server set up at all").
        """
        src = Path(__file__).resolve().parent.parent / "services" / "library" / "jellyfin.py"
        text = src.read_text(encoding="utf-8")
        assert text.count("JELLYFIN_API_KEY") == 1, (
            "jellyfin.py reaches past the credential seam. Every Jellyfin URL must be built with "
            "_api_token() / owner_media_token() — see PLEX_PROFILE_AUTH_PLAN §4d.")


# ------------------------------------------------------ 3. the wiring, over the app's own HTTP

@pytest.fixture()
def http(tmp_path, monkeypatch):
    """A TestClient signed in on a session with 'Kid' selected, with a recording library.

    The store is isolated and the library is faked, but the ROUTES, the router-level
    ``require_session`` dependency and the contextvar are the real ones — which is the point:
    it is exactly the wiring that did not exist before Phase C.
    """
    store = SessionStore(path=tmp_path / "sessions.json")
    monkeypatch.setattr(session_mod, "session_store", lambda config=None: store)
    monkeypatch.setattr(session_mod.get_config(), "RKM_AUTH_REQUIRED", "false")

    seen: list = []

    class RecordingLibrary:
        name = "jellyfin"

        @property
        def providers(self):
            """The facade exposes the providers it wraps; /api/library iterates them."""
            return [self]

        def _note(self, method):
            seen.append((method, acting_media_token(), acting_user_id()))

        def library_folders(self):
            self._note("library_folders")
            return {"provider": "jellyfin", "folders": [
                {"id": "f1", "name": "Movies", "collection_type": "movies",
                 "path": "/data/Movies", "locations": ["/data/Movies"]}]}

        def all_items(self):
            self._note("all_items")
            return {"provider": "jellyfin", "items": []}

        def continue_watching(self):
            self._note("continue_watching")
            return {"provider": "jellyfin", "items": []}

        def recently_watched(self):
            self._note("recently_watched")
            return {"provider": "jellyfin", "items": []}

        def episodes(self, series_id, limit=1000):
            self._note("episodes")
            return {"provider": "jellyfin", "episodes": []}

        def item_detail(self, item_id):
            self._note("item_detail")
            return {"id": item_id}

        def item_similar(self, item_id, limit=10):
            self._note("item_similar")
            return []

        def get_poster(self, item_id, max_width=500, kind="Primary"):
            self._note("get_poster")
            return None

        def playback_info(self, item_id):
            self._note("playback_info")
            return {"media_source_id": item_id, "container": "mkv", "video": None,
                    "audio": [], "subtitles": []}

        def mark_state(self, item_id, watched):
            self._note("mark_state")
            return {"played": watched, "play_count": 1}

        def set_playback_position(self, item_id, ticks):
            self._note("set_playback_position")
            return True

        def subtitle_search_context(self, item_id):
            self._note("subtitle_search_context")
            return None

        def subtitle_search(self, *a, **k):
            self._note("subtitle_search")
            return {"results": [], "warnings": []}

        def items_in_folder(self, folder_id, limit=None):
            self._note("items_in_folder")
            return {"provider": "jellyfin", "items": []}

        def recently_added(self, limit=8):
            self._note("recently_added")
            return []

        def _get_items(self, item_type):
            self._note(f"_get_items:{item_type}")
            return []

        def _browser_base(self):
            return "http://jellyfin.test:8096/web/index.html"

        def last_api_error(self):
            return None

    library = RecordingLibrary()

    # The routes each hold their OWN ``get_config`` reference, and five of them refuse with a 503
    # before ever reaching the provider when the media server is unconfigured (which is the
    # sandbox's state). One fake config object, patched everywhere it is read, keeps the test about
    # the identity rather than about the sandbox's .env.
    cfg = _config(media_libraries=[
        SimpleNamespace(name="Movies", path="/data/Movies", media_type="movie"),
        SimpleNamespace(name="TV Shows", path="/media2/TV Shows", media_type="tv"),
    ], media_library_warnings=["'TV Shows' could not be checked"])
    cfg.RKM_AUTH_REQUIRED = "false"
    monkeypatch.setattr(session_mod, "get_config", lambda: cfg)

    import api.routes.library as library_route
    import api.routes.jellyfin_detail as detail_route
    import api.routes.jellyfin_poster as poster_route
    import api.routes.jellyfin_similar as similar_route
    import api.routes.jellyfin_stream as stream_route
    import api.routes.jellyfin_hls as hls_route
    import api.routes.jellyfin_tracks as tracks_route
    import api.routes.jellyfin_subtitles as subtitles_route
    modules = (library_route, detail_route, poster_route, similar_route, stream_route, hls_route,
               tracks_route, subtitles_route)
    for module in modules:
        if hasattr(module, "build_library_service"):
            monkeypatch.setattr(module, "build_library_service", lambda *a, **k: library)
        if hasattr(module, "get_config"):
            monkeypatch.setattr(module, "get_config", lambda: cfg)

    from api.main import app
    client = TestClient(app)
    session_id, _ = store.create(user_id=OWNER_ID, user_name="admin", token=OWNER_TOKEN)
    store.set_profile(session_id, user_id=PROFILE_ID, user_name="Kid", token=PROFILE_TOKEN)
    client.cookies.set(SESSION_COOKIE, session_id)
    return SimpleNamespace(client=client, seen=seen, library=library, store=store, cfg=cfg,
                           session_id=session_id)


class TestTheWiringOverHttp:
    """Every route family must reach the provider AS THE PROFILE."""

    #: (method, path, provider method expected, json body). One entry per ROUTE FAMILY — the shape
    #: families (list / detail / playback / progress / artwork) rather than one per endpoint.
    FAMILIES = [
        ("get", "/api/library", "recently_added", None),
        ("get", "/api/library/folders", "library_folders", None),
        ("get", "/api/library/items", "all_items", None),
        ("get", "/api/library/continue-watching", "continue_watching", None),
        ("get", "/api/library/recently-watched", "recently_watched", None),
        ("get", "/api/library/folders/f1/items", "items_in_folder", None),
        ("get", "/api/library/series/s1/episodes", "episodes", None),
        ("post", "/api/library/i1/state", "mark_state", {"watched": True}),
        ("get", "/api/jellyfin/detail?id=i1", "item_detail", None),
        ("get", "/api/jellyfin/playback-info?id=i1", "playback_info", None),
        ("get", "/api/jellyfin/poster?id=i1", "get_poster", None),
    ]

    @pytest.mark.parametrize("verb,path,expected,body", FAMILIES)
    def test_the_route_runs_as_the_selected_profile(self, http, verb, path, expected, body):
        before = len(http.seen)
        getattr(http.client, verb)(path, **({"json": body} if body is not None else {}))
        assert len(http.seen) > before, f"{verb.upper()} {path} never reached the provider"
        method, token, user_id = http.seen[-1]
        assert method == expected, f"{path} called {method}, expected {expected}"
        assert token == PROFILE_TOKEN, (
            f"{path} reached the provider on {token!r} — the router-level require_session "
            "dependency is missing in api/main.py, so nothing published the identity")
        assert user_id == PROFILE_ID

    def test_an_unsigned_request_is_still_served(self, http):
        """`RKM_AUTH_REQUIRED=false` must stay true to its name: enforcement is HIS opt-in."""
        client = TestClient(http.client.app)
        r = client.get("/api/library/folders")
        assert r.status_code == 200

    def test_a_signed_out_request_falls_back_to_the_app_key(self, http):
        """No session ⇒ today's behaviour, over real HTTP this time."""
        client = TestClient(http.client.app)
        client.get("/api/library")
        method, token, user_id = http.seen[-1]
        assert token == APP_KEY, "an unsigned request must keep using the app's own credential"
        assert user_id == "", "and must not be scoped to a user it never named"


class TestTheSidebarIsTheProfilesOwnLibraries:
    """`/api/library/folders` must answer with the GRANTS, not the administrator's config."""

    def test_a_member_sees_only_the_granted_library(self, http):
        body = http.client.get("/api/library/folders").json()
        names = [lib["name"] for lib in body["libraries"]]
        assert names == ["Movies"], "the grant list decides, and TV Shows was never granted"
        assert body["warnings"] == [], (
            "the administrator's config problems are not this person's screen — and a warning here "
            "would send them hunting a config fault that does not exist")

    def test_the_owner_still_gets_the_configured_list_and_its_warnings(self, http, monkeypatch):
        """The administrator's own view is unchanged: config matching, warnings and all.

        Re-signed-in as the OWNER (no profile selected) against the same app, so the only thing
        that differs from the test above is the session's profile.
        """
        monkeypatch.setattr(
            http.library, "library_folders",
            lambda: {"provider": "jellyfin", "folders": [
                {"id": "f1", "name": "Movies", "collection_type": "movies",
                 "path": "/data/Movies", "locations": ["/data/Movies"]}]})
        client = TestClient(http.client.app)
        session_id, _ = http.store.create(user_id=OWNER_ID, user_name="admin", token=OWNER_TOKEN)
        client.cookies.set(SESSION_COOKIE, session_id)   # note: NO profile selected
        body = client.get("/api/library/folders").json()
        by_name = {lib["name"]: lib for lib in body["libraries"]}
        assert by_name["Movies"]["ok"] is True, "the configured library still resolves by path"
        assert by_name["TV Shows"]["ok"] is False, "and an unresolved one is still reported"
        assert by_name["TV Shows"]["warning"], "with the reason the administrator needs"
        assert body["warnings"] == http.cfg.media_library_warnings


class TestVisibleLibraries:
    """:func:`visible_libraries` — the pure rule the sidebar follows."""

    CONFIGURED = [SimpleNamespace(name="Movies", path="/data/Movies", media_type="movie"),
                  SimpleNamespace(name="TV Shows", path="/media2/TV Shows", media_type="tv")]

    def test_an_ungranted_configured_library_is_omitted_not_warned_about(self):
        rows = visible_libraries(self.CONFIGURED, [
            {"id": "f1", "name": "Movies", "collection_type": "movies", "path": ""}])
        assert [r["name"] for r in rows] == ["Movies"]
        assert rows[0]["ok"] is True and rows[0]["warning"] == ""

    def test_a_grant_with_no_configured_entry_is_shown_under_the_servers_name(self):
        """A grant must never be invisible in the UI."""
        rows = visible_libraries([], [
            {"id": "f9", "name": "Documentaries", "collection_type": "movies", "path": ""}])
        assert [r["name"] for r in rows] == ["Documentaries"]
        assert rows[0]["folder_id"] == "f9" and rows[0]["ok"] is True

    def test_a_granted_configured_library_keeps_its_configured_name(self):
        """A view row carries no usable PATH, so NAME is the only key the two lists share — and
        the configured name is what the administrator chose to see."""
        rows = visible_libraries(self.CONFIGURED, [
            {"id": "f2", "name": "TV Shows", "collection_type": "tvshows", "path": ""}])
        assert [r["name"] for r in rows] == ["TV Shows"]
        assert rows[0]["path"] == "/media2/TV Shows"

    def test_a_renamed_view_is_shown_under_the_SERVERS_name_not_force_matched(self):
        """The server's view name and the config name need not agree. When they do not, the grant
        still shows (never invisible) — under the name the server itself reports."""
        rows = visible_libraries(self.CONFIGURED, [
            {"id": "f2", "name": "TV", "collection_type": "tvshows", "path": ""}])
        assert [r["name"] for r in rows] == ["TV"]
        assert rows[0]["folder_id"] == "f2" and rows[0]["ok"] is True

    def test_nothing_granted_is_an_empty_sidebar_not_an_error(self):
        assert visible_libraries(self.CONFIGURED, []) == []

    def test_every_row_carries_the_shape_the_ui_needs(self):
        rows = visible_libraries(self.CONFIGURED, [
            {"id": "f1", "name": "Movies", "collection_type": "movies", "path": ""},
            {"id": "f9", "name": "Extras", "collection_type": "movies", "path": ""}])
        assert rows, "expected rows"
        for row in rows:
            assert set(row) == {"name", "path", "folder_id", "collection_type", "ok", "warning"}


class TestEveryAppRouterPublishesTheIdentity:
    """The structural half of the wiring: a NEW router cannot silently ship unprotected."""

    #: Public by design — the Docker HEALTHCHECK, and sign-in itself.
    PUBLIC = ("/api/health", "/api/auth/")

    #: Gated by ``require_admin_session``, which publishes the context itself and is STRICTER.
    ADMIN = ("/api/admin/",)

    def _dependency_names(self, route) -> set:
        names, stack = set(), [route.dependant]
        while stack:
            dep = stack.pop()
            for child in getattr(dep, "dependencies", []) or []:
                if child.call is not None:
                    names.add(getattr(child.call, "__name__", ""))
                stack.append(child)
        return names

    def test_every_api_route_publishes_a_identity(self):
        from api.main import app
        missing = []
        for route in app.routes:
            path = getattr(route, "path", "")
            if not path.startswith("/api"):
                continue
            if path.startswith(self.PUBLIC):
                continue
            names = self._dependency_names(route)
            if path.startswith(self.ADMIN):
                if "require_admin_session" not in names:
                    missing.append(path)
                continue
            if "require_session" not in names:
                missing.append(path)
        assert not missing, (
            "these routes do not publish the session identity, so every media call they make runs "
            "on the ADMINISTRATOR's credential: " + ", ".join(sorted(set(missing))))

    def test_health_and_sign_in_stay_reachable_even_when_enforcement_is_armed(self, http,
                                                                             monkeypatch):
        """The two hatch doors that must survive ARMING (Phase 2's own requirement).

        ``/api/health`` is called by the api's Docker HEALTHCHECK — a 401 there marks the api
        unhealthy and cascades through ``depends_on``. ``/api/auth/login`` must be reachable signed
        out by definition: a dependency that demanded a session to sign in would be a lockout with
        no way out. Arming the flag is the only way to prove either, so this test arms it.
        """
        monkeypatch.setattr(http.cfg, "RKM_AUTH_REQUIRED", "true")
        client = TestClient(http.client.app)
        # …and with the flag armed, an app route with no session really is refused — which also
        # proves the router-level dependency is doing its job in the armed world.
        assert client.get("/api/library/folders").status_code == 401
        assert client.get("/api/health").status_code == 200
        assert client.post("/api/auth/login", json={}).status_code != 401, (
            "sign-in itself was refused a session — nobody could ever get in")


class TestTheOwnerTokenSurvivesASwitchBack:
    """The bug the live two-profile proof found — and it was silent.

    Jellyfin invalidates the previous token for a given **device + user** on every login, and the
    app signs in on ONE device id. So the administrator selecting their OWN profile (which
    re-authenticates as them, on this device) kills the token the session has held since sign-in.
    Everything administrator-level then answers 401: the library metadata a profile's views are
    enriched with, and the household routes. Symptom on the running stack: the administrator's
    sidebar came back EMPTY after switching back. The session must TAKE the new token.
    """

    def test_a_members_login_leaves_the_owners_token_alone(self, tmp_path):
        store = SessionStore(path=tmp_path / "sessions.json")
        sid, _ = store.create(user_id=OWNER_ID, user_name="admin", token="owner-token-1")
        store.set_profile(sid, user_id=PROFILE_ID, user_name="Kid", token="kid-token")
        row = store.lookup(sid)
        assert row["jellyfin_token"] == "owner-token-1", (
            "a MEMBER's login rotates only that member's token — the owner's must survive, or the "
            "administrator could never switch back")
        assert row["profile_token"] == "kid-token"

    def test_the_owners_own_profile_replaces_a_dead_owner_token(self, tmp_path):
        store = SessionStore(path=tmp_path / "sessions.json")
        sid, _ = store.create(user_id=OWNER_ID, user_name="admin", token="owner-token-1")
        store.set_profile(sid, user_id=OWNER_ID, user_name="admin", token="owner-token-2",
                          owns_session=True)
        row = store.lookup(sid)
        assert row["jellyfin_token"] == "owner-token-2", "the dead owner token was kept — 401s follow"
        assert row["profile_token"] == "owner-token-2"

    def test_the_owner_token_is_only_ever_replaced_by_the_owner(self, tmp_path):
        """Three ways NOT to touch it, and each is a real caller mistake."""
        store = SessionStore(path=tmp_path / "sessions.json")
        sid, _ = store.create(user_id=OWNER_ID, user_name="admin", token="owner-token-1")

        store.set_profile(sid, user_id=PROFILE_ID, user_name="Kid", token="kid-token")
        assert store.lookup(sid)["jellyfin_token"] == "owner-token-1", "the flag is off by default"

        store.set_profile(sid, user_id=PROFILE_ID, user_name="Kid", token="kid-token-2",
                          owns_session=True)
        assert store.lookup(sid)["jellyfin_token"] == "owner-token-1", (
            "a MEMBER's id with the owner flag must not be able to write a member's token over the "
            "administrator's credential — the store checks the id itself")

        store.set_profile(sid, user_id=OWNER_ID, user_name="admin", token="", owns_session=True)
        assert store.lookup(sid)["jellyfin_token"] == "owner-token-1", "an empty token is not a token"

    def test_the_select_route_passes_the_flag_for_the_owners_own_profile(self, tmp_path,
                                                                        monkeypatch):
        """Route → store: the mechanism above is only worth anything if the ROUTE sets it."""
        store = SessionStore(path=tmp_path / "sessions.json")
        members = [
            {"id": OWNER_ID, "name": "admin", "is_admin": True, "disabled": False,
             "has_password": True, "enable_all_folders": True, "enabled_folders": [],
             "last_login": ""},
            {"id": PROFILE_ID, "name": "Kid", "is_admin": False, "disabled": False,
             "has_password": False, "enable_all_folders": False, "enabled_folders": ["f1"],
             "last_login": ""},
        ]

        class FakeLibrary:
            def list_users(self):
                return [dict(m) for m in members]

            def library_folders(self):
                return {"provider": "jellyfin", "folders": [
                    {"id": "f1", "name": "Movies", "collection_type": "movies", "path": ""}]}

            def last_api_error(self):
                return None

        def fake_auth(username, password, *, config=None, transport=None):
            if username == "admin" and password != "the-password":
                raise InvalidCredentialsError("Incorrect username or password")
            user = next(m for m in members if m["name"] == username)
            # A NEW token every login — exactly what Jellyfin does for a device+user pair.
            return JellyfinIdentity(user_id=user["id"], user_name=user["name"],
                                    token=f"fresh-{username}")

        monkeypatch.setattr(auth_route, "authenticate_jellyfin", fake_auth)
        monkeypatch.setattr(auth_route, "default_session_store", lambda config=None: store)
        monkeypatch.setattr(auth_route, "build_library_service",
                            lambda *a, **k: FakeLibrary())
        monkeypatch.setattr(session_mod, "session_store", lambda config=None: store)

        from api.main import app
        client = TestClient(app)

        # 1. the administrator switches to the member: the owner's token must be untouched
        sid, _ = store.create(user_id=OWNER_ID, user_name="admin", token="owner-token-1")
        client.cookies.set(SESSION_COOKIE, sid)
        assert client.post("/api/auth/profile",
                           json={"user_id": PROFILE_ID, "password": ""}).status_code == 200
        assert store.lookup(sid)["jellyfin_token"] == "owner-token-1"

        # 2. and back to their OWN profile: the session must take the fresh token
        r = client.post("/api/auth/profile", json={"user_id": OWNER_ID, "password": "the-password"})
        assert r.status_code == 200, r.text
        row = store.lookup(sid)
        assert row["jellyfin_token"] == "fresh-admin", (
            "the route did not pass owns_session, so the session kept a token Jellyfin has already "
            "invalidated — every administrator-level call would 401 from here on")
        assert row["profile_token"] == "fresh-admin"
