#!/usr/bin/env python3
"""Serve the PRODUCTION build from `dist/`, with `/api` proxied to the live stack.

    cd frontend && npm run build
    python3 tools/serve_prod_build.py 5201
    python3 tools/measure_library_latency.py --base http://localhost:5201

**Why this exists.** The dev server renders in development mode, which is a different ballgame from
the bundle he actually deploys — measured on the same folder, the dev build took **15.5 s** to mount
714 rows where the production build took **1.7–2.3 s**. So a change to list performance cannot be
judged on `vite` alone, and it cannot be judged on his deployed app either (that is the OLD code).

This serves `dist/` — the same artefact the web image gets — and proxies `/api` (cookies included) to
the live app, so `measure_library_latency.py` can take before/after numbers on a production bundle
WITHOUT deploying: build the tree, measure, `git stash` the change, build again, measure.

⚠ Measurement aid only — it is never part of the app or the web image, and it holds no credentials.
It signs nothing in: you sign in through it, exactly as through the real app.
"""

import http.server
import socketserver
import sys
import urllib.error
import urllib.request
from pathlib import Path

DIST = Path("/workspace/projects/rkm-cinema/frontend/dist")
UPSTREAM = "http://host.docker.internal:8124"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(DIST), **kw)

    def log_message(self, *a):  # quiet
        pass

    def _proxy(self):
        body = None
        length = int(self.headers.get("content-length") or 0)
        if length:
            body = self.rfile.read(length)
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length", "accept-encoding")}
        req = urllib.request.Request(UPSTREAM + self.path, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    if key.lower() in ("transfer-encoding", "content-length", "content-encoding"):
                        continue
                    self.send_header(key, value)
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as exc:  # a 401 or 404 is an answer, not a failure
            payload = exc.read()
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() in ("transfer-encoding", "content-length", "content-encoding"):
                    continue
                self.send_header(key, value)
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        target = DIST / self.path.lstrip("/").split("?")[0]
        if not target.exists() or target.is_dir():
            self.path = "/index.html"          # SPA fallback
        return super().do_GET()

    def do_POST(self):
        return self._proxy()

    def do_PUT(self):
        return self._proxy()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5201
    if not DIST.exists():
        raise SystemExit(f"{DIST} does not exist — run `npm run build` first")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", port), Handler) as httpd:
        print(f"serving {DIST} on :{port} with /api -> {UPSTREAM}", flush=True)
        httpd.serve_forever()
