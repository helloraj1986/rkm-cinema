"""Media-library .env parsing (MEDIA_LIBRARIES_PLAN Phase 1).

Covers the dedicated parser in config/media_libraries.py: arbitrary N, Windows
paths with spaces and drive letters, gaps, missing NAME/PATH, duplicate names /
paths, and that the internal env key is never surfaced as a name.
"""
from config.media_libraries import (
    MediaLibrary,
    MediaRoot,
    container_mount_for,
    media_roots,
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


class TestMediaRoots:
    """RKM_MEDIA_PATH (+ _2, _3 …) — a second drive is a first-class citizen."""

    def test_single_primary_root_maps_to_data(self):
        roots, warnings = media_roots({"RKM_MEDIA_PATH": "D:/RKM_MEDIA"})
        assert roots == [MediaRoot(host="D:/RKM_MEDIA", container="/data")]
        assert warnings == []

    def test_second_and_third_roots_get_their_own_mounts(self):
        roots, warnings = media_roots({
            "RKM_MEDIA_PATH": "D:/RKM_MEDIA",
            "RKM_MEDIA_PATH_3": "F:/Archive",
            "RKM_MEDIA_PATH_2": "B:/RKM_MEDIA",
        })
        assert warnings == []
        assert [(r.host, r.container) for r in roots] == [
            ("D:/RKM_MEDIA", "/data"),
            ("B:/RKM_MEDIA", "/media2"),
            ("F:/Archive", "/media3"),
        ]

    def test_backslash_host_root_is_normalised(self):
        roots, _ = media_roots({"RKM_MEDIA_PATH_2": r"B:\RKM_MEDIA"})
        assert roots == [MediaRoot(host="B:/RKM_MEDIA", container="/media2")]

    def test_blank_root_ignored(self):
        roots, warnings = media_roots({"RKM_MEDIA_PATH": "D:/RKM_MEDIA",
                                       "RKM_MEDIA_PATH_2": "   "})
        assert [r.container for r in roots] == ["/data"]
        assert warnings == []

    def test_duplicate_host_root_warns_and_keeps_first_mount(self):
        roots, warnings = media_roots({"RKM_MEDIA_PATH": "D:/RKM_MEDIA",
                                       "RKM_MEDIA_PATH_2": "d:/rkm_media/"})
        assert [(r.container) for r in roots] == ["/data"]
        assert any("already mounted at /data" in w for w in warnings)

    def test_no_roots_is_empty_not_an_error(self):
        assert media_roots({}) == ([], [])
        assert media_roots({"SOMETHING_ELSE": "x"}) == ([], [])

    def test_container_mount_for(self):
        assert container_mount_for(1) == "/data"
        assert container_mount_for(2) == "/media2"
        assert container_mount_for(9) == "/media9"


class TestTranslateMediaPathMultiRoot:
    """A PATH on the SECOND drive translates to that root's container mount."""

    TWO = [MediaRoot(host="D:/RKM_MEDIA", container="/data"),
           MediaRoot(host="B:/RKM_MEDIA", container="/media2")]

    def test_second_drive_host_path(self):
        assert translate_media_path("B:/RKM_MEDIA/TV Shows", self.TWO) == ("/media2/TV Shows", "")

    def test_first_drive_host_path_unchanged_behaviour(self):
        assert translate_media_path("D:/RKM_MEDIA/Movies", self.TWO) == ("/data/Movies", "")

    def test_root_itself_maps_to_its_mount(self):
        assert translate_media_path("B:/RKM_MEDIA", self.TWO) == ("/media2", "")

    def test_case_insensitive_second_drive(self):
        assert translate_media_path("b:/rkm_media/TV", self.TWO) == ("/media2/TV", "")

    def test_container_path_on_second_mount_passes_through(self):
        assert translate_media_path("/media2/TV Shows", self.TWO) == ("/media2/TV Shows", "")

    def test_longest_matching_root_wins(self):
        roots = [MediaRoot(host="D:/RKM_MEDIA", container="/data"),
                 MediaRoot(host="D:/RKM_MEDIA/Kids", container="/media2")]
        assert translate_media_path("D:/RKM_MEDIA/Kids/Cartoons", roots) == ("/media2/Cartoons", "")
        assert translate_media_path("D:/RKM_MEDIA/Movies", roots) == ("/data/Movies", "")

    def test_outside_every_root_warns_and_names_them(self):
        p, w = translate_media_path("E:/Other", self.TWO)
        assert p == "E:/Other"
        assert "outside every configured media root" in w
        assert "D:/RKM_MEDIA → /data" in w and "B:/RKM_MEDIA → /media2" in w
        assert "RKM_MEDIA_PATH_2" in w

    def test_single_root_message_still_says_rkm_media_path(self):
        p, w = translate_media_path("E:/Other", self.TWO[:1])
        assert "outside RKM_MEDIA_PATH" in w


class TestParseMediaLibrariesAcrossTwoDrives:
    def test_host_paths_on_both_drives_translate(self):
        libs, warnings = parse_media_libraries({
            "RKM_MEDIA_PATH": "D:/RKM_MEDIA",
            "RKM_MEDIA_PATH_2": "B:/RKM_MEDIA",
            "MEDIA_LIBRARY_1_NAME": "Movies",
            "MEDIA_LIBRARY_1_PATH": "D:/RKM_MEDIA/Movies",
            "MEDIA_LIBRARY_1_TYPE": "movie",
            "MEDIA_LIBRARY_2_NAME": "TV Shows",
            "MEDIA_LIBRARY_2_PATH": "B:/RKM_MEDIA/TV Shows",
            "MEDIA_LIBRARY_2_TYPE": "tv",
        })
        assert warnings == []
        assert [(l.name, l.path, l.collection_type) for l in libs] == [
            ("Movies", "/data/Movies", "movies"),
            ("TV Shows", "/media2/TV Shows", "tvshows"),
        ]

    def test_unmounted_drive_path_warns_but_is_kept(self):
        libs, warnings = parse_media_libraries({
            "RKM_MEDIA_PATH": "D:/RKM_MEDIA",
            "MEDIA_LIBRARY_1_NAME": "TV Shows",
            "MEDIA_LIBRARY_1_PATH": "B:/RKM_MEDIA/TV Shows",
        })
        assert libs[0].path == "B:/RKM_MEDIA/TV Shows"
        assert any("RKM_MEDIA_PATH_2" in w for w in warnings)

    def test_duplicate_root_warning_surfaces_through_the_parser(self):
        _, warnings = parse_media_libraries({
            "RKM_MEDIA_PATH": "D:/RKM_MEDIA",
            "RKM_MEDIA_PATH_2": "D:/RKM_MEDIA",
            "MEDIA_LIBRARY_1_NAME": "Movies",
            "MEDIA_LIBRARY_1_PATH": "/data/Movies",
        })
        assert any("duplicate media root" in w for w in warnings)


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
