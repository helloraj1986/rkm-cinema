#!/usr/bin/env python3
"""RKM bundled-stack provisioner: configure Jellyfin headlessly for rkm-cinema.

Runs as a one-shot container (see ../docker-compose.yml service `provisioner`).
What it does, all idempotent:

  1. Wait for Jellyfin to be reachable.
  2. Ensure the admin user exists — either by authenticating with the configured
     creds, or by running Jellyfin's headless "Startup" wizard first-run (which
     creates the first admin user).
  3. Create / reuse an API key (`POST /Auth/Keys`) for RKM.
  4. Register the Movies + TV Shows libraries pointing at /data/media/_movie and
     /data/media/_tv (the single shared /data mount).
  5. Write /shared/runtime.json so the rkm `api` container can read the freshly
     created JELLYFIN_API_KEY (chicken-and-egg: it doesn't exist until here).

Expected env: JELLYFIN_URL, JELLYFIN_ADMIN_USER, JELLYFIN_ADMIN_PASSWORD,
JELLYFIN_BROWSER_URL, TZ. Stdout is verbose for troubleshooting.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid

JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://jellyfin:8096").rstrip("/")
ADMIN_USER = os.environ.get("JELLYFIN_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("JELLYFIN_ADMIN_PASSWORD", "")
BROWSER_URL = os.environ.get("JELLYFIN_BROWSER_URL", "http://localhost:8098")
RUNTIME_PATH = "/shared/runtime.json"


class ApiError(Exception):
    pass


def _request(method: str, path: str, *, token: str | None = None, body=None,
             q: dict | None = None, timeout: int = 15, append_query: dict | None = None):
    url = JELLYFIN_URL + path
    params = dict(q or {})
    if token:
        params["api_key"] = token
    url += ("?" + urllib.parse.urlencode(params)) if params else ""
    data = None
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        return e.code, {"error": detail}
    except Exception as e:  # network down / no route
        return 0, {"error": str(e)}


def wait_ready(retries: int = 60, delay: float = 2.0) -> None:
    print(f"[jellyfin] waiting for {JELLYFIN_URL} ...")
    for i in range(retries):
        code, _ = _request("GET", "/System/Info/Public", timeout=5)
        if code == 200:
            print("[jellyfin] reachable")
            return
        if i and i % 10 == 0:
            print(f"[jellyfin] not ready yet ({code}); retrying ...")
        time.sleep(delay)
    print("[jellyfin] ERROR: timed out waiting for Jellyfin to start.")
    sys.exit(1)


def startup_complete() -> bool:
    code, data = _request("GET", "/Startup/Configuration")
    if code == 200 and isinstance(data, dict):
        return bool(data.get("IsStartupWizardCompleted", False))
    return True  # if the endpoint is unhelpful, assume already configured


def run_startup() -> None:
    print("[jellyfin] first-run: running headless Startup wizard to create admin user")
    code, data = _request("GET", "/Startup/Configuration")
    print(f"[jellyfin] startup config: {code}")
    if code != 200:
        # Non-critical: some images boot with wizard already dismissed. Carry on.
        print("[jellyfin] (startup config unavailable; will try auth anyway)")
        return
    sha1 = hashlib.sha1(ADMIN_PASSWORD.encode()).hexdigest().lower()
    # POST /Startup/User creates the first admin. Both Password + PasswordSha1
    # are sent defensively (versions differ in which they require).
    code, _ = _request("POST", "/Startup/User", body={
        "Name": ADMIN_USER,
        "Password": ADMIN_PASSWORD,
        "PasswordSha1": sha1,
        "EnableAutoLogin": True,
    })
    print(f"[jellyfin] POST /Startup/User -> {code}")
    # Best-effort remote-access nudges; failures are non-fatal for local use.
    _request("POST", "/Startup/RemoteAccess", body={
        "EnableRemoteAccess": True, "EnableAutomaticPortMapping": False})
    _request("POST", "/Startup/Complete")
    # Startup sometimes needs a moment to persist the user.
    time.sleep(2.0)


def authenticate() -> str | None:
    """Authenticate as the admin; return an AccessToken or None."""
    code, data = _request("POST", "/Users/AuthenticateByName", body={
        "Username": ADMIN_USER, "Pw": ADMIN_PASSWORD})
    if code == 200 and isinstance(data, dict):
        return data.get("AccessToken")
    return None


def ensure_admin() -> str:
    token = authenticate()
    if token:
        print(f"[jellyfin] authenticated admin '{ADMIN_USER}'")
        return token
    if not startup_complete():
        run_startup()
        time.sleep(2.0)
        token = authenticate()
        if token:
            print(f"[jellyfin] admin created + authenticated '{ADMIN_USER}'")
            return token
    print("[jellyfin] ERROR: could not authenticate admin (wrong password? "
          "rkm.config.toml jellyfin_admin_password).")
    sys.exit(1)


def ensure_api_key(admin_token: str) -> str:
    # Reuse an existing RKM key if present.
    code, data = _request("GET", "/Auth/Keys", token=admin_token)
    if code == 200 and isinstance(data, dict):
        for it in (data.get("Items") or []):
            if str(it.get("App", "")) == "RKM Cinema":
                key = it.get("Key")
                if key:
                    print("[jellyfin] reusing existing RKM API key")
                    return str(key)
    api_key = uuid.uuid4().hex
    code, data = _request("POST", "/Auth/Keys", token=admin_token, body={
        "App": "RKM Cinema", "ApiKey": api_key})
    print(f"[jellyfin] created API key -> {code}")
    return api_key


def ensure_library(admin_token: str, name: str, ctype: str, path: str) -> None:
    # Do not duplicate folders; check existing virtual folders for the path.
    code, data = _request("GET", "/Library/VirtualFolders", token=admin_token)
    if code == 200 and isinstance(data, list):
        for vf in data:
            for p in (vf.get("Locations") or vf.get("Paths") or []):
                if p.rstrip("/") == path.rstrip("/"):
                    print(f"[jellyfin] library '{name}' already has {path} — skipping")
                    return
    # Modern form: JSON body with PathInfos; query carries name + collectionType.
    body = {
        "LibraryOptions": {"SaveLocalMetadata": False, "EnableInternetProviders": True},
        "PathInfos": [{"Path": path}],
        "RefreshLibrary": False,
    }
    q = {"name": name, "collectionType": ctype, "refreshLibrary": "false"}
    code, _ = _request("POST", "/Library/VirtualFolders", token=admin_token,
                       body=body, q=q)
    print(f"[jellyfin] add library '{name}' ({ctype} -> {path}) -> {code}")
    if code not in (200, 204):
        # Fallback: the older `paths=` query form.
        q2 = {"name": name, "collectionType": ctype, "paths": path}
        code2, _ = _request("POST", "/Library/VirtualFolders", token=admin_token, q=q2)
        print(f"[jellyfin]   retry (paths=) -> {code2}")


def main() -> None:
    if not ADMIN_PASSWORD:
        print("ERROR: JELLYFIN_ADMIN_PASSWORD not set (edit rkm.config.toml jellyfin_admin_password).")
        sys.exit(1)
    wait_ready()

    admin_token = ensure_admin()
    api_key = ensure_api_key(admin_token)
    ensure_library(admin_token, "Movies", "movies", "/data/media/_movie")
    ensure_library(admin_token, "TV Shows", "tvshows", "/data/media/_tv")

    server_id = ""
    code, data = _request("GET", "/System/Info/Public")
    if code == 200 and isinstance(data, dict):
        server_id = str(data.get("Id", ""))

    runtime = {
        "JELLYFIN_URL": JELLYFIN_URL,
        "JELLYFIN_API_KEY": api_key,
        "JELLYFIN_SERVER_ID": server_id,
        "JELLYFIN_BROWSER_URL": BROWSER_URL,
        "MEDIA_SERVER": "jellyfin",
    }
    with open(RUNTIME_PATH, "w", encoding="utf-8") as f:
        json.dump(runtime, f, indent=2)
    print(f"[rkm] wrote runtime config -> {RUNTIME_PATH}")
    print(runtime)
    print("[rkm] provisioner DONE (restart the api container to pick up the API key)")


if __name__ == "__main__":
    main()