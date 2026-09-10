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
