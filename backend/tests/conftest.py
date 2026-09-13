"""Shared test support: how a test signs in as an administrator.

``require_admin_session`` (``api/session.py``) is the ONE dependency that is strict **even while
``RKM_AUTH_REQUIRED=false``** — a missing session is a 401 and a member's session is a 403, in
every world. Phase E (his decision 2026-09-13) put it on four more routes — the library scan, the
generic job runner, the reconcile pass and the *arr download action — because they are
administrative *in effect* though they were only session-gated.

So a test that drives one of those routes over real HTTP now needs both halves of the gate:
a session in a store the test owns, and an answer to *"is this account an administrator?"*.

What this fixture replaces is **only the thing that has to ask the media server** — ``admin_status``.
The dependency itself, the session store, the cookie, the router wiring and the routes are the
shipped code. The gate's own three answers (401 anonymous · 403 a member · 503 the server could not
be asked) are proved against a fake PROVIDER in ``tests/test_admin_users_api.py``; the inventory
that stops a new route shipping without a decision is ``tests/test_route_protection.py``.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.session as session_mod
from services.auth import SESSION_COOKIE, SessionStore

ADMIN_ID = "uid-admin"


@pytest.fixture()
def signed_in(tmp_path, monkeypatch):
    """``signed_in(client)`` → the same client, now carrying a live administrator's cookie.

    The store is isolated per test, ``RKM_AUTH_REQUIRED`` is left **false** (so the rest of the app
    keeps behaving exactly as it does today, which is the state under test), and ``admin_status``
    answers without a media server. Pass ``admin=False`` for a member.

    A route that is *not* admin-gated must stay reachable signed out — so do NOT reach for this
    fixture to make a test pass. If a route refuses a signed-out caller, that refusal is the fact
    under test.
    """
    def _apply(client: TestClient, *, admin: bool = True, user_id: str = ADMIN_ID) -> TestClient:
        store = SessionStore(path=tmp_path / "sessions.json")
        session_id, _ = store.create(user_id=user_id, user_name=user_id, token="jf-token")
        monkeypatch.setattr(session_mod, "session_store", lambda config=None: store)
        monkeypatch.setattr(session_mod, "admin_status", lambda cfg, uid: admin)
        # The real config answers this by reading its own flag; arming it here would turn every
        # other route strict too and hide whatever the test was actually checking.
        monkeypatch.setattr(session_mod.get_config(), "RKM_AUTH_REQUIRED", "false")
        client.cookies.set(SESSION_COOKIE, session_id)
        return client

    return _apply
