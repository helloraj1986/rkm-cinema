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
        monkeypatch.setattr(provision, "discover_all_media_roots", lambda: [])
        targets = provision.configured_target_libraries()
        assert targets == provision.LEGACY_TARGET_LIBRARIES

    def test_no_libraries_but_other_keys_still_falls_back(self, monkeypatch):
        for k in list(os.environ):
            if k.startswith("MEDIA_LIBRARY_"):
                monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("RKM_MEDIA_PATH", "D:/RKM_MEDIA")
        monkeypatch.setattr(provision, "discover_all_media_roots", lambda: [])
        assert provision.configured_target_libraries() == provision.LEGACY_TARGET_LIBRARIES

    def test_auto_discovers_media_root_subfolders_when_unconfigured(self, monkeypatch):
        """No MEDIA_LIBRARY_* → every real folder under the root becomes a library."""
        for k in list(os.environ):
            if k.startswith("MEDIA_LIBRARY_"):
                monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr(provision, "discover_all_media_roots",
                            lambda: [("Movies Kids", "movies", "/data/Movies Kids"),
                                     ("TV Shows", "tvshows", "/data/TV Shows")])
        targets = provision.configured_target_libraries()
        assert targets == [("Movies Kids", "movies", "/data/Movies Kids"),
                           ("TV Shows", "tvshows", "/data/TV Shows")]

    def test_explicit_libraries_on_two_drives(self, monkeypatch):
        """A library declared on the second drive wires to /media2, not /data."""
        monkeypatch.setenv("RKM_MEDIA_PATH", "D:/RKM_MEDIA")
        monkeypatch.setenv("RKM_MEDIA_PATH_2", "B:/RKM_MEDIA")
        monkeypatch.setenv("MEDIA_LIBRARY_1_NAME", "Movies")
        monkeypatch.setenv("MEDIA_LIBRARY_1_PATH", "D:/RKM_MEDIA/Movies")
        monkeypatch.setenv("MEDIA_LIBRARY_1_TYPE", "movie")
        monkeypatch.setenv("MEDIA_LIBRARY_2_NAME", "TV Shows")
        monkeypatch.setenv("MEDIA_LIBRARY_2_PATH", "B:/RKM_MEDIA/TV Shows")
        monkeypatch.setenv("MEDIA_LIBRARY_2_TYPE", "tv")
        assert provision.configured_target_libraries() == [
            ("Movies", "movies", "/data/Movies"),
            ("TV Shows", "tvshows", "/media2/TV Shows"),
        ]


class TestMediaRootMounts:
    def test_env_drives_the_mount_list(self, monkeypatch):
        monkeypatch.setenv("RKM_MEDIA_PATH", "D:/RKM_MEDIA")
        monkeypatch.setenv("RKM_MEDIA_PATH_2", "B:/RKM_MEDIA")
        assert provision._media_root_mounts() == [("/data", "D:/RKM_MEDIA"),
                                                  ("/media2", "B:/RKM_MEDIA")]

    def test_undeclared_extra_root_is_not_in_the_list(self, monkeypatch):
        """compose mounts /media2 regardless — an unset _2 must NOT be discovered."""
        monkeypatch.setenv("RKM_MEDIA_PATH", "D:/RKM_MEDIA")
        monkeypatch.delenv("RKM_MEDIA_PATH_2", raising=False)
        assert provision._media_root_mounts() == [("/data", "D:/RKM_MEDIA")]

    def test_no_root_at_all_falls_back_to_data(self, monkeypatch):
        monkeypatch.delenv("RKM_MEDIA_PATH", raising=False)
        monkeypatch.delenv("RKM_MEDIA_PATH_2", raising=False)
        assert provision._media_root_mounts() == [("/data", "/data")]


class TestDiscoverAllMediaRoots:
    def test_discovers_folders_on_both_drives(self, monkeypatch, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        (a / "Movies").mkdir(parents=True)
        (b / "TV Shows").mkdir(parents=True)
        monkeypatch.setattr(provision, "_media_root_mounts",
                            lambda: [(str(a), "D:/RKM_MEDIA"), (str(b), "B:/RKM_MEDIA")])
        assert provision.discover_all_media_roots() == [
            ("Movies", "movies", f"{a}/Movies"),
            ("TV Shows", "tvshows", f"{b}/TV Shows"),
        ]

    def test_missing_root_contributes_nothing(self, monkeypatch, tmp_path):
        a = tmp_path / "a"
        (a / "Movies").mkdir(parents=True)
        monkeypatch.setattr(provision, "_media_root_mounts",
                            lambda: [(str(a), "D:/RKM_MEDIA"),
                                     (str(tmp_path / "gone"), "B:/RKM_MEDIA")])
        assert provision.discover_all_media_roots() == [("Movies", "movies", f"{a}/Movies")]

    def test_same_folder_name_on_two_roots_kept_once_with_a_note(
        self, monkeypatch, tmp_path, capsys
    ):
        a = tmp_path / "a"
        b = tmp_path / "b"
        (a / "Movies").mkdir(parents=True)
        (b / "Movies").mkdir(parents=True)
        monkeypatch.setattr(provision, "_media_root_mounts",
                            lambda: [(str(a), "D:/RKM_MEDIA"), (str(b), "B:/RKM_MEDIA")])
        found = provision.discover_all_media_roots()
        assert found == [("Movies", "movies", f"{a}/Movies")]
        out = capsys.readouterr().out
        assert "exists on more than one media root" in out
        assert "MEDIA_LIBRARY_N_NAME" in out


class TestPruneUntargetedLibraries:
    """Leftover libraries are removed — but never at the cost of real ones."""

    def _fake_jellyfin(self, monkeypatch, libraries):
        state = {"folders": [dict(f) for f in libraries]}
        calls = []

        def fake_request(method, path, *, token=None, body=None, q=None, timeout=15):
            calls.append((method, path, dict(q or {})))
            if method == "GET" and path == "/Library/VirtualFolders":
                return 200, [dict(f) for f in state["folders"]]
            if method == "DELETE" and path == "/Library/VirtualFolders":
                name = (q or {}).get("name")
                state["folders"] = [f for f in state["folders"] if f.get("Name") != name]
                return 204, None
            if method == "POST" and path == "/Library/VirtualFolders":
                state["folders"].append({"Name": (q or {}).get("name"),
                                         "CollectionType": (q or {}).get("collectionType"),
                                         "Locations": [(q or {}).get("paths")],
                                         "ItemId": "new"})
                return 204, None
            return 204, None

        monkeypatch.setattr(provision, "_request", fake_request)
        return state, calls

    def test_removes_leftover_inside_our_mount_and_keeps_targets_and_internals(self, monkeypatch):
        state, calls = self._fake_jellyfin(monkeypatch, [
            {"Name": "Movies", "CollectionType": "movies", "Locations": ["/data/media/_movie"], "ItemId": "1"},
            {"Name": "TV Shows", "CollectionType": "tvshows", "Locations": ["/data/media/_tv"], "ItemId": "2"},
            {"Name": "Movies Kids", "CollectionType": "movies", "Locations": ["/data/Movies Kids"], "ItemId": "3"},
            # Jellyfin-internal library OUTSIDE our mounts — must survive.
            {"Name": "Playlists", "CollectionType": "playlists", "Locations": ["/config/data/playlists"], "ItemId": "4"},
        ])
        deleted = provision.prune_untargeted_libraries(
            "tok", [("Movies Kids", "movies", "/data/Movies Kids")],
            source=provision.SOURCE_DISCOVERED, mounts=["/data", "/media2"])
        assert sorted(deleted) == ["Movies", "TV Shows"]
        left = {f["Name"] for f in state["folders"]}
        assert left == {"Movies Kids", "Playlists"}
        assert not any(c[2].get("name") == "Movies Kids" for c in calls if c[0] == "DELETE")

    def test_never_prunes_targets_by_name_case_insensitively(self, monkeypatch):
        state, _ = self._fake_jellyfin(monkeypatch, [
            {"Name": "movies kids", "Locations": ["/data/Movies Kids"], "ItemId": "3"}])
        deleted = provision.prune_untargeted_libraries(
            "tok", [("Movies Kids", "movies", "/data/Movies Kids")],
            source=provision.SOURCE_CONFIGURED, mounts=["/data"])
        assert deleted == []

    def test_refuses_when_nothing_was_configured_or_discovered(self, monkeypatch, capsys):
        """The failed-mount case: pruning here would delete the user's real libraries."""
        state, calls = self._fake_jellyfin(monkeypatch, [
            {"Name": "Movies Kids", "Locations": ["/data/Movies Kids"], "ItemId": "3"}])
        deleted = provision.prune_untargeted_libraries(
            "tok", provision.LEGACY_TARGET_LIBRARIES,
            source=provision.SOURCE_SAMPLE, mounts=["/data"])
        assert deleted == []
        assert not any(c[0] == "DELETE" for c in calls)
        assert "must never delete your libraries" in capsys.readouterr().out

    def test_disabled_by_env_is_a_strict_no_op(self, monkeypatch, capsys):
        state, calls = self._fake_jellyfin(monkeypatch, [
            {"Name": "Movies", "Locations": ["/data/media/_movie"], "ItemId": "1"}])
        deleted = provision.prune_untargeted_libraries(
            "tok", [("Movies Kids", "movies", "/data/Movies Kids")],
            source=provision.SOURCE_DISCOVERED, mounts=["/data"], enabled=False)
        assert deleted == [] and state["folders"]
        assert not any(c[0] == "DELETE" for c in calls)
        assert "pruning disabled" in capsys.readouterr().out

    def test_library_outside_our_mounts_is_never_touched(self, monkeypatch):
        state, _ = self._fake_jellyfin(monkeypatch, [
            {"Name": "Somewhere Else", "Locations": ["E:/Other"], "ItemId": "9"}])
        assert provision.prune_untargeted_libraries(
            "tok", [("Movies", "movies", "/data/Movies")],
            source=provision.SOURCE_DISCOVERED, mounts=["/data", "/media2"]) == []
        assert state["folders"]

    def test_prune_enabled_defaults_on_and_honours_env(self):
        assert provision._prune_enabled({}) is True
        assert provision._prune_enabled({"RKM_PRUNE_LIBRARIES": "true"}) is True
        for off in ("0", "false", "FALSE", "no", "off"):
            assert provision._prune_enabled({"RKM_PRUNE_LIBRARIES": off}) is False

    def test_under_mount_matches_exactly_and_by_prefix(self):
        assert provision._under_mount("/data", ["/data"])
        assert provision._under_mount("/data/Movies Kids", ["/data"])
        assert provision._under_mount("/media2/TV Shows", ["/data", "/media2"])
        assert not provision._under_mount("/datax/Movies", ["/data"])
        assert not provision._under_mount("/config/data/playlists", ["/data", "/media2"])
        assert not provision._under_mount("", ["/data"])


class TestTargetLibrariesSource:
    def test_reports_configured_source(self, monkeypatch):
        monkeypatch.setenv("RKM_MEDIA_PATH", "D:/RKM_MEDIA")
        monkeypatch.setenv("MEDIA_LIBRARY_1_NAME", "Movies")
        monkeypatch.setenv("MEDIA_LIBRARY_1_PATH", "/data/Movies")
        targets, source = provision.target_libraries_with_source()
        assert source == provision.SOURCE_CONFIGURED
        assert targets == [("Movies", "mixed", "/data/Movies")]

    def test_reports_discovered_source(self, monkeypatch):
        for k in list(os.environ):
            if k.startswith("MEDIA_LIBRARY_"):
                monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr(provision, "discover_all_media_roots",
                            lambda: [("Movies Kids", "movies", "/data/Movies Kids")])
        targets, source = provision.target_libraries_with_source()
        assert source == provision.SOURCE_DISCOVERED
        assert targets == [("Movies Kids", "movies", "/data/Movies Kids")]

    def test_reports_sample_source_when_nothing_found(self, monkeypatch):
        for k in list(os.environ):
            if k.startswith("MEDIA_LIBRARY_"):
                monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr(provision, "discover_all_media_roots", lambda: [])
        targets, source = provision.target_libraries_with_source()
        assert source == provision.SOURCE_SAMPLE
        assert targets == provision.LEGACY_TARGET_LIBRARIES

    def test_configured_target_libraries_is_the_targets_only(self, monkeypatch):
        monkeypatch.setenv("MEDIA_LIBRARY_1_NAME", "Movies")
        monkeypatch.setenv("MEDIA_LIBRARY_1_PATH", "/data/Movies")
        assert provision.configured_target_libraries() == [("Movies", "mixed", "/data/Movies")]


class TestDiscoverMediaRootLibraries:
    def test_discovers_real_folders_and_skips_bookkeeping(self, tmp_path):
        for d in ("Movies Kids", "TV Shows", "downloads", "rkm", "media", ".hidden"):
            (tmp_path / d).mkdir()
        (tmp_path / "a-file.txt").write_text("x")
        found = provision.discover_media_root_libraries(root=str(tmp_path))
        names = [t[0] for t in found]
        assert names == ["Movies Kids", "TV Shows"]
        # the returned path is rooted at the mount that was scanned
        assert ("Movies Kids", "movies", f"{tmp_path}/Movies Kids") in found
        assert ("TV Shows", "tvshows", f"{tmp_path}/TV Shows") in found

    def test_returned_path_uses_the_scanned_mount_not_a_hardcoded_data(self, monkeypatch, tmp_path):
        """A second-drive mount must yield paths under THAT mount, never /data."""
        (tmp_path / "TV Shows").mkdir()
        monkeypatch.setattr(provision, "_media_root_mounts",
                            lambda: [(str(tmp_path), "B:/RKM_MEDIA")])
        found = provision.discover_all_media_roots()
        assert found == [("TV Shows", "tvshows", f"{tmp_path}/TV Shows")]
        assert all("/data/" not in p for _, _, p in found)

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
