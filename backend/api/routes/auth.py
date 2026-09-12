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

from api.models import (LoginRequest, LoginResponse, MeResponse, ProfileUser,
                        ProfilesResponse, SelectProfileRequest, SelectProfileResponse,
                        SessionUser)
from api.session import admin_status, grantable_rows, session_context_from_request
from config.settings import get_config
from services.auth import (SESSION_COOKIE, AuthUnavailableError, InvalidCredentialsError,
                           authenticate_jellyfin, default_session_store,
                           revoke_jellyfin_session)
from services.library.factory import build_library_service

router = APIRouter()
logger = logging.getLogger("rkm.api.auth")


def _user(user_id: str, user_name: str) -> SessionUser:
    return SessionUser(id=str(user_id or ""), name=str(user_name or ""))


def _profile(row: dict) -> ProfileUser:
    """One account row (from the provider) as the picker needs it — never a credential."""
    return ProfileUser(id=str(row.get("id") or ""), name=str(row.get("name") or ""),
                       is_admin=bool(row.get("is_admin")), has_password=bool(row.get("has_password")),
                       disabled=bool(row.get("disabled")),
                       last_login=str(row.get("last_login") or ""))


def _why_empty_profiles(library) -> str:
    """Why a profile list came back empty — so it never reads as \"there are no profiles\"."""
    error = getattr(library, "last_api_error", None)
    error = error() if callable(error) else error
    if not error:
        return ""
    if error.get("status"):
        return f"The media server answered HTTP {error['status']} while listing profiles."
    return f"Could not reach the media server ({error.get('error', 'unknown error')})."


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

    # PLEX_PROFILE_AUTH_PLAN §6.2 (user decision, 2026-09-12): ONLY an ADMINISTRATOR signs in to
    # the server. Everyone else reaches the app by picking a profile inside this session, so a
    # member's credential must never open a session of its own — enforced here, backend-side, not
    # by hiding a form. The message is deliberately explicit: telling a household member "you are
    # not an administrator" costs an attacker who already holds that member's password nothing (it
    # still gets them in nowhere) and saves the person a baffling dead end.
    status = admin_status(cfg, identity.user_id)
    if status is not True:
        # Whatever Jellyfin handed back is not going to be used — do not leave it live.
        revoke_jellyfin_session(identity.token, config=cfg)
        if status is None:
            logger.info("auth.login could not verify administrator rights")
            raise HTTPException(
                status_code=503,
                detail="Could not reach the media server to check administrator rights.")
        logger.info("auth.login refused: %s is not an administrator", identity.user_id)
        raise HTTPException(
            status_code=403,
            detail=("Only the administrator can sign in to this server. Everyone else picks "
                    "their profile from the household screen once the administrator is signed in."))

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


@router.get("/auth/profiles", response_model=ProfilesResponse)
def profiles(request: Request):
    """Every profile on the server, for "Who's watching?".

    A SESSION is required — the list itself sits behind the server login, which is what makes
    "members have no independent access" true rather than merely unlinked: without the
    administrator's sign-in there is no way to even see who exists.

    Reports whether each profile is password-protected and enabled, so the picker can show a lock
    and grey out a disabled profile BEFORE anyone tries to enter it.
    """
    context = session_context_from_request(request)
    if context is None:
        raise HTTPException(status_code=401, detail="Sign in to see the profiles on this server")
    cfg = get_config()
    library = build_library_service(cfg)
    if library is None:
        raise HTTPException(status_code=503,
                            detail="Could not reach the media server to list profiles.")
    rows = library.list_users()
    return ProfilesResponse(
        profiles=[_profile(row) for row in rows],
        current=ProfileUser(id=context.profile_id(), name=context.profile_name()),
        # `profile_id()` falls back to the owner, so the raw record is the only honest source for
        # "has anybody actually been chosen yet" (Phase B's picker marks the current row with it).
        profile_selected=bool(context.profile_user_id),
        warning="" if rows else _why_empty_profiles(library),
    )


@router.post("/auth/profile", response_model=SelectProfileResponse)
def select_profile(payload: SelectProfileRequest, request: Request):
    """Switch this session to a profile — the whole of "who is watching".

    Why it can only work this way: **Jellyfin has no impersonation** (measured 2026-09-12 — the
    only user-scoped token endpoint is ``/Users/AuthenticateByName``), so the app asks Jellyfin to
    authenticate AS the chosen profile. A password-less profile signs in with a blank password; a
    protected one needs its own. **The administrator knowing a member's password is not the
    mechanism — resetting it from Settings → Household is**, which is why that rail exists.

    Selecting the ADMINISTRATOR'S OWN profile requires the administrator's password: the device
    holds their session, so this is what stops a guest on the shared iPad from walking into it
    (decision 3, 2026-09-12). Switching back is therefore always deliberate, never automatic.
    """
    context = session_context_from_request(request)
    if context is None:
        raise HTTPException(status_code=401, detail="Sign in before choosing a profile")
    cfg = get_config()
    library = build_library_service(cfg)
    if library is None:
        raise HTTPException(status_code=503,
                            detail="Could not reach the media server to switch profile.")
    rows = {str(row.get("id") or ""): row for row in library.list_users()}
    target = rows.get(str(payload.user_id or ""))
    if target is None:
        raise HTTPException(status_code=404, detail="No such profile on this server")
    if target.get("disabled"):
        raise HTTPException(status_code=403,
                            detail="That profile is disabled — ask the administrator to enable it")

    wants_admin = bool(target.get("is_admin"))
    if wants_admin and not payload.password:
        # A BLANK attempt on the administrator's profile is always refused, so it can never be
        # entered by accident on a shared device. Be honest about the limit of that: when the
        # administrator's account genuinely has NO password, Jellyfin accepts ANY supplied value
        # (there is nothing to compare against — measured 2026-09-12), so in that one case this is
        # a check on INTENT rather than a cryptographic one. `has_password` tells the picker to show
        # a lock, and the Household screen nudges the administrator to set one for real.
        raise HTTPException(
            status_code=401,
            detail="Enter the administrator's password to switch to that profile")

    try:
        identity = authenticate_jellyfin(str(target.get("name") or ""), payload.password or "",
                                         config=cfg)
    except InvalidCredentialsError:
        # The profile's own password is the only secret here — never echoed, and a blank attempt
        # on a protected profile lands in exactly this branch.
        logger.info("auth.profile rejected (wrong password) for %s", str(target.get("id") or "")[:8])
        raise HTTPException(status_code=401, detail="That profile's password is not correct")
    except AuthUnavailableError as exc:
        logger.info("auth.profile unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    record = default_session_store(cfg).set_profile(
        context.session_id, user_id=identity.user_id, user_name=identity.user_name,
        token=identity.token,
        # ⚠ The administrator selecting their OWN profile re-authenticates on THIS session's device,
        # and Jellyfin invalidates the previous token for that device+user on every login. Without
        # this flag the session keeps a dead owner token and every administrator-level call 401s
        # (measured 2026-09-12: the sidebar came back empty after switching back).
        owns_session=(identity.user_id == context.user_id))
    if record is None:
        # The row vanished between resolving the cookie and writing (expired/revoked).
        raise HTTPException(status_code=401, detail="That session has ended — sign in again")

    # Which libraries this profile may see, resolved to names. The shape handling lives in
    # `grantable_rows` (facade dict vs provider list) — the trap that 500'd a route on 2026-09-12.
    all_rows = grantable_rows(library)
    by_id = {str(row.get("id") or ""): str(row.get("name") or "") for row in all_rows}
    if target.get("enable_all_folders"):
        libraries = [{"id": row_id, "name": name} for row_id, name in by_id.items()]
    else:
        libraries = [{"id": fid, "name": by_id.get(fid, "")}
                     for fid in (target.get("enabled_folders") or [])]

    logger.info("auth.profile switched to user=%s (admin=%s)", identity.user_id, wants_admin)
    return SelectProfileResponse(ok=True, profile=_profile(target), libraries=libraries)


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
                      profile=_user(context.profile_id(), context.profile_name()),
                      on_own_profile=context.on_own_profile(),
                      # The picker's ONE server-side trigger (Phase B): a fresh sign-in has no
                      # profile yet, and `profile_id()`'s fallback to the owner would otherwise make
                      # that indistinguishable from "the administrator chose themselves".
                      profile_selected=bool(context.profile_user_id),
                      expires=context.expires)
