"""Sign in, sign out, and "who am I" (AUTH_MULTIUSER_PLAN §3.7/§6 Phase 0).

Additive only: three new paths, nothing enforced (ADR-0001). The app is completely
usable signed-out until Phase 2 arms ``RKM_AUTH_REQUIRED`` — the phase order exists so
an enforcement deploy can never strand the user in an app with no way to sign in.

Deliberate properties, each pinned by a test:

* the cookie is the ONLY thing the browser gets — an opaque session id, ``HttpOnly``,
  ``SameSite=Lax``, and **no ``Secure``** while the tailnet is plain http (Tailscale
  encrypts the transport itself; ``Secure`` here would silently break sign-in);
* the Jellyfin token is NEVER in a response body, a log line, or the cookie;
* a rejected sign-in is a generic 401: an unknown user and a wrong password are
  indistinguishable, and the password never appears in the message.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from api.models import LoginRequest, LoginResponse, MeResponse, SessionUser
from api.session import session_context_from_request
from config.settings import get_config
from services.auth import (SESSION_COOKIE, AuthUnavailableError, InvalidCredentialsError,
                           authenticate_jellyfin, default_session_store)

router = APIRouter()
logger = logging.getLogger("rkm.api.auth")


def _user(user_id: str, user_name: str) -> SessionUser:
    return SessionUser(id=str(user_id or ""), name=str(user_name or ""))


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    """Exchange Jellyfin credentials for an app session (and nothing else).

    Identity is DELEGATED: the username/password go to Jellyfin's
    ``/Users/AuthenticateByName`` and are never stored; what we keep is the access
    token Jellyfin handed back, behind an opaque id this app invented.
    """
    cfg = get_config()
    try:
        identity = authenticate_jellyfin(payload.username, payload.password, config=cfg)
    except InvalidCredentialsError as exc:
        # Never the username, never the password: the log line is the outcome, and
        # the message is deliberately identical for an unknown user and a bad one.
        logger.info("auth.login rejected")
        raise HTTPException(status_code=401, detail=str(exc))
    except AuthUnavailableError as exc:
        logger.info("auth.login unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    store = default_session_store(cfg)
    session_id, record = store.create(user_id=identity.user_id,
                                      user_name=identity.user_name,
                                      token=identity.token)
    logger.info("auth.login ok user=%s", identity.user_id)

    # Build the response FIRST and set the cookie on it: returning a JSONResponse
    # means FastAPI does not merge headers set on an injected Response, so a cookie
    # set that way would silently never reach the browser.
    response = JSONResponse(LoginResponse(
        ok=True,
        user=_user(identity.user_id, identity.user_name),
        expires=str(record.get("expires") or ""),
    ).model_dump())
    response.set_cookie(
        SESSION_COOKIE, session_id,
        max_age=store.ttl_seconds,
        httponly=True,          # JavaScript cannot read it (no XSS token theft)
        samesite="lax",         # survives a normal top-level navigation
        secure=False,           # tailnet is plain http — Secure would break login
        path="/",
    )
    return response


@router.post("/auth/logout")
def logout(request: Request):
    """Revoke THIS session server-side and clear the cookie.

    Deleting the row is what makes sign-out real: the id is useless the moment it
    goes, unlike a stateless token that stays valid until it expires.
    """
    cfg = get_config()
    session_id = str((request.cookies or {}).get(SESSION_COOKIE) or "")
    revoked = default_session_store(cfg).revoke(session_id) if session_id else False
    logger.info("auth.logout revoked=%s", revoked)
    response = JSONResponse({"ok": True, "revoked": bool(revoked)})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/auth/me", response_model=MeResponse)
def me(request: Request):
    """Who is signed in on this browser, or 401.

    Strict on purpose, and independent of ``RKM_AUTH_REQUIRED``: this is the route the
    frontend guard asks, so it must answer truthfully about the session rather than
    about enforcement — "signed out" and "not enforced yet" are different states.
    """
    context = session_context_from_request(request)
    if context is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return MeResponse(user=_user(context.user_id, context.user_name),
                      expires=context.expires)
