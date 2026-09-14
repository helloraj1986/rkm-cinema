#!/usr/bin/env python3
"""Verify nginx/default.conf really delivers the SPA-shell cache + compression policy.

Sibling of ``tools/verify_nginx_artwork_cache.py`` (same shape, same reason: a header
policy that lives only in a config file rots the moment someone edits the file).

Runs a stand-in upstream that mimics the FastAPI api, then starts nginx with the REAL
repo config (only the upstream address + listen port + document root rewritten) and
asserts:

  1. /                            -> 200, `no-cache`, and NOT `no-store` (storable, so the
                                     document CAN be kept; revalidated so it is never stale)
  2. a deep-link route            -> same policy (the SPA fallback must not lose the header)
  3. /assets/<hashed>.js|.css     -> exactly one `Cache-Control`, `immutable`, 1 year
  4. /assets/<missing>            -> 404 and NOT index.html (a missing bundle must be loud)
  5. the bundle, Accept-Encoding: gzip -> `Content-Encoding: gzip`, `Vary: Accept-Encoding`,
                                     and genuinely FEWER bytes than the file on disk
  6. media through the proxy      -> NOT gzipped (video/mp4, video/mp2t) — `gzip_types` is a
                                     whitelist and this is the property that depends on it
  7. /api/ JSON                   -> still `no-store`, AND gzipped when it is worth compressing
  8. artwork through the proxy    -> still the 1-week cacheable policy (the sibling tool's
                                     subject, re-checked here because server-level gzip is new
                                     and could have disturbed it)

⚠ WHY 6 AND 7 EXIST: switching `gzip on` at server level changes what happens to EVERY
response, including the proxied ones. Compressing video would cost CPU on both ends and save
nothing, and dropping `no-store` from the api would serve a stale library row.

Usage:
    python3 tools/verify_nginx_shell_cache.py                 # the repo config
    python3 tools/verify_nginx_shell_cache.py --config OLD.conf   # must FAIL — falsify it
Exits non-zero on any failure.
"""
from __future__ import annotations

import gzip
import os
import socket
import shutil
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
DEFAULT_CONFIG = REPO / "nginx" / "default.conf"
UPSTREAM_PORT = 19312
NGINX_PORT = 18898
SHELL_BYTES = 20 * 1024          # the bundle must clear gzip_min_length with room to spare
JSON_BYTES = 3 * 1024            # an api response that IS worth compressing
MEDIA_BYTES = 8 * 1024           # media: large, and must stay uncompressed
POSTER = b"\xff\xd8\xff\xe0fake-jpeg"


class FakeApi(BaseHTTPRequestHandler):
    """Mimics the api: JSON, artwork, and a media stream."""

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path in ("/api/jellyfin/poster", "/api/jellyfin/person", "/api/jellyfin/backdrop"):
            body, ctype, extra = POSTER, "image/jpeg", {"Cache-Control":
                "public, max-age=604800, stale-while-revalidate=604800"}
        elif path in ("/api/jellyfin/stream", "/api/jellyfin/hls/seg.ts"):
            body, ctype, extra = b"~" * MEDIA_BYTES, "video/mp4", {}
        else:
            body, ctype, extra = b'{"rows":[' + b'"x",' * (JSON_BYTES // 4) + b'""]}', \
                "application/json", {}
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        for k, v in extra.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # silence
        pass


def find_mime_types() -> Path | None:
    """The system mime.types the REAL container's nginx.conf includes.

    ⚠⚠ WITHOUT THIS THE HARNESS LIES ABOUT COMPRESSION, and it took a failing run to see it:
    `gzip_types` is matched against the Content-Type nginx ASSIGNED, and for a static file
    that type comes from mime.types. A test config that omits it leaves every static file on
    `default_type` (or none at all), so no `gzip_types` entry can ever match and the check
    reports "your config does not compress the bundle" about a config that does — the
    proxied JSON still compressed, because THAT Content-Type comes from the upstream, which
    is the asymmetry that gave the harness away.
    """
    for candidate in (Path("/etc/nginx/mime.types"), Path("/usr/share/nginx/mime.types"),
                      Path("/usr/local/nginx/conf/mime.types")):
        if candidate.is_file():
            return candidate
    return None


def build_config(tmp: Path, config: Path) -> Path:
    text = config.read_text(encoding="utf-8")
    text = text.replace("proxy_pass http://api:8000;", f"proxy_pass http://127.0.0.1:{UPSTREAM_PORT};")
    text = text.replace("listen 80;", f"listen {NGINX_PORT};")
    text = text.replace("root /usr/share/nginx/html;", f"root {tmp}/html;")
    mimes = find_mime_types()
    conf = tmp / "nginx.conf"
    conf.write_text(
        "worker_processes 1;\n"
        f"pid {tmp}/nginx.pid;\n"
        f"error_log {tmp}/error.log warn;\n"
        "events { worker_connections 64; }\n"
        "http {\n"
        f"  access_log {tmp}/access.log;\n"
        f"  client_body_temp_path {tmp}/body;\n"
        f"  proxy_temp_path {tmp}/proxy;\n"
        f"  fastcgi_temp_path {tmp}/fastcgi;\n"
        f"  uwsgi_temp_path {tmp}/uwsgi;\n"
        f"  scgi_temp_path {tmp}/scgi;\n"
        + (f"  include {mimes};\n  default_type application/octet-stream;\n" if mimes else "")
        + "  include " + str(conf.with_name("server.conf")) + ";\n"
        "}\n", encoding="utf-8")
    conf.with_name("server.conf").write_text(text, encoding="utf-8")
    return conf


def get(url: str, accept_encoding: str | None = "gzip") -> tuple[int, dict[str, list[str]], bytes]:
    """Return (status, headers-lowercased-lists, raw-body).

    ⚠ The body is returned RAW and NOT decompressed — urllib does not decode
    `Content-Encoding: gzip` — which is what makes "fewer bytes on the wire" measurable.
    """
    req = urllib.request.Request(url)
    if accept_encoding:
        req.add_header("Accept-Encoding", accept_encoding)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, _hdrs(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, _hdrs(e.headers), e.read()


SHELL_MARKER = b'<script type="module"'


def is_shell(body: bytes) -> bool:
    """True when a response body is the SPA document, not a bundle and not an error page."""
    return SHELL_MARKER in body


def _hdrs(h) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for k, v in h.items():
        out.setdefault(k.lower(), []).append(v)
    return out


def main() -> int:
    config = DEFAULT_CONFIG
    if "--config" in sys.argv:
        config = Path(sys.argv[sys.argv.index("--config") + 1]).resolve()

    if not config.exists():
        print(f"FAIL: {config} missing")
        return 1
    if not shutil.which("nginx"):
        print("SKIP: nginx not installed — cannot execute this check")
        return 0
    mimes = find_mime_types()
    print(f"mime.types: {mimes or 'NOT FOUND'}")
    if mimes is None:
        # Static files then get no Content-Type from nginx, so `gzip_types` cannot match and
        # the bundle cases below would fail for a reason that has nothing to do with the
        # config. Say so rather than reporting a false failure.
        print("  ⚠ the static-bundle COMPRESSION cases are SKIPPED (they need mime.types to mean anything)")

    tmp = Path(tempfile.mkdtemp(prefix="ngx-shell-"))
    # ⚠ mkdtemp is 0700 root-only and nginx's WORKER runs as an unprivileged user (nobody
    # here, since this generated main config declares no `user`), so without this every
    # static-file request answers 500 and the check reads as a broken config rather than a
    # broken harness — which is exactly what the first falsification run showed.
    os.chmod(tmp, 0o755)
    (tmp / "html" / "assets").mkdir(parents=True)
    os.chmod(tmp / "html", 0o755)
    os.chmod(tmp / "html" / "assets", 0o755)
    (tmp / "html" / "index.html").write_text(
        '<!doctype html><html><head><script type="module" '
        'src="/assets/index-abc123.js"></script></head><body>rkm</body></html>', encoding="utf-8")
    bundle = ("// a compressible bundle\n" + "export const x = 1; // padding\n" * 800)
    css = "/* css */ .a{color:#08090b}\n" * 400
    (tmp / "html" / "assets" / "index-abc123.js").write_text(bundle, encoding="utf-8")
    (tmp / "html" / "assets" / "index-abc123.css").write_text(css, encoding="utf-8")
    for sub in ("body", "proxy", "fastcgi", "uwsgi", "scgi"):
        (tmp / sub).mkdir()

    upstream = ThreadingHTTPServer(("127.0.0.1", UPSTREAM_PORT), FakeApi)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()

    conf = build_config(tmp, config)
    check = subprocess.run(["nginx", "-t", "-c", str(conf)], capture_output=True, text=True)
    print(f"nginx -t: rc={check.returncode} {check.stderr.strip().splitlines()[-1:]}")
    if check.returncode != 0:
        print(check.stderr)
        return 1

    proc = subprocess.Popen(["nginx", "-c", str(conf), "-g", "daemon off;"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{NGINX_PORT}"
    failures: list[str] = []

    def case(label: str, ok: bool, detail: str) -> None:
        print(f"  {'PASS' if ok else 'FAIL'} {label}\n        {detail}")
        if not ok:
            failures.append(label)

    try:
        for _ in range(40):
            try:
                get(f"{base}/api/health", accept_encoding=None)
                break
            except Exception:
                time.sleep(0.25)

        # 1 + 2 — the document: storable AND revalidated, on `/` and on a deep link.
        for path in ("/", "/library/item/abc-123", "/settings"):
            status, hdrs, body = get(f"{base}{path}", accept_encoding=None)
            cc = hdrs.get("cache-control", [])
            joined = " | ".join(cc)
            case(f"{path} (shell document)", status == 200 and len(cc) == 1
                 and "no-cache" in joined and "no-store" not in joined and is_shell(body),
                 f"status={status} cache-control={cc} serves_shell={is_shell(body)}")

        # 3 — hashed bundles, immutable.
        for path in ("/assets/index-abc123.js", "/assets/index-abc123.css"):
            status, hdrs, _ = get(f"{base}{path}", accept_encoding="identity")
            cc = hdrs.get("cache-control", [])
            joined = " | ".join(cc)
            case(f"{path} (hashed bundle)", status == 200 and len(cc) == 1
                 and "max-age=31536000" in joined and "immutable" in joined
                 and "no-store" not in joined,
                 f"status={status} cache-control={cc}")

        # 4 — a missing bundle is a 404, never the shell document.
        status, _, body = get(f"{base}/assets/index-gone.js", accept_encoding="identity")
        case("/assets/index-gone.js (missing bundle)",
             status == 404 and not is_shell(body),
             f"status={status} served_shell_html={is_shell(body)}")
        # ...while an unknown PAGE route still falls back to the shell (unchanged behaviour).
        status, _, body = get(f"{base}/some/client/route", accept_encoding="identity")
        case("/some/client/route (SPA fallback intact)",
             status == 200 and is_shell(body),
             f"status={status} serves_shell={is_shell(body)}")

        # 5 — the bundle is really compressed, really smaller, and really varies.
        # ⚠ BOTH bundle types: `.js` and `.css` take different Content-Types from nginx's own
        # mime.types, and `gzip_types` is a whitelist matched against exactly those — so a
        # list that names one and not the other compresses half the shell silently.
        for path, expected in (("/assets/index-abc123.js", bundle),
                               ("/assets/index-abc123.css", css)):
            if mimes is None:
                break
            status, hdrs, raw = get(f"{base}{path}", accept_encoding="gzip")
            on_disk = len(expected.encode())
            ce = hdrs.get("content-encoding", [])
            var = hdrs.get("vary", [])
            decoded_ok = False
            if "gzip" in ce:
                try:
                    decoded_ok = gzip.decompress(raw).decode() == expected
                except Exception:
                    decoded_ok = False
            case(f"{path} (gzip)",
                 status == 200 and "gzip" in ce and len(raw) < on_disk
                 and any("Accept-Encoding" in v for v in var) and decoded_ok,
                 f"status={status} content-encoding={ce} vary={var} "
                 f"wire={len(raw)}B vs disk={on_disk}B roundtrip_ok={decoded_ok}")

        # 6 — MEDIA must NOT be compressed. This is the property `gzip_types` being a
        # whitelist buys, and the one that would be expensive to get wrong.
        for path in ("/api/jellyfin/stream?id=m1", "/api/jellyfin/hls/seg.ts"):
            status, hdrs, raw = get(f"{base}{path}", accept_encoding="gzip")
            ce = hdrs.get("content-encoding", [])
            case(f"{path} (media stays uncompressed)",
                 status == 200 and not ce and len(raw) == MEDIA_BYTES,
                 f"status={status} content-encoding={ce} bytes={len(raw)}")

        # 7 — dynamic JSON: no-store intact, and compressed because it is worth it.
        status, hdrs, raw = get(f"{base}/api/library", accept_encoding="gzip")
        cc = hdrs.get("cache-control", [])
        ce = hdrs.get("content-encoding", [])
        case("/api/library (JSON: no-store kept, compressed)",
             status == 200 and cc == ["no-store"] and "gzip" in ce
             and len(raw) < JSON_BYTES,
             f"status={status} cache-control={cc} content-encoding={ce} wire={len(raw)}B")

        # 8 — the sibling policy, re-checked because server-level gzip is new.
        status, hdrs, _ = get(f"{base}/api/jellyfin/poster?id=m1&width=500",
                              accept_encoding="identity")
        cc = hdrs.get("cache-control", [])
        joined = " | ".join(cc)
        case("/api/jellyfin/poster (artwork policy undisturbed)",
             status == 200 and len(cc) == 1 and "max-age=604800" in joined
             and "no-store" not in joined,
             f"status={status} cache-control={cc}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        upstream.shutdown()

    if failures:
        print(f"\nFAILED ({len(failures)}): {failures}")
        return 1
    print("\nAll shell cache + compression checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
