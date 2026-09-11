#!/usr/bin/env python3
"""Render the SINGLE repo-level `.env` -> the api container env (`.rkm.env`).

The one config file is ``<repo>/.env`` (copy `.env.example` and fill it in).
This script:

* reads ONLY that file — no rkm.config.toml, no workspace-level .env;
* fills safe defaults into `.env` if keys are missing (ports, media path,
  backend, watchlist store, scheduler…) and auto-generates + persists
  ``JELLYFIN_ADMIN_PASSWORD`` when it is blank;
* validates required keys (TMDB_API_KEY etc.) and prints exactly what is
  missing;
* creates the media/storage tree (``RKM_MEDIA_PATH``);
* writes ``.rkm.env`` (the api container's env_file — container-internal
  values such as ``http://jellyfin:8096`` are derived HERE) and a small
  ``.rkm_state.json`` summary.

``docker compose`` reads the same ``.env`` directly for port/path/provisioner
substitution, so there is exactly one file to edit.

Run inside bootstrap.sh / bootstrap.ps1 before `docker compose up`.
Python 3.11+. Runs from the repo root.
"""
from __future__ import annotations

import json
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"              # THE single user config
API_ENV = ROOT / ".rkm.env"           # api container env_file (generated)
STATE_PATH = ROOT / ".rkm_state.json"  # small render summary (generated)

# Keys we can safely default (non-secret). Appended to .env when absent so the
# file stays complete and self-documenting for the user.
DEFAULTS = {
    "RKM_MEDIA_PATH": "./data",
    "RKM_DASHBOARD_PORT": "8124",
    "RKM_JELLYFIN_PORT": "8098",
    "RKM_TIMEZONE": "Australia/Melbourne",
    "RKM_PUID": "1000",
    "RKM_PGID": "1000",
    "MEDIA_SERVER": "jellyfin",
    "RKM_JELLYFIN_ADMIN_USER": "admin",
    "RKM_JELLYFIN_BROWSER": "http://localhost:8098",
    "WATCHLIST_STORE": "json",
    "WATCHLIST_DB_PATH": "/data/rkm/watchlist.json",
    "WATCHLIST_SCHEDULER": "true",
    "AUTO_ADD_ENABLED": "false",
    "AUTO_ADD_HOUR": "18",
    "RECONCILE_INTERVAL_MIN": "10",
}

# Internal compose service names used as fallbacks when the user has not
# pointed at already-running *arr (the opt-in `fullstack` profile).
INTERNAL_FALLBACKS = {
    "RADARR_URL": "http://radarr:7878",
    "SONARR_URL": "http://sonarr:8989",
    "PROWLARR_URL": "http://prowlarr:9696",
    "QBITTORRENT_URL": "http://qbittorrent:8080",
}

# Service keys migrated ONE TIME from the legacy workspace .env (the file the
# old render_config used to borrow from). Not included on purpose: Jellyfin_
# (the bundled stack runs its own container) and WATCHLIST_* (bundled keeps its
# isolated /data/rkm store) stay repo-.env-only.
LEGACY_KEYS = [
    "TMDB_API_KEY", "TVDB_API_KEY",
    "RADARR_URL", "RADARR_API_KEY", "SONARR_URL", "SONARR_API_KEY",
    "PROWLARR_URL", "PROWLARR_API_KEY", "QBITTORRENT_URL",
    "RADARR_QUALITY_PROFILE_ID", "SONARR_QUALITY_PROFILE_ID",
    "BROWSER_RADARR_URL", "BROWSER_SONARR_URL",
]


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def _strip_inline_comment(value: str) -> str:
    """Drop a trailing ``␣#…`` comment from an UNQUOTED .env value.

    Matches how Docker Compose / godotenv read the same file (a ``#`` only starts
    a comment when preceded by whitespace, so ``D:/a#b`` survives). Quoted values
    never reach here, so a legitimate ``' #'`` is still expressible as "value #x".
    2026-09-10: this parser used to keep the comment while Compose stripped it —
    two readings of one file, which is how a value silently picks up stray text.
    """
    idx = value.find(" #")
    return (value[:idx] if idx != -1 else value).rstrip()


def parse_env_file(path: Path) -> dict:
    """Parse a .env file (comments, blank lines, `export`, quotes)."""
    parsed: dict = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return parsed
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip().lstrip("export").strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]                      # quoted → verbatim between the quotes
        else:
            v = _strip_inline_comment(v)
        if k:
            parsed[k] = v
    return parsed


def write_env_key(path: Path, key: str, value: str) -> None:
    """Append or replace one key in a .env file, preserving everything else."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().startswith("#") or "=" not in line:
            out.append(line)
            continue
        k = line.split("=", 1)[0].strip().lstrip("export").strip()
        if k == key:
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")


def find_legacy_env() -> dict:
    """Ancestor .env files OUTSIDE the repo (the workspace-root env the old
    render_config borrowed from). Later/higher files override. Never the repo's
    own .env — that is the single source from now on."""
    merged: dict = {}
    p = ROOT.parent
    for _ in range(12):
        f = p / ".env"
        if f.exists():
            merged.update(parse_env_file(f))
        if p == p.parent:
            break
        p = p.parent
    return merged


def migrate_legacy(env: dict) -> int:
    """One-time migration: copy any missing service keys from the legacy
    workspace .env into the repo .env so the user never has to re-type them.
    After this the repo .env is complete and self-contained."""
    legacy = find_legacy_env()
    if not legacy:
        return 0
    n = 0
    for k in LEGACY_KEYS:
        if k not in env and str(legacy.get(k) or "").strip():
            write_env_key(ENV_PATH, k, str(legacy.get(k)).strip())
            n += 1
    if n:
        print(f"[env] one-time migration: copied {n} missing key(s) from the legacy "
              f"workspace .env into {ENV_PATH.name} — this file is now the single source.")
    return n


def ensure_defaults() -> dict:
    """Fill safe defaults into .env (if the file is missing, seed it from
    .env.example), migrate missing service keys from the legacy workspace .env,
    then return the parsed env."""
    if not ENV_PATH.exists():
        example = ROOT / ".env.example"
        if example.exists():
            ENV_PATH.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Created {ENV_PATH.name} from .env.example — EDIT IT and fill in your keys, then re-run.")
            fail(f"{ENV_PATH.name} still needs your values (TMDB_API_KEY, *arr keys, …).")
        fail(f"No {ENV_PATH.name} found and no .env.example to copy. Add a .env with your settings.")
    env = parse_env_file(ENV_PATH)
    added = [k for k, v in DEFAULTS.items() if k not in env]
    for k, v in DEFAULTS.items():
        if k not in env:
            write_env_key(ENV_PATH, k, v)
    if added:
        print(f"[env] filled {len(added)} default key(s) into {ENV_PATH.name}: {', '.join(added)}")
    migrate_legacy(env)
    return parse_env_file(ENV_PATH)


def resolve_data_path(env: dict) -> Path:
    raw = str(env.get("RKM_MEDIA_PATH") or "./data")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p


def is_real_media_root(raw: str) -> bool:
    """True when ``RKM_MEDIA_PATH`` points somewhere real, not the repo default.

    Deliberately platform-independent: ``D:/RKM_MEDIA`` is absolute to a Windows
    interpreter but looks RELATIVE to a POSIX one, and the sample tree
    (``media/_movie``, ``media/_tv``) must never be seeded into a user's drive on
    either platform. So a drive-letter path and a UNC path count as real even on
    Linux, and only ``./data``-style relative paths select the sample tree.
    """
    p = (raw or "").strip()
    if not p:
        return False
    if re.match(r"^[A-Za-z]:[\\/]", p) or p.startswith("\\\\"):
        return True
    return Path(p).expanduser().is_absolute()


def ensure_storage(data: Path, env: dict | None = None) -> None:
    """Create the storage tree and validate configured media libraries.

    Rules:
    - the app's own dirs (downloads/, rkm/) are always ensured under the PRIMARY
      media root — that is where the stack keeps qBittorrent output + the
      watchlist DB (a second media drive holds library folders only);
    - SAMPLE media dirs (media/_movie, media/_tv) are created ONLY when the root
      is the repo-local default (``./data``) — never inside a real media drive
      the user pointed us at, and never when libraries are configured;
    - EVERY configured media root is reported (host path → mount), so a missing
      drive or a mistyped RKM_MEDIA_PATH_N is visible before the containers even
      start; with MEDIA_LIBRARY_N_* set each library folder is existence-checked
      here too.
    """
    env = env or {}
    (data / "downloads").mkdir(parents=True, exist_ok=True)
    (data / "rkm").mkdir(parents=True, exist_ok=True)

    roots, root_warnings = [], []
    libraries, warnings = [], []
    try:
        import sys as _sys
        if str(ROOT / "backend") not in _sys.path:
            _sys.path.insert(0, str(ROOT / "backend"))
        from config.media_libraries import media_roots, parse_media_libraries

        roots, root_warnings = media_roots(env)
        libraries, warnings = parse_media_libraries(env)
    except Exception as e:  # pragma: no cover - imported lazily for safety
        print(f"[env] WARN: could not parse media libraries ({e})")

    for w in [*root_warnings, *warnings]:
        print(f"[env] WARN: {w}")

    # Every declared root: the primary one is this `data` dir; the others are
    # extra drives the containers mount at /media2, /media3 … Their library
    # folders are checked below through the configured libraries.
    for r in roots:
        if r.container == "/data":
            print(f"[env] media root: {r.host} → {r.container} "
                  f"({'ok' if data.exists() else 'MISSING'})")
        else:
            print(f"[env] media root: {r.host} → {r.container} (extra drive — mounted "
                  "by compose; create it on the host if it is missing)")
    if not roots:
        print("[env] WARN: no RKM_MEDIA_PATH configured — the containers fall back to ./data")

    # A relative root means the repo-local sample tree; a real drive (absolute,
    # UNC or Windows drive letter) must never be seeded with sample folders.
    raw_root = str(env.get("RKM_MEDIA_PATH") or "./data").strip()
    is_default_root = not is_real_media_root(raw_root)

    if libraries:
        for lib in libraries:
            # container path (/data/… → primary root, /media2/… → extra root)
            root = next((r for r in roots if lib.path.startswith(r.container + "/")
                         or lib.path == r.container), None)
            if root and root.container != "/data":
                print(f"[env] library '{lib.name}' → {lib.path} "
                      f"(on {root.host} — check the folder exists on that drive)")
                continue
            rel = lib.path[len("/data"):].lstrip("/") if root else ""
            host = data / rel if rel else data
            if host.exists() and host.is_dir():
                state = "ok"
            elif host.exists():
                state = "NOT A FOLDER"
            else:
                state = "MISSING (create it, or fix the PATH in .env)"
            print(f"[env] library '{lib.name}' → {host} [{state}]")
        print(f"storage tree ready at: {data} "
              f"({len(libraries)} configured librar{'y' if len(libraries) == 1 else 'ies'}"
              f", {len(roots)} media root{'s' if len(roots) != 1 else ''})")
        return

    if is_default_root:
        for sub in ("media/_movie", "media/_tv"):
            (data / sub).mkdir(parents=True, exist_ok=True)
        print(f"storage tree ready at: {data} (default sample libraries)")
        return

    print(f"storage tree ready at: {data} — no MEDIA_LIBRARY_N_* configured; the "
          "provisioner will auto-discover each media root's subfolders as libraries")


def build_api_vars(env: dict) -> dict:
    """Derive the api container env from the single repo .env (pure mapping —
    unit-testable). Container-internal addresses are resolved here."""
    raw_backend = str(env.get("MEDIA_SERVER") or "").strip().lower()
    # There is exactly ONE media server (Jellyfin) and the api can only wire it.
    # This used to `fail()` on a retired value, which would strand a working box on
    # an un-updated .env; it now warns and continues. The rendered value is ALWAYS
    # jellyfin (never a pass-through), and that is deliberate for a second reason:
    # the admin-password generation below is gated on the backend, and letting a
    # legacy value reach it produces a stack whose libraries are all disabled.
    if raw_backend != "jellyfin":
        print(f"[env] WARNING: MEDIA_SERVER={raw_backend or '(blank)'} is not a live backend; "
              f"rendering jellyfin (the only media server).")
    backend = "jellyfin"

    # Metadata required for discovery/Suggest.
    tmdb_key = str(env.get("TMDB_API_KEY") or "").strip()
    if not tmdb_key:
        fail("TMDB_API_KEY is empty — add it to .env (TMDB dashboard -> API).")

    # Jellyfin admin password: generate only when the backend is the bundled
    # Jellyfin (persisted into .env so it stays stable).
    admin_pw = str(env.get("RKM_JELLYFIN_ADMIN_PASSWORD") or "").strip()
    if backend == "jellyfin" and not admin_pw:
        admin_pw = secrets.token_urlsafe(18)
        write_env_key(ENV_PATH, "RKM_JELLYFIN_ADMIN_PASSWORD", admin_pw)
        print(f"[env] generated RKM_JELLYFIN_ADMIN_PASSWORD -> saved to {ENV_PATH.name}")

    jf_browser = str(env.get("RKM_JELLYFIN_BROWSER") or "").strip() or (
        f"http://localhost:{env.get('RKM_JELLYFIN_PORT') or '8098'}"
    )
    # Container-to-container address: bundled jellyfin service, unless the user
    # explicitly points at an external Jellyfin.
    jf_internal = str(env.get("JELLYFIN_URL") or "").strip() or "http://jellyfin:8096"

    api = {
        "MEDIA_SERVER": backend,
        "JELLYFIN_URL": jf_internal,
        "JELLYFIN_BROWSER_URL": jf_browser,
        "TMDB_API_KEY": tmdb_key,
        "TVDB_API_KEY": str(env.get("TVDB_API_KEY") or "").strip(),
        # Watchlist persistence + scheduler.
        "WATCHLIST_STORE": str(env.get("WATCHLIST_STORE") or "json").strip().lower(),
        "WATCHLIST_DB_PATH": str(env.get("WATCHLIST_DB_PATH") or "/data/rkm/watchlist.json").strip(),
        "WATCHLIST_SCHEDULER": str(env.get("WATCHLIST_SCHEDULER") or "true").strip().lower(),
        "AUTO_ADD_ENABLED": str(env.get("AUTO_ADD_ENABLED") or "false").strip().lower(),
        "DAILY_JOB_HOUR": str(env.get("AUTO_ADD_HOUR") or "18").strip(),
        "RECONCILE_INTERVAL_MIN": str(env.get("RECONCILE_INTERVAL_MIN") or "10").strip(),
        "RKM_RUNTIME_PATH": "/shared/runtime.json",
    }
    # Acquisition (*arr/qbit): already-running services the user pastes in, else
    # the opt-in fullstack profile service names.
    for k in ("RADARR_URL", "SONARR_URL", "PROWLARR_URL", "QBITTORRENT_URL"):
        api[k] = str(env.get(k) or "").strip() or INTERNAL_FALLBACKS[k]
    for k in ("RADARR_API_KEY", "SONARR_API_KEY", "PROWLARR_API_KEY",
              "RADARR_QUALITY_PROFILE_ID", "SONARR_QUALITY_PROFILE_ID"):
        api[k] = str(env.get(k) or "").strip()
    # Media libraries (MEDIA_LIBRARIES_PLAN): pass every MEDIA_LIBRARY_N_NAME /
    # PATH / TYPE key through to the api container so config.settings can parse
    # them, plus EVERY media root (RKM_MEDIA_PATH + RKM_MEDIA_PATH_2/3 …) so a
    # host-style PATH (D:/RKM_MEDIA/Movies Kids, B:/RKM_MEDIA/TV Shows) can be
    # translated to the container path the containers actually mount.
    api["RKM_MEDIA_PATH"] = str(env.get("RKM_MEDIA_PATH") or "./data").strip()
    for k, v in env.items():
        if k.startswith("MEDIA_LIBRARY_"):
            api[k] = str(v).strip()
        elif k.startswith("RKM_MEDIA_PATH_"):
            api[k] = str(v).strip()
    # Provisioner behaviour: prune Jellyfin libraries that are not targets. The
    # bundled Jellyfin is app-managed, so this defaults ON (blank = on); set
    # RKM_PRUNE_LIBRARIES=false to keep libraries the app does not declare.
    api["RKM_PRUNE_LIBRARIES"] = str(env.get("RKM_PRUNE_LIBRARIES") or "").strip()
    return api


def render(env: dict, data: Path) -> dict:
    """Write .rkm.env + .rkm_state.json from the env; returns api_vars."""
    api_vars = build_api_vars(env)
    API_ENV.write_text("".join(f"{k}={v}\n" for k, v in api_vars.items()), encoding="utf-8")
    print(f"wrote {API_ENV.name} (backend={api_vars['MEDIA_SERVER']})")

    summary = {
        "config_file": str(ENV_PATH),
        "data_path": str(data),
        "backend": api_vars["MEDIA_SERVER"],
        "dashboard": f"http://localhost:{env.get('RKM_DASHBOARD_PORT') or '8124'}",
        "jellyfin_browser": api_vars["JELLYFIN_BROWSER_URL"],
        "watchlist_store": api_vars["WATCHLIST_STORE"],
    }
    STATE_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return api_vars


def main() -> None:
    env = ensure_defaults()
    data = resolve_data_path(env)
    ensure_storage(data, env)
    api = render(env, data)
    print(f"\nConfig rendered from {ENV_PATH.name} (single source). Next: run bootstrap.sh "
          f"(or .\\bootstrap.ps1).")
    if api["MEDIA_SERVER"] == "jellyfin":
        print(f"Jellyfin admin: user={env.get('RKM_JELLYFIN_ADMIN_USER') or 'admin'} — "
              f"password in {ENV_PATH.name} (RKM_JELLYFIN_ADMIN_PASSWORD).")


if __name__ == "__main__":
    main()
