"""Shared plumbing for the RKM operation/diagnostic tools.

Everything the tools need to know about WHERE the stack is runs through here, so a
tool behaves the same whether it is run from the Windows host (localhost) or from
the sandbox (host.docker.internal), without anyone having to remember a URL.

Also the single place that finds the repo root, so tools work no matter which
directory they are invoked from.
"""
from __future__ import annotations

import http.cookiejar
import json
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

#: The SHARED .env parser lives with the app config (repo ``backend/config/``) so
#: the tools, the renderer and the api read one file the same way — including BOM
#: tolerance (see config/env_file.py). Imported by path because tools/ is not a
#: package and this module is imported by scripts run from anywhere.
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
from config.env_file import parse_env_file  # noqa: E402

#: Ports used by the bundled stack (overridable in .env).
DEFAULT_DASHBOARD_PORT = "8124"
DEFAULT_JELLYFIN_PORT = "8098"


def repo_root(start: Path | None = None) -> Path:
    """The repo containing docker-compose.yml (walk up from this file)."""
    here = (start or Path(__file__).resolve()).parent
    for candidate in (here, *here.parents):
        if (candidate / "docker-compose.yml").exists():
            return candidate
    return here


def load_env(root: Path | None = None) -> dict:
    """Parse the repo .env through the SHARED parser (``config/env_file.py``).

    One reading for every reader: values keep everything before an unquoted `` #``
    comment (matching Docker Compose and ``render_config``), a quoted value is taken
    verbatim, an ``export`` prefix is not part of the name, and a leading BOM is
    stripped rather than silently renaming the first key. This tool-side copy used to
    be a fourth implementation of those rules.
    """
    path = (root or repo_root()) / ".env"
    return parse_env_file(path)


def _reachable(host: str, port: str, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def pick_host(port: str) -> str:
    """``host.docker.internal`` when it answers, else ``localhost``.

    The sandbox reaches the stack through Docker's host alias; on the Windows host
    that name usually does not resolve and localhost is correct. Probing beats
    guessing, and it means one command works in both places.
    """
    if _reachable("host.docker.internal", port):
        return "host.docker.internal"
    return "localhost"


def jellyfin_base(env: dict | None = None, explicit: str | None = None) -> str:
    """Base URL of the bundled Jellyfin, reachable from here."""
    if explicit:
        return explicit.rstrip("/")
    env = env if env is not None else load_env()
    port = str(env.get("RKM_JELLYFIN_PORT") or DEFAULT_JELLYFIN_PORT)
    return f"http://{pick_host(port)}:{port}"


def app_base(env: dict | None = None, explicit: str | None = None) -> str:
    """Base URL of the RKM dashboard/api."""
    if explicit:
        return explicit.rstrip("/")
    env = env if env is not None else load_env()
    port = str(env.get("RKM_DASHBOARD_PORT") or DEFAULT_DASHBOARD_PORT)
    return f"http://{pick_host(port)}:{port}"


def http_json(url: str, *, token: str | None = None, data=None, method=None,
              headers=None, timeout: float = 30.0, raw: bool = False):
    """GET/POST a URL, returning parsed JSON (or text with ``raw=True``).

    Errors come back as ``{"__error__": ...}`` / ``{"__http_error__": ...}`` rather
    than raising, so a caller can report a partial picture instead of crashing.
    """
    h = dict(headers or {})
    if token:
        h["X-Emby-Token"] = token
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
    try:
        req = urllib.request.Request(url, data=body, headers=h, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", "replace")
            return payload if raw else json.loads(payload or "null")
    except urllib.error.HTTPError as e:
        return {"__http_error__": e.code,
                "body": e.read()[:300].decode("utf-8", "replace")}
    except Exception as e:
        return {"__error__": str(e)}


class App:
    """Client for the app's OWN api, holding a real session — for tools that are not a browser.

    **Why this exists.** With ``RKM_AUTH_REQUIRED=false`` a caller with no cookie was served as the
    stack's own credential, so a tool could simply fetch ``/api/library/...`` and get an answer.
    Arming the flag (his opt-in, 2026-09-13 work) makes all 36 session routes answer **401 to a
    caller with no session** — including every tool in this directory. The rule that comes with it:
    **only the browser has a session for free.** Anything else that speaks HTTP to the app signs in
    first.

    ⚠ **Sign in on the TOOLS' own device id, never the app's.** ``services/auth.py::CLIENT_HEADER``
    is the device the web app uses, and Jellyfin invalidates the previous token of a *(device, user)*
    pair on every login. A tool authenticating on that pair would rotate the browser's token away and
    leave the running session answering 401 on every media call — the §6h symptom, caused by running a
    diagnostic. Hence ``device_id="rkm-tools"``.

    ⚠ **Only an ADMINISTRATOR may sign in** (``api/routes/auth.py::login`` — everyone else reaches the
    app by picking a profile inside a session). So this needs the administrator's own credentials,
    read from ``.env`` exactly as :class:`Jellyfin` does. Never the literal name ``admin``: the account
    was renamed (plan §5) and a hard-coded name signs in as nobody.

    Failure is REPORTED, never guessed at: ``self.error`` says whether the credentials were refused,
    the account is not an administrator, the media server was unreachable, or no credentials are
    configured — because "the api refused this" and "the library is empty" are different answers and
    conflating them is the fault this repo keeps having to fix.
    """

    #: The device id tools sign in on. Must match ``services/auth.py::TOOLS_DEVICE_ID``.
    DEVICE_ID = "rkm-tools"

    def __init__(self, base: str | None = None, env: dict | None = None,
                 device_id: str = DEVICE_ID, sign_in: bool = True):
        self.env = env if env is not None else load_env()
        self.base = (base or app_base(self.env)).rstrip("/")
        self.device_id = device_id
        self.error = ""
        self.signed_in = False
        #: A cookie jar IS the session: the api issues an opaque id in a Set-Cookie and reads it back.
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        if sign_in:
            self.sign_in()

    # -- session ---------------------------------------------------------------
    @property
    def cookie(self) -> str | None:
        pairs = [f"{c.name}={c.value}" for c in self.jar]
        return "; ".join(pairs) if pairs else None

    def sign_in(self) -> bool:
        """Sign in as the administrator. Returns False and fills ``self.error`` when it cannot."""
        user = str(self.env.get("RKM_JELLYFIN_ADMIN_USER") or "").strip()
        password = str(self.env.get("RKM_JELLYFIN_ADMIN_PASSWORD") or "")
        if not user or not password:
            self.error = (
                "no administrator credentials in .env — set RKM_JELLYFIN_ADMIN_USER and "
                "RKM_JELLYFIN_ADMIN_PASSWORD. Only an administrator can sign in to this app, so a "
                "tool cannot borrow the app's own credential for HTTP calls.")
            return False
        result = self.post("/api/auth/login",
                           {"username": user, "password": password, "device_id": self.device_id})
        if isinstance(result, dict) and result.get("__http_error__"):
            self.error = self._sign_in_refusal(int(result["__http_error__"]))
            return False
        if isinstance(result, dict) and result.get("__error__"):
            self.error = f"could not reach the app at {self.base}: {result['__error__']}"
            return False
        if not self.cookie:
            # A 200 without a cookie is NOT a session. Saying so beats every later call reading 401.
            self.error = "the app answered the sign-in without a session cookie (is this the api?)"
            return False
        self.signed_in = True
        return True

    @staticmethod
    def _sign_in_refusal(status: int) -> str:
        """The app's refusal, named. Never echoes the username or the password."""
        return {
            401: "the app refused those credentials (wrong administrator password?)",
            403: "that account is not a media-server ADMINISTRATOR — only an administrator may sign in",
            503: "the app could not reach the media server to verify the account",
        }.get(status, f"the sign-in failed with HTTP {status}")

    def sign_out(self) -> bool:
        """Revoke this tool's session. Optional — it also dies at its 30-day TTL."""
        result = self.post("/api/auth/logout", {})
        revoked = isinstance(result, dict) and bool(result.get("revoked"))
        self.jar.clear()
        self.signed_in = False
        return revoked

    # -- requests --------------------------------------------------------------
    def request(self, path: str, *, data=None, method=None, timeout: float = 30.0, headers=None):
        """One request through the cookie jar, shaped exactly like :func:`http_json`."""
        h = {"Content-Type": "application/json"} if data is not None else {}
        h.update(headers or {})
        body = None
        if data is not None:
            body = data if isinstance(data, bytes) else json.dumps(data).encode()
        try:
            req = urllib.request.Request(self.base + path, data=body, headers=h, method=method)
            with self.opener.open(req, timeout=timeout) as resp:
                payload = resp.read().decode("utf-8", "replace")
                self.last_status = resp.status
                return json.loads(payload or "null")
        except urllib.error.HTTPError as e:
            self.last_status = e.code
            return {"__http_error__": e.code,
                    "body": e.read()[:300].decode("utf-8", "replace")}
        except Exception as e:
            self.last_status = 0
            return {"__error__": str(e)}

    def get(self, path: str, **kw):
        return self.request(path, method="GET", **kw)

    def post(self, path: str, data=None, **kw):
        return self.request(path, data={} if data is None else data, method="POST", **kw)


def app_client(base: str | None = None, env: dict | None = None, **kw) -> App:
    """A signed-in :class:`App`, or one whose ``error`` says why not.

    Callers should check ``client.signed_in`` before reporting anything about the app — an unsigned
    client's answers are 401s, and reporting those as "no items" is the confusion this class exists
    to end.
    """
    return App(base=base, env=env, **kw)


class Jellyfin:
    """Minimal read-mostly Jellyfin client for the tools."""

    def __init__(self, base: str | None = None, env: dict | None = None):
        self.env = env if env is not None else load_env()
        self.base = (base or jellyfin_base(self.env)).rstrip("/")
        self.token = self._login()

    def _login(self) -> str | None:
        hdr = ('MediaBrowser Client="rkm-tools", Device="tools", '
               'DeviceId="rkm-tools-1", Version="1.0.0"')
        res = http_json(f"{self.base}/Users/AuthenticateByName",
                        data={"Username": self.env.get("RKM_JELLYFIN_ADMIN_USER") or "admin",
                              "Pw": self.env.get("RKM_JELLYFIN_ADMIN_PASSWORD") or ""},
                        headers={"Content-Type": "application/json", "X-Emby-Authorization": hdr},
                        method="POST")
        return res.get("AccessToken") if isinstance(res, dict) else None

    def get(self, path: str, **kw):
        return http_json(self.base + path, token=self.token, **kw)

    def libraries(self) -> list:
        res = self.get("/Library/VirtualFolders")
        return res if isinstance(res, list) else []

    def count(self, parent_id: str, kinds: str) -> int:
        res = self.get(f"/Items?ParentId={parent_id}&Recursive=true&IncludeItemTypes={kinds}"
                       f"&Limit=0&EnableTotalRecordCount=true")
        return res.get("TotalRecordCount", -1) if isinstance(res, dict) else -1

    def scan_task(self) -> dict:
        tasks = self.get("/ScheduledTasks")
        if not isinstance(tasks, list):
            return {}
        return next((t for t in tasks if (t.get("Name") or "") == "Scan Media Library"), {})
