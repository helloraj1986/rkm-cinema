"""OpenSubtitles config plumbing (SUBTITLES_OPENSUBTITLES_PLAN Phase 0).

Phase 0 ships NO subtitle behaviour: it declares the settings, proves they survive the
env passthrough, and pins the availability rules the later phases build on. The two
rules worth guarding are the ones the plan calls out:

* **the API key is what enables the feature** — it is mandatory on every OpenSubtitles
  call and carries the anonymous allowance, so it must reach the api at all;
* **a missing LOGIN must never disable it** — username/password only raise the daily
  quota (rank-dependent); key-only is a supported mode, and "login absent → subtitle
  search off" would silently break a working anonymous setup.

Also pinned: nothing is required, and no credential reaches the public config. An
undeclared key is dropped by the real-env passthrough (the 2026-09-10 RKM_MEDIA_PATH
bug greyed out every library that way), so `KNOWN_KEYS` in
``test_config_env_passthrough`` is extended deliberately, not silently.
"""
import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.main
from config import settings as settings_mod
from config.settings import Config

#: The five keys Phase 0 introduces, and the env a "configured" box looks like.
SUBTITLE_KEYS = (
    "OPENSUBTITLES_API_KEY", "OPENSUBTITLES_USERNAME", "OPENSUBTITLES_PASSWORD",
    "OPENSUBTITLES_LANGUAGES", "OPENSUBTITLES_ENABLED",
)
KEY_ONLY = {"OPENSUBTITLES_API_KEY": "abc123"}


@pytest.fixture()
def cfg_from_env(tmp_path, monkeypatch):
    """A Config whose ONLY config source is a .env file this test writes."""
    env_path = tmp_path / ".env"

    def build(text: str):
        env_path.write_text(text, encoding="utf-8")
        for key in (*SUBTITLE_KEYS, "TMDB_API_KEY", "WATCHLIST_SCHEDULER"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setattr(settings_mod, "canonical_env_paths", lambda: [env_path])
        return Config()

    return build


class TestDeclaredEverywhere:
    def test_the_keys_are_declared_so_the_passthrough_carries_them(self):
        """An UNdeclared key is silently dropped before the api ever sees it."""
        keys = Config()._get_all_keys()
        missing = sorted(k for k in SUBTITLE_KEYS if k not in keys)
        assert missing == [], f"not declared on Config: {missing}"

    def test_real_env_vars_reach_the_config(self):
        passed = Config()._env_passthrough({"OPENSUBTITLES_API_KEY": "k",
                                            "OPENSUBTITLES_LANGUAGES": "en,hi",
                                            "SOME_OTHER_KEY": "x"})
        assert passed == {"OPENSUBTITLES_API_KEY": "k", "OPENSUBTITLES_LANGUAGES": "en,hi"}


class TestAvailability:
    def test_key_alone_enables_it(self, cfg_from_env):
        cfg = cfg_from_env("OPENSUBTITLES_API_KEY=abc123\n")
        assert cfg.has_opensubtitles() is True
        assert cfg.has_opensubtitles_login() is False      # anonymous tier

    def test_a_missing_login_never_disables_it(self, cfg_from_env):
        """Key-only is a supported mode — the plan's §3.1 rule, pinned."""
        cfg = cfg_from_env("OPENSUBTITLES_API_KEY=abc123\nOPENSUBTITLES_USERNAME=\n"
                           "OPENSUBTITLES_PASSWORD=\n")
        assert cfg.has_opensubtitles() is True
        assert cfg.has_opensubtitles_login() is False

    def test_username_alone_is_not_a_login(self, cfg_from_env):
        cfg = cfg_from_env("OPENSUBTITLES_API_KEY=abc123\nOPENSUBTITLES_USERNAME=rajee\n")
        assert cfg.has_opensubtitles() is True
        assert cfg.has_opensubtitles_login() is False

    def test_username_and_password_are_reported_as_a_login(self, cfg_from_env):
        cfg = cfg_from_env("OPENSUBTITLES_API_KEY=abc123\nOPENSUBTITLES_USERNAME=rajee\n"
                           "OPENSUBTITLES_PASSWORD=pw\n")
        assert cfg.has_opensubtitles_login() is True

    def test_no_key_means_off(self, cfg_from_env):
        cfg = cfg_from_env("OPENSUBTITLES_USERNAME=rajee\nOPENSUBTITLES_PASSWORD=pw\n")
        assert cfg.has_opensubtitles() is False

    @pytest.mark.parametrize("value", ["false", "False", "0", "no", "off"])
    def test_an_explicit_off_beats_a_present_key(self, cfg_from_env, value):
        cfg = cfg_from_env(f"OPENSUBTITLES_API_KEY=abc123\nOPENSUBTITLES_ENABLED={value}\n")
        assert cfg.has_opensubtitles() is False
        assert cfg.opensubtitles_disabled() is True

    @pytest.mark.parametrize("value", ["auto", "true", "on", "1", ""])
    def test_enabled_values_do_not_disable_it(self, cfg_from_env, value):
        cfg = cfg_from_env(f"OPENSUBTITLES_API_KEY=abc123\nOPENSUBTITLES_ENABLED={value}\n")
        assert cfg.has_opensubtitles() is True

    def test_enabling_without_a_key_stays_off(self, cfg_from_env):
        """The key is mandatory on every call: 'enabled' cannot conjure one."""
        cfg = cfg_from_env("OPENSUBTITLES_ENABLED=true\n")
        assert cfg.has_opensubtitles() is False

    def test_never_required_by_validate_required(self, cfg_from_env):
        """A blank config must boot: subtitles are optional (spec criterion 10)."""
        cfg = cfg_from_env("RADARR_API_KEY=k\nSONARR_API_KEY=k\n")
        assert cfg.validate_required() == []
        assert cfg.has_opensubtitles() is False


class TestLanguages:
    def test_default_is_english(self, cfg_from_env):
        cfg = cfg_from_env("")
        assert cfg.OPENSUBTITLES_LANGUAGES == "en"
        assert cfg.opensubtitles_languages() == ["en"]

    def test_parsed_lowercased_deduped_and_order_kept(self, cfg_from_env):
        cfg = cfg_from_env("OPENSUBTITLES_LANGUAGES=en, HI ,hi,, Tamil\n")
        assert cfg.opensubtitles_languages() == ["en", "hi", "tamil"]

    @pytest.mark.parametrize("raw", ["", " ", ",", ",,"])
    def test_an_empty_list_falls_back_to_english(self, cfg_from_env, raw):
        cfg = cfg_from_env(f"OPENSUBTITLES_LANGUAGES={raw}\n")
        assert cfg.opensubtitles_languages() == ["en"]


class TestSecretsStayServerSide:
    def test_the_public_config_exposes_no_subtitle_credentials(self, monkeypatch):
        """Criterion 11: credentials must never reach the frontend."""
        from api.routes import config as config_route

        fake_lib = SimpleNamespace(providers=[SimpleNamespace(health=lambda: True)])
        monkeypatch.setattr(config_route, "build_library_service", lambda cfg: fake_lib)
        monkeypatch.setattr(config_route, "build_acquisition_service",
                            lambda config=None: SimpleNamespace(
                                health=lambda: {"radarr": False, "sonarr": False}))

        r = TestClient(api.main.app).get("/api/config")
        assert r.status_code == 200
        body = r.json()
        assert set(body["services"]) == {"radarr", "sonarr", "tmdb", "jellyfin"}
        payload = json.dumps(body).lower()
        for token in ("opensubtitles", "subtitlekey", "api_key", "api-key"):
            assert token not in payload, f"{token!r} leaked into /api/config"


class TestStartupLogLine:
    """ONE clear line, so "why is subtitle search empty?" is answerable from the log."""

    def _startup_messages(self, monkeypatch, tmp_path, env_text):
        env_path = tmp_path / ".env"
        env_path.write_text(env_text, encoding="utf-8")
        for key in (*SUBTITLE_KEYS, "WATCHLIST_SCHEDULER"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setattr(settings_mod, "canonical_env_paths", lambda: [env_path])
        settings_mod.get_config.cache_clear()
        try:
            app = api.main.create_app()
            messages = []
            monkeypatch.setattr(logging, "info",
                                lambda msg, *a, **k: messages.append(msg % a if a else msg))
            asyncio.run(app.router.on_startup[0]())
        finally:
            settings_mod.get_config.cache_clear()
        return messages

    def test_unconfigured_says_so_and_why(self, monkeypatch, tmp_path):
        messages = self._startup_messages(monkeypatch, tmp_path, "TMDB_API_KEY=k\n")
        assert any("OpenSubtitles not configured" in m and "OPENSUBTITLES_API_KEY" in m
                   for m in messages), messages

    def test_disabled_by_flag_names_the_flag(self, monkeypatch, tmp_path):
        messages = self._startup_messages(
            monkeypatch, tmp_path,
            "OPENSUBTITLES_API_KEY=abc123\nOPENSUBTITLES_ENABLED=false\n")
        assert any("OpenSubtitles not configured" in m and "OPENSUBTITLES_ENABLED" in m
                   for m in messages), messages

    def test_key_only_is_reported_as_anonymous(self, monkeypatch, tmp_path):
        messages = self._startup_messages(monkeypatch, tmp_path,
                                         "OPENSUBTITLES_API_KEY=abc123\n")
        line = next(m for m in messages if "OpenSubtitles" in m)
        assert "anonymous" in line and "en" in line
        assert "abc123" not in line, "the API key must never be logged"

    def test_a_login_is_reported_without_leaking_it(self, monkeypatch, tmp_path):
        messages = self._startup_messages(
            monkeypatch, tmp_path,
            "OPENSUBTITLES_API_KEY=abc123\nOPENSUBTITLES_USERNAME=rajeev\n"
            "OPENSUBTITLES_PASSWORD='p#ss w0rd'\n")
        line = next(m for m in messages if "OpenSubtitles" in m)
        assert "login configured" in line
        for secret in ("p#ss w0rd", "rajeev"):
            assert secret not in line, "the login must never be logged"
