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
import json
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
        monkeypatch.setattr(provision, "authenticate", lambda password=None, quiet=False: "tok")
        assert provision.ensure_admin(retries=5, delay=0) == "tok"
        assert no_sleep == []

    def test_waits_out_a_booting_jellyfin_then_succeeds(self, monkeypatch, no_sleep):
        """The exact live case: 503 for a while, then auth works."""
        state = {"n": 0}

        def fake_auth(password=None, quiet=False):
            state["n"] += 1
            return "tok" if state["n"] >= 4 else None

        monkeypatch.setattr(provision, "authenticate", fake_auth)
        monkeypatch.setattr(provision, "wizard_pending", lambda: None)  # still booting
        assert provision.ensure_admin(retries=10, delay=0) == "tok"
        assert state["n"] == 4
        assert len(no_sleep) == 3, "it must keep waiting, not give up"

    def test_creates_the_admin_on_a_truly_fresh_install(self, monkeypatch, no_sleep):
        state = {"auth": 0, "startup": 0}

        def fake_auth(password=None, quiet=False):
            state["auth"] += 1
            return "tok" if state["startup"] else None   # works only after the wizard

        def fake_startup(password=None):
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

        def fake_auth(password=None, quiet=False):
            calls["n"] += 1
            return None

        monkeypatch.setattr(provision, "authenticate", fake_auth)
        monkeypatch.setattr(provision, "wizard_pending", lambda: False)
        assert provision.ensure_admin(retries=40, delay=0) is None
        assert calls["n"] == 1, "no pointless retries on a credentials problem"
        out = capsys.readouterr().out
        assert "RKM_JELLYFIN_ADMIN_PASSWORD" in out

    def test_gives_up_after_the_retry_budget(self, monkeypatch, no_sleep, capsys):
        monkeypatch.setattr(provision, "authenticate", lambda password=None, quiet=False: None)
        monkeypatch.setattr(provision, "wizard_pending", lambda: None)
        assert provision.ensure_admin(retries=3, delay=0) is None
        assert "gave up waiting" in capsys.readouterr().out


# --------------------------------------------------------------------------------------------
# Phase 1 (ADMIN_CREDENTIALS_PLAN.md §6): bootstrap stops needing the admin's password at all.
# --------------------------------------------------------------------------------------------

class TestTheCredentialLadder:
    """Three ways in, tried in the order that makes a password unnecessary.

    1. the API key a previous run stored in /shared/runtime.json;
    2. the optional configured password (the .env override);
    3. only on a genuinely fresh install, a GENERATED password that is printed once and written
       nowhere.

    Every test here is about a WAY OUT of needing the password, because that is what makes "no
    password in .env" safe rather than reckless.
    """

    @pytest.fixture(autouse=True)
    def _no_module_state_leak(self, monkeypatch):
        monkeypatch.setattr(provision, "GENERATED_ADMIN_PASSWORD", "")

    def _stored(self, tmp_path, monkeypatch, key: str):
        path = tmp_path / "runtime.json"
        path.write_text(json.dumps({"JELLYFIN_API_KEY": key}), encoding="utf-8")
        monkeypatch.setattr(provision, "RUNTIME_PATH", str(path))

    # ---------------------------------------------------------------- 1. the stored API key

    def test_a_stored_working_key_needs_no_password_at_all(self, tmp_path, monkeypatch, no_sleep,
                                                          capsys):
        self._stored(tmp_path, monkeypatch, "stored-key")
        monkeypatch.setattr(provision, "key_works", lambda key: key == "stored-key")
        monkeypatch.setattr(provision, "enabled_admin", lambda credential: "Rajeev")

        def never(*_a, **_k):
            raise AssertionError("authenticate must not run when a stored key already works")

        monkeypatch.setattr(provision, "authenticate", never)
        assert provision.ensure_admin(retries=3, delay=0) == "stored-key"
        out = capsys.readouterr().out
        assert "no admin password needed" in out
        assert "Rajeev" in out, "the administrator is named BY POLICY, not by the literal 'admin'"

    def test_a_dead_stored_key_falls_through_to_the_password(self, tmp_path, monkeypatch, no_sleep):
        """The user deleted the key in Jellyfin's dashboard — that must not stop a bootstrap."""
        self._stored(tmp_path, monkeypatch, "deleted-in-jellyfin")
        monkeypatch.setattr(provision, "key_works", lambda key: False)
        monkeypatch.setattr(provision, "ADMIN_PASSWORD", "the-override")
        monkeypatch.setattr(provision, "authenticate",
                            lambda password=None, quiet=False: "tok" if password is None else None)
        assert provision.ensure_admin(retries=3, delay=0) == "tok"

    def test_no_runtime_file_corrupt_or_absent_is_simply_no_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr(provision, "RUNTIME_PATH", str(tmp_path / "nope.json"))
        assert provision.stored_api_key() == ""
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(provision, "RUNTIME_PATH", str(bad))
        assert provision.stored_api_key() == ""

    def test_the_key_probe_is_an_ELEVATED_read(self, monkeypatch):
        """`/Library/VirtualFolders` is the probe because a member's token 403s on it."""
        seen = {}

        def fake_request(method, path, **kw):
            seen["path"], seen["token"], seen["method"] = path, kw.get("token"), method
            return 200, []

        monkeypatch.setattr(provision, "_request", fake_request)
        assert provision.key_works("stored-key") is True
        assert seen["path"] == "/Library/VirtualFolders"
        assert seen["method"] == "GET", "a probe must not mutate anything"
        assert seen["token"] == "stored-key"

    # ------------------------------------------------------------- 3. the fresh-install password

    def test_a_fresh_install_generates_prints_and_set_a_password(self, monkeypatch, no_sleep,
                                                                capsys):
        monkeypatch.setattr(provision, "ADMIN_PASSWORD", "")
        monkeypatch.setattr(provision, "stored_api_key", lambda: "")
        monkeypatch.setattr(provision, "wizard_pending", lambda: True)
        created = {}

        def fake_startup(password=None):
            created["password"] = password
            return True

        def fake_auth(password=None, quiet=False):
            # Jellyfin accepts ONLY the account's real password, so this also pins that the value
            # PRINTED is the value that was SET.
            return "tok" if password and password == created.get("password") else None

        monkeypatch.setattr(provision, "run_startup", fake_startup)
        monkeypatch.setattr(provision, "authenticate", fake_auth)
        assert provision.ensure_admin(retries=3, delay=0) == "tok"
        assert len(created["password"]) >= 20, f"too weak: {created['password']!r}"
        assert provision.GENERATED_ADMIN_PASSWORD == created["password"]
        out = capsys.readouterr().out
        assert "SHOWN ONCE" in out
        assert created["password"] in out, "the user must be able to record what was set"
        assert ".env" not in out, "and must not be sent to .env for it"

    def test_a_configured_password_is_used_and_nothing_is_generated_or_printed(
            self, monkeypatch, no_sleep, capsys):
        monkeypatch.setattr(provision, "ADMIN_PASSWORD", "the-override")
        monkeypatch.setattr(provision, "stored_api_key", lambda: "")
        monkeypatch.setattr(provision, "wizard_pending", lambda: True)
        seen = {}

        def fake_startup(password=None):
            seen["password"] = password
            return True

        monkeypatch.setattr(provision, "run_startup", fake_startup)
        monkeypatch.setattr(provision, "authenticate",
                            lambda password=None, quiet=False:
                                "tok" if password == "the-override" else None)
        assert provision.ensure_admin(retries=3, delay=0) == "tok"
        assert seen["password"] == "the-override", "the override IS the first-run password"
        assert provision.GENERATED_ADMIN_PASSWORD == ""
        assert "SHOWN ONCE" not in capsys.readouterr().out

    def test_a_password_is_never_announced_unless_it_authenticates(self, monkeypatch, no_sleep,
                                                                  capsys):
        """The wizard claimed success but the account did not sign in — print NOTHING.

        Announcing a password that does not work is worse than announcing none: the user records a
        value, believes it, and is then locked out with no explanation.
        """
        monkeypatch.setattr(provision, "ADMIN_PASSWORD", "")
        monkeypatch.setattr(provision, "stored_api_key", lambda: "")
        monkeypatch.setattr(provision, "wizard_pending", lambda: True)
        monkeypatch.setattr(provision, "run_startup", lambda password=None: True)
        monkeypatch.setattr(provision, "authenticate", lambda password=None, quiet=False: None)
        assert provision.ensure_admin(retries=1, delay=0) is None
        assert "SHOWN ONCE" not in capsys.readouterr().out
        assert provision.GENERATED_ADMIN_PASSWORD == ""

    # -------------------------------------------------------------- the authenticate() contract

    def test_authenticate_uses_the_configured_password_when_none_is_given(self, monkeypatch):
        monkeypatch.setattr(provision, "ADMIN_PASSWORD", "the-override")
        seen = {}

        def fake_request(method, path, **kw):
            seen["body"] = kw.get("body")
            return 200, {"AccessToken": "tok"}

        monkeypatch.setattr(provision, "_request", fake_request)
        assert provision.authenticate() == "tok"
        assert seen["body"] == {"Username": provision.ADMIN_USER, "Pw": "the-override"}

    def test_authenticate_lets_an_explicit_password_win(self, monkeypatch):
        """This is what lets a GENERATED password be used before anything stores it."""
        monkeypatch.setattr(provision, "ADMIN_PASSWORD", "stale-in-env")
        seen = {}
        monkeypatch.setattr(provision, "_request",
                            lambda method, path, **kw: (seen.update(body=kw.get("body")), (200, {"AccessToken": "tok"}))[1])
        assert provision.authenticate(password="generated") == "tok"
        assert seen["body"] == {"Username": provision.ADMIN_USER, "Pw": "generated"}


class TestTheAdministratorIsFoundByPolicyNotByName:
    """Renaming the account must not break provisioning (ADMIN_CREDENTIALS_PLAN.md §5)."""

    def test_a_renamed_administrator_is_found(self, monkeypatch):
        users = [{"Name": "Geetanjali", "Policy": {"IsAdministrator": False}},
                 {"Name": "Rajeev", "Policy": {"IsAdministrator": True, "IsDisabled": False}}]
        monkeypatch.setattr(provision, "_request", lambda *a, **k: (200, users))
        assert provision.enabled_admin("k") == "Rajeev"

    def test_a_disabled_administrator_is_not_offered(self, monkeypatch):
        users = [{"Name": "Rajeev", "Policy": {"IsAdministrator": True, "IsDisabled": True}},
                 {"Name": "Geetanjali",
                  "Policy": {"IsAdministrator": True, "IsDisabled": False}}]
        monkeypatch.setattr(provision, "_request", lambda *a, **k: (200, users))
        assert provision.enabled_admin("k") == "Geetanjali"

    def test_an_unanswerable_server_is_an_empty_string_not_an_error(self, monkeypatch):
        """This is a log line, never a gate: a refusal must not stop the run."""
        monkeypatch.setattr(provision, "_request", lambda *a, **k: (403, {"error": "no"}))
        assert provision.enabled_admin("k") == ""
