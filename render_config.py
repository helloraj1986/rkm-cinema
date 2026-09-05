#!/usr/bin/env python3
"""Render rkm.config.toml → the compose `.env` + api `.rkm.env` for the bundled stack.

Also creates the storage tree (./data/media/{_movie,_tv}, ./data/downloads,
./data/rkm). Run inside bootstrap.sh / bootstrap.ps1 before `docker compose up`.

The TOML is the single source of truth; this script is the only bridge to the
compose/env files, so there is exactly one place to configure the stack.

Python 3.11+ (uses stdlib `tomllib`). Run from the repo root.
"""
from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPOSE_ENV = ROOT / ".env"          # compose ${VAR} substitution
API_ENV = ROOT / ".rkm.env"          # api container env_file

# Jellyfin container host + internal port (service name on the rkm-exp network).
JELLYFIN_INTERNAL = "http://jellyfin:8096"


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_config() -> dict:
    cfg_path = ROOT / "rkm.config.toml"
    if not cfg_path.exists():
        fail("rkm.config.toml not found. Copy rkm.config.example.toml -> rkm.config.toml and fill it in.")
    with open(cfg_path, "rb") as f:
        return tomllib.load(f)


def resolve_data_path(cfg: dict) -> Path:
    raw = str((cfg.get("storage") or {}).get("runtime_app_media_path", "./data"))
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p


def ensure_storage(data: Path) -> None:
    for sub in ("media/_movie", "media/_tv", "downloads", "rkm"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    print(f"storage tree ready at: {data}")


def render(cfg: dict, data: Path) -> None:
    app = cfg.get("app", {})
    media_cfg = cfg.get("media_server", {})
    tmdb = cfg.get("tmdb", {})
    rec = cfg.get("recommend", {})
    arr = cfg.get("arr", {})

    if not tmdb.get("api_key") or tmdb["api_key"] == "REPLACE_ME":
        fail("[tmdb] api_key is required (free from TMDB settings). Edit rkm.config.toml.")
    backend = str(media_cfg.get("backend", "jellyfin")).lower()
    if backend not in ("jellyfin", "plex", "emby"):
        fail(f"media_server.backend must be jellyfin|plex|emby, got: {backend}")

    # --- .env for compose ${VAR} substitution ---
    compose_vars = {
        "RKM_MEDIA_PATH": str(data),
        "RKM_DASHBOARD_PORT": str(app.get("dashboard_port", 8124)),
        "RKM_JELLYFIN_PORT": "8098",
        "RKM_TIMEZONE": str(app.get("timezone", "Australia/Melbourne")),
        "RKM_PUID": "1000",
        "RKM_PGID": "1000",
        "RKM_PROJECT": "rkm-bundled",
        "RKM_JELLYFIN_BROWSER": str(media_cfg.get("jellyfin_browser_url", "http://localhost:8098")).rstrip("/"),
        "RKM_JELLYFIN_ADMIN_USER": str(media_cfg.get("jellyfin_admin_user", "admin")),
        "RKM_JELLYFIN_ADMIN_PASSWORD": str(media_cfg.get("jellyfin_admin_password", "")),
        "RKM_QBT_TORRENT_PORT": str((cfg.get("qbit") or {}).get("torrent_port", 6881)),
    }
    COMPOSE_ENV.write_text("".join(f"{k}={v}\n" for k, v in compose_vars.items()), encoding="utf-8")
    print(f"wrote {COMPOSE_ENV.name} ({len(compose_vars)} vars)")

    # --- .rkm.env for the api container ---
    api_vars = {
        "MEDIA_SERVER": backend,
        # Backup: if the provisioner hasn't written runtime.json yet, ask the
        # provisioner container URL; runtime.json overrides this with the real key.
        "JELLYFIN_URL": JELLYFIN_INTERNAL,
        "JELLYFIN_BROWSER_URL": str(media_cfg.get("jellyfin_browser_url", "http://localhost:8098")).rstrip("/"),
        "TMDB_API_KEY": str(tmdb.get("api_key", "")),
        "TVDB_API_KEY": str((cfg.get("tvdb") or {}).get("api_key", "")),
        "WATCHLIST_STORE": "json",
        "WATCHLIST_DB_PATH": str(data / "rkm" / "watchlist.json"),
        "WATCHLIST_SCHEDULER": "true",
        "AUTO_ADD_ENABLED": str(bool(rec.get("auto_add_enabled", False))).lower(),
        "RECONCILE_INTERVAL_MIN": str(rec.get("reconcile_interval_min", 10)),
        "DAILY_JOB_HOUR": str(rec.get("auto_add_hour", 18)),
        "RKM_RUNTIME_PATH": "/shared/runtime.json",
        # Internal-only URLs (service names; Radarr/Sonarr are on the fullstack profile).
        "RADARR_URL": "http://radarr:7878",
        "SONARR_URL": "http://sonarr:8989",
        "PROWLARR_URL": "http://prowlarr:9696",
        "QBITTORRENT_URL": "http://qbittorrent:8080",
    }
    API_ENV.write_text("".join(f"{k}={v}\n" for k, v in api_vars.items()), encoding="utf-8")
    print(f"wrote {API_ENV.name} (backend={backend})")

    # Export a small resolved summary for other scripts/verify steps.
    summary = {
        "data_path": str(data),
        "jellyfin_internal": JELLYFIN_INTERNAL,
        "dashboard": f"http://localhost:{app.get('dashboard_port', 8124)}",
        "jellyfin_browser": api_vars["JELLYFIN_BROWSER_URL"],
        "auto_add_enabled": bool(rec.get("auto_add_enabled", False)),
    }
    (ROOT / ".rkm_state.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    cfg = load_config()
    data = resolve_data_path(cfg)
    ensure_storage(data)
    render(cfg, data)
    print("\nConfig rendered. Next: run bootstrap.sh (or .\\bootstrap.ps1).")


if __name__ == "__main__":
    main()