"""OpenSubtitles.com REST API v1 client (SUBTITLES_OPENSUBTITLES_PLAN §3.2).

Deliberately ISOLATED: no Jellyfin imports, no app state, no knowledge of the
player. It turns a media identity into subtitle bytes and a quota figure — nothing
else. Architecture decision A (user-confirmed 2026-09-12): the api owns this client
so the credentials stay server-side in `.env`; no Jellyfin plugin is installed.

Measured API facts this encodes (2026-09-12, opensubtitles.stoplight.io + the
vendor's own help centre):

* ``Api-Key`` is MANDATORY on every call — it identifies the APPLICATION (one key per
  app) and a missing one is a 4xx, not a silent anonymous mode. A descriptive
  ``User-Agent`` is required too.
* ``POST /login {username,password}`` → a JWT. ``/download`` and ``/infos/user`` need
  it; **searching does not**, so key-only (anonymous) is a real, supported mode.
* ``GET /subtitles?…`` is NOT metered. Only downloads are.
* ``POST /download {file_id}`` → ``{link, file_name, remaining, reset_time_utc}``, then
  GET that link for the bytes.

QUOTA — never hardcode a number. It varies by account rank (anonymous 5/24h per IP;
a free account reports its own figure; VIP is far higher), so ``async`` callers read
``allowed_downloads``/``remaining_downloads`` from ``/infos/user`` and ``remaining``
from every ``/download`` response. Counters reset at midnight UTC (= 10:00 AEST).

Two transport rules worth stating, because both are about not wasting the user's
daily allowance:

* Only **GETs** are retried once on a network error. A ``/download`` POST is never
  retried: the request may already have spent a download, and a blind retry would
  charge the user twice for one subtitle.
* The download ``link`` embeds a token in its query string. It is fetched WITHOUT the
  ``Api-Key``, is never returned to a client, and never appears in a log line — see
  :func:`safe_url`.
"""
from __future__ import annotations

import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config.settings import get_config
from core.exceptions import RKMError

logger = logging.getLogger("rkm.opensubtitles")


# ------------------------------------------------------------------- errors
#: The error taxonomy lives WITH the client (plan §3.2): these are only ever raised
#: around a subtitle call, and keeping them here means no other layer can accidentally
#: catch a generic "transport" error that means something else. ``RKMError`` is the
#: repo-wide base, so an app-level handler still sees them as app errors.
class OpenSubtitlesError(RKMError):
    """Base for every OpenSubtitles failure. Never leaks a stack trace to a client."""


class NotConfiguredError(OpenSubtitlesError):
    """No API key (or no login where a login is genuinely required)."""


class AuthFailedError(OpenSubtitlesError):
    """The API rejected the key or the account login (401/403)."""


class QuotaExhaustedError(OpenSubtitlesError):
    """The daily download allowance is spent — wait for the midnight-UTC reset."""


class RateLimitedError(OpenSubtitlesError):
    """Too many requests in a short window (429 without a quota message)."""

    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class NoResultsError(OpenSubtitlesError):
    """A specific lookup resolved to nothing (dead file id, or no results asked for)."""


class UnsupportedFormatError(OpenSubtitlesError):
    """The file is not a text subtitle this player can render (bitmap/archive)."""


class TransportError(OpenSubtitlesError):
    """Network-level failure, or an upstream 5xx. The only retryable condition."""

#: Sent on every call — the vendor rejects a missing/blank UA. Mirrors the app
#: version declared on the FastAPI app.
USER_AGENT = "RKM Cinema v2.0"

#: Subtitle formats the player can actually render (the app proxies them as VTT).
TEXT_FORMATS = ("srt", "vtt", "ass", "ssa")

#: Formats that are NOT usable here: bitmap subtitles need OCR, and an archive needs
#: unpacking. Rejected with a clear message rather than attached and unplayable.
UNSUPPORTED_FORMATS = ("sub", "idx", "zip", "rar", "7z")

#: A JWT lasts 24h upstream; re-login happens on 401 anyway, so cache shorter.
TOKEN_TTL_SECONDS = 12 * 3600

#: Socket timeout for JSON calls (connect + read share it — urllib exposes one).
DEFAULT_TIMEOUT = 15.0

#: Downloads are larger; give the read a little longer.
DOWNLOAD_TIMEOUT = 60.0


# --------------------------------------------------------------------- results
@dataclass(frozen=True)
class SubtitleResult:
    """One candidate subtitle, normalised to what this app stores and shows.

    ``subtitle_id`` is the IDENTITY we persist (``os:<file_id>``): Jellyfin stream
    indices are POSITIONAL and change whenever a track is added or removed — which
    our own download does — so the index is resolved at playback time from this
    identity, never stored (plan §3.6).
    """

    file_id: int
    language: str
    display_title: str
    provider: str = "opensubtitles"
    download_count: int = 0
    hearing_impaired: bool = False
    format: str = ""
    feature_title: str = ""
    year: Optional[int] = None

    @property
    def subtitle_id(self) -> str:
        return f"os:{self.file_id}"

    def to_dict(self) -> dict:
        """The wire shape the API hands the frontend (no tokens, ever)."""
        return {
            "subtitle_id": self.subtitle_id,
            "file_id": self.file_id,
            "language": self.language,
            "display_title": self.display_title,
            "provider": self.provider,
            "download_count": self.download_count,
            "hearing_impaired": self.hearing_impaired,
            "format": self.format,
            "feature_title": self.feature_title,
            "year": self.year,
        }


@dataclass(frozen=True)
class DownloadedSubtitle:
    """Subtitle bytes plus the quota facts the API reported with them."""

    file_id: int
    file_name: str
    content: bytes
    remaining: Optional[int] = None
    reset_time_utc: Optional[str] = None

    @property
    def extension(self) -> str:
        return (self.file_name.rsplit(".", 1)[-1] if "." in self.file_name else "").lower()


@dataclass(frozen=True)
class QuotaInfo:
    """Downloads allowed/remaining as the ACCOUNT reports them (rank-dependent)."""

    allowed: Optional[int] = None
    remaining: Optional[int] = None
    level: str = ""

    @property
    def exhausted(self) -> bool:
        return self.remaining == 0


# ------------------------------------------------------------------ transport
@dataclass
class TransportResponse:
    """A raw HTTP response: the client maps status codes, the transport does not."""

    status: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> Any:
        if not self.body:
            return {}
        try:
            return json.loads(self.body.decode("utf-8", "replace"))
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise TransportError(f"invalid JSON in response: {exc}") from exc


class UrllibTransport:
    """The real transport (stdlib only — no new dependency).

    4xx/5xx are RETURNED, not raised: mapping them to the app's error taxonomy is the
    client's job. Only network-level failures (DNS, refused, timeout) raise
    :class:`TransportError`, which is the one condition worth a single retry.
    """

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    def request(self, method: str, url: str, *, headers: Optional[Dict[str, str]] = None,
                params: Optional[Dict[str, Any]] = None, json_body: Optional[dict] = None,
                timeout: Optional[float] = None) -> TransportResponse:
        if params:
            clean = {k: v for k, v in params.items() if v not in (None, "")}
            if clean:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{urllib.parse.urlencode(clean)}"
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        hdrs = dict(headers or {})
        if data is not None:
            hdrs.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return TransportResponse(status=resp.status,
                                         headers={k.lower(): v for k, v in resp.headers.items()},
                                         body=resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read() if exc.fp else b""
            return TransportResponse(status=exc.code,
                                     headers={k.lower(): v for k, v in (exc.headers or {}).items()},
                                     body=body)
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise TransportError(f"network error contacting {safe_url(url)}: {reason}") from exc


def safe_url(url: str) -> str:
    """A URL with its query string removed — for logs.

    The download ``link`` carries a token in the query string (and the JWT travels in
    a header, never a URL), so logging a full URL is a credential leak. Use this
    everywhere a URL would otherwise be printed.
    """
    return (url or "").split("?", 1)[0]


def _imdb_digits(imdb_id: Optional[str]) -> Optional[int]:
    """``tt0133093`` → ``133093`` (the API takes the numeric id)."""
    if not imdb_id:
        return None
    digits = "".join(ch for ch in str(imdb_id) if ch.isdigit())
    return int(digits) if digits else None


def format_supported(file_name: str) -> bool:
    """True when the file is a subtitle the player can render (text-based)."""
    ext = (file_name or "").rsplit(".", 1)[-1].lower() if "." in (file_name or "") else ""
    return ext in TEXT_FORMATS


# ---------------------------------------------------------------------- client
class OpenSubtitlesClient:
    """Search + download OpenSubtitles files for one media item.

    Injected collaborators keep the unit tests offline and deterministic:

    * ``config``    — anything exposing ``OPENSUBTITLES_*`` (see ``config.settings``);
    * ``transport`` — an object with ``request(method, url, headers=, params=,
      json_body=, timeout=) -> TransportResponse`` (tests pass a fake).
    """

    BASE_URL = "https://api.opensubtitles.com/api/v1"
    #: Where the API reports the user's own quota.
    USER_INFO_PATH = "/infos/user"
    LOGIN_PATH = "/login"
    SEARCH_PATH = "/subtitles"
    DOWNLOAD_PATH = "/download"

    def __init__(self, *, config=None, transport=None, clock=time.monotonic):
        self.config = config if config is not None else get_config()
        self.transport = transport if transport is not None else UrllibTransport()
        self._clock = clock
        self._token: Optional[str] = None
        self._token_at: float = 0.0
        #: Last quota facts the API volunteered (a `/download` response carries them
        #: even without a login, which `/infos/user` requires).
        self._last_remaining: Optional[int] = None
        self._last_reset: Optional[str] = None

    # ------------------------------------------------------------ configuration
    @property
    def api_key(self) -> str:
        return str(getattr(self.config, "OPENSUBTITLES_API_KEY", "") or "").strip()

    def is_configured(self) -> bool:
        """True when this client can make a call at all (the API key is mandatory)."""
        if hasattr(self.config, "has_opensubtitles"):
            return bool(self.config.has_opensubtitles())
        return bool(self.api_key)

    @property
    def has_login(self) -> bool:
        """True when a username + password are present (raises the quota tier)."""
        if hasattr(self.config, "has_opensubtitles_login"):
            return bool(self.config.has_opensubtitles_login())
        return bool(getattr(self.config, "OPENSUBTITLES_USERNAME", None)
                    and getattr(self.config, "OPENSUBTITLES_PASSWORD", None))

    def languages(self) -> List[str]:
        if hasattr(self.config, "opensubtitles_languages"):
            return list(self.config.opensubtitles_languages())
        return ["en"]

    def _require_configured(self) -> None:
        if not self.is_configured():
            raise NotConfiguredError(
                "OpenSubtitles is not configured — set OPENSUBTITLES_API_KEY in .env")

    def _headers(self, *, with_token: bool = False, download: bool = False) -> Dict[str, str]:
        """Request headers. The KEY goes to the API only — never to a download link."""
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if not download:
            headers["Api-Key"] = self.api_key
        if with_token and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    # --------------------------------------------------------------- low level
    def _request(self, method: str, path_or_url: str, *, params=None, json_body=None,
                 with_token: bool = False, timeout: Optional[float] = None,
                 retry: bool = True) -> TransportResponse:
        """One call, mapped to the typed error taxonomy.

        ``retry`` is reserved for idempotent GETs — see the module docstring: a
        download POST must never be re-sent, because it may already have been charged.
        """
        self._require_configured()
        url = path_or_url if path_or_url.startswith("http") else f"{self.BASE_URL}{path_or_url}"
        attempts = 2 if (retry and method.upper() == "GET") else 1
        last: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                resp = self.transport.request(
                    method.upper(), url, headers=self._headers(with_token=with_token),
                    params=params, json_body=json_body,
                    timeout=timeout or DEFAULT_TIMEOUT)
                # Mapping happens INSIDE the loop so a 5xx is retried with the same
                # budget as a network error — 5xx is the other transient condition.
                return self._map_errors(resp, url)
            except TransportError as exc:
                last = exc
                if attempt < attempts:
                    logger.warning("OpenSubtitles retry %d/%d for %s (%s)",
                                   attempt, attempts, safe_url(url), exc)
                    continue
                raise
        raise last if last else TransportError("request failed")  # pragma: no cover

    def _map_errors(self, resp: TransportResponse, url: str) -> TransportResponse:
        """Translate an HTTP status into the app's typed errors (never a raw stack)."""
        status = resp.status
        if 200 <= status < 300:
            return resp
        body_text = (resp.body or b"").decode("utf-8", "replace")
        detail = _api_message(body_text)
        if status in (401, 403):
            raise AuthFailedError(
                f"OpenSubtitles rejected the credentials ({status})"
                + (f": {detail}" if detail else "")
                + (" — check OPENSUBTITLES_API_KEY"
                   + (" / the account login" if self.has_login else ""))
            )
        if status == 429:
            retry_after = _retry_after(resp)
            if _looks_like_quota(detail) or self._last_remaining == 0:
                raise QuotaExhaustedError(
                    "OpenSubtitles daily download limit reached"
                    + (f": {detail}" if detail else "")
                    + (f" — resets {self._last_reset}" if self._last_reset else ""))
            raise RateLimitedError(
                "OpenSubtitles rate limit hit" + (f": {detail}" if detail else ""),
                retry_after=retry_after)
        if status == 406 or "no results" in detail.lower():
            raise NoResultsError(f"OpenSubtitles returned no result: {detail or status}")
        if status >= 500:
            raise TransportError(f"OpenSubtitles server error {status} at {safe_url(url)}")
        raise OpenSubtitlesError(f"OpenSubtitles request failed ({status}): {detail or 'unknown'}")

    # ------------------------------------------------------------------- login
    def login(self, *, force: bool = False) -> str:
        """Return a cached JWT, logging in when needed.

        Only required for ``/download`` and ``/infos/user``; the anonymous tier works
        without it. Raises :class:`NotConfiguredError` when no account is set — callers
        that can work anonymously check :attr:`has_login` first.
        """
        self._require_configured()
        if not self.has_login:
            raise NotConfiguredError(
                "OpenSubtitles login not configured — set OPENSUBTITLES_USERNAME and "
                "OPENSUBTITLES_PASSWORD (or keep working anonymously)")
        if not force and self._token and (self._clock() - self._token_at) < TOKEN_TTL_SECONDS:
            return self._token
        resp = self.transport.request(
            "POST", f"{self.BASE_URL}{self.LOGIN_PATH}",
            headers=self._headers(),
            json_body={"username": self.config.OPENSUBTITLES_USERNAME,
                       "password": self.config.OPENSUBTITLES_PASSWORD},
            timeout=DEFAULT_TIMEOUT)
        if resp.status in (401, 403):
            # Never echo the credentials or the response body (it can carry the token).
            raise AuthFailedError(
                "OpenSubtitles login rejected — check OPENSUBTITLES_USERNAME / "
                "OPENSUBTITLES_PASSWORD in .env")
        self._map_errors(resp, f"{self.BASE_URL}{self.LOGIN_PATH}")
        token = str((resp.json() or {}).get("token") or "")
        if not token:
            raise AuthFailedError("OpenSubtitles login returned no token")
        self._token = token
        self._token_at = self._clock()
        logger.info("OpenSubtitles login ok")
        return token

    def _with_auth_retry(self, call):
        """Run *call*; on an auth failure, re-login once and try again.

        A JWT can expire (or be revoked) between calls; the plan's rule is a single
        re-login, then fail fast rather than loop.
        """
        try:
            return call()
        except AuthFailedError:
            if not self.has_login:
                raise
            logger.info("OpenSubtitles token expired — re-logging in once")
            self.login(force=True)
            return call()

    def _ensure_login(self) -> None:
        """Log in once, lazily, when an account is configured and a JWT is needed.

        Done BEFORE the call rather than waiting for a 401: the login is cached and
        unmetered, whereas a bare 401 round-trip on ``/download`` is a wasted request
        that could also be mistaken for a quota problem.
        """
        if self.has_login and not self._token:
            self.login()

    # ------------------------------------------------------------------ search
    def search(self, *, tmdb_id=None, imdb_id: Optional[str] = None, title: Optional[str] = None,
               year: Optional[int] = None, season: Optional[int] = None,
               episode: Optional[int] = None, languages: Optional[List[str]] = None,
               limit: int = 30) -> List[SubtitleResult]:
        """Search for subtitles, keyed by the STRONGEST id available (§3.2).

        Priority: ``tmdb_id`` → ``imdb_id`` → ``title`` (+``year``, and
        ``season``/``episode`` for an episode). An empty list is a legitimate answer —
        "nothing found" is not an error at this layer; the caller merges it with the
        item's local tracks.
        """
        self._require_configured()
        langs = languages or self.languages()
        params: Dict[str, Any] = {"languages": ",".join(langs) if langs else "en"}
        if tmdb_id:
            params["tmdb_id"] = tmdb_id
        elif _imdb_digits(imdb_id):
            params["imdb_id"] = _imdb_digits(imdb_id)
        elif title:
            params["query"] = title
            if year:
                params["year"] = year
            if season is not None:
                params["season_number"] = season
            if episode is not None:
                params["episode_number"] = episode
        else:
            raise OpenSubtitlesError("search needs a tmdb_id, an imdb_id or a title")

        resp = self._request("GET", self.SEARCH_PATH, params=params)
        rows = ((resp.json() or {}).get("data") or [])
        results = [r for r in (_normalise_row(row) for row in rows) if r is not None]
        logger.info("OpenSubtitles search (%s) → %d result(s)",
                    params.get("tmdb_id") or params.get("imdb_id") or "title", len(results))
        return results[:limit]

    # ---------------------------------------------------------------- download
    def download(self, file_id: int, *, sub_format: Optional[str] = None) -> DownloadedSubtitle:
        """Fetch one subtitle's BYTES and the quota facts reported with it.

        Never retried (a retry could spend a second download), and the credential is
        deliberately NOT sent to the returned link — that URL is pre-signed and a CDN
        has no business seeing the API key.
        """
        self._require_configured()
        self._ensure_login()
        body: Dict[str, Any] = {"file_id": int(file_id)}
        if sub_format:
            body["sub_format"] = sub_format

        def _call():
            return self._request("POST", self.DOWNLOAD_PATH, json_body=body,
                                 with_token=self.has_login, retry=False)

        resp = self._with_auth_retry(_call) if self.has_login else _call()
        payload = resp.json() or {}
        link = str(payload.get("link") or "")
        file_name = str(payload.get("file_name") or f"{file_id}.srt")
        remaining = payload.get("remaining")
        self._last_remaining = int(remaining) if isinstance(remaining, int) else self._last_remaining
        self._last_reset = payload.get("reset_time_utc") or payload.get("reset_time") or self._last_reset
        if not link:
            raise NoResultsError(
                f"OpenSubtitles returned no download link for file {file_id} "
                "(the subtitle may have been removed)")

        if not format_supported(file_name):
            raise UnsupportedFormatError(
                f"{file_name} is not a text subtitle the player can render "
                f"(supported: {', '.join(TEXT_FORMATS)})")

        raw = self.transport.request("GET", link, headers=self._headers(download=True),
                                     timeout=DOWNLOAD_TIMEOUT)
        if raw.status in (401, 403, 404, 410):
            raise NoResultsError(f"OpenSubtitles download link is no longer valid ({raw.status})")
        self._map_errors(raw, "download link")
        if not raw.body:
            raise NoResultsError("OpenSubtitles returned an empty subtitle file")
        logger.info("OpenSubtitles downloaded %s (%d bytes%s)", file_name, len(raw.body),
                    f", {self._last_remaining} downloads left today"
                    if self._last_remaining is not None else "")
        return DownloadedSubtitle(file_id=int(file_id), file_name=file_name,
                                 content=raw.body, remaining=self._last_remaining,
                                 reset_time_utc=self._last_reset)

    # ------------------------------------------------------------------- quota
    def user_info(self) -> Optional[QuotaInfo]:
        """The account's own quota (needs a login; ``None`` when anonymous or on error).

        Read at RUNTIME on purpose: the daily allowance depends on the account's rank
        and changes over time, so a hardcoded number would be a lie in the UI.
        """
        if not self.is_configured() or not self.has_login:
            return None
        try:
            self._ensure_login()
            resp = self._with_auth_retry(
                lambda: self._request("GET", self.USER_INFO_PATH, with_token=True))
        except OpenSubtitlesError as exc:
            logger.info("OpenSubtitles user_info unavailable: %s", exc)
            return None
        data = (resp.json() or {}).get("data") or resp.json() or {}
        info = QuotaInfo(
            allowed=_as_int(data.get("allowed_downloads")),
            remaining=_as_int(data.get("remaining_downloads")),
            level=str(data.get("level") or ""),
        )
        if info.remaining is not None:
            self._last_remaining = info.remaining
        return info

    def last_quota(self) -> Optional[int]:
        """Downloads left today as last reported by the API (``None`` = not yet known).

        This is what an anonymous (key-only) setup has: ``/infos/user`` needs a JWT, but
        every ``/download`` response still carries ``remaining``.
        """
        return self._last_remaining


# ------------------------------------------------------------------- helpers
def _normalise_row(row: Any) -> Optional[SubtitleResult]:
    """Map one API row to :class:`SubtitleResult`; ``None`` for a row we cannot use."""
    attrs = (row or {}).get("attributes") or {}
    files = attrs.get("files") or []
    file_id = None
    file_name = ""
    for f in files:
        file_id = f.get("file_id") or file_id
        file_name = f.get("file_name") or file_name
        if file_id:
            break
    if file_id is None:
        return None
    feature = attrs.get("feature_details") or {}
    release = str(attrs.get("release") or file_name or f"file {file_id}")
    fmt = str(attrs.get("format") or (file_name.rsplit(".", 1)[-1] if "." in file_name else ""))
    return SubtitleResult(
        file_id=int(file_id),
        language=str(attrs.get("language") or ""),
        display_title=release,
        download_count=_as_int(attrs.get("download_count")) or 0,
        hearing_impaired=bool(attrs.get("hearing_impaired")),
        format=fmt.lower(),
        feature_title=str(feature.get("title") or ""),
        year=_as_int(feature.get("year")),
    )


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _retry_after(resp: TransportResponse) -> Optional[int]:
    value = resp.headers.get("retry-after")
    return _as_int(value)


def _api_message(body_text: str) -> str:
    """A short, safe message from an error body.

    Sanitised: an error payload is never dumped verbatim (it can echo request fields),
    and only the first line/short form is kept.
    """
    if not body_text:
        return ""
    try:
        data = json.loads(body_text)
    except json.JSONDecodeError:
        return " ".join(body_text.split())[:160]
    if isinstance(data, dict):
        for key in ("message", "error", "detail"):
            if isinstance(data.get(key), str):
                return data[key][:160]
    return " ".join(body_text.split())[:160]


def _looks_like_quota(message: str) -> bool:
    """Distinguish 'you've used your daily allowance' from a generic rate limit.

    Both arrive as 429 and the user-facing advice differs completely (wait for the
    midnight-UTC reset vs slow down), so the body is inspected rather than assumed.
    """
    text = (message or "").lower()
    return any(token in text for token in ("quota", "download limit", "allowed_downloads",
                                           "remaining_downloads", "exceeded the limit"))


# ------------------------------------------------------------------ factory
def build_opensubtitles_client(config=None) -> OpenSubtitlesClient:
    """The one place a client is constructed (mirrors the repo's other services)."""
    return OpenSubtitlesClient(config=config)
