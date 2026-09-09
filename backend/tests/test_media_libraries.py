"""Media-library .env parsing (MEDIA_LIBRARIES_PLAN Phase 1).

Covers the dedicated parser in config/media_libraries.py: arbitrary N, Windows
paths with spaces and drive letters, gaps, missing NAME/PATH, duplicate names /
paths, and that the internal env key is never surfaced as a name.
"""
from config.media_libraries import (
    MediaLibrary,
    normalize_media_path,
    parse_media_libraries,
)


class TestParseMediaLibraries:
    def test_parses_ordered_pairs_arbitrary_count(self):
        libs, warnings = parse_media_libraries({
            "MEDIA_LIBRARY_1_NAME": "Movies",
            "MEDIA_LIBRARY_1_PATH": "C:/rkm-media/movies",
            "MEDIA_LIBRARY_2_NAME": "TV Shows",
            "MEDIA_LIBRARY_2_PATH": "D:/rkm-media/tv",
            "MEDIA_LIBRARY_3_NAME": "4K Movies",
            "MEDIA_LIBRARY_3_PATH": "E:/4K/Movies",
            "MEDIA_LIBRARY_4_NAME": "Anime",
            "MEDIA_LIBRARY_4_PATH": "F:/Anime",
        })
        assert warnings == []
        assert libs == [
            MediaLibrary(name="Movies", path="C:/rkm-media/movies"),
            MediaLibrary(name="TV Shows", path="D:/rkm-media/tv"),
            MediaLibrary(name="4K Movies", path="E:/4K/Movies"),
            MediaLibrary(name="Anime", path="F:/Anime"),
        ]

    def test_supports_spaces_and_backslash_windows_paths(self):
        libs, warnings = parse_media_libraries({
            "MEDIA_LIBRARY_1_NAME": "My Anime",
            "MEDIA_LIBRARY_1_PATH": r"F:\Media\Anime Collection",
        })
        assert warnings == []
        assert libs == [MediaLibrary(name="My Anime", path=r"F:\Media\Anime Collection")]

    def test_non_sequential_indexes_are_supported(self):
        libs, warnings = parse_media_libraries({
            "MEDIA_LIBRARY_2_NAME": "Movies",
            "MEDIA_LIBRARY_2_PATH": "/data/media/_movie",
            "MEDIA_LIBRARY_7_NAME": "Anime",
            "MEDIA_LIBRARY_7_PATH": "/data/media/_anime",
        })
        assert warnings == []
        assert len(libs) == 2

    def test_empty_env_returns_empty(self):
        assert parse_media_libraries({}) == ([], [])
        assert parse_media_libraries(None) == ([], [])

    def test_ignores_unrelated_keys(self):
        libs, warnings = parse_media_libraries({
            "MEDIA_LIBRARY_1_NAME": "Movies",
            "MEDIA_LIBRARY_1_PATH": "/data/media/_movie",
            "MEDIA_HOST": "192.168.65.254",
            "RADARR_API_KEY": "secret",
        })
        assert warnings == []
        assert len(libs) == 1

    def test_missing_path_warns_and_skips(self):
        libs, warnings = parse_media_libraries({
            "MEDIA_LIBRARY_1_NAME": "Movies",
            "MEDIA_LIBRARY_1_PATH": "/data/media/_movie",
            "MEDIA_LIBRARY_2_NAME": "Broken",
        })
        assert len(libs) == 1
        assert libs[0].name == "Movies"
        assert any("PATH is empty" in w and "Broken" in w for w in warnings)

    def test_missing_name_warns_and_skips(self):
        libs, warnings = parse_media_libraries({
            "MEDIA_LIBRARY_1_NAME": "Movies",
            "MEDIA_LIBRARY_1_PATH": "/data/media/_movie",
            "MEDIA_LIBRARY_2_PATH": "/data/media/_orphan",
        })
        assert len(libs) == 1
        assert any("NAME is empty" in w for w in warnings)

    def test_empty_values_warn_not_crash(self):
        libs, warnings = parse_media_libraries({
            "MEDIA_LIBRARY_1_NAME": "",
            "MEDIA_LIBRARY_1_PATH": "",
        })
        assert libs == []
        assert len(warnings) >= 1

    def test_duplicate_names_warn(self):
        libs, warnings = parse_media_libraries({
            "MEDIA_LIBRARY_1_NAME": "Movies",
            "MEDIA_LIBRARY_1_PATH": "/data/media/_movie",
            "MEDIA_LIBRARY_2_NAME": "movies",
            "MEDIA_LIBRARY_2_PATH": "/data/media/_movies2",
        })
        assert len(libs) == 2
        assert any("duplicate library name" in w for w in warnings)

    def test_duplicate_paths_warn(self):
        libs, warnings = parse_media_libraries({
            "MEDIA_LIBRARY_1_NAME": "Movies",
            "MEDIA_LIBRARY_1_PATH": "/data/media/_movie",
            "MEDIA_LIBRARY_2_NAME": "Films",
            "MEDIA_LIBRARY_2_PATH": "/data/media/_movie",
        })
        assert len(libs) == 2
        assert any("duplicate media path" in w for w in warnings)

    def test_env_key_never_becomes_the_name(self):
        # The VALUE ("Movies") is the name — never the key MEDIA_LIBRARY_1_NAME.
        libs, _ = parse_media_libraries({
            "MEDIA_LIBRARY_1_NAME": "Movies",
            "MEDIA_LIBRARY_1_PATH": "/data/media/_movie",
        })
        assert libs[0].name == "Movies"
        assert "MEDIA_LIBRARY_1_NAME" not in libs[0].name


class TestNormalizeMediaPath:
    def test_backslashes_become_slashes(self):
        assert normalize_media_path(r"C:\rkm-media\movies") == "C:/rkm-media/movies"

    def test_trailing_slash_stripped(self):
        assert normalize_media_path("/data/media/_movie/") == "/data/media/_movie"

    def test_root_slash_survives(self):
        assert normalize_media_path("/") == "/"

    def test_whitespace_trimmed_and_spaces_kept(self):
        assert normalize_media_path("  F:/Media/Anime Collection  ") == "F:/Media/Anime Collection"
