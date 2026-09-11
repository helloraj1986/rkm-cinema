"""Centralized configuration management for RKM Watchlist."""
import os
from pathlib import Path
from typing import Optional
from functools import lru_cache

from config.media_libraries import parse_media_libraries

#: Env-key FAMILIES the media-library parser needs, beyond the declared config
#: keys above. Expressed as a prefix predicate so the contract is testable: a key
#: the parser needs but that is NOT covered here is silently dropped from the
#: environment, and then every host-style library path stops translating.
#: 2026-09-10: RKM_MEDIA_PATH was in neither list, so the api had no media roots,
#: could not translate D:/B: paths, and reported ALL libraries unresolved — the
#: sidebar greyed out every one of them while Jellyfin's own folders were correct.
MEDIA_CONFIG_KEY_PREFIXES = ("MEDIA_LIBRARY_", "RKM_MEDIA_PATH")

#: Keys that are READ from the environment but never annotated on the class, so
#: the derived key set in :meth:`Config._get_all_keys` cannot see them. Keep this
#: list empty if possible — annotating the attribute is the better fix.
_EXTRA_ENV_KEYS = {"TMDB_CACHE_TTL", "PLEX_SCAN_TTL"}


def is_env_passthrough_key(key: str) -> bool:
    """True when a real environment variable must reach the config env.

    Covers the ``MEDIA_LIBRARY_N_*`` declarations AND every media root
    (``RKM_MEDIA_PATH``, ``RKM_MEDIA_PATH_2``, ``RKM_MEDIA_PATH_3`` …). Deliberately
    narrow: other ``RKM_*`` keys (admin passwords, ports) stay out of the api's
    config on purpose.
    """
    return any(str(key).startswith(p) for p in MEDIA_CONFIG_KEY_PREFIXES)


#: The media servers this app knows how to read.
MEDIA_SERVERS = ("jellyfin", "plex", "emby")


def resolve_media_server(raw: Optional[str]) -> str:
    """Which library backend a ``MEDIA_SERVER`` value selects.

    JELLYFIN is the default, and the fallback for anything unrecognised: the
    bundled self-contained stack is the only deployment, so an unset, blank or
    typo'd value must never silently re-select the retired Plex-primary path.
    (Before 2026-09-11 the default was ``"plex"`` — a missing key quietly switched
    the whole library backend, and the symptom was every library row greyed out,
    which reads like a broken drive mount rather than a config default.)

    ONE rule, shared by the config loader, the provider factory and ``/api/config``
    so the three can never disagree about what a value means.
    """
    value = (raw or "").strip().lower()
    return value if value in MEDIA_SERVERS else "jellyfin"


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
    # Primary library backend. Default "jellyfin" — the bundled self-contained
    # stack is the only deployment now (the old Plex-primary + Emby-fallback
    # profile is retired). "plex"/"emby" are still accepted for legacy configs,
    # but nothing deploys them any more.
    MEDIA_SERVER: str = "jellyfin"

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
    JELLYFIN_BROWSER_URL: Optional[str]

    # --- Quality profile overrides (optional) ---
    RADARR_QUALITY_PROFILE_ID: Optional[int]
    SONARR_QUALITY_PROFILE_ID: Optional[int]

    # --- Persistence (Phase 3) ---
    WATCHLIST_STORE: str            # 'json' (default) | 'sqlite'
    WATCHLIST_DB_PATH: Optional[str]  # SQLite file path; ':memory:' for tests

    # --- Scheduling (Phase 13/14) ---
    WATCHLIST_SCHEDULER: bool       # run the in-process background job loop (spec §26)
    AUTO_ADD_ENABLED: bool          # gate the autonomous daily recommendation auto-add
    RECONCILE_INTERVAL_MIN: int     # frequent reconcile cadence (default 10 min)
    DAILY_JOB_HOUR: int             # daily recommendation job hour (24h, default 18)

    # --- Media libraries (MEDIA_LIBRARIES_PLAN) ---
    # Parsed from MEDIA_LIBRARY_N_NAME/PATH .env keys. Empty when the user has
    # not configured any — the UI then falls back to the server's own folders.
    media_libraries: list        # list[MediaLibrary]
    media_library_warnings: list # list[str] — config problems worth surfacing

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
            # Repo-level single-source .env (repo root = backend/../..) — used
            # when running from a bare checkout with no /workspace or /app env.
            Path(__file__).resolve().parent.parent.parent / ".env",
        ]
        for path in canonical_paths:
            if path.exists():
                for line in path.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        env[k.strip()] = v.strip()
                break

        # 1.5 Provisioner-written runtime config (bundled stack). The one-shot
        # provisioner writes /shared/runtime.json with the freshly-created
        # Jellyfin/Emby/Prowlarr URLs + API keys it set up (chicken-and-egg:
        # these don't exist until the service containers are up). This layer
        # overrides .env but stays below real env vars.
        try:
            runtime_path = os.environ.get("RKM_RUNTIME_PATH", "/shared/runtime.json")
            if os.path.exists(runtime_path):
                import json as _json
                with open(runtime_path, encoding="utf-8") as _f:
                    runtime = _json.load(_f)
                for k, v in (runtime or {}).items():
                    if k in self._get_all_keys() and v not in (None, ""):
                        env[k] = str(v)
        except Exception:  # never let a bad runtime file break boot
            pass

        # 2. Real environment variables override .env
        for key, value in self._env_passthrough(os.environ).items():
            env[key] = value

        # Assign with validation
        self.MEDIA_HOST = env.get("MEDIA_HOST", "192.168.65.254")
        self.RADARR_URL = self._normalize_url(env.get("RADARR_URL", f"http://{self.MEDIA_HOST}:7878"))
        self.RADARR_API_KEY = env.get("RADARR_API_KEY", "")
        self.SONARR_URL = self._normalize_url(env.get("SONARR_URL", f"http://{self.MEDIA_HOST}:8989"))
        self.SONARR_API_KEY = env.get("SONARR_API_KEY", "")
        self.PLEX_URL = self._normalize_url(env.get("PLEX_URL", f"http://{self.MEDIA_HOST}:32400"))
        self.PLEX_TOKEN = env.get("PLEX_TOKEN", "")
        self.MEDIA_SERVER = resolve_media_server(env.get("MEDIA_SERVER"))

        self.TMDB_API_KEY = env.get("TMDB_API_KEY") or None
        self.TVDB_API_KEY = env.get("TVDB_API_KEY") or None
        # TMDB metadata cache TTL (seconds). Metadata is stable over hours/days,
        # so we cache it long instead of re-fetching per title (spec §29).
        try:
            self.TMDB_CACHE_TTL = int(env.get("TMDB_CACHE_TTL") or 21600)  # 6h default
        except ValueError:
            self.TMDB_CACHE_TTL = 21600
        # Plex full-library scan cache TTL (seconds). The library changes rarely,
        # so the refresh button / reconcile reuse one scan instead of re-scanning
        # Plex on every click. Default 1h; invalidate via clear_cache() on writes.
        try:
            self.PLEX_SCAN_TTL = int(env.get("PLEX_SCAN_TTL") or 3600)
        except ValueError:
            self.PLEX_SCAN_TTL = 3600
        self.JELLYFIN_URL = self._normalize_url(env["JELLYFIN_URL"]) if env.get("JELLYFIN_URL") else None
        self.JELLYFIN_API_KEY = env.get("JELLYFIN_API_KEY") or None
        self.JELLYFIN_BROWSER_URL = self._normalize_url(env.get("JELLYFIN_BROWSER_URL") or "") or None
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
        # Autonomous daily auto-add gate. Default TRUE (historical behaviour); the
        # bundled stack sets AUTO_ADD_ENABLED=false so a fresh install is
        # Suggest-only until the user opts into automation (decision 2026-09).
        self.AUTO_ADD_ENABLED = (env.get("AUTO_ADD_ENABLED") or "true").strip().lower() not in ("0", "false", "no", "off")
        try:
            self.RECONCILE_INTERVAL_MIN = int(env.get("RECONCILE_INTERVAL_MIN") or 10)
        except ValueError:
            self.RECONCILE_INTERVAL_MIN = 10
        try:
            self.DAILY_JOB_HOUR = int(env.get("DAILY_JOB_HOUR") or 18)
        except ValueError:
            self.DAILY_JOB_HOUR = 18

        # Media libraries (MEDIA_LIBRARIES_PLAN Phase 1): parsed here in the
        # dedicated settings layer — never read MEDIA_LIBRARY_* anywhere else.
        self.media_libraries, self.media_library_warnings = parse_media_libraries(env)

    def _env_passthrough(self, environ) -> dict:
        """The real env vars that override .env — declared keys + media families.

        Extracted so the contract is directly testable: if a key the media-library
        parser needs is not covered here, it silently disappears from the api's
        environment and every host-style library path stops translating
        (2026-09-10 regression — see MEDIA_CONFIG_KEY_PREFIXES).
        """
        return {k: v for k, v in environ.items()
                if k in self._get_all_keys() or is_env_passthrough_key(k)}

    def _get_all_keys(self) -> set:
        """Every env key this config reads.

        DERIVED from the class annotations rather than hand-listed: a setting
        declared on the class can no longer be added and then silently dropped
        from the real-env passthrough. That is not hypothetical — on 2026-09-10
        ``RKM_MEDIA_PATH`` was absent from the hand-written list, so the api had no
        media roots and every configured library went unresolved, while
        ``EMBY_URL``/``EMBY_API_KEY``/``YOUTUBE_API_KEY`` were quietly missing from
        it in exactly the same way.
        """
        annotated = {name for name in getattr(type(self), "__annotations__", {})
                     if name.isupper() and not name.startswith("_")}
        return annotated | _EXTRA_ENV_KEYS
    def _normalize_url(self, url: str) -> str:
        """Ensure URL has no trailing slash."""
        return url.rstrip("/")

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