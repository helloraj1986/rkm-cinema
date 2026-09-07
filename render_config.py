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


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


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
        v = v.strip().strip('"').strip("'")
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


def ensure_defaults() -> dict:
    """Fill safe defaults into .env (if the file is missing, seed it from
    .env.example), then return the parsed env."""
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
        env = parse_env_file(ENV_PATH)
        print(f"[env] filled {len(added)} default key(s) into {ENV_PATH.name}: {', '.join(added)}")
    return env


def resolve_data_path(env: dict) -> Path:
    raw = str(env.get("RKM_MEDIA_PATH") or "./data")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p


def ensure_storage(data: Path) -> None:
    for sub in ("media/_movie", "media/_tv", "downloads", "rkm"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    print(f"storage tree ready at: {data}")


def build_api_vars(env: dict) -> dict:
    """Derive the api container env from the single repo .env (pure mapping —
    unit-testable). Container-internal addresses are resolved here."""
    backend = str(env.get("MEDIA_SERVER") or "jellyfin").strip().lower()
    if backend not in ("jellyfin", "plex", "emby"):
        fail(f"MEDIA_SERVER must be jellyfin|plex|emby, got: {backend}")

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
        # Plex/Emby always passed through (used when MEDIA_SERVER=plex|emby).
        "PLEX_URL": str(env.get("PLEX_URL") or "").strip(),
        "PLEX_TOKEN": str(env.get("PLEX_TOKEN") or "").strip(),
        "EMBY_URL": str(env.get("EMBY_URL") or "").strip(),
        "EMBY_API_KEY": str(env.get("EMBY_API_KEY") or "").strip(),
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
    ensure_storage(data)
    api = render(env, data)
    print(f"\nConfig rendered from {ENV_PATH.name} (single source). Next: run bootstrap.sh "
          f"(or .\\bootstrap.ps1).")
    if api["MEDIA_SERVER"] == "jellyfin":
        print(f"Jellyfin admin: user={env.get('RKM_JELLYFIN_ADMIN_USER') or 'admin'} — "
              f"password in {ENV_PATH.name} (RKM_JELLYFIN_ADMIN_PASSWORD).")


if __name__ == "__main__":
    main()
