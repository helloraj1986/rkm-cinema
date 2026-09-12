"""Household accounts (AUTH_MULTIUSER_PLAN Phase 1b): create, grant, disable, reset, delete.

This is the app's own front end for **Jellyfin's** user management — the app still owns no
accounts and stores no passwords. It is what makes the second Jellyfin user Phase 3 needs
creatable from the UI instead of the Jellyfin dashboard.

Every route is gated by :func:`api.session.require_admin_session`: a session **and** a LIVE
Jellyfin administrator check, and it is **never lenient** — unlike the rest of the app it
enforces a session even while ``RKM_AUTH_REQUIRED`` is false, because these routes can create
and delete accounts.

Rails that are not negotiable (each one has a test):

* the password is used ONCE and passed straight to Jellyfin — never stored in the app, never
  logged, never returned;
* the policy is **read-modify-write**: ``POST /Users/{id}/Policy`` replaces all 47 fields, so
  a partial body would silently reset permissions;
* a **password-less** account is supported (user decision 2026-09-12) and is never an
  administrator;
* the **last administrator** cannot be deleted, and neither can the account you are signed in
  as;
* deleting requires the account's NAME typed out, because it is irreversible.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from api.models import (AdminCreateUserRequest, AdminDeleteUserRequest,
                        AdminSetPasswordRequest, AdminUserPolicyRequest)
from api.session import SessionContext, require_admin_session
from config.settings import get_config
from services.library.factory import build_library_service

router = APIRouter()
logger = logging.getLogger("rkm.api.admin_users")


def _library(cfg):
    """The provider the account calls go through (a test seam: routes call it BY NAME)."""
    return build_library_service(cfg)


def _warning(library) -> str:
    """Why a LISTING may be empty — an empty household must not look like "no accounts"."""
    error = getattr(library, "last_api_error", None)
    if callable(error):
        error = error()
    if not error:
        return ""
    if error.get("status") == 403:
        return ("The media server refused the request — the app's own credential is not an "
                "administrator, so accounts cannot be listed.")
    if error.get("status"):
        return f"The media server answered HTTP {error['status']} while listing accounts."
    return f"Could not reach the media server ({error.get('error', 'unknown error')})."


def _find(library, user_id: str) -> dict:
    """One account by id, or a 404 — never a silent no-op on a wrong id."""
    for user in library.list_users():
        if str(user.get("id")) == str(user_id):
            return user
    raise HTTPException(status_code=404, detail="No such account")


def _live_users(library) -> list[dict]:
    """The household as the SERVER reports it (used for the rails, never cached)."""
    return list(library.list_users() or [])


@router.get("/admin/users")
def list_users(session: SessionContext = Depends(require_admin_session)):
    """Every household account: who they are, whether they are an admin, what they can see."""
    cfg = get_config()
    library = _library(cfg)
    users = _live_users(library)
    return JSONResponse({
        "users": users,
        "signed_in_as": session.user_id,
        "warning": "" if users else _warning(library),
    })


@router.get("/admin/libraries")
def list_grantable_libraries(session: SessionContext = Depends(require_admin_session)):
    """The libraries a member can be granted — the tick-box list, with the ids a grant holds."""
    cfg = get_config()
    library = _library(cfg)
    folders = library.library_folders()
    return JSONResponse({
        "libraries": [{"id": str(f.get("id") or ""), "name": str(f.get("name") or ""),
                       "collection_type": str(f.get("collection_type") or ""),
                       "path": str(f.get("path") or "")} for f in folders],
        "warning": "" if folders else _warning(library),
    })


@router.post("/admin/users")
def create_user(payload: AdminCreateUserRequest,
                session: SessionContext = Depends(require_admin_session)):
    """Create an account and grant it libraries.

    A blank password is DELIBERATE and supported: that member signs in with just their
    username. The account is never created as an administrator — there is no way to ask for
    one here on purpose, since a password-less administrator would hand account management
    to anyone who can reach the app.
    """
    cfg = get_config()
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="A name is required")
    library = _library(cfg)
    if any(str(u.get("name", "")).lower() == name.lower() for u in _live_users(library)):
        raise HTTPException(status_code=409, detail=f"There is already an account called {name}")

    created = library.create_user(name, payload.password or "")
    if not created or not created.get("id"):
        logger.info("household create failed for %r", name)
        raise HTTPException(status_code=502,
                            detail="The media server did not create the account")

    # The grant. None = every library (the administrator's own access, the chosen default);
    # an empty list = none.
    granted: list[str] = []
    if payload.library_ids is None:
        policy = library.set_folder_access(created["id"], [], enable_all=True)
        granted = [str(f.get("id")) for f in (library.library_folders() or [])]
    else:
        policy = library.set_folder_access(created["id"], payload.library_ids)
        granted = [str(i) for i in payload.library_ids]
    if policy is None:
        # The account exists; say so rather than pretend the whole action failed.
        logger.warning("created %r but could not set its libraries", name)
        return JSONResponse({
            "ok": True, "user": created, "granted": [],
            "warning": "The account was created, but its library access could not be set — "
                       "retry from this screen.",
        })

    logger.info("household account created id=%s admin=False", created["id"])
    return JSONResponse({"ok": True, "user": created, "granted": granted, "warning": ""})


@router.post("/admin/users/{user_id}/policy")
def update_user_policy(user_id: str, payload: AdminUserPolicyRequest,
                       session: SessionContext = Depends(require_admin_session)):
    """Change a member's library access and/or enable-disable them.

    Both fields are optional and independent: omitting one leaves it exactly as it is
    (the policy is read-modify-written, so nothing else on the policy is touched either).
    """
    cfg = get_config()
    library = _library(cfg)
    target = _find(library, user_id)
    warning = ""

    if payload.library_ids is not None:
        if library.set_folder_access(user_id, payload.library_ids) is None:
            warning = "The library access change did not take."
    if payload.disabled is not None:
        if library.set_user_disabled(user_id, payload.disabled) is None:
            warning = "The enable/disable change did not take."

    if warning:
        raise HTTPException(status_code=502, detail=warning)

    # Re-read so the screen shows what the SERVER now holds, not what was requested.
    updated = _find(library, user_id)
    logger.info("household policy updated id=%s fields=%s", user_id,
                [k for k in ("library_ids", "disabled") if getattr(payload, k) is not None])
    return JSONResponse({"ok": True, "user": updated, "was": target.get("name", "")})


@router.post("/admin/users/{user_id}/password")
def set_user_password(user_id: str, payload: AdminSetPasswordRequest,
                      session: SessionContext = Depends(require_admin_session)):
    """Set or reset a member's password.

    The value is passed straight to Jellyfin and deliberately appears in NO response and NO
    log line. There is no endpoint that can read a password back — not even for an admin.
    """
    new_password = payload.new_password or ""
    if not new_password:
        raise HTTPException(
            status_code=400,
            detail="A password is required here — an account is created without one, "
                   "not emptied afterwards")
    cfg = get_config()
    library = _library(cfg)
    _find(library, user_id)  # 404 rather than a silent no-op on a wrong id
    if not library.set_user_password(user_id, new_password):
        raise HTTPException(status_code=502, detail="The media server refused the password change")
    logger.info("household password set id=%s", user_id)
    return JSONResponse({"ok": True})


@router.delete("/admin/users/{user_id}")
def delete_user(user_id: str, payload: AdminDeleteUserRequest,
                session: SessionContext = Depends(require_admin_session)):
    """Delete an account — irreversible, so the rails come first.

    Refused: the account you are signed in as, and the LAST administrator. Note the ordering
    honestly: because the gate already guarantees the caller is an ENABLED administrator, the
    last-administrator check cannot fire from a normal request (any non-self admin target has
    the caller for company) — the self rail is what actually protects the final admin. The
    check stays as a backstop for the window where the caller's own rights change mid-request,
    and for any future caller that is not itself an administrator.
    """
    cfg = get_config()
    library = _library(cfg)
    target = _find(library, user_id)

    if str(target.get("id")) == str(session.user_id):
        raise HTTPException(status_code=400, detail="You cannot delete the account you are signed in as")

    users = _live_users(library)
    admins = [u for u in users if u.get("is_admin")]
    if target.get("is_admin") and len(admins) <= 1:
        raise HTTPException(
            status_code=400,
            detail="That is the only administrator — deleting it would leave nobody able to "
                   "manage the household")

    expected = str(target.get("name") or "")
    if (payload.confirm_name or "").strip().lower() != expected.strip().lower():
        raise HTTPException(status_code=400,
                            detail=f"Type the account's name ({expected}) to confirm")

    if not library.delete_user(user_id):
        raise HTTPException(status_code=502, detail="The media server refused to delete the account")
    logger.info("household account deleted id=%s", user_id)
    return JSONResponse({"ok": True, "deleted": str(user_id), "name": expected})
