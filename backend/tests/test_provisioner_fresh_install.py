"""Provisioning a FRESH Jellyfin (empty /config volume).

2026-09-10, real failure: after dropping the damaged `jellyfin-config` volume,
Jellyfin came up serving its HTML "Jellyfin Startup" page. The provisioner:
  - called the port ready because /System/Info/Public answered 200 in that window,
  - got HTTP 503 trying to authenticate,
  - and SKIPPED creating the admin entirely, because wizard_pending() returned
    False when it could not tell (it treated "unknown" as "already set up").
Net result: no API key was written, so the api could not read any library and
EVERY library showed as disabled in the sidebar.

These tests pin the fixed behaviour: patience while Jellyfin boots, a tri-state
wizard check, and a fast, clearly-explained failure only when the credentials are
genuinely wrong.
"""
import sys
from pathlib import Path

import pytest

_PROV_DIR = Path(__file__).resolve().parent.parent / "provisioner"
if str(_PROV_DIR) not in sys.path:
    sys.path.insert(0, str(_PROV_DIR))

import provision  # noqa: E402

#: What Jellyfin serves while it initialises a new config volume.
BOOT_PAGE = (503, {"error": "<!DOCTYPE html><html><title>Jellyfin Startup</title>"})
#: /System/Info/Public before the API is really usable.
INFO_NO_VERSION = (200, {"ServerName": "rkm"})
INFO_READY = (200, {"ServerName": "rkm", "Version": "10.11.11"})
WIZARD_PENDING = (200, {"StartupWizardCompleted": False, "Version": "10.11.11"})
WIZARD_DONE = (200, {"StartupWizardCompleted": True, "Version": "10.11.11"})


@pytest.fixture()
def no_sleep(monkeypatch):
    """Never actually wait in tests."""
    calls = []
    monkeypatch.setattr(provision.time, "sleep", lambda s: calls.append(s))
    return calls


class TestWaitReady:
    def test_boot_page_does_not_count_as_ready(self, monkeypatch, no_sleep):
        """503 while starting, then a real JSON answer -> ready (and it waited)."""
        responses = [BOOT_PAGE, INFO_NO_VERSION, INFO_READY]
        monkeypatch.setattr(provision, "_request", lambda *a, **k: responses.pop(0))
        provision.wait_ready(retries=10, delay=0)
        assert no_sleep, "it should have waited between attempts"

    def test_200_without_version_is_not_ready(self, monkeypatch, no_sleep):
        responses = [INFO_NO_VERSION, INFO_NO_VERSION, INFO_READY]
        monkeypatch.setattr(provision, "_request", lambda *a, **k: responses.pop(0))
        provision.wait_ready(retries=10, delay=0)
        assert len(no_sleep) == 2

    def test_timeout_exits(self, monkeypatch, no_sleep):
        monkeypatch.setattr(provision, "_request", lambda *a, **k: BOOT_PAGE)
        with pytest.raises(SystemExit):
            provision.wait_ready(retries=3, delay=0)


class TestWizardPending:
    def test_true_when_the_wizard_is_incomplete(self, monkeypatch):
        monkeypatch.setattr(provision, "_request", lambda *a, **k: WIZARD_PENDING)
        assert provision.wizard_pending() is True

    def test_false_when_complete(self, monkeypatch):
        monkeypatch.setattr(provision, "_request", lambda *a, **k: WIZARD_DONE)
        assert provision.wizard_pending() is False

    def test_none_while_the_boot_page_is_up(self, monkeypatch):
        """Unknown must NOT look like 'already set up' — that was the bug."""
        monkeypatch.setattr(provision, "_request", lambda *a, **k: BOOT_PAGE)
        assert provision.wizard_pending() is None

    def test_none_when_the_field_is_absent(self, monkeypatch):
        monkeypatch.setattr(provision, "_request", lambda *a, **k: INFO_READY)
        assert provision.wizard_pending() is None


class TestEnsureAdmin:
    def test_authenticates_immediately_when_ready(self, monkeypatch, no_sleep):
        monkeypatch.setattr(provision, "authenticate", lambda quiet=False: "tok")
        assert provision.ensure_admin(retries=5, delay=0) == "tok"
        assert no_sleep == []

    def test_waits_out_a_booting_jellyfin_then_succeeds(self, monkeypatch, no_sleep):
        """The exact live case: 503 for a while, then auth works."""
        state = {"n": 0}

        def fake_auth(quiet=False):
            state["n"] += 1
            return "tok" if state["n"] >= 4 else None

        monkeypatch.setattr(provision, "authenticate", fake_auth)
        monkeypatch.setattr(provision, "wizard_pending", lambda: None)  # still booting
        assert provision.ensure_admin(retries=10, delay=0) == "tok"
        assert state["n"] == 4
        assert len(no_sleep) == 3, "it must keep waiting, not give up"

    def test_creates_the_admin_on_a_truly_fresh_install(self, monkeypatch, no_sleep):
        state = {"auth": 0, "startup": 0}

        def fake_auth(quiet=False):
            state["auth"] += 1
            return "tok" if state["startup"] else None   # works only after the wizard

        def fake_startup():
            state["startup"] += 1
            return True

        monkeypatch.setattr(provision, "authenticate", fake_auth)
        monkeypatch.setattr(provision, "wizard_pending", lambda: True)
        monkeypatch.setattr(provision, "run_startup", fake_startup)
        assert provision.ensure_admin(retries=5, delay=0) == "tok"
        assert state["startup"] == 1

    def test_wrong_credentials_fail_fast_with_an_explanation(self, monkeypatch, no_sleep, capsys):
        """Wizard COMPLETE + auth failing = a credentials problem: don't retry 40x."""
        calls = {"n": 0}

        def fake_auth(quiet=False):
            calls["n"] += 1
            return None

        monkeypatch.setattr(provision, "authenticate", fake_auth)
        monkeypatch.setattr(provision, "wizard_pending", lambda: False)
        assert provision.ensure_admin(retries=40, delay=0) is None
        assert calls["n"] == 1, "no pointless retries on a credentials problem"
        out = capsys.readouterr().out
        assert "RKM_JELLYFIN_ADMIN_PASSWORD" in out

    def test_gives_up_after_the_retry_budget(self, monkeypatch, no_sleep, capsys):
        monkeypatch.setattr(provision, "authenticate", lambda quiet=False: None)
        monkeypatch.setattr(provision, "wizard_pending", lambda: None)
        assert provision.ensure_admin(retries=3, delay=0) is None
        assert "gave up waiting" in capsys.readouterr().out
