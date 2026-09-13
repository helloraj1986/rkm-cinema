"""`tools/set_env_value.py` — the .env editor behind `rkm-cinema.ps1 auth on|off`.

⚠ **And the FIRST direct test of `render_config.py::write_env_key`**, which every one of these depends
on. Until now it was only ever *stubbed* by the renderer's own tests (they assert the renderer CALLS it,
never what it does to a file) — so its promise, "append or replace one key, preserving everything
else", was untested while it quietly became the thing that edits the user's single source of config.

What must hold: comments, ordering, other keys and a BOM all survive; a missing key is APPENDED; a
value that already matches changes nothing (no write, no backup).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for extra in (REPO / "tools", REPO):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import set_env_value as sev  # noqa: E402
from render_config import write_env_key  # noqa: E402

SAMPLE = """\
# ---------------------------------------------------------------- stack
# A comment that must survive, with an = sign and a # inside it
RKM_DASHBOARD_PORT=8124
RKM_JELLYFIN_PORT=8098

#-----RKM-CINEMA-AUTH------
RKM_AUTH_REQUIRED=false

# ---- metadata ----
TMDB_API_KEY=abc123   # trailing comment on its own key
"""


@pytest.fixture()
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(SAMPLE, encoding="utf-8")
    return path


class TestWriteEnvKey:
    """The repo's existing writer, pinned directly for the first time."""

    def test_it_replaces_the_value_and_keeps_everything_else(self, env_file):
        write_env_key(env_file, "RKM_AUTH_REQUIRED", "true")
        text = env_file.read_text(encoding="utf-8")
        assert "RKM_AUTH_REQUIRED=true" in text
        assert "RKM_AUTH_REQUIRED=false" not in text
        # every comment and every other key untouched, in order
        for kept in ("# A comment that must survive, with an = sign and a # inside it",
                     "#-----RKM-CINEMA-AUTH------", "RKM_DASHBOARD_PORT=8124",
                     "RKM_JELLYFIN_PORT=8098", "TMDB_API_KEY=abc123   # trailing comment on its own key"):
            assert kept in text
        assert text.index("RKM_DASHBOARD_PORT") < text.index("RKM_AUTH_REQUIRED") < text.index("TMDB_API_KEY")

    def test_a_missing_key_is_appended_not_dropped(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text("A=1\n", encoding="utf-8")
        write_env_key(path, "RKM_AUTH_REQUIRED", "true")
        assert path.read_text(encoding="utf-8") == "A=1\nRKM_AUTH_REQUIRED=true\n"

    def test_it_creates_the_file_when_there_is_none(self, tmp_path):
        path = tmp_path / ".env"
        write_env_key(path, "A", "1")
        assert path.read_text(encoding="utf-8") == "A=1\n"

    def test_a_commented_out_key_is_NOT_a_key_and_stays_a_comment(self, env_file):
        """`# RKM_AUTH_REQUIRED=false` is documentation, not config — it must not be rewritten."""
        write_env_key(env_file, "RKM_AUTH_REQUIRED", "true")
        assert "# RKM_AUTH_REQUIRED=false" not in env_file.read_text(encoding="utf-8")
        assert env_file.read_text(encoding="utf-8").count("RKM_AUTH_REQUIRED=") == 1


class TestSetValue:
    def test_it_changes_the_value_and_takes_a_backup_first(self, env_file):
        result = sev.set_value(env_file, "RKM_AUTH_REQUIRED", "true")
        assert result["changed"] is True
        assert result["old"] == "false" and result["new"] == "true"
        backup = Path(result["backup"])
        assert backup.exists() and backup.name.startswith(".env.bak-")
        # the backup is the file as it WAS, byte for byte
        assert backup.read_text(encoding="utf-8") == SAMPLE
        assert "RKM_AUTH_REQUIRED=true" in env_file.read_text(encoding="utf-8")

    def test_setting_the_value_it_already_has_changes_nothing(self, env_file):
        """No write, no backup, no mtime churn — a no-op must be visibly a no-op."""
        before = env_file.read_text(encoding="utf-8")
        result = sev.set_value(env_file, "RKM_AUTH_REQUIRED", "false")
        assert result["changed"] is False
        assert result["backup"] is None
        assert env_file.read_text(encoding="utf-8") == before
        assert list(env_file.parent.glob(".env.bak-*")) == []

    def test_a_dry_run_writes_nothing_at_all(self, env_file):
        result = sev.set_value(env_file, "RKM_AUTH_REQUIRED", "true", dry_run=True)
        assert result["changed"] is True
        assert env_file.read_text(encoding="utf-8") == SAMPLE
        assert list(env_file.parent.glob(".env.bak-*")) == []

    def test_an_absent_key_is_ADDED(self, env_file):
        result = sev.set_value(env_file, "RKM_AUTH_REQUIRED", "true")
        assert result["old"] == "false"
        env_file.unlink()
        env_file.write_text("OTHER=1\n", encoding="utf-8")
        added = sev.set_value(env_file, "RKM_AUTH_REQUIRED", "true")
        assert added["old"] is None and added["changed"] is True
        assert "RKM_AUTH_REQUIRED=true" in env_file.read_text(encoding="utf-8")

    @pytest.mark.parametrize("value", ["true\nRKM_EVIL=1", "true\r\nRKM_EVIL=1", "a\nb"])
    def test_a_value_with_a_line_break_is_REFUSED(self, env_file, value):
        """A newline is a second line in .env — an injection, not a value."""
        with pytest.raises(sev.ValueError_):
            sev.set_value(env_file, "RKM_AUTH_REQUIRED", value)
        assert env_file.read_text(encoding="utf-8") == SAMPLE

    @pytest.mark.parametrize("key", ["", "  ", "A B", "A=B", "A#B"])
    def test_an_unusable_key_is_REFUSED(self, env_file, key):
        with pytest.raises(sev.ValueError_):
            sev.set_value(env_file, key, "x")

    def test_the_cli_reports_the_change_and_the_backup(self, env_file, capsys):
        code = sev.main(["--file", str(env_file), "RKM_AUTH_REQUIRED", "true"])
        out = capsys.readouterr().out
        assert code == 0
        assert "false -> true" in out
        assert "backup: .env.bak-" in out

    def test_the_cli_says_so_when_there_is_nothing_to_do(self, env_file, capsys):
        code = sev.main(["--file", str(env_file), "RKM_AUTH_REQUIRED", "false"])
        assert code == 0
        assert "nothing to do" in capsys.readouterr().out

    def test_the_cli_refuses_a_bad_value_with_a_nonzero_code(self, env_file, capsys):
        code = sev.main(["--file", str(env_file), "RKM_AUTH_REQUIRED", "true\nEVIL=1"])
        assert code == 2
        assert "REFUSED" in capsys.readouterr().err
        assert env_file.read_text(encoding="utf-8") == SAMPLE

    def test_the_cli_dry_run_touches_nothing(self, env_file, capsys):
        code = sev.main(["--file", str(env_file), "RKM_AUTH_REQUIRED", "true", "--dry-run"])
        assert code == 0
        assert "would set" in capsys.readouterr().out
        assert env_file.read_text(encoding="utf-8") == SAMPLE
