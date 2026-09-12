"""Server-side sessions + Jellyfin identity (AUTH_MULTIUSER_PLAN §3.1/§3.2, Phase 0).

Two things live here, and keeping them apart is what makes the design safe:

* :class:`SessionStore` — the app's OWN session state: an opaque id (held by the
  browser in an HttpOnly cookie) mapped to a Jellyfin access token. Only the
  ``sha256`` of the id is stored, so a leaked store file yields no usable session
  (and logout is a real revocation: the row is deleted).
* :func:`authenticate_jellyfin` — the ONE place a username/password is exchanged
  for an identity + token. Identity is DELEGATED to Jellyfin: this app owns no
  accounts, no password store and no password reset.

Rules this module exists to enforce (plan §3, §8):

* the Jellyfin token **never** reaches the browser (an opaque session id does) and
  is **never** logged — ``records()`` deliberately omits it;
* a failed login is GENERIC: unknown user and wrong password are indistinguishable
  to the caller, and neither the password nor the response body is echoed;
* the store sits on the media root (``/data/rkm``) beside the watchlist, so an api
  rebuild does not sign the household out;
* a corrupt store file degrades to empty rather than taking login down.

Phase 0 ships this with **nothing enforced** — ``require_session`` (api/session.py)
only starts rejecting requests when ``RKM_AUTH_REQUIRED`` is true, and the flag is
false until the login UI has shipped (plan §5, the lockout rule).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import socket
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.settings import get_config
from core.exceptions import RKMError

logger = logging.getLogger("rkm.auth")

#: The cookie the browser holds. Opaque id only — never a Jellyfin token (plan §8.3).
SESSION_COOKIE = "rkm_session"

#: File name used beside the watchlist (and the container default).
SESSION_FILENAME = "sessions.json"

#: Where the store lives when the watchlist path is unknown (container default).
DEFAULT_DIR = "/data/rkm"

#: 30 days, refreshed on use (plan §11.1: shorter means re-logging in on the TV
#: browser; longer means a lost device stays signed in).
SESSION_TTL_SECONDS = 30 * 24 * 3600

#: Sliding expiry without a disk write per request: a session is only re-written
#: once it has gone this long without being touched.
TOUCH_INTERVAL_SECONDS = 60

#: Socket timeout for the authentication call.
DEFAULT_TIMEOUT = 15.0

#: Who the login is attributed to in Jellyfin's own activity log. Deliberately NOT
#: the ``rkm-tools`` identity the probe tools use: when a write is later found to
#: have been dropped, the app name in ``/System/Logs`` is what identifies which
#: client made the call (that forensics routine is written up in the repo skill).
CLIENT_HEADER = ('MediaBrowser Client="RKM Cinema", Device="RKM Cinema Web", '
                 'DeviceId="rkm-cinema-web", Version="2.0"')


# ----------------------------------------------------------------------- errors
class AuthError(RKMError):
    """Base for every authentication/session failure. Never leaks a stack trace."""


class InvalidCredentialsError(AuthError):
    """The username/password pair was not accepted. Deliberately unspecific."""


class AuthUnavailableError(AuthError):
    """Jellyfin is not configured, unreachable, or answered something unusable."""


# ----------------------------------------------------------------------- helpers
def default_session_path(watchlist_path: Optional[str] = None) -> Path:
    """The session store path, derived from the watchlist's own location.

    The watchlist is already placed by `.env` (``WATCHLIST_DB_PATH=/data/rkm/…``
    on the media root, so it survives rebuilds); sessions belong beside it for the
    same reason, and this keeps working when the user moves the media root.
    """
    if watchlist_path:
        return Path(str(watchlist_path)).with_name(SESSION_FILENAME)
    return Path(DEFAULT_DIR) / SESSION_FILENAME


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse a stored timestamp; ``None`` when it is missing or malformed."""
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def hash_session_id(session_id: str) -> str:
    """The stored key: ``sha256`` of the opaque id (plan §3.1, §8.3)."""
    return hashlib.sha256(str(session_id or "").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------- results
@dataclass(frozen=True)
class JellyfinIdentity:
    """Who just signed in, and the token that acts as them."""

    user_id: str
    user_name: str
    token: str


# -------------------------------------------------------------------- transport
@dataclass
class AuthResponse:
    """A raw HTTP response: statuses are RETURNED, mapping them is the caller's job.

    Deliberately local to this module rather than shared with the OpenSubtitles
    client: auth must not depend on a subtitle vendor's module, and a shared
    transport is a refactor of its own (not Phase 0's business).
    """

    status: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> Any:
        if not self.body:
            return {}
        try:
            return json.loads(self.body.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            return None


class UrllibTransport:
    """The real transport (stdlib only — no new dependency)."""

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    def request(self, method: str, url: str, *, headers: Optional[Dict[str, str]] = None,
                json_body: Optional[dict] = None,
                timeout: Optional[float] = None) -> AuthResponse:
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        hdrs = dict(headers or {})
        if data is not None:
            hdrs.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return AuthResponse(status=resp.status,
                                    headers={k.lower(): v for k, v in resp.headers.items()},
                                    body=resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read() if exc.fp else b""
            return AuthResponse(status=exc.code,
                                headers={k.lower(): v for k, v in (exc.headers or {}).items()},
                                body=body)
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            # The exception CLASS only — a urllib error can stringify the URL it
            # called, and that is a leak this module must not create (the rule the
            # OpenSubtitles client paid for).
            raise AuthUnavailableError(
                f"could not reach the media server ({type(exc).__name__})") from exc


# ------------------------------------------------------------------ jellyfin call
def authenticate_jellyfin(username: str, password: str, *, config=None,
                          transport=None) -> JellyfinIdentity:
    """Exchange a username/password for a Jellyfin identity + access token.

    Mirrors the proven call in ``tools/rkm_common.py::Jellyfin._login`` (an
    ``X-Emby-Authorization: MediaBrowser …`` header against
    ``/Users/AuthenticateByName``) and adds the failure taxonomy:

    * 401/403 ⇒ :class:`InvalidCredentialsError` — GENERIC, so an unknown user and a
      bad password are indistinguishable, and the password is never echoed;
    * 5xx, a network failure, or a 200 without a token ⇒ :class:`AuthUnavailableError`;
    * no ``JELLYFIN_URL`` ⇒ :class:`AuthUnavailableError` (unconfigured, not a reject).

    The raised messages carry a status code or an exception CLASS — never the
    response body (which can contain the username) and never the password.
    """
    cfg = config if config is not None else get_config()
    base = str(getattr(cfg, "JELLYFIN_URL", "") or "").rstrip("/")
    if not base:
        raise AuthUnavailableError("the media server is not configured")

    transport = transport if transport is not None else UrllibTransport()
    try:
        response = transport.request(
            "POST", f"{base}/Users/AuthenticateByName",
            headers={"X-Emby-Authorization": CLIENT_HEADER},
            json_body={"Username": str(username or ""), "Pw": str(password or "")},
        )
    except AuthError:
        raise
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
        # A RAW transport error must be wrapped, or it escapes this module's taxonomy
        # and the route answers a 500 instead of an honest 503 — the trap the
        # OpenSubtitles client fell into, found there only by writing the failure-path
        # test. The message carries the exception CLASS, never its text: a urllib error
        # stringifies the URL it called.
        raise AuthUnavailableError(
            f"could not reach the media server ({type(exc).__name__})") from exc

    if response.status in (401, 403):
        raise InvalidCredentialsError("Incorrect username or password")
    if response.status >= 500:
        raise AuthUnavailableError(
            f"the media server answered HTTP {response.status} while signing in")
    if response.status != 200:
        raise AuthUnavailableError(
            f"the media server rejected the sign-in request (HTTP {response.status})")

    payload = response.json()
    if not isinstance(payload, dict):
        raise AuthUnavailableError("the media server returned an unexpected sign-in response")
    token = str(payload.get("AccessToken") or "")
    user = payload.get("User") if isinstance(payload.get("User"), dict) else {}
    user_id = str((user or {}).get("Id") or "")
    if not token or not user_id:
        raise AuthUnavailableError("the media server returned an unexpected sign-in response")
    return JellyfinIdentity(user_id=user_id,
                            user_name=str((user or {}).get("Name") or username or ""),
                            token=token)


# ------------------------------------------------------------- revoking a token
def revoke_jellyfin_session(token: str, *, config=None, transport=None) -> bool:
    """Best-effort: end the Jellyfin session a token belongs to. Never raises.

    Used when the app has just obtained a token it will NOT use — the refused non-administrator
    login in `api/routes/auth.py`. Leaving a live token behind would be a small but real hole
    (a credential sitting in Jellyfin's session list that nothing in the app can see or expire),
    and Jellyfin offers `POST /Sessions/Logout` for exactly this.
    """
    cfg = config if config is not None else get_config()
    base = str(getattr(cfg, "JELLYFIN_URL", "") or "").rstrip("/")
    if not base or not token:
        return False
    try:
        request = urllib.request.Request(
            f"{base}/Sessions/Logout",
            data=b"",
            method="POST",
            headers={"X-Emby-Authorization": CLIENT_HEADER, "Authorization": token},
        )
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
            return 200 <= int(getattr(response, "status", 200)) < 300
    except Exception as exc:  # noqa: BLE001 - revocation is best-effort by definition
        logger.info("could not revoke an unused media-server session (%s)", type(exc).__name__)
        return False


# ------------------------------------------------------------------ session store
class SessionStore:
    """Atomic, corrupt-tolerant sessions.

    Reads are cached on the file's mtime (the watchlist/subtitle-store pattern), so
    a long-lived config object does not re-read the file on every request. Writes are
    tmp-file + ``os.replace``: a reader can never see a half-written store, and a
    crash mid-write leaves the previous state intact. The file is written ``0600``
    and holds sha256 hashes, never the ids themselves.
    """

    def __init__(self, *, path: Optional[Path] = None, config=None,
                 ttl_seconds: int = SESSION_TTL_SECONDS):
        self._config = config if config is not None else get_config()
        if path is None:
            watchlist = getattr(self._config, "WATCHLIST_DB_PATH", None)
            path = default_session_path(watchlist)
        self.path = Path(path)
        self.ttl_seconds = int(ttl_seconds)
        self._lock = threading.Lock()
        self._cache: Optional[dict] = None
        self._cache_mtime: float = 0.0

    # ------------------------------------------------------------------ reading
    def load(self) -> dict:
        """The whole store as ``{"sessions": {<sha256>: record}}`` (never raises)."""
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self._cache, self._cache_mtime = {"sessions": {}}, 0.0
            return dict(self._cache)
        if self._cache is not None and mtime == self._cache_mtime:
            return self._cache
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError) as e:
            # A corrupt store must never lock the household out of the app: start
            # empty, say so, and leave the damaged file alone rather than
            # overwriting evidence. (Everyone signs in again; nobody is stuck.)
            logger.warning("session store at %s is unreadable (%s) — starting empty",
                           self.path, type(e).__name__)
            raw = {}
        sessions = (raw or {}).get("sessions") if isinstance(raw, dict) else {}
        data = {"sessions": dict(sessions) if isinstance(sessions, dict) else {}}
        self._cache, self._cache_mtime = data, mtime
        return data

    def _expired(self, record: dict) -> bool:
        """True when the record carries no usable future expiry."""
        expires = _parse_iso(record.get("expires"))
        return expires is None or expires <= _now()

    def lookup(self, session_id: str) -> Optional[dict]:
        """The record for a session id, or ``None``.

        Expiry is checked here (never trusted to the cookie's own Max-Age) and an
        expired row is revoked on the spot. A live row has its expiry slid forward,
        at most once per :data:`TOUCH_INTERVAL_SECONDS` so this stays a read on the
        hot path.
        """
        key = hash_session_id(session_id or "")
        if not session_id:
            return None
        record = (self.load().get("sessions") or {}).get(key)
        if not isinstance(record, dict):
            return None
        if self._expired(record):
            self.revoke(session_id)
            return None
        return self._touch(key, record)

    def _touch(self, key: str, record: dict) -> dict:
        now = _now()
        last_seen = _parse_iso(record.get("last_seen")) or now
        if (now - last_seen).total_seconds() < TOUCH_INTERVAL_SECONDS:
            return dict(record)

        def mutate(data):
            row = dict(data.setdefault("sessions", {}).get(key) or record)
            row["last_seen"] = _iso(now)
            row["expires"] = _iso(now + timedelta(seconds=self.ttl_seconds))
            data["sessions"][key] = row
            return row

        return dict(self._mutate(mutate))

    def records(self) -> List[dict]:
        """Every session's METADATA — never the Jellyfin token (plan §3.1).

        This is the shape anything diagnostic (a status page, a probe tool) may
        print: who is signed in, which profile is active, and until when, with no
        credential in it.
        """
        return [
            {
                "user_id": str(row.get("user_id") or ""),
                "user_name": str(row.get("user_name") or ""),
                "profile_user_id": str(row.get("profile_user_id") or ""),
                "profile_user_name": str(row.get("profile_user_name") or ""),
                "created": str(row.get("created") or ""),
                "expires": str(row.get("expires") or ""),
                "last_seen": str(row.get("last_seen") or ""),
            }
            for row in (self.load().get("sessions") or {}).values()
            if isinstance(row, dict)
        ]

    def set_profile(self, session_id: str, *, user_id: str, user_name: str,
                    token: str, owns_session: bool = False) -> Optional[dict]:
        """Point this session at a PROFILE — the Jellyfin identity it now acts as.

        The OWNER fields stay untouched: the server login that authorised this session remains
        identifiable, so administrator access can be re-granted without a fresh login (the switch
        back to the administrator is password-checked at the route) and a shared device cannot
        lose track of whose session it is holding.

        ⚠ **``owns_session`` — the ONE case where the owner's token IS replaced.** Set it when this
        switch authenticated as the account that signed in (the administrator selecting their own
        profile). Jellyfin invalidates the previous token for a given **device + user** on every
        login, and the app logs in on ONE device id, so that switch-back silently kills the token
        the session has been holding since sign-in: every later administrator-level call (the
        library metadata a profile's views are enriched with, account management) then answers
        **401** and the sidebar comes back empty. Measured live 2026-09-12 by
        ``tools/prove_profile_isolation.py`` — the token must be REPLACED, not kept.
        """
        key = hash_session_id(session_id or "")
        if not session_id:
            return None

        def mutate(data):
            sessions = data.setdefault("sessions", {})
            row = sessions.get(key)
            if not isinstance(row, dict):
                return None
            row["profile_user_id"] = str(user_id or "")
            row["profile_user_name"] = str(user_name or "")
            row["profile_token"] = str(token or "")
            if owns_session and token and str(user_id or "") == str(row.get("user_id") or ""):
                # The administrator re-authenticated on this session's device: the old owner token
                # is dead from this moment (see the docstring). The id check is a rail, not a
                # formality — a caller whose flag and id disagree must NOT be able to overwrite the
                # administrator's credential with a member's.
                row["jellyfin_token"] = str(token)
            sessions[key] = row
            return row

        result = self._mutate(mutate)
        return dict(result) if isinstance(result, dict) else None

    def rename_identity(self, session_id: str, *, user_id: str, name: str) -> Optional[dict]:
        """Follow a RENAME: update the names THIS session is holding for that account.

        The session stores the name it was handed at sign-in / profile selection, and nothing
        re-reads Jellyfin per request — so without this the header chip keeps showing the OLD name
        after a rename until the profile is chosen again. That is a silent wrong answer about who
        is watching, which is exactly what this workstream exists to stop.

        Only THIS session can be corrected here (it is the one making the request). Another device
        fixes itself on its next profile selection; a name is display, so that is tolerable —
        unlike a token, which must never be stale.

        The owner and the profile are updated independently: they are the same account only on the
        administrator's own profile.
        """
        key = hash_session_id(session_id or "")
        if not session_id or not user_id or not str(name or "").strip():
            return None

        def mutate(data):
            sessions = data.setdefault("sessions", {})
            row = sessions.get(key)
            if not isinstance(row, dict):
                return None
            if str(row.get("user_id") or "") == str(user_id):
                row["user_name"] = str(name)
            if str(row.get("profile_user_id") or "") == str(user_id):
                row["profile_user_name"] = str(name)
            sessions[key] = row
            return row

        result = self._mutate(mutate)
        return dict(result) if isinstance(result, dict) else None

    def count(self) -> int:
        return len(self.load().get("sessions") or {})

    # ------------------------------------------------------------------ writing
    def _write(self, data: dict) -> None:
        """Atomically persist the whole store (tmp + ``os.replace``), mode ``0600``."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".rkm-tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2, sort_keys=True))
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:  # pragma: no cover - Windows/no-op filesystems
            pass
        self._cache, self._cache_mtime = data, self.path.stat().st_mtime

    def _mutate(self, mutate) -> Any:
        with self._lock:
            data = json.loads(json.dumps(self.load()))   # private copy: no shared refs
            result = mutate(data)
            self._write(data)
            return result

    def create(self, *, user_id: str, user_name: str, token: str,
               ttl_seconds: Optional[int] = None) -> Tuple[str, dict]:
        """Start a session; returns ``(session_id, record)``.

        ``session_id`` is returned to the CALLER ONLY (it goes into an HttpOnly
        cookie). What is stored is its sha256, so the file on disk cannot be replayed.
        """
        user_id = str(user_id or "")
        token = str(token or "")
        if not user_id or not token:
            raise ValueError("create() needs a user_id and a token")
        session_id = secrets.token_urlsafe(32)
        ttl = int(ttl_seconds or self.ttl_seconds)
        now = _now()
        record = {
            "user_id": user_id,
            "user_name": str(user_name or ""),
            "jellyfin_token": token,
            "created": _iso(now),
            "expires": _iso(now + timedelta(seconds=ttl)),
            "last_seen": _iso(now),
        }
        key = hash_session_id(session_id)

        def mutate(data):
            # Opportunistic hygiene: a login is a natural moment to drop rows that
            # expired while nobody was looking.
            sessions = data.setdefault("sessions", {})
            for stale in [k for k, row in sessions.items()
                          if not isinstance(row, dict) or self._expired(row)]:
                sessions.pop(stale, None)
            sessions[key] = dict(record)
            return record

        self._mutate(mutate)
        return session_id, dict(record)

    def revoke(self, session_id: str) -> bool:
        """Delete a session (logout = REAL revocation). ``True`` when one was removed."""
        if not session_id:
            return False
        key = hash_session_id(session_id)

        def mutate(data):
            return bool((data.get("sessions") or {}).pop(key, None))

        return bool(self._mutate(mutate))

    def prune(self) -> int:
        """Remove every expired session; returns how many went."""
        def mutate(data):
            sessions = data.get("sessions") or {}
            gone = [k for k, row in sessions.items()
                    if not isinstance(row, dict) or self._expired(row)]
            for k in gone:
                sessions.pop(k, None)
            return len(gone)

        return int(self._mutate(mutate))


def default_session_store(config=None) -> SessionStore:
    """The store the api uses, resolved from the ONE config (a test seam: the
    routes call this by name, so a test can point them at ``tmp_path``)."""
    return SessionStore(config=config)
