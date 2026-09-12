"""tools/reset_admin_password.py — the break-glass, and the rules that keep it safe.

The tool itself runs on the Windows host against the live server (no Docker in the sandbox), so what
is pinned here are the DECISIONS: the body it sends, which account it picks, and how it reports what
it observed. Those are exactly the places this workstream has already been burned:

* ``ResetPassword: true`` is a silent no-op that CLEARS a password (plan §6c) -- the plan's own
  Phase 4 row said ``true`` before it was measured, so the rule is asserted rather than trusted;
* the administrator must be found BY POLICY, never by the name ``admin`` (plan §5: the account was
  renamed, and a member can be called anything);
* a 2xx is not evidence (plan §6d) -- the verdict comes from signing in with the new password.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import reset_admin_password as rec  # noqa: E402

ADMIN = {"Id": "uid-admin", "Name": "rkm",
         "Policy": {"IsAdministrator": True, "IsDisabled": False}}
MEMBER = {"Id": "uid-kid", "Name": "Geetanjali",
          "Policy": {"IsAdministrator": False, "IsDisabled": False}}
#: The §5 trap: a MEMBER whose account happens to be called "admin". Picking by name would reset
#: this one and leave nobody able to administer the server.
MEMBER_NAMED_ADMIN = {"Id": "uid-fake", "Name": "admin",
                      "Policy": {"IsAdministrator": False, "IsDisabled": False}}
#: A renamed administrator: policy is the only thing that still says "this is the admin".
RENAMED_ADMIN = {"Id": "uid-renamed", "Name": "Rajeev",
                 "Policy": {"IsAdministrator": True, "IsDisabled": False}}
DISABLED_ADMIN = {"Id": "uid-off", "Name": "OldAdmin",
                  "Policy": {"IsAdministrator": True, "IsDisabled": True}}
USERS = [MEMBER, ADMIN, MEMBER_NAMED_ADMIN, RENAMED_ADMIN, DISABLED_ADMIN]


class TestTheBodyItSends:
    def test_reset_password_is_FALSE_because_true_clears_the_password(self):
        """Measured on Jellyfin 10.11.11 (plan §6c): ``true`` answers 204, sets NOTHING, and wipes a
        password that existed. The privilege authorises the reset, not the flag."""
        body = rec.password_reset_body("Fresh-Pass-1")
        assert body["ResetPassword"] is False
        assert body["NewPw"] == "Fresh-Pass-1"
        assert body["CurrentPw"] == "", "the break-glass does not know the old password, by design"

    def test_the_body_can_never_carry_the_destructive_flag(self):
        for value in ("", " ", "x" * 200):
            assert rec.password_reset_body(value)["ResetPassword"] is False


class TestWhichAccountItPicks:
    def test_a_single_administrator_is_chosen_by_policy(self):
        target, reason = rec.pick_administrator([MEMBER, ADMIN])
        assert target is ADMIN and reason == ""

    def test_a_RENAMED_administrator_is_still_found(self):
        """Plan §5: nothing may depend on the literal name 'admin'."""
        target, reason = rec.pick_administrator([MEMBER, RENAMED_ADMIN])
        assert target is RENAMED_ADMIN and reason == ""

    def test_a_member_Named_admin_is_never_chosen(self):
        target, reason = rec.pick_administrator([MEMBER, MEMBER_NAMED_ADMIN, RENAMED_ADMIN])
        assert target is RENAMED_ADMIN, "policy decides, not the name"

    def test_a_disabled_administrator_is_not_a_target(self):
        assert rec.administrators([DISABLED_ADMIN]) == []

    def test_two_administrators_ask_which_one(self):
        target, reason = rec.pick_administrator([ADMIN, RENAMED_ADMIN])
        assert target is None
        assert "2 enabled administrators" in reason and "-Name" in reason

    def test_a_name_picks_between_them(self):
        target, reason = rec.pick_administrator([ADMIN, RENAMED_ADMIN], "Rajeev")
        assert target is RENAMED_ADMIN and reason == ""
        target, reason = rec.pick_administrator([ADMIN, RENAMED_ADMIN], "rkm")
        assert target is ADMIN, "names match case-insensitively"

    def test_a_MEMBER_is_refused_by_name_with_the_right_advice(self):
        """The break-glass is the lockout recovery, not a way to set somebody else's password."""
        target, reason = rec.pick_administrator(USERS, "Geetanjali")
        assert target is None
        assert "not an enabled administrator" in reason and "Household" in reason

    def test_an_unknown_name_says_so(self):
        target, reason = rec.pick_administrator(USERS, "Nobody")
        assert target is None and "no account named 'Nobody'" in reason

    def test_no_administrator_at_all_is_an_honest_dead_end(self):
        target, reason = rec.pick_administrator([MEMBER])
        assert target is None
        assert "NO enabled administrator" in reason and "status" in reason

    def test_junk_rows_do_not_crash_the_choice(self):
        assert rec.administrators([None, "x", {}, {"Policy": None}]) == []
        target, _ = rec.pick_administrator([None, "x", ADMIN])
        assert target is ADMIN


class TestTheVerdictItReports:
    def test_a_token_is_proof(self):
        assert rec.verify_verdict({"AccessToken": "abc"}) == "verified"

    def test_a_refusal_is_a_refusal_even_though_the_server_answered(self):
        assert rec.verify_verdict({"__http_error__": 401, "body": "no"}) == "refused"
        assert rec.verify_verdict({"AccessToken": ""}) == "refused"

    def test_could_not_ask_is_never_reported_as_a_failure_of_the_change(self):
        """Plan §6d: "unavailable" must not be dressed up as "it did not work" — the live symptom of
        getting that wrong was a user told their change had not landed when it had."""
        assert rec.verify_verdict({"__error__": "timed out"}) == "unavailable"
        assert rec.verify_verdict({"__http_error__": 500}) == "unavailable"
        assert rec.verify_verdict("not a dict") == "unavailable"
        assert rec.verify_verdict(None) == "unavailable"


class TestReadingTheStoredKey:
    def test_the_volume_is_project_prefixed_the_way_compose_names_it(self):
        assert rec.volume_name("rkm-bundled") == "rkm-bundled_rkm_shared"
        assert rec.volume_name("rkm-test") == "rkm-test_rkm_shared"

    def test_the_key_comes_out_of_runtime_json(self):
        assert rec.stored_key(json.dumps({"JELLYFIN_API_KEY": "abc123"})) == "abc123"

    def test_junk_is_a_missing_key_never_an_exception(self):
        for text in ("", "not json", "[]", "null", "{}", json.dumps({"JELLYFIN_API_KEY": None})):
            assert rec.stored_key(text) == ""

    def test_it_prefers_the_running_container_and_falls_back_to_the_volume(self):
        """Both paths, in order — the first makes the normal case instant, the second works with the
        stack stopped (the pattern backup-rkm-state.ps1 uses)."""
        seen: list[list[str]] = []

        def runner(cmd):
            seen.append(cmd)
            if cmd[:2] == ["docker", "compose"]:
                return (1, "", "no such service: api")
            return (0, json.dumps({"JELLYFIN_API_KEY": "from-volume"}), "")

        key, how = rec.read_stored_api_key("rkm-bundled", runner=runner)
        assert key == "from-volume" and how == "the rkm_shared volume"
        assert seen[0][:2] == ["docker", "compose"]
        assert seen[1][:2] == ["docker", "run"]

    def test_the_api_container_is_preferred_when_it_answers(self):
        def runner(cmd):
            assert cmd[:2] == ["docker", "compose"]
            return (0, json.dumps({"JELLYFIN_API_KEY": "from-container"}) + "\n", "")

        key, how = rec.read_stored_api_key("rkm-bundled", runner=runner)
        assert key == "from-container" and how == "the running api container"

    def test_a_stderr_warning_does_not_break_the_read(self):
        """compose writes progress and warnings to stderr; the JSON comes from stdout."""
        def runner(cmd):
            return (0, '{"JELLYFIN_API_KEY": "k"}\n', "WARN[0000] a compose warning\n")

        key, _ = rec.read_stored_api_key("rkm-bundled", runner=runner)
        assert key == "k"

    def test_both_paths_failing_names_what_to_check(self):
        def runner(cmd):
            return (1, "", "docker: no such volume")

        key, why = rec.read_stored_api_key("rkm-bundled", runner=runner)
        assert key == ""
        assert "rkm-bundled_rkm_shared" in why and "docker compose -p rkm-bundled ps" in why


class TestThePasswordIsNeverAnArgument:
    def test_the_tool_takes_no_password_option(self):
        """An argument would sit in PowerShell history and in the process list for anyone to read."""
        import inspect

        source = inspect.getsource(rec.main)
        assert "--password" not in source
        assert "getpass" in inspect.getsource(rec._ask_twice)

    def test_nothing_it_prints_contains_a_password(self, capsys):
        """The prompts echo nothing and the messages carry the account, never the value."""
        assert rec.password_reset_body("Super-Secret-9")["NewPw"] == "Super-Secret-9"
        out = capsys.readouterr().out
        assert "Super-Secret-9" not in out


@pytest.mark.parametrize("name", ["volume_name", "stored_key", "password_reset_body",
                                  "administrators", "pick_administrator", "verify_verdict",
                                  "read_stored_api_key"])
def test_the_decisions_are_importable_without_docker_or_network(name):
    """Every rule above is a pure function: no docker call, no socket, no env — which is what makes
    them testable in the sandbox at all."""
    assert callable(getattr(rec, name))


# ------------------------------------------------------------------ the flow, against a stub

class StubMediaServer:
    """A real HTTP server on localhost: the tool's own flow, with nothing claimed but what ran."""

    def __init__(self, *, users=None, reset_status=204, sign_in_status=200):
        import http.server
        import threading

        self.requests: list[dict] = []
        self._users = users if users is not None else [ADMIN, MEMBER]
        self._reset_status = reset_status
        self._sign_in_status = sign_in_status

        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_a):    # keep pytest's output readable
                pass

            def _record(self, body):
                outer.requests.append({"method": self.command,
                                       "path": self.path.split("?")[0],
                                       "query": self.path.split("?")[1] if "?" in self.path else "",
                                       "body": body})
                return body

            def do_GET(self):                                   # noqa: N802
                self._record(None)
                self._send(200, json.dumps(outer._users))

            def do_POST(self):                                  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode("utf-8") if length else ""
                try:
                    body = json.loads(raw) if raw else {}
                except Exception:
                    body = {"__raw__": raw}
                self._record(body)
                if self.path.startswith("/Users/AuthenticateByName"):
                    if outer._sign_in_status != 200:
                        return self._send(outer._sign_in_status, json.dumps({"detail": "no"}))
                    return self._send(200, json.dumps({"AccessToken": "tok", "User": ADMIN}))
                return self._send(outer._reset_status, "")

            def _send(self, status, payload):
                data = payload.encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if data:
                    self.wfile.write(data)

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def close(self):
        self._httpd.shutdown()
        self._httpd.server_close()

    def paths(self) -> list[str]:
        return [r["path"] for r in self.requests]

    def write_bodies(self) -> list[dict]:
        return [r["body"] for r in self.requests if r["path"] == "/Users/Password"]


@pytest.fixture()
def stub(monkeypatch):
    """The tool wired to a stub server, with the stored key supplied and the prompt scripted."""
    server = StubMediaServer()
    monkeypatch.setattr(rec, "read_stored_api_key", lambda project, **kw: ("stored-key", "a test run"))
    yield server
    server.close()


def _script_prompt(monkeypatch, *values):
    answers = list(values)
    monkeypatch.setattr(rec.getpass, "getpass", lambda _prompt="": answers.pop(0))


class TestTheWholeFlowAgainstAStubServer:
    def test_dry_run_names_the_administrator_and_writes_NOTHING(self, stub, monkeypatch):
        """The safety valve: the wrapper tells you to look before you leap, so looking must be
        genuinely read-only."""
        code = rec.main(["--base", stub.base, "--dry-run"])
        assert code == 0
        assert stub.paths() == ["/Users"], "a dry run touched something other than the account list"
        assert stub.write_bodies() == []

    def test_the_reset_sends_the_measured_body_and_PROVES_it_by_signing_in(self, stub, monkeypatch,
                                                                          capsys):
        _script_prompt(monkeypatch, "Fresh-Pass-1", "Fresh-Pass-1")
        code = rec.main(["--base", stub.base])

        assert code == 0, "a verified reset must exit 0"
        writes = stub.write_bodies()
        assert writes == [{"CurrentPw": "", "NewPw": "Fresh-Pass-1", "ResetPassword": False}], (
            f"the write must be the measured shape, got {writes}")
        sign_in = next(r for r in stub.requests if r["path"] == "/Users/AuthenticateByName")
        assert sign_in["body"]["Pw"] == "Fresh-Pass-1", (
            "the ONLY proof is signing in with the new value (plan §6d)")
        out = capsys.readouterr().out
        assert "Fresh-Pass-1" not in out, "the password must never appear in the output"
        assert "OK: the administrator password was changed" in out

    def test_a_refused_sign_in_is_reported_as_NOT_taken(self, monkeypatch):
        server = StubMediaServer(sign_in_status=401)
        monkeypatch.setattr(rec, "read_stored_api_key", lambda project, **kw: ("k", "test"))
        _script_prompt(monkeypatch, "Fresh-Pass-1", "Fresh-Pass-1")
        try:
            code = rec.main(["--base", server.base])
        finally:
            server.close()
        assert code == 6, "an accepted-but-unprovable change must not exit 0"

    def test_two_different_typed_passwords_change_nothing(self, stub, monkeypatch):
        """The prompt is the confirmation: a mismatch must not reach the server at all."""
        _script_prompt(monkeypatch, "one", "two", "three", "three")
        code = rec.main(["--base", stub.base])
        assert code == 0
        assert stub.write_bodies()[0]["NewPw"] == "three", "it retried and used the matching pair"

    def test_a_member_cannot_be_targeted_by_name(self, stub, monkeypatch, capsys):
        code = rec.main(["--base", stub.base, "--name", "Geetanjali"])
        assert code == 4
        assert stub.write_bodies() == []
        assert "not an enabled administrator" in capsys.readouterr().out

    def test_no_account_list_means_no_write(self, monkeypatch):
        server = StubMediaServer(users=[])
        monkeypatch.setattr(rec, "read_stored_api_key", lambda project, **kw: ("k", "test"))
        try:
            code = rec.main(["--base", server.base])
        finally:
            server.close()
        assert code == 4 and server.write_bodies() == []

    def test_a_refused_api_key_says_how_to_get_a_new_one(self, monkeypatch):
        server = StubMediaServer(users={"__http_error__": 401, "body": "nope"})
        monkeypatch.setattr(rec, "read_stored_api_key", lambda project, **kw: ("stale", "test"))
        try:
            code = rec.main(["--base", server.base])
        finally:
            server.close()
        assert code == 3
