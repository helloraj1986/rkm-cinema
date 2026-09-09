"""Configured-library → server-folder resolution (MEDIA_LIBRARIES_PLAN Phase 2).

Pure resolver tests (no I/O): match by path, name fallback, no-match warnings,
and the no-configuration sidebar fallback (server folder names only).
"""
from config.media_libraries import MediaLibrary
from services.library.media_libraries import (
    find_folder_name,
    match_libraries,
    server_default_libraries,
)

# Real shapes live-probed from the bundled Jellyfin 10.11 (2026-09-10).
SERVER_FOLDERS = [
    {"id": "f137a2dd21bbc1b99aa5c0f6bf02a805", "name": "Movies",
     "collection_type": "movies", "path": "/data/media/_movie",
     "locations": ["/data/media/_movie"]},
    {"id": "767bffe4f11c93ef34b805451a696a4e", "name": "TV Shows",
     "collection_type": "tvshows", "path": "/data/media/_tv",
     "locations": ["/data/media/_tv"]},
]


class TestMatchLibraries:
    def test_matches_configured_path_to_server_folder(self):
        rows = match_libraries(
            [MediaLibrary(name="Movies", path="/data/media/_movie")],
            SERVER_FOLDERS,
        )
        assert len(rows) == 1
        assert rows[0]["ok"] is True
        assert rows[0]["folder_id"] == "f137a2dd21bbc1b99aa5c0f6bf02a805"
        assert rows[0]["name"] == "Movies"
        assert rows[0]["warning"] == ""

    def test_windows_backslash_path_matches_same_folder(self):
        rows = match_libraries(
            [MediaLibrary(name="Movies", path=r"D:\rkm-media\movies")],
            [
                {"id": "f1", "name": "Movies", "collection_type": "movies",
                 "path": "D:/rkm-media/movies", "locations": ["D:/rkm-media/movies"]},
            ],
        )
        assert rows[0]["ok"] is True
        assert rows[0]["folder_id"] == "f1"

    def test_name_fallback_when_path_differs(self):
        # Server renamed the on-disk folder but the configured path no longer
        # matches → still resolve by NAME (secondary fallback).
        rows = match_libraries(
            [MediaLibrary(name="My Anime", path="/data/media/anime-old")],
            [{"id": "an1", "name": "My Anime", "collection_type": "movies",
              "path": "/data/media/anime", "locations": ["/data/media/anime"]}],
        )
        assert rows[0]["ok"] is True
        assert rows[0]["folder_id"] == "an1"

    def test_unmatched_path_warns(self):
        rows = match_libraries(
            [MediaLibrary(name="4K Movies", path="/data/media/_4k")],
            SERVER_FOLDERS,
        )
        assert rows[0]["ok"] is False
        assert rows[0]["folder_id"] is None
        assert "does not match" in rows[0]["warning"]

    def test_server_silent_warns_connection(self):
        rows = match_libraries(
            [MediaLibrary(name="Movies", path="/data/media/_movie")],
            [],
        )
        assert rows[0]["ok"] is False
        assert "not reporting library folders" in rows[0]["warning"]

    def test_user_name_never_an_env_key(self):
        rows = match_libraries(
            [MediaLibrary(name="Movies", path="/data/media/_movie")],
            SERVER_FOLDERS,
        )
        assert "MEDIA_LIBRARY_1_NAME" not in rows[0]["name"]
        assert rows[0]["name"] == "Movies"

    def test_empty_configured_returns_empty(self):
        assert match_libraries([], SERVER_FOLDERS) == []


class TestServerDefaultLibraries:
    def test_falls_back_to_server_folder_names(self):
        rows = server_default_libraries(SERVER_FOLDERS)
        assert [r["name"] for r in rows] == ["Movies", "TV Shows"]
        assert all(r["ok"] for r in rows)
        assert rows[0]["path"] == "/data/media/_movie"

    def test_empty_server_returns_empty(self):
        assert server_default_libraries([]) == []


class TestFindFolderName:
    def test_finds_by_id(self):
        assert find_folder_name(SERVER_FOLDERS, "767bffe4f11c93ef34b805451a696a4e") == "TV Shows"

    def test_unknown_id_returns_empty(self):
        assert find_folder_name(SERVER_FOLDERS, "nope") == ""
        assert find_folder_name([], "x") == ""
