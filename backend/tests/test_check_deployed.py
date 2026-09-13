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


class StubSpecServer:
    """Serves one /openapi.json, exactly as FastAPI does (plus a 404 mode)."""

    def __init__(self, spec: dict | None):
        import http.server

        self._spec = spec
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_GET(self):                                   # noqa: N802
                if outer._spec is None or self.path != "/openapi.json":
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = json.dumps(outer._spec).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
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
        code = cd.main(["--app", "http://127.0.0.1:1", "--snapshot", str(SNAPSHOT)])
        assert code == 2
        assert "did not answer" in capsys.readouterr().err

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
