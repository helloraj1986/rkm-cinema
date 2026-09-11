#!/usr/bin/env python3
"""Verify nginx/default.conf really delivers the artwork cache policy.

Runs a stand-in upstream that mimics the FastAPI api — artwork returns its own
`Cache-Control: public, max-age=604800...` (as the api now does), JSON returns
nothing special — then starts nginx with the REAL repo config (only the upstream
address + listen port rewritten) and asserts:

  1. /api/jellyfin/poster  -> 200 with the cacheable policy, NO no-store
  2. /api/jellyfin/person + /backdrop -> same
  3. /api/library          -> still no-store (dynamic state)
  4. exactly ONE Cache-Control header on artwork (proxy_hide_header works)
  5. the nested location inherits proxy_pass (no 404/502)

Usage: python3 tools/verify_nginx_artwork_cache.py
Exits non-zero on any failure.
"""
from __future__ import annotations

import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "nginx" / "default.conf"
UPSTREAM_PORT = 19311
NGINX_PORT = 18899
JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


class FakeApi(BaseHTTPRequestHandler):
    """Mimics the api: cacheable artwork, uncacheable dynamic JSON."""

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        artwork = path in ("/api/jellyfin/poster", "/api/jellyfin/person",
                           "/api/jellyfin/backdrop")
        if artwork:
            body = JPEG
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "public, max-age=604800, "
                                              "stale-while-revalidate=604800")
            self.send_header("Last-Modified", "Thu, 10 Sep 2026 01:39:37 GMT")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # silence
        pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_config(tmp: Path) -> Path:
    text = CONFIG.read_text(encoding="utf-8")
    text = text.replace("proxy_pass http://api:8000;", f"proxy_pass http://127.0.0.1:{UPSTREAM_PORT};")
    text = text.replace("listen 80;", f"listen {NGINX_PORT};")
    text = text.replace("root /usr/share/nginx/html;", f"root {tmp}/html;")
    conf = tmp / "nginx.conf"
    conf.write_text(
        "worker_processes 1;\n"
        f"pid {tmp}/nginx.pid;\n"
        f"error_log {tmp}/error.log warn;\n"
        f"events {{ worker_connections 64; }}\n"
        "http {\n"
        f"  access_log {tmp}/access.log;\n"
        f"  client_body_temp_path {tmp}/body;\n"
        f"  proxy_temp_path {tmp}/proxy;\n"
        f"  fastcgi_temp_path {tmp}/fastcgi;\n"
        f"  uwsgi_temp_path {tmp}/uwsgi;\n"
        f"  scgi_temp_path {tmp}/scgi;\n"
        "  include " + str(conf.with_name("server.conf")) + ";\n"
        "}\n", encoding="utf-8")
    conf.with_name("server.conf").write_text(text, encoding="utf-8")
    return conf


def headers_of(url: str) -> tuple[int, list[str]]:
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers.get_all("Cache-Control") or []
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get_all("Cache-Control") or []


def main() -> int:
    if not CONFIG.exists():
        print(f"FAIL: {CONFIG} missing")
        return 1
    for tool in ("nginx",):
        if not shutil.which(tool):
            print(f"SKIP: {tool} not installed — cannot execute this check")
            return 0

    tmp = Path(tempfile.mkdtemp(prefix="ngx-artwork-"))
    (tmp / "html").mkdir()
    (tmp / "html" / "index.html").write_text("ok")
    for sub in ("body", "proxy", "fastcgi", "uwsgi", "scgi"):
        (tmp / sub).mkdir()

    upstream = ThreadingHTTPServer(("127.0.0.1", UPSTREAM_PORT), FakeApi)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()

    conf = build_config(tmp)
    check = subprocess.run(["nginx", "-t", "-c", str(conf)], capture_output=True, text=True)
    print(f"nginx -t: rc={check.returncode} {check.stderr.strip().splitlines()[-1:]}")
    if check.returncode != 0:
        print(check.stderr)
        return 1

    proc = subprocess.Popen(["nginx", "-c", str(conf), "-g", "daemon off;"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{NGINX_PORT}"
    failures = []
    try:
        for _ in range(40):
            try:
                headers_of(f"{base}/api/health")
                break
            except Exception:
                time.sleep(0.25)

        cacheable = ["/api/jellyfin/poster?id=m1&width=500",
                     "/api/jellyfin/person?id=p1&width=300",
                     "/api/jellyfin/backdrop?id=m1&width=1600"]
        for path in cacheable:
            status, ccs = headers_of(f"{base}{path}")
            joined = " | ".join(ccs)
            ok = status == 200 and len(ccs) == 1 and "no-store" not in joined \
                and "max-age=604800" in joined
            print(f"  {'PASS' if ok else 'FAIL'} {path}\n        status={status} cache-control={ccs}")
            if not ok:
                failures.append(path)

        for path in ("/api/library", "/api/watchlist/entries", "/api/health"):
            status, ccs = headers_of(f"{base}{path}")
            ok = status == 200 and ccs == ["no-store"]
            print(f"  {'PASS' if ok else 'FAIL'} {path}\n        status={status} cache-control={ccs}")
            if not ok:
                failures.append(path)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        upstream.shutdown()

    if failures:
        print(f"\nFAILED: {failures}")
        return 1
    print("\nAll artwork-cache checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
