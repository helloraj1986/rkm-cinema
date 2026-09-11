"""tools/rkm_common.py — the shared plumbing every operation tool depends on.

The URL resolution is the part worth pinning down: the same `.\rkm-cinema.ps1 status`
must work inside the sandbox (where the stack is at host.docker.internal) and on
the Windows host (where it is at localhost). Getting that wrong made the tools
sandbox-only, which is what these tests prevent regressing.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import rkm_common as rc  # noqa: E402


class TestEnvParsing:
    def test_plain_values(self, tmp_path):
        (tmp_path / ".env").write_text("RKM_JELLYFIN_PORT=8098\nTZ=Australia/Melbourne\n",
                                       encoding="utf-8")
        env = rc.load_env(tmp_path)
        assert env["RKM_JELLYFIN_PORT"] == "8098"
        assert env["TZ"] == "Australia/Melbourne"

    def test_comments_blank_lines_and_export_are_ignored(self, tmp_path):
        (tmp_path / ".env").write_text(
            "# a comment\n\n   \nexport RKM_HOST=x\n", encoding="utf-8")
        env = rc.load_env(tmp_path)
        assert env.get("RKM_HOST") == "x"
        assert "# a comment" not in env

    def test_inline_comment_is_stripped_like_compose_does(self, tmp_path):
        """One .env line must mean the same thing to RKM and to Docker Compose."""
        (tmp_path / ".env").write_text(
            "RKM_MEDIA_PATH_2=B:/RKM_MEDIA   # B: = the TV drive\n", encoding="utf-8")
        assert rc.load_env(tmp_path)["RKM_MEDIA_PATH_2"] == "B:/RKM_MEDIA"

    def test_quoted_values_keep_everything_between_the_quotes(self, tmp_path):
        (tmp_path / ".env").write_text(
            'PASS="has # and spaces"\nOTHER=\'single quoted\'\n', encoding="utf-8")
        env = rc.load_env(tmp_path)
        assert env["PASS"] == "has # and spaces"
        assert env["OTHER"] == "single quoted"

    def test_missing_file_is_not_an_error(self, tmp_path):
        assert rc.load_env(tmp_path) == {}


class TestUrlResolution:
    def test_explicit_url_always_wins(self):
        env = {"RKM_JELLYFIN_PORT": "9999", "RKM_DASHBOARD_PORT": "9998"}
        assert rc.jellyfin_base(env, "http://example.test:1234/") == "http://example.test:1234"
        assert rc.app_base(env, "http://other.test/") == "http://other.test"

    def test_defaults_come_from_env_then_constants(self, monkeypatch):
        monkeypatch.setattr(rc, "pick_host", lambda port: "localhost")
        assert rc.jellyfin_base({}) == f"http://localhost:{rc.DEFAULT_JELLYFIN_PORT}"
        assert rc.jellyfin_base({"RKM_JELLYFIN_PORT": "8123"}) == "http://localhost:8123"
        assert rc.app_base({}) == f"http://localhost:{rc.DEFAULT_DASHBOARD_PORT}"
        assert rc.app_base({"RKM_DASHBOARD_PORT": "8124"}) == "http://localhost:8124"

    def test_host_falls_back_to_localhost_when_the_container_alias_is_absent(self, monkeypatch):
        monkeypatch.setattr(rc, "_reachable", lambda host, port, timeout=1.5: False)
        assert rc.pick_host("8098") == "localhost"

    def test_host_uses_the_container_alias_when_it_answers(self, monkeypatch):
        monkeypatch.setattr(rc, "_reachable", lambda host, port, timeout=1.5: True)
        assert rc.pick_host("8098") == "host.docker.internal"

    def test_repo_root_is_found_by_walking_up_to_the_compose_file(self):
        assert (rc.repo_root() / "docker-compose.yml").is_file()
        # from a nested directory too (the tools import this module from anywhere)
        assert rc.repo_root(REPO / "tools") == rc.repo_root()
