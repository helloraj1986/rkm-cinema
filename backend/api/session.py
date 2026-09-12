"""The session seam: cookie → SessionStore → contextvar (AUTH_MULTIUSER_PLAN §3.3).

ONE dependency publishes the signed-in user's Jellyfin identity for the duration of a
request; :meth:`JellyfinLibraryProvider._token` then prefers it over the admin token
(Phase 3). That is deliberately a single diff point instead of threading a token
through the 18 ``build_library_service()`` call sites and the provider's 21
``api_key=`` URL builds — and it fails SAFE: no request context (the provisioner,
bootstrap health checks, the PowerShell/Python tooling, unit tests) behaves exactly
as it does today, with the admin token.

Two things are easy to get wrong here, so both are pinned by tests:

* ``require_session`` must be an ``async def``. FastAPI runs a *sync* dependency in a
  worker thread whose context is a **copy**, so a contextvar set there is discarded
  before the endpoint body runs — the provider would then silently fall back to the
  admin token, i.e. every user would share one identity again with no error anywhere.
  An async dependency runs in the event-loop context, which is the context the
  endpoint's own threadpool call copies.
* Enforcement is a FLAG, not a code path: ``RKM_AUTH_REQUIRED`` (default false in
  Phase 0, flipped in Phase 2) decides whether a missing session is a 401 or an
  anonymous request, so the documented lockout recovery is one value in `.env`.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request

from config.settings import get_config
from services.auth import SESSION_COOKIE, SessionStore, default_session_store

logger = logging.getLogger("rkm.api.session")


@dataclass(frozen=True)
class SessionContext:
    """Who this request is, and the token that acts as them.

    ``session_id`` is the opaque cookie value (in-process only, never logged);
    ``token`` is the Jellyfin access token — server-side only, never in a response.
    """

    session_id: str
    user_id: str
    user_name: str
    token: str
    expires: str = ""


#: The current request's session. Default ``None`` is meaningful: "no request
#: context" ⇒ behave exactly as before this feature (admin token).
_current_session: ContextVar[Optional[SessionContext]] = ContextVar(
    "rkm_current_session", default=None)


def current_session() -> Optional[SessionContext]:
    """The signed-in session for the request being handled, or ``None``."""
    return _current_session.get()


def set_current_session(context: Optional[SessionContext]) -> Token:
    """Publish a session for this request context (returns the reset token)."""
    return _current_session.set(context)


def reset_current_session(token: Token) -> None:
    """Undo :func:`set_current_session` (used by tests and long-lived tasks)."""
    _current_session.reset(token)


def session_store(config=None) -> SessionStore:
    """The store this module reads (monkeypatchable so a test never writes /data)."""
    return default_session_store(config)


def session_context_from_request(request: Request, *, config=None) -> Optional[SessionContext]:
    """Resolve a request's cookie to a session, or ``None``. Never raises.

    A stale/unknown/expired cookie is simply "not signed in" — the store has already
    dropped the row — so no error is reported back to a stranger probing the app.
    """
    session_id = str((request.cookies or {}).get(SESSION_COOKIE) or "")
    if not session_id:
        return None
    cfg = config if config is not None else get_config()
    record = session_store(cfg).lookup(session_id)
    if not record:
        return None
    return SessionContext(
        session_id=session_id,
        user_id=str(record.get("user_id") or ""),
        user_name=str(record.get("user_name") or ""),
        token=str(record.get("jellyfin_token") or ""),
        expires=str(record.get("expires") or ""),
    )


async def require_session(request: Request) -> Optional[SessionContext]:
    """Publish this request's session, and reject it when enforcement is armed.

    With ``RKM_AUTH_REQUIRED=false`` (Phase 0's default, and the permanent escape
    hatch) a missing session is NOT an error: the request proceeds exactly as it did
    before auth existed, and the provider keeps using the admin token. With the flag
    true, a missing/invalid session is a 401.

    Do not "simplify" this to a sync ``def`` — see the module docstring.
    """
    cfg = get_config()
    context = session_context_from_request(request, config=cfg)
    set_current_session(context)
    if context is None and cfg.auth_required():
        raise HTTPException(status_code=401, detail="Sign in to use this app")
    return context
