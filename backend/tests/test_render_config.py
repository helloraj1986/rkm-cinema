"""render_config.py media-library passthrough (MEDIA_LIBRARIES_PLAN).

The api + provisioner containers read .rkm.env (rendered by render_config from
the repo .env). Configured MEDIA_LIBRARY_* keys and the host media root must
survive that render, or the containers never see the user's libraries.

The module is loaded by path with its env-writer stubbed so these tests NEVER
touch the real repo .env.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root


@pytest.fixture()
def rc(monkeypatch):
    """render_config loaded with write_env_key stubbed (no real .env writes)."""
    spec = importlib.util.spec_from_file_location("render_config_test", ROOT / "render_config.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["render_config_test"] = mod
    spec.loader.exec_module(mod)
    writes = []
    monkeypatch.setattr(mod, "write_env_key",
                        lambda path, k, v: writes.append((str(path), k, v)))
    mod._test_writes = writes
    return mod


BASE = {"MEDIA_SERVER": "jellyfin", "TMDB_API_KEY": "k",
        "RKM_JELLYFIN_ADMIN_PASSWORD": "pw"}


def test_media_library_keys_passed_through(rc):
    env = dict(BASE, RKM_MEDIA_PATH="D:/RKM_MEDIA",
               MEDIA_LIBRARY_1_NAME="Movies Kids",
               MEDIA_LIBRARY_1_PATH="D:/RKM_MEDIA/Movies Kids",
               MEDIA_LIBRARY_1_TYPE="movie",
               MEDIA_LIBRARY_2_NAME="TV Shows",
               MEDIA_LIBRARY_2_PATH="/data/TV Shows")
    api = rc.build_api_vars(env)
    assert api["MEDIA_LIBRARY_1_NAME"] == "Movies Kids"
    # PATH stays as written (host-style); the shared parser normalises it in-container
    assert api["MEDIA_LIBRARY_1_PATH"] == "D:/RKM_MEDIA/Movies Kids"
    assert api["MEDIA_LIBRARY_1_TYPE"] == "movie"
    assert api["MEDIA_LIBRARY_2_PATH"] == "/data/TV Shows"
    assert api["RKM_MEDIA_PATH"] == "D:/RKM_MEDIA"


def test_media_root_defaults_when_absent(rc):
    api = rc.build_api_vars(dict(BASE))
    assert api["RKM_MEDIA_PATH"] == "./data"
    assert not any(k.startswith("MEDIA_LIBRARY_") for k in api)


def test_second_media_root_passed_through(rc):
    """A second drive must reach the containers, or its libraries can't resolve."""
    env = dict(BASE, RKM_MEDIA_PATH="D:/RKM_MEDIA", RKM_MEDIA_PATH_2="B:/RKM_MEDIA")
    api = rc.build_api_vars(env)
    assert api["RKM_MEDIA_PATH"] == "D:/RKM_MEDIA"
    assert api["RKM_MEDIA_PATH_2"] == "B:/RKM_MEDIA"


def test_ensure_storage_reports_every_root_and_never_seeds_a_real_drive(rc, tmp_path, capsys):
    data = tmp_path / "data"
    rc.ensure_storage(data, {"RKM_MEDIA_PATH": "D:/RKM_MEDIA",
                             "RKM_MEDIA_PATH_2": "B:/RKM_MEDIA"})
    out = capsys.readouterr().out
    assert "media root: D:/RKM_MEDIA → /data" in out
    assert "media root: B:/RKM_MEDIA → /media2" in out
    # app state lives on the primary root only …
    assert (data / "downloads").is_dir() and (data / "rkm").is_dir()
    # … and an absolute (real) root is never seeded with the sample folders
    assert not (data / "media").exists()


def test_ensure_storage_reports_a_library_on_the_second_drive(rc, tmp_path, capsys):
    rc.ensure_storage(tmp_path, {
        "RKM_MEDIA_PATH": "D:/RKM_MEDIA",
        "RKM_MEDIA_PATH_2": "B:/RKM_MEDIA",
        "MEDIA_LIBRARY_1_NAME": "TV Shows",
        "MEDIA_LIBRARY_1_PATH": "B:/RKM_MEDIA/TV Shows",
    })
    out = capsys.readouterr().out
    assert "library 'TV Shows' → /media2/TV Shows" in out
    assert "on B:/RKM_MEDIA" in out          # named, so a wrong drive is obvious
    assert "MISSING (create it" not in out   # never checked against the primary root


def test_prune_setting_passed_through(rc):
    """The provisioner reads .rkm.env — the prune switch must reach it."""
    api = rc.build_api_vars(dict(BASE, RKM_PRUNE_LIBRARIES="false"))
    assert api["RKM_PRUNE_LIBRARIES"] == "false"
    # absent → blank, and the provisioner's own default (ON) applies
    assert rc.build_api_vars(dict(BASE))["RKM_PRUNE_LIBRARIES"] == ""


def test_ensure_storage_seeds_samples_only_for_the_repo_default(rc, tmp_path):
    rc.ensure_storage(tmp_path, {})
    assert (tmp_path / "media/_movie").is_dir()
    assert (tmp_path / "media/_tv").is_dir()


def test_windows_drive_root_is_never_mistaken_for_the_repo_default(rc, tmp_path):
    """D:/… is absolute on Windows but looks relative to a POSIX interpreter."""
    rc.ensure_storage(tmp_path, {"RKM_MEDIA_PATH": "D:\\RKM_MEDIA"})
    assert not (tmp_path / "media").exists()
    assert (tmp_path / "rkm").is_dir()


def test_is_real_media_root_covers_windows_and_posix_forms(rc):
    assert rc.is_real_media_root("D:/RKM_MEDIA")
    assert rc.is_real_media_root(r"B:\RKM_MEDIA")
    assert rc.is_real_media_root("/mnt/media")
    assert rc.is_real_media_root(r"\\nas\media")
    assert not rc.is_real_media_root("./data")
    assert not rc.is_real_media_root("data")
    assert not rc.is_real_media_root("")


def test_ensure_storage_warns_when_no_root_is_configured(rc, tmp_path, capsys):
    rc.ensure_storage(tmp_path, {})
    assert "no RKM_MEDIA_PATH configured" in capsys.readouterr().out


def test_generated_password_is_persisted_once(rc):
    """A blank password is generated + written back to .env exactly once."""
    rc.build_api_vars({"MEDIA_SERVER": "jellyfin", "TMDB_API_KEY": "k"})
    assert any(k == "RKM_JELLYFIN_ADMIN_PASSWORD" for _, k, _ in rc._test_writes)
