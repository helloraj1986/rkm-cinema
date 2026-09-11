"""Shared plumbing for the RKM operation/diagnostic tools.

Everything the tools need to know about WHERE the stack is runs through here, so a
tool behaves the same whether it is run from the Windows host (localhost) or from
the sandbox (host.docker.internal), without anyone having to remember a URL.

Also the single place that finds the repo root, so tools work no matter which
directory they are invoked from.
"""
from __future__ import annotations

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
