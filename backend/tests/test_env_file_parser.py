"""ONE .env parser for every reader (2026-09-12, SUBTITLES_OPENSUBTITLES_PLAN Phase 0).

The same `.env` was read by three implementations: `render_config.py` (the host-side
renderer), `config.settings` (the api's file layer) and `tools/rkm_common` (the probe
tools). Two of them disagreed about quoting — `KEY='p#ss w0rd'` arrived WITH its
quotes on the api's bare-checkout path — and none of them tolerated a leading UTF-8
BOM, which silently renames the first key to `\ufeffKEY` (the plan's §4.1 trap: the
spec's own snippet starts with a BOM, so pasting it would have killed the feature with
no error anywhere).

These tests pin the RULES and then prove the three readers AGREE on one tricky file —
the parity assertion is the one that stops the implementations drifting apart again.
"""
import importlib.util
import sys
from pathlib import Path

from config.env_file import (BOM, parse_env_file, parse_env_line, parse_env_text,
                             strip_bom, strip_inline_comment)

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root

#: Exercise every rule at once. Kept as one string so the parity test uses the
#: EXACT bytes the rule tests use.
TRICKY = (
    "# a comment line\n"
    "\n"
    "PLAIN=value\n"
    "SPACED = value   \n"
    "HASH_IN_VALUE=a#b\n"
    "INLINE_COMMENT=D:/RKM_MEDIA   # the movie drive\n"
    'QUOTED_DOUBLE="keeps #hash and spaces"\n'
    "QUOTED_SINGLE='p#ss w0rd'\n"
    "export EXPORTED=yes\n"
    "EMPTY=\n"
    "NOT_A_PAIR\n"
    "  INDENTED=ok\n"
)

EXPECTED = {
    "PLAIN": "value",
    "SPACED": "value",                    # surrounding whitespace trimmed
    "HASH_IN_VALUE": "a#b",               # no space → not a comment
    "INLINE_COMMENT": "D:/RKM_MEDIA",     # " #" starts a comment
    "QUOTED_DOUBLE": "keeps #hash and spaces",
    "QUOTED_SINGLE": "p#ss w0rd",         # the value that used to arrive quoted
    "EXPORTED": "yes",
    "EMPTY": "",
    "INDENTED": "ok",
}


class TestRules:
    def test_the_tricky_file_parses_to_the_expected_values(self):
        assert parse_env_text(TRICKY) == EXPECTED

    def test_key_without_an_equals_sign_is_ignored(self):
        assert parse_env_line("NOT_A_PAIR") is None
        assert parse_env_line("# comment") is None
        assert parse_env_line("   ") is None

    def test_a_leading_bom_does_not_rename_the_first_key(self):
        """The plan's §4.1 trap: a pasted block's BOM used to rename key #1."""
        parsed = parse_env_text(BOM + "OPENSUBTITLES_API_KEY=abc\nSECOND=2\n")
        assert parsed == {"OPENSUBTITLES_API_KEY": "abc", "SECOND": "2"}
        assert not any(k.startswith(BOM) for k in parsed), "a key carries the BOM"

    def test_a_bom_only_on_the_first_line_is_stripped(self):
        assert parse_env_text("\n" + BOM + "KEY=1\n") == {"KEY": "1"}

    def test_strip_bom_is_a_no_op_without_one(self):
        assert strip_bom("KEY=1") == "KEY=1"
        assert strip_bom("") == ""

    def test_inline_comment_rule_is_the_compose_rule(self):
        assert strip_inline_comment("v   # note") == "v"
        assert strip_inline_comment("a#b") == "a#b"
        assert strip_inline_comment("v") == "v"

    def test_a_missing_file_parses_to_empty(self, tmp_path):
        assert parse_env_file(tmp_path / "nope.env") == {}

    def test_a_quoted_value_keeps_its_hash_and_spaces(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("KEY='a # b'\n", encoding="utf-8")
        assert parse_env_file(f)["KEY"] == "a # b"


# ------------------------------------------------------------------ the three readers
def _render_config():
    """render_config.py loaded by path (it is a repo-root script, not a package)."""
    spec = importlib.util.spec_from_file_location("render_config_parity", ROOT / "render_config.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["render_config_parity"] = mod
    spec.loader.exec_module(mod)
    return mod


def _rkm_common():
    spec = importlib.util.spec_from_file_location("rkm_common_parity", ROOT / "tools" / "rkm_common.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rkm_common_parity"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_parity_env(tmp_path: Path) -> Path:
    """A file carrying all three traps, with real declared keys so Config shows them."""
    path = tmp_path / ".env"
    path.write_text(
        BOM                                            # 1. the BOM trap
        + "OPENSUBTITLES_API_KEY='k#1 please'\n"       # 2. the quoting trap
        + "RKM_MEDIA_PATH=D:/RKM_MEDIA   # movie drive\n"   # 3. the inline comment
        + 'TMDB_API_KEY="quoted key"\n'
        + "OPENSUBTITLES_LANGUAGES=en, hi ,en\n",
        encoding="utf-8",
    )
    return path


class TestReadersAgree:
    """One file, one reading — for all three consumers."""

    def test_render_config_and_the_tools_produce_identical_dicts(self, tmp_path):
        from config.env_file import parse_env_file as shared

        env_path = _write_parity_env(tmp_path)
        renderer = _render_config().parse_env_file(env_path)
        tools = _rkm_common().load_env(tmp_path)
        assert renderer == tools, "the renderer and the tools disagree about one file"
        # ... and both equal the shared parser, so neither carries a stray copy
        assert renderer == shared(env_path)

    def test_the_api_reads_the_same_values(self, tmp_path, monkeypatch):
        from config import settings as settings_mod

        env_path = _write_parity_env(tmp_path)
        for key in ("OPENSUBTITLES_API_KEY", "OPENSUBTITLES_LANGUAGES", "TMDB_API_KEY",
                    "RKM_MEDIA_PATH", "OPENSUBTITLES_USERNAME", "OPENSUBTITLES_PASSWORD"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setattr(settings_mod, "canonical_env_paths", lambda: [env_path])

        cfg = settings_mod.Config()
        assert cfg.OPENSUBTITLES_API_KEY == "k#1 please"   # quotes gone, '#' kept
        assert cfg.TMDB_API_KEY == "quoted key"
        assert cfg.opensubtitles_languages() == ["en", "hi"]
        # and the shared parser agrees key for key
        parsed = settings_mod.parse_env_file(env_path)
        assert parsed["OPENSUBTITLES_API_KEY"] == cfg.OPENSUBTITLES_API_KEY
        assert parsed["TMDB_API_KEY"] == cfg.TMDB_API_KEY

    def test_the_api_layer_never_hands_quotes_to_the_caller(self, tmp_path, monkeypatch):
        """The regression itself: a quoted value used to arrive WITH its quotes.

        A password containing ``#`` (or a space) is the real-world case — it was
        truncated or wrong on a bare-checkout run while the container (which gets the
        rendered .rkm.env) was fine, i.e. "works in docker, fails locally".
        """
        from config import settings as settings_mod

        env_path = tmp_path / ".env"
        env_path.write_text("OPENSUBTITLES_PASSWORD='p#ss w0rd'\n", encoding="utf-8")
        for key in ("OPENSUBTITLES_PASSWORD", "OPENSUBTITLES_API_KEY"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setattr(settings_mod, "canonical_env_paths", lambda: [env_path])
        assert settings_mod.Config().OPENSUBTITLES_PASSWORD == "p#ss w0rd"
