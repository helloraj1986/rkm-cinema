"""Provisioner library wiring (MEDIA_LIBRARIES_PLAN).

The bundled provisioner must wire EVERY MEDIA_LIBRARY_N_* entry from .env into
Jellyfin at startup (not the old hardcoded pair), and must report a missing /
unreadable folder instead of creating a broken empty library. These tests
exercise the pure helpers (no Jellyfin, no network).
"""
import os
import sys
from pathlib import Path

# The provisioner is a script, not a package: import it by path.
_PROV_DIR = Path(__file__).resolve().parent.parent / "provisioner"
if str(_PROV_DIR) not in sys.path:
    sys.path.insert(0, str(_PROV_DIR))

import provision  # noqa: E402


class TestConfiguredTargetLibraries:
    def test_uses_env_libraries_with_translation(self, monkeypatch):
        monkeypatch.setenv("RKM_MEDIA_PATH", "D:/RKM_MEDIA")
        monkeypatch.setenv("MEDIA_LIBRARY_1_NAME", "Movies Kids")
        monkeypatch.setenv("MEDIA_LIBRARY_1_PATH", "D:/RKM_MEDIA/Movies Kids")
        monkeypatch.setenv("MEDIA_LIBRARY_1_TYPE", "movie")
        monkeypatch.setenv("MEDIA_LIBRARY_2_NAME", "TV Shows")
        monkeypatch.setenv("MEDIA_LIBRARY_2_PATH", "/data/TV Shows")
        targets = provision.configured_target_libraries()
        assert targets == [
            ("Movies Kids", "movies", "/data/Movies Kids"),
            ("TV Shows", "mixed", "/data/TV Shows"),
        ]

    def test_falls_back_to_sample_pair_when_unconfigured(self, monkeypatch):
        for k in list(os.environ):
            if k.startswith("MEDIA_LIBRARY_"):
                monkeypatch.delenv(k, raising=False)
        # No auto-discoverable subfolders in the test environment → sample pair.
        monkeypatch.setattr(provision, "discover_media_root_libraries", lambda: [])
        targets = provision.configured_target_libraries()
        assert targets == provision.LEGACY_TARGET_LIBRARIES

    def test_no_libraries_but_other_keys_still_falls_back(self, monkeypatch):
        for k in list(os.environ):
            if k.startswith("MEDIA_LIBRARY_"):
                monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("RKM_MEDIA_PATH", "D:/RKM_MEDIA")
        monkeypatch.setattr(provision, "discover_media_root_libraries", lambda: [])
        assert provision.configured_target_libraries() == provision.LEGACY_TARGET_LIBRARIES

    def test_auto_discovers_media_root_subfolders_when_unconfigured(self, monkeypatch):
        """No MEDIA_LIBRARY_* → every real folder under the root becomes a library."""
        for k in list(os.environ):
            if k.startswith("MEDIA_LIBRARY_"):
                monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr(provision, "discover_media_root_libraries",
                            lambda: [("Movies Kids", "movies", "/data/Movies Kids"),
                                     ("TV Shows", "tvshows", "/data/TV Shows")])
        targets = provision.configured_target_libraries()
        assert targets == [("Movies Kids", "movies", "/data/Movies Kids"),
                           ("TV Shows", "tvshows", "/data/TV Shows")]


class TestDiscoverMediaRootLibraries:
    def test_discovers_real_folders_and_skips_bookkeeping(self, tmp_path):
        for d in ("Movies Kids", "TV Shows", "downloads", "rkm", "media", ".hidden"):
            (tmp_path / d).mkdir()
        (tmp_path / "a-file.txt").write_text("x")
        found = provision.discover_media_root_libraries(root=str(tmp_path))
        names = [t[0] for t in found]
        assert names == ["Movies Kids", "TV Shows"]
        assert ("Movies Kids", "movies", "/data/Movies Kids") in found
        assert ("TV Shows", "tvshows", "/data/TV Shows") in found

    def test_missing_root_returns_empty(self):
        assert provision.discover_media_root_libraries(root="/definitely/not/here") == []

    def test_guess_collection_type(self):
        assert provision._guess_collection_type("Movies Kids") == "movies"
        assert provision._guess_collection_type("4K Films") == "movies"
        assert provision._guess_collection_type("TV Shows") == "tvshows"
        assert provision._guess_collection_type("Series") == "tvshows"
        assert provision._guess_collection_type("Anime") == "mixed"
        assert provision._guess_collection_type("Random") == "mixed"


class TestFolderCheck:
    def test_missing_folder_not_wireable(self, tmp_path):
        wireable, msg = provision._folder_check(str(tmp_path / "nope"))
        assert wireable is False
        assert "MISSING" in msg

    def test_empty_folder_is_wireable(self, tmp_path):
        empty = tmp_path / "Empty Library"
        empty.mkdir()
        wireable, msg = provision._folder_check(str(empty))
        assert wireable is True
        assert "EMPTY" in msg

    def test_populated_folder_ok(self, tmp_path):
        lib = tmp_path / "Movies Kids"
        lib.mkdir()
        (lib / "movie.mkv").write_text("x")
        wireable, msg = provision._folder_check(str(lib))
        assert wireable is True
        assert msg == "ok"

    def test_file_not_folder(self, tmp_path):
        f = tmp_path / "afile"
        f.write_text("x")
        wireable, msg = provision._folder_check(str(f))
        assert wireable is False
        assert "NOT A FOLDER" in msg

    def test_non_container_path_rejected(self):
        wireable, msg = provision._folder_check("D:/RKM_MEDIA/Movies")
        assert wireable is False
        assert "not a container path" in msg

    def test_unreadable_folder_flagged(self, tmp_path):
        lib = tmp_path / "locked"
        lib.mkdir()
        os.chmod(lib, 0o000)
        try:
            wireable, msg = provision._folder_check(str(lib))
            # root can read anything, so only assert when the perms actually bite
            if not wireable:
                assert "NOT READABLE" in msg
        finally:
            os.chmod(lib, 0o755)


class TestEnsureLibrariesWiring:
    """ensure_libraries() end-to-end against a faked Jellyfin (no network)."""

    def test_creates_every_configured_library_and_skips_missing(self, monkeypatch, tmp_path):
        real = tmp_path / "Movies Kids"
        real.mkdir()
        (real / "m.mkv").write_text("x")

        monkeypatch.setenv("RKM_MEDIA_PATH", str(tmp_path))
        monkeypatch.setenv("MEDIA_LIBRARY_1_NAME", "Movies Kids")
        monkeypatch.setenv("MEDIA_LIBRARY_1_PATH", str(real))
        monkeypatch.setenv("MEDIA_LIBRARY_1_TYPE", "movie")
        monkeypatch.setenv("MEDIA_LIBRARY_2_NAME", "Ghost")
        monkeypatch.setenv("MEDIA_LIBRARY_2_PATH", str(tmp_path / "missing"))

        state = {"folders": []}
        calls = []

        def fake_request(method, path, *, token=None, body=None, q=None, timeout=15):
            calls.append((method, path, dict(q or {}), body))
            if method == "GET" and path == "/Library/VirtualFolders":
                return 200, list(state["folders"])
            if method == "POST" and path == "/Library/VirtualFolders":
                name = (q or {}).get("name")
                p = (q or {}).get("paths")
                state["folders"] = [f for f in state["folders"] if f.get("Name") != name]
                state["folders"].append(
                    {"Name": name, "CollectionType": (q or {}).get("collectionType"),
                     "Locations": [p], "ItemId": f"id-{name}"})
                return 204, None
            if method == "POST" and path == "/Library/Refresh":
                return 204, None
            return 200, []

        monkeypatch.setattr(provision, "_request", fake_request)
        provision.ensure_libraries("tok")

        created = [f for f in state["folders"] if f["Name"] == "Movies Kids"]
        assert created, "the real folder must be wired into Jellyfin"
        assert created[0]["Locations"] == [str(real)]
        assert created[0]["CollectionType"] == "movies"
        # the missing folder must NOT create a library
        assert not any(f["Name"] == "Ghost" for f in state["folders"])
        # and a scan is triggered
        assert any(c[1] == "/Library/Refresh" for c in calls)

    def test_idempotent_when_library_already_correct(self, monkeypatch, tmp_path):
        real = tmp_path / "Movies"
        real.mkdir()
        (real / "m.mkv").write_text("x")
        monkeypatch.setenv("RKM_MEDIA_PATH", str(tmp_path))
        monkeypatch.setenv("MEDIA_LIBRARY_1_NAME", "Movies")
        monkeypatch.setenv("MEDIA_LIBRARY_1_PATH", str(real))

        state = {"folders": [{"Name": "Movies", "CollectionType": "movies",
                              "Locations": [str(real)], "ItemId": "id-1"}]}
        creates = []

        def fake_request(method, path, *, token=None, body=None, q=None, timeout=15):
            if method == "GET" and path == "/Library/VirtualFolders":
                return 200, list(state["folders"])
            if method == "POST" and path == "/Library/VirtualFolders":
                creates.append(q)
                return 204, None
            return 204, None

        monkeypatch.setattr(provision, "_request", fake_request)
        provision.ensure_libraries("tok")
        assert creates == [], "an already-correct library must not be re-created"

    def test_repairs_library_with_wrong_path(self, monkeypatch, tmp_path):
        real = tmp_path / "Movies"
        real.mkdir()
        (real / "m.mkv").write_text("x")
        monkeypatch.setenv("RKM_MEDIA_PATH", str(tmp_path))
        monkeypatch.setenv("MEDIA_LIBRARY_1_NAME", "Movies")
        monkeypatch.setenv("MEDIA_LIBRARY_1_PATH", str(real))

        state = {"folders": [{"Name": "Movies", "CollectionType": "movies",
                              "Locations": ["/data/media/_movie"], "ItemId": "old"}]}
        deletes = []

        def fake_request(method, path, *, token=None, body=None, q=None, timeout=15):
            if method == "GET" and path == "/Library/VirtualFolders":
                return 200, list(state["folders"])
            if method == "DELETE":
                deletes.append(dict(q or {}))
                state["folders"] = []
                return 204, None
            if method == "POST" and path == "/Library/VirtualFolders":
                state["folders"].append({"Name": (q or {}).get("name"),
                                         "Locations": [(q or {}).get("paths")],
                                         "ItemId": "new"})
                return 204, None
            return 204, None

        monkeypatch.setattr(provision, "_request", fake_request)
        provision.ensure_libraries("tok")
        assert deletes and deletes[0].get("name") == "Movies"
        assert state["folders"][0]["Locations"] == [str(real)]
