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


def test_env_file_inline_comment_is_stripped_like_compose_does(rc, tmp_path):
    """RKM's parser and Docker Compose must read the same value from one file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment line\n"
        "RKM_MEDIA_PATH=D:/RKM_MEDIA\n"
        "RKM_MEDIA_PATH_2=B:/RKM_MEDIA   # B: = the TV drive\n"
        "PLAIN=a#b\n"
        "QUOTED=\"keeps #hash and spaces\"\n"
        "export EXPORTED=yes\n"
        "EMPTY=\n",
        encoding="utf-8",
    )
    parsed = rc.parse_env_file(env_file)
    assert parsed["RKM_MEDIA_PATH"] == "D:/RKM_MEDIA"
    assert parsed["RKM_MEDIA_PATH_2"] == "B:/RKM_MEDIA"   # comment gone
    assert parsed["PLAIN"] == "a#b"                       # no space → not a comment
    assert parsed["QUOTED"] == "keeps #hash and spaces"   # quoted → verbatim
    assert parsed["EXPORTED"] == "yes"
    assert parsed["EMPTY"] == ""


def test_stripping_an_inline_comment_matches_the_library_path_it_serves(rc, tmp_path):
    """The whole point: the parsed root must match the libraries written beside it."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "RKM_MEDIA_PATH_2=B:/RKM_MEDIA  # the TV drive (mounted at /media2)\n"
        "MEDIA_LIBRARY_1_NAME=TV Shows\n"
        "MEDIA_LIBRARY_1_PATH=B:/RKM_MEDIA/TV Shows\n",
        encoding="utf-8",
    )
    import sys
    sys.path.insert(0, str(rc.ROOT / "backend"))
    from config.media_libraries import parse_media_libraries

    libs, warnings = parse_media_libraries(rc.parse_env_file(env_file))
    assert warnings == []
    assert libs[0].path == "/media2/TV Shows"


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


# ---------------------------------------------------------------- subtitles (Phase 0)
SUBTITLE_ENV = {
    "OPENSUBTITLES_API_KEY": "abc123",
    "OPENSUBTITLES_USERNAME": "",
    "OPENSUBTITLES_PASSWORD": "",
    "OPENSUBTITLES_LANGUAGES": "en",
    "OPENSUBTITLES_ENABLED": "auto",
}


def test_opensubtitles_keys_reach_the_api_env(rc):
    """The api is the only consumer — an unrouted key means a dead feature.

    The api container has no `.env` at all: its configuration IS `.rkm.env`, so a
    credential that does not survive this render can never reach the client
    (2026-09-12, the plan's §3.1 "how a new key actually reaches the api").
    """
    api = rc.build_api_vars(dict(BASE, **SUBTITLE_ENV))
    for key, value in SUBTITLE_ENV.items():
        assert api[key] == value, key


def test_key_only_renders_as_enabled_and_reports_itself(rc, capsys):
    api = rc.build_api_vars(dict(BASE, OPENSUBTITLES_API_KEY="abc123",
                                 OPENSUBTITLES_LANGUAGES="en,hi"))
    assert api["OPENSUBTITLES_USERNAME"] == ""
    out = capsys.readouterr().out
    assert "OpenSubtitles: enabled" in out
    assert "anonymous (no login)" in out
    assert "en,hi" in out
    assert "abc123" not in out, "the key must never be printed"


def test_absent_keys_render_blank_and_say_so(rc, capsys):
    """Blank is a supported state: no key = the feature is off, not a broken stack."""
    api = rc.build_api_vars(dict(BASE))
    assert all(api.get(k) == "" for k in SUBTITLE_ENV)
    assert "OpenSubtitles: not configured" in capsys.readouterr().out


def test_a_pasted_block_with_a_bom_still_renders_the_key(rc, tmp_path):
    """The plan's §4.1 trap: the spec's snippet starts with a BOM.

    Read as plain utf-8 it renamed the FIRST key to ``\\ufeffOPENSUBTITLES_API_KEY`` —
    the credential then simply vanished, with nothing logged anywhere.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("\ufeffOPENSUBTITLES_API_KEY=abc123\nTMDB_API_KEY=k\n", encoding="utf-8")
    parsed = rc.parse_env_file(env_file)
    assert parsed["OPENSUBTITLES_API_KEY"] == "abc123"
    assert not any(k.startswith("\ufeff") for k in parsed)
    assert rc.build_api_vars(dict(parsed, MEDIA_SERVER="jellyfin",
                                  RKM_JELLYFIN_ADMIN_PASSWORD="pw"))["OPENSUBTITLES_API_KEY"] == "abc123"


# ---------------------------------------------------------------- retired MEDIA_SERVER
def test_retired_media_server_still_renders_and_resolves_to_jellyfin(rc, capsys):
    """An un-updated `.env` naming a retired backend must NOT be able to fail.

    Regression guard for the deploy that would strand the Windows box: this used
    to `fail()` the render, and even a tolerated pass-through would skip the
    Jellyfin admin-password generation below (that block is gated on the backend),
    which produces a stack whose libraries are all disabled.
    """
    api = rc.build_api_vars(dict(BASE, MEDIA_SERVER="plex",
                                 PLEX_URL="http://old:32400", PLEX_TOKEN="legacy"))
    assert api["MEDIA_SERVER"] == "jellyfin"          # normalised, not passed through
    assert "PLEX_URL" not in api and "PLEX_TOKEN" not in api
    out = capsys.readouterr().out
    assert "MEDIA_SERVER=plex is not a live backend" in out   # warned, not failed


def test_retired_media_server_still_generates_the_admin_password(rc, monkeypatch):
    """The password generation is gated on the backend — a legacy value must not skip it."""
    writes = []
    monkeypatch.setattr(rc, "write_env_key", lambda path, k, v: writes.append((k, v)))
    env = {"MEDIA_SERVER": "emby", "TMDB_API_KEY": "k"}   # no JELLYFIN admin password yet
    api = rc.build_api_vars(env)
    assert api["MEDIA_SERVER"] == "jellyfin"
    assert any(k == "RKM_JELLYFIN_ADMIN_PASSWORD" and v for k, v in writes), writes


def test_unknown_media_server_warns_instead_of_failing(rc, capsys):
    """A typo is tolerated too: the api's resolver already maps it to jellyfin."""
    api = rc.build_api_vars(dict(BASE, MEDIA_SERVER="typo-backend"))
    assert api["MEDIA_SERVER"] == "jellyfin"
    assert "is not a live backend" in capsys.readouterr().out


# --- Auth / multi-user (AUTH_MULTIUSER_PLAN Phase 0) --------------------------
# The api container's environment is the RENDERED .rkm.env, so a key that is not
# carried here cannot be set by the user at all — `RKM_AUTH_REQUIRED` would read
# false forever, and the lockout recovery would silently do nothing.

def test_auth_required_defaults_to_false(rc):
    """Absent = not enforced. An un-updated `.env` must keep working as it does now."""
    assert rc.build_api_vars(dict(BASE))["RKM_AUTH_REQUIRED"] == "false"


def test_auth_required_is_carried_when_armed(rc):
    api = rc.build_api_vars(dict(BASE, RKM_AUTH_REQUIRED="true"))
    assert api["RKM_AUTH_REQUIRED"] == "true"


def test_auth_required_is_normalised_and_a_typo_renders_false(rc, capsys):
    """`.rkm.env` must be unambiguous, and a typo must fail OPEN, never closed."""
    assert rc.build_api_vars(dict(BASE, RKM_AUTH_REQUIRED=" TRUE "))["RKM_AUTH_REQUIRED"] == "true"
    api = rc.build_api_vars(dict(BASE, RKM_AUTH_REQUIRED="yes"))
    assert api["RKM_AUTH_REQUIRED"] == "false"
    assert "RKM_AUTH_REQUIRED" in capsys.readouterr().out
