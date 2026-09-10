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


def test_generated_password_is_persisted_once(rc):
    """A blank password is generated + written back to .env exactly once."""
    rc.build_api_vars({"MEDIA_SERVER": "jellyfin", "TMDB_API_KEY": "k"})
    assert any(k == "RKM_JELLYFIN_ADMIN_PASSWORD" for _, k, _ in rc._test_writes)
