"""Centralized configuration management for RKM Watchlist."""
import os
from pathlib import Path
from typing import Optional
from functools import lru_cache


class Config:
    """Single source of truth for all environment configuration."""

    # --- Required ---
    MEDIA_HOST: str
    RADARR_URL: str
    RADARR_API_KEY: str
    SONARR_URL: str
    SONARR_API_KEY: str
    PLEX_URL: str
    PLEX_TOKEN: str

    # --- Optional ---
    TMDB_API_KEY: Optional[str]
    TVDB_API_KEY: Optional[str]
    JELLYFIN_URL: Optional[str]
    JELLYFIN_API_KEY: Optional[str]
    PROWLARR_URL: Optional[str]
    PROWLARR_API_KEY: Optional[str]
    EMBY_URL: Optional[str]
    EMBY_API_KEY: Optional[str]
    YOUTUBE_API_KEY: Optional[str]
    QBITTORRENT_URL: str
    # Browser-reachable (Tailscale MagicDNS) endpoints for deep links. `app.plex.tv`
    # cloud links fail to auto-open; these point at the local server's own web UI.
    PLEX_BROWSER_URL: Optional[str]
    EMBY_BROWSER_URL: Optional[str]

    # --- Quality profile overrides (optional) ---
    RADARR_QUALITY_PROFILE_ID: Optional[int]
    SONARR_QUALITY_PROFILE_ID: Optional[int]

    # --- Persistence (Phase 3) ---
    WATCHLIST_STORE: str            # 'json' (default) | 'sqlite'
    WATCHLIST_DB_PATH: Optional[str]  # SQLite file path; ':memory:' for tests

    # --- Scheduling (Phase 13/14) ---
    WATCHLIST_SCHEDULER: bool       # run the in-process background job loop (spec §26)
    RECONCILE_INTERVAL_MIN: int     # frequent reconcile cadence (default 10 min)
    DAILY_JOB_HOUR: int             # daily recommendation job hour (24h, default 18)

    # --- Internal ---
    _loaded: bool = False

    def __init__(self):
        if self._loaded:
            return
        self._load()
        self._loaded = True

    def _load(self):
        """Load from canonical .env file, then override with real env vars."""
        env = {}

        # 1. Canonical .env file (host-backed at /workspace/.env = D:\.env)
        canonical_paths = [
            Path("/workspace/.env"),
            Path("/app/.env"),
        ]
        for path in canonical_paths:
            if path.exists():
                for line in path.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        env[k.strip()] = v.strip()
                break

        # 2. Real environment variables override .env
        for key in os.environ:
            if key in self._get_all_keys():
                env[key] = os.environ[key]

        # Assign with validation
        self.MEDIA_HOST = env.get("MEDIA_HOST", "192.168.65.254")
        self.RADARR_URL = self._normalize_url(env.get("RADARR_URL", f"http://{self.MEDIA_HOST}:7878"))
        self.RADARR_API_KEY = env.get("RADARR_API_KEY", "")
        self.SONARR_URL = self._normalize_url(env.get("SONARR_URL", f"http://{self.MEDIA_HOST}:8989"))
        self.SONARR_API_KEY = env.get("SONARR_API_KEY", "")
        self.PLEX_URL = self._normalize_url(env.get("PLEX_URL", f"http://{self.MEDIA_HOST}:32400"))
        self.PLEX_TOKEN = env.get("PLEX_TOKEN", "")

        self.TMDB_API_KEY = env.get("TMDB_API_KEY") or None
        self.TVDB_API_KEY = env.get("TVDB_API_KEY") or None
        self.JELLYFIN_URL = self._normalize_url(env["JELLYFIN_URL"]) if env.get("JELLYFIN_URL") else None
        self.JELLYFIN_API_KEY = env.get("JELLYFIN_API_KEY") or None
        self.PROWLARR_URL = self._normalize_url(env["PROWLARR_URL"]) if env.get("PROWLARR_URL") else None
        self.PROWLARR_API_KEY = env.get("PROWLARR_API_KEY") or None
        self.EMBY_URL = env.get("EMBY_URL") or None
        self.EMBY_API_KEY = env.get("EMBY_API_KEY") or None
        self.YOUTUBE_API_KEY = env.get("YOUTUBE_API_KEY") or None
        self.QBITTORRENT_URL = self._normalize_url(env.get("QBITTORRENT_URL", f"http://{self.MEDIA_HOST}:1701"))
        self.PLEX_BROWSER_URL = self._normalize_url(env.get("PLEX_BROWSER_URL") or "") or None
        self.EMBY_BROWSER_URL = self._normalize_url(env.get("EMBY_BROWSER_URL") or "") or None

        # Optional quality profile overrides
        radarr_qp = env.get("RADARR_QUALITY_PROFILE_ID")
        self.RADARR_QUALITY_PROFILE_ID = int(radarr_qp) if radarr_qp and radarr_qp.isdigit() else None
        sonarr_qp = env.get("SONARR_QUALITY_PROFILE_ID")
        self.SONARR_QUALITY_PROFILE_ID = int(sonarr_qp) if sonarr_qp and sonarr_qp.isdigit() else None

        # Persistence (Phase 3): 'json' default for backward-compat, 'sqlite' for the new store.
        self.WATCHLIST_STORE = (env.get("WATCHLIST_STORE") or "json").strip().lower()
        if self.WATCHLIST_STORE not in ("json", "sqlite"):
            self.WATCHLIST_STORE = "json"
        self.WATCHLIST_DB_PATH = env.get("WATCHLIST_DB_PATH") or None

        # Scheduling (Phase 13/14). Off by default; enable via WATCHLIST_SCHEDULER=true.
        self.WATCHLIST_SCHEDULER = (env.get("WATCHLIST_SCHEDULER") or "").strip().lower() in ("1", "true", "yes", "on")
        try:
            self.RECONCILE_INTERVAL_MIN = int(env.get("RECONCILE_INTERVAL_MIN") or 10)
        except ValueError:
            self.RECONCILE_INTERVAL_MIN = 10
        try:
            self.DAILY_JOB_HOUR = int(env.get("DAILY_JOB_HOUR") or 18)
        except ValueError:
            self.DAILY_JOB_HOUR = 18

    def _normalize_url(self, url: str) -> str:
        """Ensure URL has no trailing slash."""
        return url.rstrip("/")

    def _get_all_keys(self) -> set:
        return {
            "MEDIA_HOST", "RADARR_URL", "RADARR_API_KEY", "SONARR_URL", "SONARR_API_KEY",
            "PLEX_URL", "PLEX_TOKEN", "TMDB_API_KEY", "TVDB_API_KEY", "JELLYFIN_URL",
            "JELLYFIN_API_KEY", "PROWLARR_URL", "PROWLARR_API_KEY", "QBITTORRENT_URL",
            "RADARR_QUALITY_PROFILE_ID", "SONARR_QUALITY_PROFILE_ID",
            "PLEX_BROWSER_URL", "EMBY_BROWSER_URL",
            "WATCHLIST_STORE", "WATCHLIST_DB_PATH",
            "WATCHLIST_SCHEDULER", "RECONCILE_INTERVAL_MIN", "DAILY_JOB_HOUR",
        }

    def validate_required(self) -> list[str]:
        """Return list of missing required configuration."""
        missing = []
        if not self.RADARR_API_KEY:
            missing.append("RADARR_API_KEY")
        if not self.SONARR_API_KEY:
            missing.append("SONARR_API_KEY")
        if not self.PLEX_TOKEN:
            missing.append("PLEX_TOKEN")
        return missing

    def has_tmdb(self) -> bool:
        return bool(self.TMDB_API_KEY)

    def has_tvdb(self) -> bool:
        return bool(self.TVDB_API_KEY)

    def has_jellyfin(self) -> bool:
        return bool(self.JELLYFIN_URL and self.JELLYFIN_API_KEY)

    def has_emby(self) -> bool:
        return bool(self.EMBY_URL and self.EMBY_API_KEY)

    def has_youtube(self) -> bool:
        return bool(self.YOUTUBE_API_KEY)

    def has_prowlarr(self) -> bool:
        return bool(self.PROWLARR_URL and self.PROWLARR_API_KEY)


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Get singleton config instance."""
    return Config()


# Convenience function for scripts that don't need full DI
def load_env() -> dict:
    """Load raw env dict (legacy compatibility)."""
    cfg = get_config()
    return {
        "MEDIA_HOST": cfg.MEDIA_HOST,
        "RADARR_URL": cfg.RADARR_URL,
        "RADARR_API_KEY": cfg.RADARR_API_KEY,
        "SONARR_URL": cfg.SONARR_URL,
        "SONARR_API_KEY": cfg.SONARR_API_KEY,
        "PLEX_URL": cfg.PLEX_URL,
        "PLEX_TOKEN": cfg.PLEX_TOKEN,
        "TMDB_API_KEY": cfg.TMDB_API_KEY or "",
        "TVDB_API_KEY": cfg.TVDB_API_KEY or "",
        "JELLYFIN_URL": cfg.JELLYFIN_URL or "",
        "JELLYFIN_API_KEY": cfg.JELLYFIN_API_KEY or "",
        "PROWLARR_URL": cfg.PROWLARR_URL or "",
        "PROWLARR_API_KEY": cfg.PROWLARR_API_KEY or "",
        "QBITTORRENT_URL": cfg.QBITTORRENT_URL,
        "RADARR_QUALITY_PROFILE_ID": str(cfg.RADARR_QUALITY_PROFILE_ID) if cfg.RADARR_QUALITY_PROFILE_ID else "",
        "SONARR_QUALITY_PROFILE_ID": str(cfg.SONARR_QUALITY_PROFILE_ID) if cfg.SONARR_QUALITY_PROFILE_ID else "",
    }