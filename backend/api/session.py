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
from services.library.factory import build_library_service

logger = logging.getLogger("rkm.api.session")


@dataclass(frozen=True)
class SessionContext:
    """Who this request is, and the token that acts as them.

    ``session_id`` is the opaque cookie value (in-process only, never logged);
    ``token`` is the Jellyfin access token — server-side only, never in a response.

    **Owner vs profile** (PLEX_PROFILE_AUTH_PLAN §3): ``user_id``/``token`` belong to the account
    that signed in to the SERVER (always an administrator now), and ``profile_*`` to the selected
    profile — the identity every media call is made as. With no profile selected the profile
    defaults to the owner, so an existing session (or one created before this feature) behaves
    exactly as it did: the administrator browsing as themselves.
    """

    session_id: str
    user_id: str
    user_name: str
    token: str
    expires: str = ""
    profile_user_id: str = ""
    profile_user_name: str = ""
    profile_token: str = ""

    def profile_id(self) -> str:
        """The id of the profile in effect (the owner when none was chosen)."""
        return self.profile_user_id or self.user_id

    def profile_name(self) -> str:
        """The display name of the profile in effect."""
        return self.profile_user_name or self.user_name

    def acting_token(self) -> str:
        """The credential media calls must use (the profile's, else the owner's)."""
        return self.profile_token or self.token

    def on_own_profile(self) -> bool:
        """Is the administrator's OWN profile the one in effect?

        False the moment somebody else's profile is selected — which is what makes the shared
        device safe: administrative routes and the switch back both require this to be True.
        """
        return self.profile_id() == self.user_id


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
        profile_user_id=str(record.get("profile_user_id") or ""),
        profile_user_name=str(record.get("profile_user_name") or ""),
        profile_token=str(record.get("profile_token") or ""),
    )


def grantable_rows(library) -> list[dict]:
    """The media server's libraries, from EITHER shape the provider stack can answer.

    The routes are handed ``LibraryService`` (a **facade**), whose ``library_folders()`` returns
    ``{"provider": …, "folders": [...]}``; the provider underneath returns a plain list. Reading
    only one of the two produced a 500 in production on 2026-09-12 — TWICE — so the shape dance
    lives in one place, here, where the administrative routes and the profile routes both reach it.
    """
    if library is None:
        return []
    try:
        folders = library.library_folders()
    except Exception:  # a server that cannot answer must not 500 the caller
        logger.warning("could not read the media server's libraries", exc_info=True)
        return []
    rows = folders.get("folders") if isinstance(folders, dict) else folders
    return [f for f in (rows or []) if isinstance(f, dict)]


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


def admin_status(cfg, user_id: str) -> Optional[bool]:
    """Is this account an ENABLED Jellyfin administrator? — ``True`` / ``False`` / ``None``.

    ``None`` means **the server could not be asked**, which is NOT the same answer as "no": the
    media server may be unconfigured, unreachable, or refusing the app's credential. Collapsing
    those into ``False`` makes the screen tell the user they are not an administrator when the
    truth is that nobody knows — the exact class of lie this repo's rules exist to prevent.

    Deliberately NOT a cached or stored flag: a stale `is_admin` is an authorisation bug (a
    demoted account would keep its powers, or a promoted one would not get them), and this app's
    rule is that the media server's own state is authoritative.

    A DISABLED administrator is refused too: the account cannot use the server at all, so it must
    not be able to manage it either.

    In Phase 1b the provider answers this with the app's admin credential, which is why the check
    must live HERE rather than being left to Jellyfin's own 403: that backstop only exists once
    every call is made as the signed-in user (Phase 3).
    """
    if not user_id:
        return False
    try:
        library = build_library_service(cfg)
    except Exception:  # a provider that cannot even be built must not grant access
        logger.warning("administrator check could not build the provider", exc_info=True)
        return None
    if library is None:
        # Jellyfin is not configured for this api — no URL or no credential. A real state
        # (`build_library_service` documents it for fresh installs), and not a decision about
        # this account.
        logger.warning("administrator check: the media server is not configured (no URL or no key)")
        return None
    try:
        policy = library.get_user_policy(user_id)
        reason = getattr(library, "last_api_error", None)
        reason = reason() if callable(reason) else reason
    except Exception:  # a provider that cannot answer must not grant access
        logger.warning("administrator check failed for %s", user_id, exc_info=True)
        return None
    if policy is None:
        logger.warning("administrator check could not ask the server about %s: %s", user_id, reason)
        return None
    return bool(policy.get("IsAdministrator")) and not bool(policy.get("IsDisabled"))


def is_administrator(cfg, user_id: str) -> bool:
    """``admin_status(...) is True`` — the strict reading, for callers that cannot say "unknown"."""
    return admin_status(cfg, user_id) is True


async def require_admin_session(request: Request) -> SessionContext:
    """A session AND a Jellyfin administrator. NEVER lenient.

    These routes can create, alter and delete accounts, so unlike the rest of the app
    they enforce a session even while ``RKM_AUTH_REQUIRED`` is false: an anonymous caller
    must not reach them in any world. 401 when nobody is signed in, 403 when the signed-in
    person is not an administrator, and **503 when the server could not be asked** — the
    three are different answers and the screen must not confuse them.
    """
    cfg = get_config()
    context = session_context_from_request(request, config=cfg)
    if context is None:
        raise HTTPException(status_code=401, detail="Sign in to manage household accounts")
    set_current_session(context)
    status = admin_status(cfg, context.user_id)
    if status is None:
        # NOT a refusal about this person: the media server could not be asked (unconfigured,
        # unreachable, or refusing the app's credential). A 403 here would tell the user they
        # are not an administrator when the truth is that nobody knows.
        logger.warning("household route could not verify admin rights for %s", context.user_id)
        raise HTTPException(
            status_code=503,
            detail=("Could not reach the media server to check administrator rights. "
                    "Nothing was changed."))
    if not status:
        logger.info("household route refused for non-admin user=%s", context.user_id)
        raise HTTPException(
            status_code=403,
            detail="Only a Jellyfin administrator can manage household accounts")
    if not context.on_own_profile():
        # Decision 3 (user, 2026-09-12): on a shared device the ADMINISTRATOR'S session is held by
        # the device, so administrative access must not be reachable while somebody else's profile
        # is selected. Switching back is a deliberate, password-checked act (POST /api/auth/profile
        # with the administrator's password) — which is what stops the family iPad from handing
        # every guest full server control.
        logger.info("household route refused: profile %s is selected, not the administrator's own",
                    context.profile_id())
        raise HTTPException(
            status_code=403,
            detail=("Switch back to your own profile to manage the household — a different "
                    "profile is selected on this device."))
    return context
