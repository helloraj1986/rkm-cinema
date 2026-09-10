"""Why does a series folder exist with no episodes indexed?

Jellyfin's own admin API can list a directory as the SERVER sees it
(`/Environment/DirectoryContents`), which is the ground truth for "are the files
there and readable?" — something the sandbox cannot check directly because the
media drives only exist inside the containers.

It also counts probe failures in the server log, since a file Jellyfin cannot
ffprobe can end up with no episode record at all.

    python3 tools/probe_media_files.py --dir "/media2/TV Shows/Adolescence (2025) S01 (1080p NF WEB-DL x265 10bit EAC3 Atmos 5.1 Ghost)"
    python3 tools/probe_media_files.py --dir "/media2/TV Shows/One Piece"        # a healthy one
    python3 tools/probe_media_files.py --log-errors                              # probe failures
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rkm_common as rc  # noqa: E402  (shared env + URL resolution)

REPO = Path(__file__).resolve().parent.parent
socket.setdefaulttimeout(30)


def load_env() -> dict:
    env: dict[str, str] = {}
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, _, v = s.partition("=")
            env[k.strip()] = v.strip()
    return env


def get(base: str, path: str, token: str | None = None, raw: bool = False):
    headers = {"X-Emby-Token": token} if token else {}
    try:
        req = urllib.request.Request(base.rstrip("/") + path, headers=headers)
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return body.decode("utf-8", "replace") if raw else json.loads(body.decode() or "null")
    except urllib.error.HTTPError as e:
        return {"__http_error__": e.code, "body": e.read()[:300].decode("utf-8", "replace")}
    except Exception as e:
        return {"__error__": str(e)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", action="append", default=[], help="container path to list (repeatable)")
    ap.add_argument("--log-errors", action="store_true", help="count probe failures in the log")
    args = ap.parse_args()

    env = load_env()
    base = rc.jellyfin_base(env)
    hdr = 'MediaBrowser Client="rkm-files", Device="sandbox", DeviceId="rkm-files-1", Version="1.0.0"'
    req = urllib.request.Request(
        base + "/Users/AuthenticateByName",
        data=json.dumps({"Username": env.get("RKM_JELLYFIN_ADMIN_USER") or "admin",
                         "Pw": env.get("RKM_JELLYFIN_ADMIN_PASSWORD") or ""}).encode(),
        headers={"Content-Type": "application/json", "X-Emby-Authorization": hdr}, method="POST")
    with urllib.request.urlopen(req) as resp:
        token = json.loads(resp.read().decode())["AccessToken"]

    for d in args.dir:
        q = urllib.request.quote(d)
        res = get(base, f"/Environment/DirectoryContents?path={q}&includeFiles=true&recursive=false", token)
        print(f"=== {d} ===")
        if isinstance(res, dict) and "__http_error__" in res:
            print(f"   HTTP {res['__http_error__']}: {res['body'][:150]}")
            continue
        if isinstance(res, list):
            for entry in res:
                kind = "DIR " if entry.get("IsDirectory") else "FILE"
                size = entry.get("Size") or 0
                print(f"   {kind} {size:>13,}  {entry.get('Name')}  |  {entry.get('Path')}")
        else:
            print(f"   unexpected response: {str(res)[:300]}")
        print()

    if args.log_errors:
        logs = get(base, "/System/Logs", token) or []
        newest = sorted(logs, key=lambda x: x.get("DateModified") or "", reverse=True)[0]
        name = newest.get("Name")
        text = get(base, f"/System/Logs/Log?name={urllib.request.quote(name)}", token, raw=True)
        lines = text.splitlines() if isinstance(text, str) else []
        probe_errs = [l for l in lines if "Probe Provider" in l or "ffprobe failed" in l]
        print(f"=== probe failures in {name}: {len(probe_errs)} ===")
        for l in probe_errs[:20]:
            print("   ", l[:180])
        media_errs = [l for l in lines if "[ERR]" in l]
        print(f"\n=== all [ERR] lines: {len(media_errs)} (showing up to 20) ===")
        for l in media_errs[:20]:
            print("   ", l[:180])
    return 0


if __name__ == "__main__":
    sys.exit(main())
