"""Config's real-env passthrough must carry the media-library keys (2026-09-10).

REGRESSION: the api copied only its DECLARED keys plus ``MEDIA_LIBRARY_*`` from the
real environment, so ``RKM_MEDIA_PATH`` / ``RKM_MEDIA_PATH_2`` never arrived. The
parser then had NO media roots, could not translate any host-style path, and the
app reported every configured library unresolved — the sidebar greyed out all
three libraries (Movies Kids, Movies, TV Shows) while Jellyfin's own folders were
correct, because the PROVISIONER reads ``os.environ`` directly and therefore
disagreed with the api.

These tests go through the real Config method, not a copy of its logic, so a
future edit to that filter fails here.
"""
from config.media_libraries import parse_media_libraries
from config.settings import Config, is_env_passthrough_key


class TestConfigKeysCoverage:
    """The hand-written key list is gone — every declared setting must pass through."""

    #: Snapshot of the keys the app is known to read. Updated 2026-09-11: the
    #: Plex/Emby settings were deleted with their providers
    #: (docs/REMOVE_PLEX_EMBY_PLAN.md). If a setting is renamed/removed this test
    #: should be updated deliberately, never silently — that is its whole job.
    KNOWN_KEYS = {
        "MEDIA_HOST", "RADARR_URL", "RADARR_API_KEY", "SONARR_URL", "SONARR_API_KEY",
        "MEDIA_SERVER", "TMDB_API_KEY", "TVDB_API_KEY",
        "JELLYFIN_URL", "JELLYFIN_API_KEY", "JELLYFIN_BROWSER_URL", "PROWLARR_URL",
        "PROWLARR_API_KEY", "QBITTORRENT_URL", "RADARR_QUALITY_PROFILE_ID",
        "SONARR_QUALITY_PROFILE_ID",
        "WATCHLIST_STORE", "WATCHLIST_DB_PATH", "WATCHLIST_SCHEDULER",
        "AUTO_ADD_ENABLED", "RECONCILE_INTERVAL_MIN", "DAILY_JOB_HOUR",
        "TMDB_CACHE_TTL",
        # declared on the class yet MISSING from the old hand-written list — it
        # was being silently dropped:
        "YOUTUBE_API_KEY",
        # Subtitles (SUBTITLES_OPENSUBTITLES_PLAN Phase 0, 2026-09-12) — declared so
        # the passthrough carries them; a dropped key disables the whole feature
        # with no error anywhere.
        "OPENSUBTITLES_API_KEY", "OPENSUBTITLES_USERNAME", "OPENSUBTITLES_PASSWORD",
        "OPENSUBTITLES_LANGUAGES", "OPENSUBTITLES_ENABLED",
    }

    #: Settings that must NOT come back: retired with the Plex/Emby providers.
    RETIRED_KEYS = {
        "PLEX_URL", "PLEX_TOKEN", "PLEX_BROWSER_URL", "PLEX_SCAN_TTL",
        "EMBY_URL", "EMBY_API_KEY", "EMBY_BROWSER_URL",
    }

    def test_every_known_key_is_covered(self):
        missing = sorted(self.KNOWN_KEYS - Config()._get_all_keys())
        assert missing == [], f"keys dropped from the passthrough: {missing}"

    def test_retired_keys_are_gone(self):
        """The Plex/Emby settings are REMOVED, not merely unused."""
        still_there = sorted(self.RETIRED_KEYS & Config()._get_all_keys())
        assert still_there == [], f"retired keys still declared: {still_there}"

    def test_previously_dropped_key_now_passes_through(self):
        passed = Config()._env_passthrough({"YOUTUBE_API_KEY": "y", "TMDB_CACHE_TTL": "3600"})
        assert passed == {"YOUTUBE_API_KEY": "y", "TMDB_CACHE_TTL": "3600"}

    def test_derived_set_ignores_internal_attributes(self):
        keys = Config()._get_all_keys()
        assert "media_libraries" not in keys
        assert "media_library_warnings" not in keys
        assert not any(k.startswith("_") for k in keys)


class TestRequiredKeys:
    """``validate_required`` must not demand a credential of a live service."""

    def test_media_server_credential_is_not_required(self):
        """A Jellyfin-only stack used to log a phantom PLEX_TOKEN warning on boot.

        The media server's configured/ok state is reported by ``/api/health``; a
        HARD requirement here would warn on every fresh install, whose API key
        only exists after the provisioner has run.
        """
        cfg = Config()
        cfg.RADARR_API_KEY = "k"
        cfg.SONARR_API_KEY = "k"
        assert cfg.validate_required() == []

    def test_missing_arr_keys_are_still_reported(self):
        cfg = Config()
        cfg.RADARR_API_KEY = ""
        cfg.SONARR_API_KEY = ""
        assert cfg.validate_required() == ["RADARR_API_KEY", "SONARR_API_KEY"]


class TestEnvPassthroughPredicate:
    def test_media_roots_are_covered(self):
        for key in ("RKM_MEDIA_PATH", "RKM_MEDIA_PATH_2", "RKM_MEDIA_PATH_3"):
            assert is_env_passthrough_key(key), key

    def test_library_declarations_are_covered(self):
        assert is_env_passthrough_key("MEDIA_LIBRARY_1_NAME")
        assert is_env_passthrough_key("MEDIA_LIBRARY_12_TYPE")

    def test_unrelated_and_sensitive_keys_stay_out(self):
        """Only the media families pass — admin passwords/ports must not."""
        for key in ("RKM_JELLYFIN_ADMIN_PASSWORD", "RKM_DASHBOARD_PORT", "PATH",
                    "MEDIA_HOST_X", "RKM_TORRENT_PORT"):
            assert not is_env_passthrough_key(key), key


class TestConfigEnvPassthrough:
    def test_two_drive_setup_survives_the_filter_and_translates(self):
        """The regression end-to-end: filter the env, then parse it."""
        live_env = {
            "RKM_MEDIA_PATH": "D:/RKM_MEDIA",
            "RKM_MEDIA_PATH_2": "B:/RKM_MEDIA",
            "MEDIA_LIBRARY_1_NAME": "Movies Kids",
            "MEDIA_LIBRARY_1_PATH": "D:/RKM_MEDIA/Movies Kids",
            "MEDIA_LIBRARY_1_TYPE": "movie",
            "MEDIA_LIBRARY_2_NAME": "TV Shows",
            "MEDIA_LIBRARY_2_PATH": "B:/RKM_MEDIA/TV Shows",
            "MEDIA_LIBRARY_2_TYPE": "tv",
            # noise that must be dropped (not silently kept, not breaking anything)
            "RKM_JELLYFIN_ADMIN_PASSWORD": "super-secret",
            "SOME_UNRELATED_KEY": "x",
        }
        passed = Config()._env_passthrough(live_env)
        assert "RKM_MEDIA_PATH" in passed and "RKM_MEDIA_PATH_2" in passed
        assert "RKM_JELLYFIN_ADMIN_PASSWORD" not in passed
        assert "SOME_UNRELATED_KEY" not in passed

        libraries, warnings = parse_media_libraries(passed)
        assert warnings == [], warnings
        assert [(l.name, l.path, l.collection_type) for l in libraries] == [
            ("Movies Kids", "/data/Movies Kids", "movies"),
            ("TV Shows", "/media2/TV Shows", "tvshows"),
        ]

    def test_single_drive_setup_still_translates(self):
        live_env = {
            "RKM_MEDIA_PATH": "D:/RKM_MEDIA",
            "MEDIA_LIBRARY_1_NAME": "Movies",
            "MEDIA_LIBRARY_1_PATH": "D:/RKM_MEDIA/Movies",
        }
        libraries, warnings = parse_media_libraries(Config()._env_passthrough(live_env))
        assert warnings == []
        assert libraries[0].path == "/data/Movies"

    def test_declared_keys_still_pass_through(self):
        """The media families are ADDITIVE — normal keys must keep working."""
        passed = Config()._env_passthrough({"TMDB_API_KEY": "k", "RADARR_URL": "http://x:7878"})
        assert passed == {"TMDB_API_KEY": "k", "RADARR_URL": "http://x:7878"}
