"""`tools/check_deployed.py` — "is the api I am running the code in this folder?"

The question this tool exists for kept arriving in a new outfit every session: *"is Phase E actually
deployed?"*, *"did my change take effect?"*, *"why does the app still behave like the old one?"*. The
answer comes from comparing the running api's own `/openapi.json` with this folder's snapshot.

What must hold, and is pinned here:
  * serving THIS folder's snapshot ⇒ MATCH, even though the snapshot decorates `info.description`
    with the ADR-0001 note that the running api does not send (that decoration is the ONE difference
    allowed between the two, so it must be ignored on both sides);
  * a missing path, a missing method and a missing schema FIELD are each reported by name — the
    last one is the real case: `LoginRequest.device_id` exists only in the merged code;
  * an api that does not answer is exit 2 (could not ask), never a false "different".
"""
from __future__ import annotations

import copy
import json
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for extra in (REPO / "tools", REPO):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import check_deployed as cd  # noqa: E402

SNAPSHOT = REPO / "docs" / "api" / "openapi.v1.json"

#: What the web container's SPA fallback answers for a path it does not proxy - i.e. index.html.
SPA_FALLBACK = "<!doctype html><html><head><title>RKM Cinema</title></head><body></body></html>"


class StubSpecServer:
    """Serves one /openapi.json, exactly as FastAPI does.

    Three modes: a spec (200 + JSON, what the api sends), `body` + `ctype` (200 + whatever SOMETHING
    ELSE sends - `StubSpecServer(None, body=SPA_FALLBACK)` is the web container's SPA fallback), and
    None (404).
    """

    def __init__(self, spec: dict | None, body: str | None = None, ctype: str = "text/html"):
        import http.server

        self._spec = spec
        self._body = body
        self._ctype = ctype
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_GET(self):                                   # noqa: N802
                if self.path != "/openapi.json":
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if outer._body is not None:
                    body = outer._body.encode()
                    ctype = outer._ctype
                elif outer._spec is not None:
                    body = json.dumps(outer._spec).encode()
                    ctype = "application/json"
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def close(self):
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture(scope="module")
def snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def run(server: StubSpecServer, capsys) -> tuple[int, str]:
    code = cd.main(["--app", server.base, "--snapshot", str(SNAPSHOT)])
    return code, capsys.readouterr().out


class TestTheVerdict:
    def test_the_snapshot_itself_is_a_MATCH_despite_the_decorated_info(self, snapshot, capsys):
        """The one allowed difference: the snapshot's `info.description` carries the ADR-0001 note
        that the running api never sends. Ignoring `info` on both sides is what makes this testable -
        without it every run would report a difference that means nothing."""
        server = StubSpecServer(snapshot)
        try:
            code, out = run(server, capsys)
            assert code == 0, out
            assert "MATCH" in out
            assert "IS this folder's code" in out
        finally:
            server.close()

    def test_a_running_api_MISSING_the_new_field_is_reported_by_name(self, snapshot, capsys):
        """THE real case: the merged code added `LoginRequest.device_id`. An api built before that
        change answers a contract without it, and the difference must be named, not counted."""
        older = copy.deepcopy(snapshot)
        older["components"]["schemas"]["LoginRequest"]["properties"].pop("device_id")
        server = StubSpecServer(older)
        try:
            code, out = run(server, capsys)
            assert code == 1, out
            assert "DIFFERENT" in out
            assert "LoginRequest" in out and "device_id" in out
            assert "rkm-cinema.ps1 apply" in out, "the reader must be told the one command that fixes it"
        finally:
            server.close()

    def test_a_running_api_missing_a_WHOLE_ENDPOINT_is_reported(self, snapshot, capsys):
        older = copy.deepcopy(snapshot)
        older["paths"].pop("/api/library/scan")
        server = StubSpecServer(older)
        try:
            code, out = run(server, capsys)
            assert code == 1
            assert "/api/library/scan" in out and "MISSING" in out
        finally:
            server.close()

    def test_a_running_api_missing_a_METHOD_is_reported(self, snapshot, capsys):
        older = copy.deepcopy(snapshot)
        older["paths"]["/api/reconcile"].pop("post")
        server = StubSpecServer(older)
        try:
            code, out = run(server, capsys)
            assert code == 1
            assert "/api/reconcile" in out and "POST" in out
        finally:
            server.close()

    def test_an_api_that_does_not_answer_is_COULD_NOT_ASK_not_different(self, capsys):
        """⚠ The distinction the whole repo keeps having to make: "I could not ask" is not "no"."""
        server = StubSpecServer(None)          # every request 404s
        try:
            code, out = run(server, capsys)
            assert code == 2, out
            assert "DIFFERENT" not in out
        finally:
            server.close()

    def test_nothing_listening_at_all_is_also_could_not_ask(self, capsys):
        """Port :1 — nothing can be listening there. Still "could not ask", and the message must name
        the address it tried and the command that fixes it: a bare `urlopen error` names neither."""
        code = cd.main(["--app", "http://127.0.0.1:1", "--snapshot", str(SNAPSHOT)])
        assert code == 2
        err = capsys.readouterr().err
        assert "COULD NOT ASK" in err
        assert "http://127.0.0.1:1/openapi.json" in err
        assert "DIFFERENT" not in err

    def test_a_missing_snapshot_file_is_reported(self, tmp_path, capsys):
        code = cd.main(["--app", "http://127.0.0.1:1", "--snapshot", str(tmp_path / "nope.json")])
        assert code == 2
        assert "could not read" in capsys.readouterr().err


class TestTheDiffItself:
    def test_info_is_ignored_only_at_the_top_level(self):
        spec = {"info": {"x": 1}, "paths": {"/a": {"get": {}}}, "components": {}}
        assert cd._without_info(spec) == {"paths": {"/a": {"get": {}}}, "components": {}}

    def test_a_changed_description_on_a_route_is_a_difference(self, snapshot):
        """Docstrings become route descriptions, so a docstring-only change in the deployed code IS
        visible here - which is the point: it means the api predates that change."""
        live = copy.deepcopy(snapshot)
        live["paths"]["/api/reconcile"]["post"]["description"] = "an older wording"
        assert any("/api/reconcile" in line for line in cd.differences(snapshot, live))

    def test_the_diff_list_is_CAPPED(self, snapshot):
        live = copy.deepcopy(snapshot)
        live["paths"] = {}
        diffs = cd.differences(snapshot, live, limit=5)
        assert len(diffs) == 5, "an unbounded list would flood the console"


class TestWhenSomethingElseAnswersForOpenapiJson:
    """⚠ MEASURED LIVE 2026-09-13, on the real stack.

    `nginx/default.conf` proxied only `/api/`, so `/openapi.json` fell through to the SPA fallback and
    came back as `index.html`. The tool then reported `did not answer: Expecting value: line 1 column 1
    (char 0)` — a message that blames the API for the PROXY's answer and tells the reader nothing. The
    nginx rule now forwards the path, but a stack that predates it (which is exactly when this check is
    most wanted) must still be diagnosed honestly.
    """

    def test_a_contract_is_never_claimed_from_a_non_json_answer(self, capsys):
        """The dangerous shape: a web page turned into a VERDICT. Nothing was compared, so the exit is
        2 — never MATCH (which would read as "your change is deployed") and never DIFFERENT (which
        would send the reader off to deploy against a difference that was never measured)."""
        server = StubSpecServer(None, body=SPA_FALLBACK)
        try:
            code, out = run(server, capsys)
        finally:
            server.close()
        assert code == 2, "could not ask is not the same answer as different"
        assert "MATCH" not in out and "DIFFERENT" not in out

    def test_the_message_names_html_the_proxy_and_the_one_command(self, capsys):
        server = StubSpecServer(None, body=SPA_FALLBACK)
        try:
            cd.main(["--app", server.base, "--snapshot", str(SNAPSHOT)])
            err = capsys.readouterr().err
        finally:
            server.close()
        assert "COULD NOT ASK" in err
        assert "HTML" in err
        assert "SPA fallback" in err and "nginx" in err
        assert "rkm-cinema.ps1 apply" in err
        assert "Expecting value" not in err, (
            "the raw json error must never be what the user reads - it blames the api for the "
            "proxy's answer")

    def test_a_plain_text_answer_is_not_blamed_on_the_web_container(self, capsys):
        """The other branch of the same failure: a proxy error page or an api that is not FastAPI. That
        is NOT the SPA fallback, and naming it would send the reader to the wrong container."""
        server = StubSpecServer(None, body="upstream timed out", ctype="text/plain")
        try:
            cd.main(["--app", server.base, "--snapshot", str(SNAPSHOT)])
            err = capsys.readouterr().err
        finally:
            server.close()
        assert "COULD NOT ASK" in err
        assert "not JSON" in err
        assert "SPA fallback" not in err and "nginx" not in err
        assert "rkm-cinema.ps1 apply" in err


class TestTheNginxRuleThisCheckDependsOn:
    """The check can only see a contract if nginx FORWARDS `/openapi.json` to the api.

    ⚠ Measured live 2026-09-13: nginx proxied only `/api/`, so the SPA fallback answered index.html and
    the tool compared a web page with a contract. This rule is what stands between the check and that
    silence. It is deliberately `location = ...` — an EXACT match, which nginx prefers over `location /`
    no matter where it sits — so this pins PRESENCE, not position; an ordering assertion here would
    claim a mechanism nginx does not have.
    """

    RULE = "location = /openapi.json"      # the canonical form, named in the failures below

    def _block(self) -> list[str]:
        """The lines of the LIVE rule that owns `/openapi.json`, as stripped lines.

        ⚠ A commented-out rule is not a rule, and a plain `in` test cannot tell the difference —
        FALSIFIED 2026-09-13: the first version of this check passed with the line commented out, which
        is exactly how someone would disable it. So the form is not pinned (an exact match is what is
        used, but any LIVE location owning the path is accepted — this is a behaviour check), while
        "commented out" and "gone" both fail with the message below.
        """
        lines = (REPO / "nginx" / "default.conf").read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            head = line.strip()
            if head.startswith("#") or "location" not in head or "/openapi.json" not in head:
                continue
            block = [head]
            for follow in lines[i + 1:]:
                block.append(follow.strip())
                if follow.strip() == "}":
                    break
            return block
        raise AssertionError(
            "no LIVE nginx rule serves /openapi.json: the SPA fallback answers it with index.html, so "
            "tools/check_deployed.py cannot see the running api's contract and `status` reports "
            "COULD NOT ASK for a perfectly healthy stack")

    def test_it_proxies_to_the_api(self):
        assert any("proxy_pass http://api:8000" in line for line in self._block())

    def test_the_contract_is_not_cacheable(self):
        assert any("no-store" in line for line in self._block()), (
            "a cached contract would make this check answer about a PREVIOUS api - the exact "
            "'did my change take effect?' question it exists to answer")
