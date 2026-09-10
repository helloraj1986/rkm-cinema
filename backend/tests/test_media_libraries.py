"""Media-library .env parsing (MEDIA_LIBRARIES_PLAN Phase 1).

Covers the dedicated parser in config/media_libraries.py: arbitrary N, Windows
paths with spaces and drive letters, gaps, missing NAME/PATH, duplicate names /
paths, and that the internal env key is never surfaced as a name.
"""
from config.media_libraries import (
    MediaLibrary,
    normalize_collection_type,
    normalize_media_path,
    parse_media_libraries,
    translate_media_path,
)


class TestParseMediaLibraries:
    def test_parses_ordered_pairs_arbitrary_count(self):
        libs, warnings = parse_media_libraries({
            "MEDIA_LIBRARY_1_NAME": "Movies",
            "MEDIA_LIBRARY_1_PATH": "/data/media/_movie",
            "MEDIA_LIBRARY_2_NAME": "TV Shows",
            "MEDIA_LIBRARY_2_PATH": "/data/media/_tv",
            "MEDIA_LIBRARY_3_NAME": "4K Movies",
            "MEDIA_LIBRARY_3_PATH": "/data/media/_4k",
            "MEDIA_LIBRARY_4_NAME": "Anime",
            "MEDIA_LIBRARY_4_PATH": "/data/media/_anime",
        })
        assert warnings == []
        assert libs == [
            MediaLibrary(name="Movies", path="/data/media/_movie"),
            MediaLibrary(name="TV Shows", path="/data/media/_tv"),
            MediaLibrary(name="4K Movies", path="/data/media/_4k"),
            MediaLibrary(name="Anime", path="/data/media/_anime"),
        ]

    def test_host_path_translated_when_under_media_root(self):
        """A host-style PATH under RKM_MEDIA_PATH becomes the /data container path."""
        libs, warnings = parse_media_libraries({
            "RKM_MEDIA_PATH": "D:/RKM_MEDIA",
            "MEDIA_LIBRARY_1_NAME": "Movies Kids",
            "MEDIA_LIBRARY_1_PATH": "D:/RKM_MEDIA/Movies Kids",
        })
        assert warnings == []
        assert libs[0].name == "Movies Kids"
        assert libs[0].path == "/data/Movies Kids"

    def test_backslash_host_path_translated(self):
        libs, warnings = parse_media_libraries({
            "RKM_MEDIA_PATH": r"D:\RKM_MEDIA",
            "MEDIA_LIBRARY_1_NAME": "Movies Kids",
            "MEDIA_LIBRARY_1_PATH": r"D:\RKM_MEDIA\Movies Kids",
        })
        assert warnings == []
        assert libs[0].path == "/data/Movies Kids"

    def test_host_path_outside_media_root_warns(self):
        libs, warnings = parse_media_libraries({
            "RKM_MEDIA_PATH": "D:/RKM_MEDIA",
            "MEDIA_LIBRARY_1_NAME": "Elsewhere",
            "MEDIA_LIBRARY_1_PATH": "E:/Other/Place",
        })
        assert libs[0].path == "E:/Other/Place"  # kept verbatim, never faked
        assert any("outside RKM_MEDIA_PATH" in w for w in warnings)

    def test_media_root_itself_maps_to_data(self):
        libs, warnings = parse_media_libraries({
            "RKM_MEDIA_PATH": "D:/RKM_MEDIA",
            "MEDIA_LIBRARY_1_NAME": "Everything",
            "MEDIA_LIBRARY_1_PATH": "D:/RKM_MEDIA",
        })
        assert warnings == []
        assert libs[0].path == "/data"

    def test_type_hint_normalised(self):
        libs, _ = parse_media_libraries({
            "MEDIA_LIBRARY_1_NAME": "Films",
            "MEDIA_LIBRARY_1_PATH": "/data/Films",
            "MEDIA_LIBRARY_1_TYPE": "movie",
            "MEDIA_LIBRARY_2_NAME": "Shows",
            "MEDIA_LIBRARY_2_PATH": "/data/Shows",
            "MEDIA_LIBRARY_2_TYPE": "tv",
            "MEDIA_LIBRARY_3_NAME": "Other",
            "MEDIA_LIBRARY_3_PATH": "/data/Other",
        })
        assert [l.collection_type for l in libs] == ["movies", "tvshows", "mixed"]

    def test_supports_spaces_and_backslash_windows_paths(self):
        libs, warnings = parse_media_libraries({
            "MEDIA_LIBRARY_1_NAME": "My Anime",
            "MEDIA_LIBRARY_1_PATH": "/data/My Anime Collection",
        })
        assert warnings == []
        assert libs == [MediaLibrary(name="My Anime", path="/data/My Anime Collection")]

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


class TestNormalizeCollectionType:
    def test_known_aliases(self):
        assert normalize_collection_type("movie") == "movies"
        assert normalize_collection_type("TV") == "tvshows"
        assert normalize_collection_type("series") == "tvshows"
        assert normalize_collection_type("mixed") == "mixed"

    def test_unknown_and_blank_default_to_mixed(self):
        assert normalize_collection_type("") == "mixed"
        assert normalize_collection_type("nonsense") == "mixed"


class TestTranslateMediaPath:
    def test_container_path_passes_through(self):
        assert translate_media_path("/data/X", "D:/RKM_MEDIA") == ("/data/X", "")

    def test_host_path_under_root(self):
        p, w = translate_media_path("D:/RKM_MEDIA/Movies Kids", "D:/RKM_MEDIA")
        assert (p, w) == ("/data/Movies Kids", "")

    def test_case_insensitive_drive_match(self):
        p, w = translate_media_path("d:/rkm_media/Movies", "D:/RKM_MEDIA")
        assert (p, w) == ("/data/Movies", "")

    def test_outside_root_warns(self):
        p, w = translate_media_path("E:/Other", "D:/RKM_MEDIA")
        assert p == "E:/Other"
        assert "outside RKM_MEDIA_PATH" in w

    def test_host_path_without_root_warns(self):
        p, w = translate_media_path("D:/RKM_MEDIA/Movies", "")
        assert "RKM_MEDIA_PATH is not set" in w

    def test_empty_path(self):
        assert translate_media_path("", "D:/RKM_MEDIA") == ("", "")


class TestNormalizeMediaPath:
    def test_backslashes_become_slashes(self):
        assert normalize_media_path(r"C:\rkm-media\movies") == "C:/rkm-media/movies"

    def test_trailing_slash_stripped(self):
        assert normalize_media_path("/data/media/_movie/") == "/data/media/_movie"

    def test_root_slash_survives(self):
        assert normalize_media_path("/") == "/"

    def test_whitespace_trimmed_and_spaces_kept(self):
        assert normalize_media_path("  F:/Media/Anime Collection  ") == "F:/Media/Anime Collection"
