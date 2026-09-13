"""The 401 TAXONOMY (Phase 5) — WHICH credential is a 401 about?

Two 401s reach this app and they need opposite responses:

* **the cookie is gone or stale** ⇒ sign in again. The browser's global "a 401 means the session is
  dead" rule is right, and it is unchanged.
* **the cookie is fine, but the credential the app is acting as was refused** ⇒ signing out is the
  WRONG answer. It throws away a live session and cannot fix anything: only re-authenticating that
  identity does, which is what **Switch profile** is for.

Before this existed, that second state was not even visible: the media calls came back EMPTY, so the
app said "you have no library" with a blank sidebar (measured 2026-09-12, PLEX_PROFILE_AUTH_PLAN
§4e). The only 401 available would have signed the person out for something one tap fixes.

The distinction is carried by ``X-RKM-Auth-Problem`` (``services/auth.py``) and produced in ONE place
— ``api/session.py::require_live_credential`` — which ``api/main.py`` applies to every app router
through the same single line as before.

**What is faked here, and what is not.** The media server's ANSWER is faked (``credential_is_accepted``
is patched, exactly as ``admin_status`` is in ``tests/conftest.py``); the dependency, the session
store, the cookie, the routers and the responses are the shipped code. ``TestTheProbeItself``
exercises the real probe against a fake transport, including the credential style that was MEASURED
against Jellyfin 10.11.11 — that style is the function.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.session as session_mod
import services.auth as auth_mod
from api.main import app
from api.session import reset_credential_probe_cache
from services.auth import (AUTH_PROBLEM_HEADER, AUTH_PROBLEM_PROFILE_TOKEN, AUTH_PROBLEM_SESSION,
                           SESSION_COOKIE, AuthResponse, SessionStore, credential_is_accepted)

ADMIN_ID = "uid-admin"
MEMBER_ID = "uid-member"
ADMIN_TOKEN = "admin-token-1"
MEMBER_TOKEN = "member-token-1"

#: A session-scoped route with no side effects — the whole app uses the same dependency.
PROBE_PATH = "/api/config"


class FakeTransport:
    """The probe's transport: records what was asked, answers one status."""

    def __init__(self, status: int = 200, raises: bool = False):
        self.status, self.raises = status, raises
        self.seen: list[tuple[str, str, dict]] = []

    def request(self, method, url, *, headers=None, json_body=None, timeout=None):
        self.seen.append((method, url, dict(headers or {})))
        if self.raises:
            raise OSError("no route to host")
        return AuthResponse(status=self.status)


class FakeConfig:
    JELLYFIN_URL = "http://media.example:8096"


@pytest.fixture(autouse=True)
def _fresh_probe_cache():
    """The probe cache is per-process, so a test must never inherit another test's answer."""
    reset_credential_probe_cache()
    yield
    reset_credential_probe_cache()


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """The real app, an isolated store, and ONE switch: what the media server answers.

    ``world.answers(False)`` = the server refuses the credential. ``world.answers(None)`` = it could
    not be asked. ``world.probes`` counts the questions, which is how the cache is proved.
    """
    store = SessionStore(path=tmp_path / "sessions.json")
    state = {"answer": True}
    probes: list[tuple] = []

    def fake_probe(token, user_id, *, device_id="", config=None, transport=None, timeout=None):
        probes.append((token, user_id, device_id))
        return state["answer"]

    monkeypatch.setattr(auth_mod, "credential_is_accepted", fake_probe)
    monkeypatch.setattr(session_mod, "session_store", lambda config=None: store)
    monkeypatch.setattr(session_mod, "admin_status", lambda cfg, uid: True)
    monkeypatch.setattr(session_mod.get_config(), "RKM_AUTH_REQUIRED", "false")

    def sign_in(*, profile: str | None = None, admin: bool = True) -> TestClient:
        user_id = ADMIN_ID if admin else MEMBER_ID
        session_id, _ = store.create(user_id=user_id, user_name=user_id, token=ADMIN_TOKEN,
                                     device_id="dev-under-test")
        if profile == "member":
            store.set_profile(session_id, user_id=MEMBER_ID, user_name="Geetanjali",
                              token=MEMBER_TOKEN)
        client = TestClient(app)
        client.cookies.set(SESSION_COOKIE, session_id)
        return client

    def answers(answer):
        state["answer"] = answer

    return type("World", (), {"sign_in": staticmethod(sign_in), "answers": staticmethod(answers),
                              "probes": probes, "store": store})()


class TestTheDependency:
    def test_a_refused_profile_credential_is_a_marked_401_that_names_the_remedy(self, world):
        """The bug this exists for: a member's media credential goes stale mid-session."""
        client = world.sign_in(profile="member")
        world.answers(False)
        r = client.get(PROBE_PATH)
        assert r.status_code == 401
        assert r.headers[AUTH_PROBLEM_HEADER] == AUTH_PROBLEM_PROFILE_TOKEN
        # ⚠ The wording is deliberately CONTROL-NEUTRAL ("pick it again"). The browser answers this
        # 401 by sending the person to the picker, so a sentence naming the account menu would
        # instruct them to go somewhere they are not. What it must still do is name the remedy —
        # "sign in again" would be a dead end (and would throw a live session away), and a bare
        # "Unauthorized" tells them nothing at all.
        assert "pick it again" in r.json()["detail"]
        assert world.probes[-1][1] == MEMBER_ID, "the probe must ask about the credential IN EFFECT"

    def test_a_refused_OWN_credential_is_a_marked_401_about_the_session(self, world):
        """The owner's own credential being refused means the session really is dead for media."""
        client = world.sign_in()                       # administrator on their own profile
        world.answers(False)
        r = client.get(PROBE_PATH)
        assert r.status_code == 401
        assert r.headers[AUTH_PROBLEM_HEADER] == AUTH_PROBLEM_SESSION
        assert "sign in again" in r.json()["detail"].lower()

    def test_every_refusal_carries_the_header_so_the_client_never_guesses(self, world):
        """A 401 WITHOUT the header is read by the browser as "the session is dead" (unchanged, so an
        older api still behaves). A refusal from THIS api always says which kind it is."""
        for profile in (None, "member"):
            client = world.sign_in(profile=profile)
            world.answers(False)
            assert AUTH_PROBLEM_HEADER in client.get(PROBE_PATH).headers

    def test_could_not_ask_is_not_a_refusal(self, world):
        """⚠ The server being unreachable must never sign anybody out: an unanswerable question is
        not a "no". This is the same rule the rest of the repo applies to 503-vs-403."""
        client = world.sign_in(profile="member")
        world.answers(None)
        assert client.get(PROBE_PATH).status_code == 200

    def test_an_accepted_credential_leaves_the_request_alone(self, world):
        client = world.sign_in(profile="member")
        world.answers(True)
        assert client.get(PROBE_PATH).status_code == 200

    def test_a_request_with_no_session_is_never_probed(self, world):
        """The unenforced app (and the health check, and every tool) must not grow a media-server
        round trip: no session ⇒ nothing to ask about."""
        client = TestClient(app)
        assert client.get(PROBE_PATH).status_code == 200
        assert world.probes == []

    def test_the_answer_is_cached_so_a_page_burst_costs_ONE_upstream_call(self, world):
        """A page load fires several media calls at once; each one asking the media server would add
        a round trip per request. The TTL is the documented compromise (20s)."""
        client = world.sign_in(profile="member")
        world.answers(True)
        for _ in range(5):
            assert client.get(PROBE_PATH).status_code == 200
        assert len(world.probes) == 1, f"expected one probe for a burst, got {len(world.probes)}"

    def test_a_refused_credential_is_REPORTED_not_cached_away(self, world):
        """The cache must not become a way to hide a refusal: every request in the burst is told."""
        client = world.sign_in(profile="member")
        world.answers(False)
        codes = {client.get(PROBE_PATH).status_code for _ in range(3)}
        assert codes == {401}
        assert len(world.probes) == 1, "one upstream call, three honest answers"

    def test_the_auth_routes_stay_reachable_when_a_credential_is_refused(self, world):
        """⚠ The dependency is deliberately NOT on /api/auth/*: those routes are the FIX. A probe in
        front of them would close the only door that opens — the person could never switch profile
        out of the state the 401 is complaining about."""
        client = world.sign_in(profile="member")
        world.answers(False)
        assert client.get(PROBE_PATH).status_code == 401
        r = client.get("/api/auth/me")
        assert r.status_code == 200, "the picker must remain reachable to fix the refusal"


class TestTheProbeItself:
    """The real ``credential_is_accepted`` — because the STYLE is the whole function."""

    def test_it_uses_the_query_credential_the_server_actually_accepts(self):
        """⚠ MEASURED on the bundled Jellyfin 10.11.11 (2026-09-13):

        ``GET /Users/<id>`` with ``Authorization: <token>``  → **401** (does not authenticate)
        ``GET /Users/<id>?api_key=<token>``                  → **200**

        So this is not a style preference: the other one would report EVERY healthy request as a
        stale credential. Pinned, with the measurement, so it cannot be "tidied" back.
        """
        transport = FakeTransport(200)
        assert credential_is_accepted("tok-1", "uid-1", config=FakeConfig, transport=transport) is True
        method, url, headers = transport.seen[0]
        assert method == "GET" and url.endswith("/Users/uid-1?api_key=tok-1")
        assert "X-Emby-Authorization" in headers, "attribution stays in Jellyfin's own logs"
        assert "Authorization" not in headers, "measured NOT to authenticate this endpoint"

    def test_200_is_accepted_and_401_is_refused(self):
        assert credential_is_accepted("t", "u", config=FakeConfig,
                                      transport=FakeTransport(200)) is True
        assert credential_is_accepted("t", "u", config=FakeConfig,
                                      transport=FakeTransport(401)) is False

    def test_a_404_is_NEITHER(self):
        """MEASURED: an unknown user id answers 404. Reading that as "refused" would sign a person out
        over a missing account — a different answer about a different thing."""
        assert credential_is_accepted("t", "u", config=FakeConfig,
                                      transport=FakeTransport(404)) is None

    def test_a_5xx_is_could_not_ask(self):
        assert credential_is_accepted("t", "u", config=FakeConfig,
                                      transport=FakeTransport(503)) is None

    def test_an_unreachable_server_is_could_not_ask(self):
        assert credential_is_accepted("t", "u", config=FakeConfig,
                                      transport=FakeTransport(raises=True)) is None

    def test_nothing_to_ask_about_means_no_call_at_all(self):
        transport = FakeTransport(200)
        assert credential_is_accepted("", "u", config=FakeConfig, transport=transport) is None
        assert credential_is_accepted("t", "", config=FakeConfig, transport=transport) is None
        assert transport.seen == []


class TestPerSessionDeviceIds:
    """§4e: two browsers signed in as the same account must not rotate each other's tokens away."""

    def test_each_session_id_is_its_own_device_and_not_the_shared_one(self):
        a, b = auth_mod.new_session_device_id(), auth_mod.new_session_device_id()
        assert a != b
        assert a.startswith(f"{auth_mod.WEB_DEVICE_PREFIX}-")

    def test_many_sessions_get_distinct_ids_within_the_header_bound(self):
        """50 sessions ⇒ 50 devices: a collision would put two sessions back on ONE (device, user)
        pair, which is the §4e bug returning.

        ⚠ The id is RANDOM rather than derived from the session id, and that is a design rule this
        test cannot enforce by itself: the session id is a credential (stored only as a sha256
        because the file must not be replayable) while a device id travels into Jellyfin's session
        list and ITS logs — so composing one from the other would leak the cookie's secret into a
        foreign system's log file. `new_session_device_id()` therefore takes no arguments.
        """
        session_ids = [auth_mod.new_session_device_id() for _ in range(50)]
        assert len(set(session_ids)) == 50, "collisions would put two sessions back on one device"
        assert all(len(sid) <= auth_mod.DEVICE_ID_MAX for sid in session_ids), (
            "the id is interpolated into a header, so `_safe_device_id`'s bound must hold")

    def test_the_store_keeps_it_and_records_reports_it(self, tmp_path):
        store = SessionStore(path=tmp_path / "sessions.json")
        session_id, record = store.create(user_id="u1", user_name="U", token="t1",
                                         device_id="rkm-cinema-web-abc123")
        assert record["device_id"] == "rkm-cinema-web-abc123"
        assert [r["device_id"] for r in store.records()] == ["rkm-cinema-web-abc123"]

    def test_an_unusable_device_id_is_sanitised_before_it_is_stored(self, tmp_path):
        """It is interpolated into a header, so a quote or a newline must not survive."""
        store = SessionStore(path=tmp_path / "sessions.json")
        _sid, record = store.create(user_id="u1", user_name="U", token="t1",
                                    device_id='bad"id\nwith control')
        assert '"' not in record["device_id"] and "\n" not in record["device_id"]

    def test_a_row_with_no_device_id_keeps_the_old_behaviour(self, tmp_path):
        """An existing session (written before Phase 5) has no device id; it must still work, on the
        app's shared device, exactly as it did."""
        store = SessionStore(path=tmp_path / "sessions.json")
        _sid, record = store.create(user_id="u1", user_name="U", token="t1")
        assert "device_id" not in record
        assert store.records()[0]["device_id"] == ""
