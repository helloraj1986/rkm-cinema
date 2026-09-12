"""Centralized configuration management for RKM Watchlist."""
import os
from pathlib import Path
from typing import Optional
from functools import lru_cache

from config.env_file import parse_env_file
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
_EXTRA_ENV_KEYS = {"TMDB_CACHE_TTL"}


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


def canonical_env_paths() -> list:
    """The `.env` files a bare-checkout / container run may read, in order.

    A module-level seam rather than an inline literal, so a test can point the
    config layer at a fixed file and assert HOW it reads it: the 2026-09-12 parity
    fix (quote handling + BOM tolerance, see :mod:`config.env_file`) is otherwise
    only reachable through the developer's own `.env`. First existing file wins.
    """
    return [
        Path("/workspace/.env"),          # host-backed workspace env
        Path("/app/.env"),                # container-local fallback
        # Repo-level single-source .env (repo root = backend/../..) — used when
        # running from a bare checkout with no /workspace or /app env.
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]


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
    # Media server selector. Jellyfin is the ONLY backend this build can wire
    # (the bundled self-contained stack); the old Plex-primary + Emby-fallback
    # profile is retired, so this value no longer selects anything — it is kept
    # so an un-updated `.env` still loads, and "plex"/"emby" are still accepted as
    # VALUES for exactly that reason (see resolve_media_server).
    MEDIA_SERVER: str = "jellyfin"

    # --- Optional ---
    TMDB_API_KEY: Optional[str]
    TVDB_API_KEY: Optional[str]
    JELLYFIN_URL: Optional[str]
    JELLYFIN_API_KEY: Optional[str]
    PROWLARR_URL: Optional[str]
    PROWLARR_API_KEY: Optional[str]
    YOUTUBE_API_KEY: Optional[str]
    QBITTORRENT_URL: str
    # Browser-reachable (Tailscale MagicDNS) endpoint for deep links. Cloud links
    # fail to auto-open; this points at the local server's own web UI.
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

    # --- Subtitles / OpenSubtitles (SUBTITLES_OPENSUBTITLES_PLAN §3.1) ---
    # The API key identifies the APPLICATION and is mandatory on every call; it
    # carries the anonymous allowance (5 downloads / 24h per IP). The username +
    # password identify the USER and only raise the quota, so they are OPTIONAL:
    # a missing login degrades to anonymous, never to "disabled".
    # Annotating these on the class is what makes the real-env passthrough carry
    # the keys at all — an undeclared key is dropped before the app ever sees it
    # (the 2026-09-10 RKM_MEDIA_PATH bug, which greyed out every library).
    OPENSUBTITLES_API_KEY: Optional[str]
    OPENSUBTITLES_USERNAME: Optional[str]
    OPENSUBTITLES_PASSWORD: Optional[str]
    OPENSUBTITLES_LANGUAGES: str    # comma list, e.g. "en" or "en,hi"
    OPENSUBTITLES_ENABLED: str      # 'auto' (default) | true | false

    # --- Auth / multi-user (AUTH_MULTIUSER_PLAN §3, Phase 0) ---
    # Enforcement is a FLAG, not a code path: 'false' (the default) means a request
    # with no session behaves exactly as it did before this feature existed, which is
    # the escape hatch the lockout recovery relies on. Phase 2 flips the default in
    # .env.example; the live .env keeps its own value. Annotated HERE so the real-env
    # passthrough carries it — an undeclared key is dropped silently (the 2026-09-10
    # RKM_MEDIA_PATH bug, which greyed out every library).
    RKM_AUTH_REQUIRED: str

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
        for path in canonical_env_paths():
            if path.exists():
                # ONE parser for every reader of this file (config/env_file.py):
                # quoting, inline comments and a leading BOM are read the same way
                # here as they are by render_config and the probe tools. This layer
                # used to do a bare partition("=") + strip(), so a quoted value
                # arrived WITH its quotes — a password containing '#' or a space
                # was then truncated or wrong on a bare-checkout run while the
                # container (which receives the rendered .rkm.env) was fine.
                env.update(parse_env_file(path))
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
        self.MEDIA_SERVER = resolve_media_server(env.get("MEDIA_SERVER"))

        self.TMDB_API_KEY = env.get("TMDB_API_KEY") or None
        self.TVDB_API_KEY = env.get("TVDB_API_KEY") or None
        # TMDB metadata cache TTL (seconds). Metadata is stable over hours/days,
        # so we cache it long instead of re-fetching per title (spec §29).
        try:
            self.TMDB_CACHE_TTL = int(env.get("TMDB_CACHE_TTL") or 21600)  # 6h default
        except ValueError:
            self.TMDB_CACHE_TTL = 21600
        self.JELLYFIN_URL = self._normalize_url(env["JELLYFIN_URL"]) if env.get("JELLYFIN_URL") else None
        self.JELLYFIN_API_KEY = env.get("JELLYFIN_API_KEY") or None
        self.JELLYFIN_BROWSER_URL = self._normalize_url(env.get("JELLYFIN_BROWSER_URL") or "") or None
        self.PROWLARR_URL = self._normalize_url(env["PROWLARR_URL"]) if env.get("PROWLARR_URL") else None
        self.PROWLARR_API_KEY = env.get("PROWLARR_API_KEY") or None
        self.YOUTUBE_API_KEY = env.get("YOUTUBE_API_KEY") or None
        self.QBITTORRENT_URL = self._normalize_url(env.get("QBITTORRENT_URL", f"http://{self.MEDIA_HOST}:1701"))

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

        # Subtitles / OpenSubtitles. Blank is normal (the feature is optional), so
        # these are never validated as required — the app boots and plays fine
        # without them and only the subtitle SEARCH section degrades.
        self.OPENSUBTITLES_API_KEY = (env.get("OPENSUBTITLES_API_KEY") or "").strip() or None
        self.OPENSUBTITLES_USERNAME = (env.get("OPENSUBTITLES_USERNAME") or "").strip() or None
        self.OPENSUBTITLES_PASSWORD = (env.get("OPENSUBTITLES_PASSWORD") or "").strip() or None
        self.OPENSUBTITLES_LANGUAGES = (env.get("OPENSUBTITLES_LANGUAGES") or "en").strip() or "en"
        self.OPENSUBTITLES_ENABLED = (env.get("OPENSUBTITLES_ENABLED") or "auto").strip().lower()

        # Auth / multi-user (AUTH_MULTIUSER_PLAN Phase 0). Default FALSE: nothing is
        # enforced until the login UI has shipped (Phase 2 arms it), so an
        # un-updated `.env` keeps working exactly as before.
        self.RKM_AUTH_REQUIRED = (env.get("RKM_AUTH_REQUIRED") or "false").strip().lower()

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
        """Return list of missing required configuration.

        Deliberately does NOT require a Jellyfin credential: a fresh install
        legitimately has no ``JELLYFIN_API_KEY`` until the provisioner writes one,
        so a hard requirement would warn on every first boot. ``/api/health``
        reports the media server's configured/ok state, which is the right place
        for it. (It used to require ``PLEX_TOKEN``, so a Jellyfin-only stack
        logged a false `Missing required config: ['PLEX_TOKEN']` on every boot.)
        """
        missing = []
        if not self.RADARR_API_KEY:
            missing.append("RADARR_API_KEY")
        if not self.SONARR_API_KEY:
            missing.append("SONARR_API_KEY")
        return missing

    def has_tmdb(self) -> bool:
        return bool(self.TMDB_API_KEY)

    def has_tvdb(self) -> bool:
        return bool(self.TVDB_API_KEY)

    def has_jellyfin(self) -> bool:
        return bool(self.JELLYFIN_URL and self.JELLYFIN_API_KEY)

    def has_youtube(self) -> bool:
        return bool(self.YOUTUBE_API_KEY)

    def has_prowlarr(self) -> bool:
        return bool(self.PROWLARR_URL and self.PROWLARR_API_KEY)

    # --- Subtitles / OpenSubtitles -------------------------------------------
    def opensubtitles_disabled(self) -> bool:
        """True when the user explicitly switched subtitle search off in `.env`."""
        return self.OPENSUBTITLES_ENABLED in ("0", "false", "no", "off")

    def has_opensubtitles(self) -> bool:
        """True when the OpenSubtitles client is usable.

        Keys off the **API key alone** (plan §3.1): the key is the application's
        identity and carries the anonymous allowance (5 downloads / 24h per IP),
        while the username/password are the *user's* identity and only raise the
        quota (rank-dependent). So a missing login must degrade to anonymous —
        never to "disabled", which is the bug this rule exists to prevent. An
        explicit ``OPENSUBTITLES_ENABLED=false`` is the one way to turn it off.
        """
        return bool(self.OPENSUBTITLES_API_KEY) and not self.opensubtitles_disabled()

    def opensubtitles_languages(self) -> list:
        """Default subtitle languages (lowercased, de-duplicated, order kept).

        Read by the UI as the default search language; the stored per-item
        preference always wins over this list.
        """
        seen, out = set(), []
        for raw in str(self.OPENSUBTITLES_LANGUAGES or "").split(","):
            code = raw.strip().lower()
            if code and code not in seen:
                seen.add(code)
                out.append(code)
        return out or ["en"]

    def has_opensubtitles_login(self) -> bool:
        """True when a username AND password are present (raises the quota).

        Deliberately separate from :meth:`has_opensubtitles`: the login is an
        upgrade to the anonymous tier, not a requirement.
        """
        return bool(self.OPENSUBTITLES_USERNAME and self.OPENSUBTITLES_PASSWORD)

    # --- Auth / multi-user ------------------------------------------------
    def auth_required(self) -> bool:
        """True when a request without a session must be answered with a 401.

        Read PER REQUEST (never cached at startup) so the documented lockout recovery
        — set ``RKM_AUTH_REQUIRED=false`` and recreate the api — takes effect at once.
        Default is False: Phase 0 ships the endpoints with NOTHING enforced, and the
        login UI ships (Phase 1) before Phase 2 arms this.
        """
        return self.RKM_AUTH_REQUIRED in ("1", "true", "yes", "on")


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