"""Phase E — what every ``/api`` route requires, and the inventory that keeps it decided.

**Why this file exists.** `tools/route_protection_report.py` answered *"are the routes protected?"*
with a list instead of a feeling (2026-09-13): 54 routes, and **six of them were administrative IN
EFFECT while only a session was checked** — a member's session was accepted for a library scan, a
generic job run, a whole-library reconcile and an *arr download action. That is the sweep this file
pins. His decisions (2026-09-13), recorded as behaviour, not as prose:

* the four **operational** routes become ``require_admin_session`` — strict in every world;
* ``POST /api/media/{id}/request`` and ``POST /api/suggest/add`` **stay member-facing** — asking for
  a title and suggesting one is the point of the app;
* ``RKM_AUTH_REQUIRED`` stays **false** — enforcement of sign-in everywhere is his opt-in and is
  NOT flipped by this work.

**The rule this file enforces above all others:** a route cannot *ship* without somebody deciding
what it requires. ``ROUTE_LEVELS`` is the complete declaration; ``test_no_route_shipped_without_a
_decision`` compares it to the routes the app actually serves in **both** directions, so a new
route fails the suite until it is declared, and a deleted one fails until its row is removed. That
is deliberate friction: the alternative is what this repo has already been bitten by twice — a
gate that looked present because nothing enumerated the routes at all (``plan §6f``), and a test
that passed while inspecting ZERO routes.

**Why the HTTP tests drive the real app with the flag UNSET.** ``require_admin_session`` is strict
*even while* ``RKM_AUTH_REQUIRED=false`` — that asymmetry is the whole reason a member cannot reach
these routes on today's live stack. A test that armed the flag first would pass for the wrong
reason: arming makes EVERY route strict, which is `require_session`'s job, not this one's.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.session as session_mod
from api.main import app
from domain.enums import DownloadResultState

# ---------------------------------------------------------------- the declaration

PUBLIC = "PUBLIC"
AUTH = "auth-route"
ADMIN = "ADMIN"
SESSION = "session"

#: Route → the level it requires. **Every** ``/api`` route appears exactly once, and the level is a
#: product decision, not a description of the code — which is why the four Phase E rows carry his
#: name and the member-facing pair carries a reason for staying open.
ROUTE_LEVELS: dict[str, str] = {
    # -- PUBLIC: the Docker HEALTHCHECK. Must stay reachable armed or unarmed, or a 401 marks the
    #    api unhealthy and cascades through `depends_on`.
    "GET /api/health": PUBLIC,

    # -- auth-route: reachable signed out BY DESIGN (sign-in must work before a session exists).
    #    These have NO `require_session` — the bug of 2026-09-12 lived here. Each one publishes
    #    the identity itself or acts only as the app/administrator; pinned row by row in
    #    tests/test_profile_identity.py::AUTH_ROUTES and driven over real HTTP by
    #    tests/test_identity_rail.py.
    "POST /api/auth/login": AUTH,
    "POST /api/auth/logout": AUTH,
    "GET /api/auth/me": AUTH,
    "POST /api/auth/profile": AUTH,
    "POST /api/auth/profile/password": AUTH,
    "GET /api/auth/profiles": AUTH,

    # -- ADMIN: `require_admin_session` — a session AND a live Jellyfin administrator.
    #    The seven household-account routes, gated from the start.
    "GET /api/admin/libraries": ADMIN,
    "GET /api/admin/users": ADMIN,
    "POST /api/admin/users": ADMIN,
    "DELETE /api/admin/users/{user_id}": ADMIN,
    "POST /api/admin/users/{user_id}/password": ADMIN,
    "POST /api/admin/users/{user_id}/policy": ADMIN,
    "POST /api/admin/users/{user_id}/rename": ADMIN,
    #    ── Phase E (HIS decision 2026-09-13): administrative IN EFFECT, only session-gated before.
    #    The legacy *arr command path. The UI requests titles through
    #    `POST /api/media/{id}/request` (member-facing, below); nothing a member can click is here.
    "POST /api/download": ADMIN,
    #    A generic job runner — it starts server-side work (media-server scans, the *arr stack) on
    #    the caller's behalf. Gated WHOLE rather than per job name, so an unknown or newly added
    #    name is refused by default. ⚠ `add_watchlist` is the one name a member-facing feature was
    #    written for (`features/watchlist/actions.ts::refreshRecommendations`, referenced by no
    #    view today); when that control is wired it needs its own member-facing route.
    "POST /api/jobs/{name}/run": ADMIN,
    #    Forces a full scan of every configured media library. The UI hides its "Scan Library"
    #    control for a non-administrator by the same rule.
    "GET /api/library/scan": ADMIN,
    #    A whole-library write pass against the database and the *arr services.
    "POST /api/reconcile": ADMIN,

    # -- session: a signed-in profile (NOT necessarily an administrator). 36 routes.
    "GET /api/config": SESSION,
    "POST /api/jellyfin/progress": SESSION,
    "GET /api/jellyfin/backdrop": SESSION,
    "GET /api/jellyfin/detail": SESSION,
    "GET /api/jellyfin/person": SESSION,
    "GET /api/jellyfin/playback-info": SESSION,
    "GET /api/jellyfin/poster": SESSION,
    "GET /api/jellyfin/similar": SESSION,
    "GET /api/jellyfin/stream/{item_id}": SESSION,
    "GET /api/jellyfin/hls/{item_id}/master.m3u8": SESSION,
    "GET /api/jellyfin/hls/{item_id}/{rest:path}": SESSION,
    "GET /api/jellyfin/subtitle": SESSION,
    "GET /api/jellyfin/subtitle-search": SESSION,
    "POST /api/jellyfin/subtitle-select": SESSION,
    "POST /api/jellyfin/subtitle-disable": SESSION,
    "GET /api/jobs": SESSION,
    "GET /api/library": SESSION,
    "GET /api/library/continue-watching": SESSION,
    "GET /api/library/folders": SESSION,
    "GET /api/library/folders/{folder_id}/items": SESSION,
    "GET /api/library/items": SESSION,
    "GET /api/library/recently-watched": SESSION,
    "GET /api/library/series/{series_id}/episodes": SESSION,
    "POST /api/library/{item_id}/state": SESSION,
    "GET /api/media/{media_id}": SESSION,
    #    MEMBER-FACING, his decision 2026-09-13: requesting a title from Radarr/Sonarr is arguably
    #    the whole point of the household, so it keeps ONE session and no administrator. Listed
    #    explicitly so a later session cannot quietly promote it to ADMIN.
    "POST /api/media/{media_id}/request": SESSION,
    "GET /api/quality": SESSION,
    "GET /api/search": SESSION,
    "GET /api/search/global": SESSION,
    "GET /api/status": SESSION,
    "POST /api/suggest": SESSION,
    #    MEMBER-FACING, same decision: adding to the household suggestion list is a member feature.
    "POST /api/suggest/add": SESSION,
    "POST /api/suggest/add/{tmdb_id}": SESSION,
    "GET /api/suggest/detail/{tmdb_id}": SESSION,
    "GET /api/watchlist": SESSION,
    "GET /api/watchlist/entries": SESSION,
}


# ---------------------------------------------------------------- the enumeration

def _dependency_names(deps) -> set[str]:
    """The names of the callables in a ``dependencies=[…]`` list (or a Dependant's children).

    ``Depends(fn)`` exposes ``call``; older/variant shapes expose ``dependency``. Reading only one
    of them is how `tools/route_protection_report.py` reported every route as unprotected on its
    first run — including the admin routes.
    """
    names: set[str] = set()
    for dep in deps or []:
        func = getattr(dep, "call", None) or getattr(dep, "dependency", None)
        names.add(getattr(func, "__name__", "") or repr(func))
    return names


def served_routes() -> dict[str, tuple[set[str], set[str]]]:
    """Every ``/api`` route the app ACTUALLY serves → ``(verbs, dependency names)``.

    ⚠ **This shape has silently gone vacuous before.** Under FastAPI 0.141 each ``include_router``
    stays an ``_IncludedRouter`` on ``app.routes`` whose sub-routes carry paths WITHOUT the prefix
    (prefix and router-level dependencies live on its ``include_context``); the older shape
    flattened everything onto ``app.routes`` with a ``.path``. A guard that read ``.path`` only
    found nothing and passed for months. Hence the assertion below, and hence the count check in
    the inventory test: **an enumeration that cannot fail is documentation.**
    """
    import fastapi

    rows: dict[str, tuple[set[str], set[str]]] = {}
    for route in app.routes:
        included = getattr(route, "original_router", None)
        context = getattr(route, "include_context", None)
        if included is not None and context is not None:
            prefix = str(getattr(context, "prefix", "") or "")
            include_deps = _dependency_names(getattr(context, "dependencies", None))
            include_deps |= _dependency_names(getattr(included, "dependencies", None))
            for sub in getattr(included, "routes", []) or []:
                path = prefix + str(getattr(sub, "path", "") or "")
                if not path.startswith("/api"):
                    continue
                deps = include_deps | _dependency_names(
                    getattr(getattr(sub, "dependant", None), "dependencies", None))
                for verb in set(getattr(sub, "methods", None) or ()):
                    rows[f"{verb} {path}"] = (set(getattr(sub, "methods", None) or ()), deps)
            continue
        path = str(getattr(route, "path", "") or "")
        if not path.startswith("/api"):
            continue
        deps = _dependency_names(getattr(getattr(route, "dependant", None), "dependencies", None))
        for verb in set(getattr(route, "methods", None) or ()):
            rows[f"{verb} {path}"] = (set(getattr(route, "methods", None) or ()), deps)

    assert len(rows) >= 40, (
        f"the route inventory found only {len(rows)} /api routes under FastAPI "
        f"{fastapi.__version__} — the shape of `app.routes` changed again, so every assertion "
        "built on this would pass vacuously. Fix the enumeration before trusting these tests "
        "(it happened once already).")
    return rows


def level_of(deps: set[str]) -> str:
    """The level a route's dependencies actually give it — the SAME rule the report uses."""
    if "require_admin_session" in deps:
        return ADMIN
    if "require_session" in deps:
        return SESSION
    return "*** NOTHING ***"


def _verb_and_path(key: str) -> tuple[str, str]:
    verb, _, path = key.partition(" ")
    return verb, path


def _actual_level(key: str, deps: set[str]) -> str:
    """``level_of``, with the two dependency-free families named rather than reported as gaps."""
    _verb, path = _verb_and_path(key)
    if path == "/api/health":
        return PUBLIC
    if path.startswith("/api/auth/"):
        return AUTH
    return level_of(deps)


# ---------------------------------------------------------------- 1. the inventory

class TestNoRouteShipsWithoutADecision:
    def test_the_inventory_is_not_vacuous(self):
        """A count assertion first, always: the enumeration above must have found the app."""
        served = served_routes()
        assert len(served) == len(ROUTE_LEVELS), (
            f"the app serves {len(served)} routes and ROUTE_LEVELS declares {len(ROUTE_LEVELS)}. "
            "If those differ, test_no_route_shipped_without_a_decision will name the difference.")

    def test_no_route_shipped_without_a_decision(self):
        """The one that matters: a NEW route cannot ship until somebody decides what it requires."""
        served = set(served_routes())
        declared = set(ROUTE_LEVELS)
        new, gone = sorted(served - declared), sorted(declared - served)
        assert not new and not gone, (
            "the /api surface changed without a decision about what it requires.\n"
            f"  NEW (declare in ROUTE_LEVELS, admin-gated unless there is a reason not to): {new}\n"
            f"  GONE (remove from ROUTE_LEVELS): {gone}\n"
            "A route that publishes no identity at all runs every media call on the "
            "ADMINISTRATOR's credential; a route that takes any session can be reached by a "
            "member. Both are decisions, never defaults (see tools/route_protection_report.py).")

    def test_every_declared_level_matches_the_dependencies_on_the_route(self):
        """The declaration and the code cannot drift — in either direction."""
        wrong = []
        for key, (verbs, deps) in sorted(served_routes().items()):
            actual = _actual_level(key, deps)
            declared = ROUTE_LEVELS.get(key)
            if declared is not None and actual != declared:
                wrong.append(f"{key}: declared {declared}, actually {actual}")
        assert not wrong, (
            "these routes do not require what the inventory says they do:\n  " + "\n  ".join(wrong))

    def test_every_route_still_publishes_an_identity_or_is_declared_public(self):
        """The original Phase C rule, restated against the declaration (not a prefix guess).

        A route with no ``require_session`` and no ``require_admin_session`` has no identity
        published, so every media call it makes runs on the app's/administrator's credential.
        PUBLIC, auth-route and ADMIN are the only acceptable answers, and each is declared above.
        """
        missing = [key for key, (_verbs, deps) in sorted(served_routes().items())
                   if "require_session" not in deps and "require_admin_session" not in deps
                   and ROUTE_LEVELS.get(key) not in (PUBLIC, AUTH)]
        assert not missing, (
            "these routes publish no session identity, so every media call they make runs on the "
            "ADMINISTRATOR's credential: " + ", ".join(missing))

    def test_the_four_phase_E_routes_are_the_ones_that_changed(self):
        """Pin the DECISION, not just the mechanism — a later session must not widen or narrow it
        by accident. Exactly these four, no more and no fewer."""
        phase_e = {"POST /api/download", "POST /api/jobs/{name}/run",
                   "GET /api/library/scan", "POST /api/reconcile"}
        declared_admin = {key for key, level in ROUTE_LEVELS.items() if level == ADMIN}
        household = {key for key in declared_admin if key.startswith(("GET /api/admin",
                                                                    "POST /api/admin",
                                                                    "DELETE /api/admin"))}
        assert declared_admin - household == phase_e, (
            "the admin-gated set outside /api/admin/* is not the four Phase E routes — his "
            "decision of 2026-09-13 was those four and nothing else")

    def test_the_two_member_facing_routes_are_still_member_facing(self):
        """His decision, pinned from the other side: these must NOT be admin-gated.

        A member's request for a title and a member's suggestion are the features; promoting them
        to ADMIN would silently break the household's use of the app (403 on a button that is
        offered).
        """
        served = served_routes()
        for key in ("POST /api/media/{media_id}/request", "POST /api/suggest/add"):
            _verbs, deps = served[key]
            assert "require_admin_session" not in deps, (
                f"{key} became administrators-only — that was NOT the decision (2026-09-13): "
                "requesting a title and suggesting one are member-facing features")
            assert ROUTE_LEVELS[key] == SESSION


# ---------------------------------------------------------------- 2. the behaviour, over real HTTP

#: The four Phase E routes, with a body/query that reaches the handler if the gate lets it
#: through. The gate answers BEFORE the body runs, so no service is ever called here.
PHASE_E_CALLS = [
    ("post", "/api/download", {"json": {"imdbId": "tt0133093", "type": "movie"}}),
    ("post", "/api/jobs/library_scan/run", {}),
    ("get", "/api/library/scan", {}),
    ("post", "/api/reconcile", {}),
]

HOUSEHOLD_CALLS = [
    ("get", "/api/admin/users", {}),
    ("get", "/api/admin/libraries", {}),
    ("post", "/api/admin/users", {"json": {"name": "X"}}),
]


class TestTheGateIsStrictEvenWhileTheAppIsUnenforced:
    """`RKM_AUTH_REQUIRED` is FALSE in every test here — and the gate still refuses.

    This is the asymmetry that makes Phase E worth shipping before he arms the switch: the
    household-account routes were already strict, and the four operational routes are now in the
    same class. Arming the flag is a separate decision (his, still open) and would only make the
    OTHER 36 routes strict too.
    """

    @pytest.mark.parametrize("verb,path,body", PHASE_E_CALLS)
    def test_a_signed_out_caller_is_refused_while_enforcement_is_unarmed(self, verb, path, body):
        client = TestClient(app)
        r = getattr(client, verb)(path, **body)
        assert r.status_code == 401, (
            f"{verb.upper()} {path} answered {r.status_code} signed out with the flag false. "
            "A no-session caller is served as the stack's own credential everywhere else, which "
            "is exactly why these four carry `require_admin_session`.")
        assert "Sign in" in r.json()["detail"]

    @pytest.mark.parametrize("verb,path,body", PHASE_E_CALLS + HOUSEHOLD_CALLS)
    def test_a_member_is_refused_and_nothing_happens(self, verb, path, body, signed_in):
        client = signed_in(TestClient(app), admin=False, user_id="uid-member")
        r = getattr(client, verb)(path, **body)
        assert r.status_code == 403, (
            f"{verb.upper()} {path} answered {r.status_code} for a MEMBER's session. These routes "
            "are administrative in effect; a member must not reach them.")
        assert "administrator" in r.json()["detail"].lower()

    @pytest.mark.parametrize("verb,path,body", PHASE_E_CALLS)
    def test_an_administrator_is_past_the_gate(self, verb, path, body, signed_in, monkeypatch):
        """The other side of the same coin: the gate must not refuse the person it is for.

        Only the GATE is under test — each handler's own work is stubbed, because what is being
        proved is that a signed-in administrator is not stopped at the door (a 401/403 here would
        mean Phase E locked the operator out of their own stack).
        """
        import api.routes.download as download_route
        import api.routes.reconcile as reconcile_route
        import jobs.library_scan as library_scan_job

        job_result = SimpleNamespace(to_dict=lambda: {"name": "library_scan", "status": "success",
                                                     "items_processed": 0, "counts": {}})
        # ⚠ Both scan routes import the job INSIDE the handler (`from jobs.library_scan import …`),
        # so the patch must land on the module that import resolves from — patching the route
        # module's own namespace would silently do nothing.
        monkeypatch.setattr(library_scan_job, "run_library_scan", lambda: job_result)
        monkeypatch.setattr(download_route, "DownloadService", lambda: SimpleNamespace(
            download=lambda **k: SimpleNamespace(
                success=False, state=DownloadResultState.UNAVAILABLE, message="not configured",
                media_type=SimpleNamespace(arr_service="radarr"))))
        monkeypatch.setattr(reconcile_route, "Reconciler", lambda: SimpleNamespace(
            compute=lambda: SimpleNamespace(snapshots={}, indexer_issue=None)))

        client = signed_in(TestClient(app))
        r = getattr(client, verb)(path, **body)
        assert r.status_code not in (401, 403), (
            f"{verb.upper()} {path} refused an ADMINISTRATOR ({r.status_code}) — the gate is "
            f"strict, but it must let the administrator through. body={r.text[:200]}")


class TestTheServicesTheSchedulerUsesAreNotBehindTheGate:
    """Nothing internal may depend on an HTTP route staying open.

    The scheduler runs the same work through ``jobs/*`` and the provisioner never has a session —
    if either reached a gated route the app would break in a way no HTTP test would show.
    """

    def test_the_job_modules_do_not_call_the_http_routes(self):
        """Read the job modules' source: no HTTP client, so the gate cannot stop the scheduler."""
        from pathlib import Path
        offenders = []
        for path in sorted(Path(__file__).resolve().parent.parent.joinpath("jobs").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "urllib.request" in text or "httpx" in text or "requests." in text:
                offenders.append(path.name)
        assert not offenders, (
            "these job modules make their own HTTP calls — if they ever point at this app, the "
            f"Phase E gate would refuse the scheduler: {offenders}")


class TestTheUnenforcedRoutesAreStillUnenforced:
    """Phase E must not have armed anything by accident. His opt-in is explicit."""

    def test_a_signed_out_caller_is_still_served_on_an_ordinary_route(self):
        client = TestClient(app)
        assert client.get("/api/library/folders").status_code == 200

    def test_RKM_AUTH_REQUIRED_is_not_armed_by_this_work(self):
        cfg = session_mod.get_config()
        assert str(getattr(cfg, "RKM_AUTH_REQUIRED", "")).strip().lower() not in ("1", "true",
                                                                                 "yes", "on"), (
            "enforcement was armed — that is HIS explicit opt-in (Phase 1's docs point at it as "
            "the lockout-sensitive switch) and must never be flipped by a code change")
