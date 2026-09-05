#!/usr/bin/env python3
"""RKM bundled-stack provisioner: configure Jellyfin headlessly for rkm-cinema.

Runs as a one-shot container (see ../docker-compose.yml service `provisioner`).
Idempotent. Steps (validated against jellyfin/jellyfin:latest 10.11.x):

  1. Wait for Jellyfin (System/Info/Public → 200).
  2. Read StartupWizardCompleted from System/Info/Public (NOT from
     Startup/Configuration, whose body has no such flag).
  3. Try to authenticate the configured admin. If it works → already set up.
  4. Else, if the wizard is pending, run the headless Startup sequence:
       GET  /Startup/Configuration        # arm the startup session
       GET  /Startup/User                 # arm user creation (required on 10.11)
       POST /Startup/User {Name, Password: SHA1-HEX}   # Password IS the SHA1, not plaintext
       POST /Startup/Complete
     then re-authenticate.
  5. Create / reuse an RKM API key (POST /Auth/Keys).
  6. Register Movies + TV Shows libraries at /data/media/_movie, /data/media/_tv.
  7. Write /shared/runtime.json so the rkm `api` container can read the key
     (chicken-and-egg: it doesn't exist until here).

Env: JELLYFIN_URL, JELLYFIN_ADMIN_USER, JELLYFIN_ADMIN_PASSWORD,
JELLYFIN_BROWSER_URL, TZ. Verbose stdout for troubleshooting.
"""
from __future__ import annotations

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


def _request(method, path, *, token=None, body=None, q=None, timeout=15):
    url = JELLYFIN_URL + path
    params = dict(q or {})
    if token:
        params["api_key"] = token
    url += ("?" + urllib.parse.urlencode(params)) if params else ""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    # Jellyfin rejects interactive authentication (AuthenticateByName) without a
    # client-identifier header -> HTTP 400 "Error processing request". Include it
    # on every call (harmless; API-key auth via ?api_key= ignores it).
    req.add_header("X-Emby-Authorization",
                   'MediaBrowser Client="RKM Provisioner", Device="rkm-bundled", '
                   f'DeviceId="{uuid.uuid4().hex}", Version="1.0", Token=""')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")}
    except Exception as e:
        return 0, {"error": str(e)}


def wait_ready(retries=60, delay=2.0) -> None:
    print(f"[jellyfin] waiting for {JELLYFIN_URL} ...")
    for i in range(retries):
        code, _ = _request("GET", "/System/Info/Public", timeout=5)
        if code == 200:
            print("[jellyfin] reachable")
            return
        time.sleep(delay)
    print("[jellyfin] ERROR: timed out waiting for Jellyfin.")
    sys.exit(1)


def wizard_pending() -> bool:
    """True if StartupWizardCompleted is false (no admin yet)."""
    code, data = _request("GET", "/System/Info/Public", timeout=6)
    if code == 200 and isinstance(data, dict):
        return data.get("StartupWizardCompleted") is False
    return False  # if we can't tell, assume set up and let auth decide


def authenticate():
    code, data = _request("POST", "/Users/AuthenticateByName",
                          body={"Username": ADMIN_USER, "Pw": ADMIN_PASSWORD})
    if code == 200 and isinstance(data, dict):
        return data.get("AccessToken")
    err = data.get("error") if isinstance(data, dict) else data
    print(f"[jellyfin] authenticate {ADMIN_USER} -> HTTP {code} {str(err)[:120]}")
    return None


def run_startup() -> bool:
    print("[jellyfin] first-run: setting first-user admin password via Startup wizard")
    # POST /Startup/User RENAMES the pre-existing first user + sets its password
    # via UserManager.ChangePassword, which hashes the value it's given. So the
    # field is the PLAINTEXT password — NOT a sha1 (sending sha1 double-hashes and
    # auth then mismatches). GET /Startup/User first is required (it calls
    # InitializeAsync which materialises the default first user; without it the
    # POST returns 404).
    for step in ("/Startup/Configuration", "/Startup/User"):
        code, _ = _request("GET", step, timeout=8)
        print(f"[jellyfin] GET {step} -> {code}")
    code, body = _request("POST", "/Startup/User", body={
        "Name": ADMIN_USER, "Password": ADMIN_PASSWORD})
    print(f"[jellyfin] POST /Startup/User -> {code} {body if code not in (200, 204) else ''}")
    code2, _ = _request("POST", "/Startup/RemoteAccess",
                        body={"EnableRemoteAccess": True, "EnableAutomaticPortMapping": False})
    code3, _ = _request("POST", "/Startup/Complete")
    print(f"[jellyfin] remote/complete -> {code2}/{code3}")
    time.sleep(2.0)
    return code in (200, 204)


def ensure_admin() -> str | None:
    token = authenticate()
    if token:
        print(f"[jellyfin] authenticated existing admin '{ADMIN_USER}'")
        return token
    if wizard_pending():
        if run_startup():
            token = authenticate()
            if token:
                print(f"[jellyfin] admin created + authenticated '{ADMIN_USER}'")
                return token
            print("[jellyfin] created user but could not authenticate "
                  "(password hash mismatch?)")
    return None


def ensure_api_key(admin_token):
    """Create or reuse an RKM Cinema API key, VERIFIED by reading back /Auth/Keys.

    The POST payload shape differs across Jellyfin versions, so after any POST we
    re-read the key list and return whatever 'RKM Cinema' key actually exists.
    """
    def _find():
        code, data = _request("GET", "/Auth/Keys", token=admin_token)
        if code == 200 and isinstance(data, dict):
            for it in (data.get("Items") or []):
                if str(it.get("App", "")) == "RKM Cinema" and it.get("Key"):
                    return str(it["Key"])
        return None

    existing = _find()
    if existing:
        print("[jellyfin] reusing existing RKM Cinema API key")
        return existing

    new_key = uuid.uuid4().hex
    # Variant A: client-supplied key; Variant B: server-generated (App only).
    variants = [
        {"App": "RKM Cinema", "ApiKey": new_key},
        {"App": "RKM Cinema"},
    ]
    for v in variants:
        code, body = _request("POST", "/Auth/Keys", token=admin_token, body=v)
        print(f"[jellyfin] POST /Auth/Keys ({'client-key' if 'ApiKey' in v else 'server-gen'}) -> {code}")
        if code in (200, 204):
            k = _find()
            if k:
                print("[jellyfin] confirmed API key registered")
                return k
    # Fallback that is guaranteed to work: Jellyfin accepts an admin user's
    # access token via ?api_key= for user-scoped queries (the same auth that
    # added the libraries). This sidesteps version-specific /Auth/Keys shapes.
    print("[jellyfin] using admin AccessToken as the RKM API credential (fallback: "
          "/Auth/Keys not available on this version).")
    return admin_token


def _existing_libraries(admin_token):
    code, data = _request("GET", "/Library/VirtualFolders", token=admin_token)
    if code == 200 and isinstance(data, list):
        return data
    return []


def _locations_of(vf) -> list:
    return [p for p in ((vf.get("Locations") or []) + (vf.get("Paths") or [])) if p]


def _is_bogus_default(vf) -> bool:
    """A library pointing at Jellyfin's own internal default path (created by the
    wizard without a real media folder) — safe to delete."""
    locs = _locations_of(vf)
    return not locs or all(p.strip("/").startswith("config/root/default") for p in locs)


# Target libraries we want: name -> (collectionType, container path)
TARGET_LIBRARIES = [
    ("Movies", "movies", "/data/media/_movie"),
    ("TV Shows", "tvshows", "/data/media/_tv"),
]


def ensure_libraries(admin_token):
    """Guarantee exactly the two media libraries exist pointing at /data/media/{_movie,_tv}.

    Cleans bogus wizard defaults (which point at /config/root/default), deletes any
    target-named library with the WRONG path, re-creates via the `paths=` QUERY form
    (the body PathInfos form silently 204s without setting a path on 10.11), then
    verifies each library's Locations and triggers a library scan.
    """
    existing = _existing_libraries(admin_token)
    for vf in existing:
        name = vf.get("Name")
        if _is_bogus_default(vf):
            code, _ = _request("DELETE", "/Library/VirtualFolders",
                               token=admin_token, q={"name": name, "refreshLibrary": "false"})
            print(f"[jellyfin] deleted bogus library '{name}' (default path) -> {code}")

    for target_name, ctype, path in TARGET_LIBRARIES:
        vfs = _existing_libraries(admin_token)
        match = next((v for v in vfs if v.get("Name") == target_name), None)
        if match and path in _locations_of(match):
            print(f"[jellyfin] library '{target_name}' already at {path}")
            continue
        if match:
            code, _ = _request("DELETE", "/Library/VirtualFolders",
                               token=admin_token, q={"name": target_name, "refreshLibrary": "false"})
            print(f"[jellyfin] deleted mis-configured '{target_name}' -> {code}")
        body = {"LibraryOptions": {"SaveLocalMetadata": True, "EnableInternetProviders": True},
                "RefreshLibrary": False}
        q = {"name": target_name, "collectionType": ctype, "refreshLibrary": "false", "paths": path}
        code, _ = _request("POST", "/Library/VirtualFolders", token=admin_token, body=body, q=q)
        print(f"[jellyfin] create library '{target_name}' ({path}) -> {code}")
        # Verify the path actually stuck (Locations must contain it).
        ok = False
        vfs = _existing_libraries(admin_token)
        m2 = next((v for v in vfs if v.get("Name") == target_name), None)
        if m2 and path in _locations_of(m2):
            ok = True
        print(f"[jellyfin]   verified '{target_name}' at {path}: {ok}")

    # Scan now so newly-attached folders index automatically (no manual Jellyfin scan).
    code, _ = _request("POST", "/Library/Refresh", token=admin_token)
    print(f"[jellyfin] triggered library scan (POST /Library/Refresh) -> {code}")


def main():
    if not ADMIN_PASSWORD:
        print("ERROR: JELLYFIN_ADMIN_PASSWORD not set (generated by render_config.py).")
        sys.exit(1)
    wait_ready()

    token = ensure_admin()
    if not token:
        print("[jellyfin] ERROR: could not create or authenticate the admin user.")
        print("          Complete the one-time wizard at "
              f"{BROWSER_URL}/web (username '{ADMIN_USER}'), then re-run bootstrap.")
        sys.exit(1)

    api_key = ensure_api_key(token)
    ensure_libraries(token)

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
    print("[rkm] provisioner DONE (bootstrap will restart api to pick up the API key)")


if __name__ == "__main__":
    main()