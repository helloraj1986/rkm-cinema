"""tools/rkm_common.py — the shared plumbing every operation tool depends on.

The URL resolution is the part worth pinning down: the same `.\rkm-cinema.ps1 status`
must work inside the sandbox (where the stack is at host.docker.internal) and on
the Windows host (where it is at localhost). Getting that wrong made the tools
sandbox-only, which is what these tests prevent regressing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

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


# ------------------------------------------------------- the tool's own SESSION (2026-09-13)

class StubAppServer:
    """A real HTTP server standing in for the app's api, with the two behaviours that matter.

    Mirrors what the shipped routes do rather than what would be convenient: ``/api/auth/login``
    answers 200 **with a Set-Cookie** only for the right credentials (401 wrong, 403 not an
    administrator, 503 media server unreachable), and a session route answers **401 without the
    cookie, 200 with it**. That last pair is the whole point — a client that does not carry the
    cookie cannot accidentally look like a client that does.
    """

    COOKIE = "rkm_session"

    def __init__(self, *, username="rkm", password="pw", admin=True, media=None):
        import http.server
        import threading

        self.requests: list[dict] = []
        self._username, self._password, self._admin, self._media = username, password, admin, media
        self._sessions: set[str] = set()
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_a):    # keep pytest's output readable
                pass

            def _cookies(self) -> dict:
                raw = self.headers.get("Cookie") or ""
                return dict(part.strip().split("=", 1) for part in raw.split(";") if "=" in part)

            def _send(self, status, payload, cookie: str | None = None):
                data = json.dumps(payload).encode() if payload is not None else b""
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                if cookie:
                    self.send_header("Set-Cookie", f"{outer.COOKIE}={cookie}; Path=/; HttpOnly")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if data:
                    self.wfile.write(data)

            def do_POST(self):                                   # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode("utf-8") if length else ""
                try:
                    body = json.loads(raw) if raw else {}
                except Exception:
                    body = {"__raw__": raw}
                outer.requests.append({"method": "POST", "path": self.path,
                                       "body": body, "cookie": self._cookies()})
                if self.path == "/api/auth/logout":
                    self._cookies() and outer._sessions.discard(
                        self._cookies().get(outer.COOKIE, ""))
                    return self._send(200, {"ok": True, "revoked": True})
                if self.path == "/api/auth/login":
                    if outer._media is not None:
                        return self._send(outer._media, {"detail": "server"})
                    if (body.get("username") != outer._username
                            or body.get("password") != outer._password):
                        return self._send(401, {"detail": "Incorrect username or password."})
                    if not outer._admin:
                        return self._send(403, {"detail": "Only the administrator can sign in"})
                    sid = f"sid-{len(outer._sessions) + 1}"
                    outer._sessions.add(sid)
                    # A body WITHOUT the cookie is not a session — the trap this stub can also
                    # reproduce (see the no-cookie test).
                    return self._send(200, {"ok": True, "user": {"id": "u1", "name": "rkm"}},
                                      cookie=None if outer.__dict__.get("_omit_cookie") else sid)
                return self._send(404, {"detail": "no"})

            def do_GET(self):                                   # noqa: N802
                outer.requests.append({"method": "GET", "path": self.path,
                                       "body": None, "cookie": self._cookies()})
                if self.path == "/api/health":
                    # PUBLIC by design — the Docker HEALTHCHECK. A tool must be able to read this
                    # signed out, which is why `rkm_status` still calls it directly.
                    return self._send(200, {"ok": True, "degraded": False,
                                            "services": {"jellyfin": True}})
                sid = self._cookies().get(outer.COOKIE, "")
                if sid not in outer._sessions:
                    return self._send(401, {"detail": "Sign in to use this app"})
                return self._send(200, {"provider": "jellyfin",
                                        "libraries": [{"name": "Movies", "path": "/data/Movies",
                                                       "ok": True, "warning": ""}],
                                        "folders": [{"id": "f1", "name": "Movies"}]})

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def close(self):
        self._httpd.shutdown()
        self._httpd.server_close()


CREDS = {"RKM_JELLYFIN_ADMIN_USER": "rkm", "RKM_JELLYFIN_ADMIN_PASSWORD": "pw"}


@pytest.fixture()
def app_server():
    server = StubAppServer()
    yield server
    server.close()


class TestTheAppClientHoldsASession:
    """`rc.App` — what a tool uses once `RKM_AUTH_REQUIRED` is armed.

    Before the flag existed, a tool could just fetch `/api/library/...`: no cookie meant the request
    was served as the stack's own credential. Armed, that same fetch is a 401 — so the client has to
    sign in, and these tests are about the two ways that goes wrong: not carrying the cookie, and
    signing in on the device the BROWSER uses.
    """

    def test_it_signs_in_and_then_the_cookie_is_what_gets_the_answer(self, app_server):
        client = rc.App(base=app_server.base, env=dict(CREDS))
        assert client.signed_in, client.error
        folders = client.get("/api/library/folders")
        assert not isinstance(folders, dict) or "__http_error__" not in folders, (
            "the session call was refused — the client did not carry the cookie it was just given")
        assert folders["folders"][0]["id"] == "f1"
        # …and the cookie really was on the wire, not merely in the jar.
        assert app_server.requests[-1]["cookie"].get(StubAppServer.COOKIE)

    def test_an_UNSIGNED_client_really_is_refused(self, app_server):
        """The falsifier for the line above: without the cookie the route answers 401.

        If this ever answered 200 the previous test would prove nothing at all.
        """
        client = rc.App(base=app_server.base, env=dict(CREDS), sign_in=False)
        refused = client.get("/api/library/folders")
        assert refused["__http_error__"] == 401
        # The BODY is asserted loosely on purpose: JSON whitespace is the serialiser's business,
        # and pinning it here would fail on a difference that means nothing.
        assert "Sign in" in refused["body"]

    def test_it_signs_in_on_the_TOOLS_own_device_not_the_apps(self, app_server):
        """⚠ The load-bearing detail: Jellyfin rotates a (device, user) token pair on every login, so
        a tool signing in on the app's device would kill the BROWSER's session (§6h)."""
        rc.App(base=app_server.base, env=dict(CREDS))
        login = next(r for r in app_server.requests if r["path"] == "/api/auth/login")
        assert login["body"]["device_id"] == rc.App.DEVICE_ID == "rkm-tools"
        assert login["body"]["device_id"] != "rkm-cinema-web"

    def test_it_reports_WHY_it_could_not_sign_in(self, app_server):
        """Each refusal is a different sentence — "the api refused this" is not "the library is empty"."""
        wrong = rc.App(base=app_server.base, env={"RKM_JELLYFIN_ADMIN_USER": "rkm",
                                                  "RKM_JELLYFIN_ADMIN_PASSWORD": "nope"})
        assert not wrong.signed_in and "refused those credentials" in wrong.error

    def test_a_member_account_is_told_it_is_not_an_administrator(self):
        server = StubAppServer(admin=False)
        try:
            client = rc.App(base=server.base, env=dict(CREDS))
            assert not client.signed_in and "ADMINISTRATOR" in client.error
        finally:
            server.close()

    def test_an_unreachable_media_server_is_not_a_bad_password(self):
        server = StubAppServer(media=503)
        try:
            client = rc.App(base=server.base, env=dict(CREDS))
            assert not client.signed_in
            assert "could not reach the media server" in client.error
            assert "password" not in client.error
        finally:
            server.close()

    def test_missing_credentials_say_so_instead_of_guessing(self):
        client = rc.App(base="http://127.0.0.1:1", env={})
        assert not client.signed_in
        assert "no administrator credentials" in client.error
        assert "RKM_JELLYFIN_ADMIN_USER" in client.error

    def test_a_200_without_a_cookie_is_not_a_session(self, app_server):
        """The api answers keep-alive 200s to other callers; none of them is a session."""
        app_server._omit_cookie = True
        client = rc.App(base=app_server.base, env=dict(CREDS))
        assert not client.signed_in and "without a session cookie" in client.error

    def test_it_never_echoes_the_username_or_the_password(self, app_server):
        client = rc.App(base=app_server.base,
                        env={"RKM_JELLYFIN_ADMIN_USER": "rajeev", "RKM_JELLYFIN_ADMIN_PASSWORD": "s3cret"})
        assert not client.signed_in
        assert "s3cret" not in client.error and "rajeev" not in client.error

    def test_signing_out_revokes_the_session_it_made(self, app_server):
        client = rc.App(base=app_server.base, env=dict(CREDS))
        assert client.signed_in and client.sign_out() is True
        assert client.signed_in is False and client.cookie is None
        assert client.get("/api/library/folders")["__http_error__"] == 401, (
            "after signing out, the tool must be as refused as any other stranger")


class TestAToolActuallySignsIn:
    """`tools/rkm_status.py` driven for real against a stub api — the wiring, not just the client.

    The unit tests above prove `App` carries a cookie. This proves the TOOL uses it: without it the
    tool still ran and still printed something, which is exactly how a broken tool looks healthy.
    """

    def _run(self, monkeypatch, capsys, server, env):
        import rkm_status

        monkeypatch.setattr(sys, "argv", ["rkm_status.py",
                                          "--app-url", server.base,
                                          # a dead Jellyfin on purpose: this test is about the APP
                                          "--jellyfin-url", "http://127.0.0.1:1"])
        monkeypatch.setattr(rc, "load_env", lambda root=None: dict(env))
        code = rkm_status.main()
        return code, capsys.readouterr().out

    def test_it_reports_the_libraries_it_had_to_sign_in_to_read(self, app_server, monkeypatch,
                                                                capsys):
        code, out = self._run(monkeypatch, capsys, app_server, CREDS)
        assert "Movies" in out, f"the library row never printed:\n{out}"
        assert "REFUSED" not in out
        assert "UNREADABLE" not in out
        # …and it really signed in: the folders call carried a cookie the stub had issued.
        folders = [r for r in app_server.requests if r["path"] == "/api/library/folders"]
        assert folders and folders[-1]["cookie"].get(StubAppServer.COOKIE)

    def test_with_the_WRONG_password_it_says_the_api_refused_it(self, app_server, monkeypatch,
                                                                capsys):
        """⚠ The distinction the tools exist to keep: "the api refused me" is not "unreadable".

        Before this, an armed app would have answered 401 and the tool would have printed
        UNREADABLE — sending the reader to look at Jellyfin for a problem that was a session.
        """
        bad = {"RKM_JELLYFIN_ADMIN_USER": "rkm", "RKM_JELLYFIN_ADMIN_PASSWORD": "wrong"}
        code, out = self._run(monkeypatch, capsys, app_server, bad)
        assert code == 1
        assert "REFUSED" in out, out
        assert "refused those credentials" in out
        assert "UNREADABLE" not in out
        # …and it really TRIED: without this, a tool that never attempted a sign-in at all would
        # produce the same message and pass (which it did, under falsification).
        assert any(r["path"] == "/api/auth/login" for r in app_server.requests)

    def test_with_NO_credentials_it_says_so_instead_of_failing_obscurely(self, app_server,
                                                                        monkeypatch, capsys):
        code, out = self._run(monkeypatch, capsys, app_server, {})
        assert code == 1
        assert "no administrator credentials" in out, out
