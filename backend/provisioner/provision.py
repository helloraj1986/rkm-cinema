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
    data = None
    if body is not None:
        # body="" means "send an EMPTY body on purpose": POST /Auth/Keys?app=...
        # needs Content-Length: 0 on Jellyfin 10.11 (an absent body 400s).
        data = b"" if body == "" else json.dumps(body).encode()
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


def wait_ready(retries=120, delay=2.0) -> None:
    """Wait until Jellyfin is past its BOOT page, not merely listening.

    A brand-new /config volume serves an HTML "Jellyfin Startup" page (HTTP 503)
    while it initialises, and /System/Info/Public can already answer 200 in that
    window — so readiness must mean "the API answers JSON", not "the port is
    open". 2026-09-10: the provisioner called the port ready on a fresh volume,
    failed to authenticate, died BEFORE writing the API key, and every library in
    the UI then showed as disabled.
    """
    print(f"[jellyfin] waiting for {JELLYFIN_URL} ...")
    for _ in range(retries):
        code, data = _request("GET", "/System/Info/Public", timeout=5)
        if code == 200 and isinstance(data, dict) and data.get("Version"):
            print("[jellyfin] reachable")
            return
        time.sleep(delay)
    print("[jellyfin] ERROR: timed out waiting for Jellyfin.")
    sys.exit(1)


def wizard_pending() -> bool | None:
    """True/False for StartupWizardCompleted, or None while Jellyfin still boots.

    The tri-state matters: the boot page is HTML (or a 503), which is NOT evidence
    that the wizard is done. Treating "can't tell" as "done" is what made the
    provisioner skip creating the admin user altogether.
    """
    code, data = _request("GET", "/System/Info/Public", timeout=6)
    if code == 200 and isinstance(data, dict):
        val = data.get("StartupWizardCompleted")
        if val is not None:
            return not bool(val)
    return None


def authenticate(quiet: bool = False):
    code, data = _request("POST", "/Users/AuthenticateByName",
                          body={"Username": ADMIN_USER, "Pw": ADMIN_PASSWORD})
    if code == 200 and isinstance(data, dict):
        return data.get("AccessToken")
    if not quiet:
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


def ensure_admin(retries=40, delay=3.0) -> str | None:
    """Create or authenticate the admin user, waiting out a fresh install.

    A brand-new /config volume needs time: authentication can keep returning 503
    (the HTML startup page) for a minute or more AFTER /System/Info/Public starts
    answering JSON. Only give up early when Jellyfin says the wizard is COMPLETE
    and auth STILL fails — that is a credentials problem, and retrying will not
    fix it.
    """
    for attempt in range(1, retries + 1):
        token = authenticate(quiet=attempt > 1)
        if token:
            print(f"[jellyfin] authenticated existing admin '{ADMIN_USER}'")
            return token

        pending = wizard_pending()
        if pending is True:
            if run_startup():
                token = authenticate(quiet=True)
                if token:
                    print(f"[jellyfin] admin created + authenticated '{ADMIN_USER}'")
                    return token
                print("[jellyfin] created user but could not authenticate "
                      "(password hash mismatch?)")
        elif pending is False:
            print(f"[jellyfin] the startup wizard is COMPLETE but '{ADMIN_USER}' could "
                  "not authenticate — check RKM_JELLYFIN_ADMIN_PASSWORD in .env "
                  "(it must match the password Jellyfin was set up with)")
            return None

        if attempt < retries:
            if attempt in (1, 5, 20):
                print(f"[jellyfin] not ready yet (attempt {attempt}/{retries}) — "
                      "waiting for Jellyfin to finish starting up")
            time.sleep(delay)

    print(f"[jellyfin] gave up waiting for '{ADMIN_USER}' after {retries} attempts")
    return None


#: The app name our Jellyfin API key is registered under.
API_KEY_APP = "RKM Cinema"


def ensure_api_key(admin_token):
    """Create or reuse the RKM Cinema API key, VERIFIED by reading back /Auth/Keys.

    Live-probed on Jellyfin 10.11.11 (2026-09-10). The shapes differ from what this
    script originally assumed — and getting them wrong is invisible, because both
    failures look like "no key exists" and the caller silently falls back:

        create : POST /Auth/Keys?app=<name>  with an EMPTY body (a JSON body -> 400)
        list   : items carry ``AppName`` + ``AccessToken`` (NOT ``App``/``Key``)

    So: try the verified query form first, accept both field spellings, and always
    confirm by re-reading the list — a create that returns 204 but registers
    nothing must NOT be reported as success.
    """
    def _find():
        code, data = _request("GET", "/Auth/Keys", token=admin_token)
        if code == 200 and isinstance(data, dict):
            for it in (data.get("Items") or []):
                app = str(it.get("AppName") or it.get("App") or "")
                key = it.get("AccessToken") or it.get("Key")
                if app == API_KEY_APP and key:
                    return str(key)
        return None

    existing = _find()
    if existing:
        print(f"[jellyfin] reusing the existing '{API_KEY_APP}' API key")
        return existing

    attempts = [
        ("query param, empty body (10.11+)", {"q": {"app": API_KEY_APP}, "body": ""}),
        ("JSON body: App + ApiKey", {"body": {"App": API_KEY_APP, "ApiKey": uuid.uuid4().hex}}),
        ("JSON body: App only", {"body": {"App": API_KEY_APP}}),
    ]
    for label, kwargs in attempts:
        code, _ = _request("POST", "/Auth/Keys", token=admin_token, **kwargs)
        print(f"[jellyfin] POST /Auth/Keys ({label}) -> {code}")
        if code in (200, 204):
            found = _find()
            if found:
                print(f"[jellyfin] confirmed '{API_KEY_APP}' API key registered")
                return found

    # Fallback that is guaranteed to work: Jellyfin accepts an admin user's access
    # token via ?api_key= for user-scoped queries (the same auth that just created
    # the libraries). This sidesteps version-specific /Auth/Keys shapes.
    print("[jellyfin] using the admin AccessToken as the RKM credential (fallback: "
          "/Auth/Keys could not be used on this version).")
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


#: Where the target list came from — what makes pruning safe to gate on.
SOURCE_CONFIGURED = "configured"
SOURCE_DISCOVERED = "discovered"
SOURCE_SAMPLE = "sample"

# Configured media libraries (MEDIA_LIBRARIES_PLAN): bootstrap wires EVERY
# MEDIA_LIBRARY_N_* entry in .env into Jellyfin at startup. The SAME shared
# parser the api uses (config/media_libraries.py) guarantees both agree on the
# container path. When NOTHING is configured we keep the historical sample pair
# so a fresh checkout still works out of the box.
LEGACY_TARGET_LIBRARIES = [
    ("Movies", "movies", "/data/media/_movie"),
    ("TV Shows", "tvshows", "/data/media/_tv"),
]


def _media_root_mounts() -> list[tuple[str, str]]:
    """``[(container_mount, host_path), …]`` — one entry per CONFIGURED root.

    Driven by the env keys themselves (the shared parser), not by guesswork:
    ``RKM_MEDIA_PATH`` → ``/data``, ``RKM_MEDIA_PATH_2`` → ``/media2`` … An
    extra root that is not declared in .env is simply not in the list, so the
    folder is never discovered twice (compose mounts /media2 unconditionally,
    pointed at the primary root when unset — that mount is ignored here).
    With no root configured at all we fall back to the historical ``/data``.
    """
    try:
        from config.media_libraries import media_roots
    except Exception as e:  # pragma: no cover - packaging sanity
        print(f"[jellyfin] WARN: shared config parser unavailable ({e})")
        return [("/data", os.environ.get("RKM_MEDIA_PATH") or "/data")]

    roots, warnings = media_roots({k: v for k, v in os.environ.items()})
    for w in warnings:
        print(f"[jellyfin] WARN config: {w}")
    if not roots:
        return [("/data", os.environ.get("RKM_MEDIA_PATH") or "/data")]
    return [(r.container, r.host) for r in roots]


def discover_media_root_libraries(root: str = "/data") -> list[tuple[str, str, str]]:
    """Auto-detect libraries from ONE mounted media root (zero-config path).

    When no MEDIA_LIBRARY_N_* is configured, every immediate subfolder of the
    media root except the stack's own bookkeeping dirs becomes a library, named
    after the folder and typed by simple name heuristics (movie/tv/mixed). This
    is what makes ``RKM_MEDIA_PATH=D:/RKM_MEDIA`` "just work": all the user's
    folders appear in the sidebar without hand-writing an entry per folder.
    ``root`` is the CONTAINER mount (``/data``, ``/media2``) and is also the
    path prefix of every returned library.
    """
    denylist = {"downloads", "rkm", "media", "_movie", "_tv",
                "@eadir", "system volume information", "$recycle.bin",
                "lost+found", "config", "cache"}
    mount = root.rstrip("/") or "/"
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return []
    out = []
    for name in entries:
        if name.startswith(".") or name.casefold() in denylist:
            continue
        if not os.path.isdir(os.path.join(root, name)):
            continue
        out.append((name, _guess_collection_type(name), f"{mount}/{name}"))
    return out


def discover_all_media_roots() -> list[tuple[str, str, str]]:
    """Union of :func:`discover_media_root_libraries` over EVERY root.

    Two drives (movies on D:, TV on B:) each contribute their own folders. A
    folder NAME that appears on two roots cannot become two Jellyfin libraries
    (sidebar names must be unique), so the first wins and the clash is reported
    with the fix — declare explicit ``MEDIA_LIBRARY_N_*`` entries to choose.
    """
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for mount, host in _media_root_mounts():
        found = discover_media_root_libraries(mount)
        if found:
            print(f"[jellyfin] auto-discovered {len(found)} folder(s) under "
                  f"{mount} ({host})")
        for name, ctype, path in found:
            key = name.casefold()
            if key in seen:
                print(f"[jellyfin] note: a '{name}' folder exists on more than one "
                      f"media root — keeping {path}; declare MEDIA_LIBRARY_N_NAME/"
                      f"PATH in .env to include the other one")
                continue
            seen.add(key)
            out.append((name, ctype, path))
    return out


def _guess_collection_type(name: str) -> str:
    """Best-effort Jellyfin collection type from a folder name (never a guess
    about CONTENT — just routing the scanner; unknown → mixed)."""
    n = name.casefold()
    if any(t in n for t in ("tv", "show", "series", "episode")):
        return "tvshows"
    if any(t in n for t in ("movie", "film", "cinema")):
        return "movies"
    return "mixed"


def configured_target_libraries() -> list[tuple[str, str, str]]:
    """``[(name, collection_type, container_path), …]`` the provisioner wires."""
    return target_libraries_with_source()[0]


def target_libraries_with_source() -> tuple[list[tuple[str, str, str]], str]:
    """``(targets, source)`` — the source is what makes PRUNING safe to gate on.

    ``source`` is one of ``"configured"`` (explicit MEDIA_LIBRARY_N_*),
    ``"discovered"`` (real folders found under a mounted media root) or
    ``"sample"`` (the fresh-checkout fallback, i.e. NOTHING was configured and
    NOTHING was discovered — typically a drive that failed to mount). Pruning is
    refused for ``"sample"``: see :func:`prune_untargeted_libraries`.
    """
    try:
        from config.media_libraries import parse_media_libraries
    except Exception as e:  # pragma: no cover - packaging sanity
        print(f"[jellyfin] WARN: shared config parser unavailable ({e}) — "
              "falling back to the default sample libraries")
        return list(LEGACY_TARGET_LIBRARIES), SOURCE_SAMPLE

    env = {k: v for k, v in os.environ.items()}
    libraries, warnings = parse_media_libraries(env)
    for w in warnings:
        print(f"[jellyfin] WARN config: {w}")
    if libraries:
        return ([(lib.name, lib.collection_type, lib.path) for lib in libraries],
                SOURCE_CONFIGURED)

    discovered = discover_all_media_roots()
    if discovered:
        mounts = ", ".join(m for m, _ in _media_root_mounts())
        print(f"[jellyfin] no MEDIA_LIBRARY_N_* configured — auto-discovered "
              f"{len(discovered)} folder(s) across {mounts}")
        return discovered, SOURCE_DISCOVERED

    print("[jellyfin] no configured or discoverable libraries — using the default sample libraries")
    return list(LEGACY_TARGET_LIBRARIES), SOURCE_SAMPLE


def _folder_check(container_path: str) -> tuple[bool, str]:
    """``(wireable, message)`` for a configured folder INSIDE this container.

    The provisioner mounts the same media root at /data as Jellyfin, so this is
    a REAL accessibility check: a missing/unreadable folder is reported here at
    bootstrap instead of silently producing a broken empty library. An EMPTY
    folder is wireable (a brand-new library is scanned as files arrive).
    """
    if not container_path.startswith("/"):
        return False, ("not a container path — check RKM_MEDIA_PATH / MEDIA_LIBRARY PATH "
                       "(a host path must sit under RKM_MEDIA_PATH to be mounted)")
    p = container_path
    if not os.path.exists(p):
        return False, f"MISSING at {p} (no such folder on the mounted media root)"
    if not os.path.isdir(p):
        return False, f"NOT A FOLDER at {p}"
    try:
        entries = os.listdir(p)
    except PermissionError:
        return False, f"NOT READABLE at {p} (permission denied)"
    if not entries:
        return True, f"EMPTY at {p} (wired anyway — will index as files arrive)"
    return True, "ok"


def prune_untargeted_libraries(admin_token, targets, *, source, mounts, enabled=True) -> list[str]:
    """Delete Jellyfin libraries that live in OUR media mounts but are not targets.

    The bundled Jellyfin is app-managed, so its library list should mirror what
    ``.env`` declares (or what discovery found) — anything else is a leftover
    from an earlier configuration: stray rows in the sidebar, inflated counts and
    artwork that 404s. Returns the deleted names.

    SAFETY RAILS (this deletes things, so each one matters):
    - ``enabled=False`` (``RKM_PRUNE_LIBRARIES=false``) → strict no-op;
    - ``source == "sample"`` → REFUSED. That source means nothing was configured
      AND nothing was discovered, which is what a failed drive mount looks like —
      pruning there would delete the user's real libraries because a mount was
      briefly missing. Never trade their library list for a debug convenience;
    - a target NAME is never deleted (that is what we just wired/repaired);
    - only libraries with a Location under one of our own container mounts are
      considered, so Jellyfin's internal collections and anything pointing
      outside the media roots are left alone.
    """
    if not enabled:
        print("[jellyfin] library pruning disabled (RKM_PRUNE_LIBRARIES=false) — "
              "leaving existing libraries untouched")
        return []
    if source == SOURCE_SAMPLE:
        print("[jellyfin] NOT pruning: no library was configured or discovered, so existing "
              "libraries are left untouched (a missing drive must never delete your libraries)")
        return []

    keep = {name.casefold() for name, _, _ in targets}
    deleted: list[str] = []
    for vf in _existing_libraries(admin_token):
        name = vf.get("Name") or ""
        if not name or name.casefold() in keep:
            continue
        locs = _locations_of(vf)
        if not any(_under_mount(loc, mounts) for loc in locs):
            continue
        code, _ = _request("DELETE", "/Library/VirtualFolders", token=admin_token,
                           q={"name": name, "refreshLibrary": "false"})
        print(f"[jellyfin] removed stale library '{name}' "
              f"({', '.join(locs) or 'no path'}) -> {code}")
        deleted.append(name)
    if not deleted:
        print("[jellyfin] no stale libraries to remove")
    return deleted


def _under_mount(location: str, mounts) -> bool:
    """True when ``location`` IS or sits under one of our container mounts."""
    loc = (location or "").strip().rstrip("/")
    for m in mounts:
        root = m.strip().rstrip("/")
        if root and (loc == root or loc.startswith(root + "/")):
            return True
    return False


def _prune_enabled(env: dict | None = None) -> bool:
    """``RKM_PRUNE_LIBRARIES`` — on by default (the bundled Jellyfin is ours)."""
    raw = str((env or os.environ).get("RKM_PRUNE_LIBRARIES", "") or "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def ensure_libraries(admin_token):
    """Wire every configured media library into Jellyfin (idempotent) and prune leftovers.

    Targets come from MEDIA_LIBRARY_N_* in .env or from discovery
    (see target_libraries_with_source); a missing/unreadable folder is reported
    loudly and SKIPPED (never a broken empty library). Cleans bogus wizard
    defaults, deletes + re-creates a target-named library whose path is wrong,
    verifies Locations, removes libraries that are no longer targets, then scans.
    """
    targets, source = target_libraries_with_source()
    print(f"[jellyfin] libraries to wire: {[t[0] for t in targets]} (source: {source})")

    existing = _existing_libraries(admin_token)
    for vf in existing:
        name = vf.get("Name")
        if _is_bogus_default(vf):
            code, _ = _request("DELETE", "/Library/VirtualFolders",
                               token=admin_token, q={"name": name, "refreshLibrary": "false"})
            print(f"[jellyfin] deleted bogus library '{name}' (default path) -> {code}")

    for target_name, ctype, path in targets:
        wireable, status = _folder_check(path)
        if not wireable:
            print(f"[jellyfin] SKIP '{target_name}' ({path}) — {status}")
            continue
        if status != "ok":
            print(f"[jellyfin] note '{target_name}': {status}")

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

    # Remove libraries that are no longer targets (leftovers from an earlier
    # configuration: stray sidebar rows, inflated counts, 404'd artwork).
    prune_untargeted_libraries(admin_token, targets, source=source,
                               mounts=[m for m, _ in _media_root_mounts()],
                               enabled=_prune_enabled())

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
        print(f"[jellyfin] ERROR: could not create or authenticate the admin user "
              f"'{ADMIN_USER}'.")
        print("          If Jellyfin is sitting on its first-run wizard, complete it at "
              f"{BROWSER_URL}/web with username '{ADMIN_USER}' and the password from "
              ".env (RKM_JELLYFIN_ADMIN_PASSWORD), then re-run bootstrap.")
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