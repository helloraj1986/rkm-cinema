"""Probe the bundled Jellyfin's real state from the sandbox (read-only).

Answers "why does the UI show X" with server facts instead of guesses:
scan progress, per-library item counts, a library's items with their UserData
(so a bogus 'watched' flag is visible as such), the episodes of a series, and the
tail of the server log filtered for problems.

    python3 tools/probe_jellyfin_state.py
    python3 tools/probe_jellyfin_state.py --library "TV Shows" --series 30 --log-lines 400

Reads the repo .env for the admin user/password and the Jellyfin URL. Never writes.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

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


class Jellyfin:
    def __init__(self, base: str, user: str, password: str):
        self.base = base.rstrip("/")
        self.token = self._auth(user, password)

    def _call(self, path: str, *, data=None, method=None, headers=None, raw=False):
        req = urllib.request.Request(self.base + path, data=data,
                                     headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                body = resp.read()
                return body.decode("utf-8", "replace") if raw else json.loads(body.decode() or "null")
        except urllib.error.HTTPError as e:
            return {"__http_error__": e.code, "body": e.read()[:200].decode("utf-8", "replace")}
        except Exception as e:  # network/DNS
            return {"__error__": str(e)}

    def _auth(self, user: str, password: str) -> str:
        hdr = 'MediaBrowser Client="rkm-probe", Device="sandbox", DeviceId="rkm-probe-1", Version="1.0.0"'
        res = self._call("/Users/AuthenticateByName",
                         data=json.dumps({"Username": user, "Pw": password}).encode(),
                         headers={"Content-Type": "application/json", "X-Emby-Authorization": hdr},
                         method="POST")
        if not isinstance(res, dict) or "AccessToken" not in res:
            print(f"FATAL: Jellyfin auth failed: {res}")
            sys.exit(1)
        return res["AccessToken"]

    def get(self, path: str, raw: bool = False):
        return self._call(path, headers={"X-Emby-Token": self.token}, raw=raw)

    def count(self, parent_id: str, kinds: str) -> int:
        res = self.get(f"/Items?ParentId={parent_id}&Recursive=true&IncludeItemTypes={kinds}"
                       f"&Limit=0&EnableTotalRecordCount=true")
        return res.get("TotalRecordCount", -1) if isinstance(res, dict) else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", default="TV Shows", help="library name to inspect deeply")
    ap.add_argument("--series", type=int, default=20, help="how many series to list")
    ap.add_argument("--episodes", type=int, default=3, help="series whose episodes to list")
    ap.add_argument("--log-lines", type=int, default=300)
    args = ap.parse_args()

    env = load_env()
    jf = Jellyfin(
        f"http://host.docker.internal:{env.get('RKM_JELLYFIN_PORT') or '8098'}",
        env.get("RKM_JELLYFIN_ADMIN_USER") or "admin",
        env.get("RKM_JELLYFIN_ADMIN_PASSWORD") or "",
    )

    task = next((t for t in jf.get("/ScheduledTasks") if (t.get("Name") or "") == "Scan Media Library"), {})
    last = task.get("LastExecutionResult") or {}
    print("=== scan ===")
    print(f"  state={task.get('State')} progress={task.get('CurrentProgressPercentage')}")
    print(f"  last: {last.get('Status')} {last.get('StartTimeUtc')} -> {last.get('EndTimeUtc')}")

    libs = jf.get("/Library/VirtualFolders") or []
    print("\n=== libraries ===")
    for vf in libs:
        locs = [x.get("Path") if isinstance(x, dict) else x for x in (vf.get("Locations") or [])]
        lid = vf.get("ItemId")
        print(f"  {str(vf.get('Name')):14} type={str(vf.get('CollectionType')):9} locs={locs}")
        print(f"       movies={jf.count(lid, 'Movie')} series={jf.count(lid, 'Series')} "
              f"episodes={jf.count(lid, 'Episode')} seasons={jf.count(lid, 'Season')}")

    target = next((v for v in libs if (v.get("Name") or "") == args.library), None)
    if not target:
        print(f"\n(no library named {args.library!r})")
        return 0

    print(f"\n=== series in {args.library!r} (with UserData - a bogus watched flag shows here) ===")
    items = jf.get(f"/Items?ParentId={target['ItemId']}&Recursive=true&IncludeItemTypes=Series"
                   f"&Limit={args.series}&fields=Path,DateCreated") or {}
    rows = items.get("Items") or []
    print(f"  showing {len(rows)} of {items.get('TotalRecordCount')}")
    for it in rows:
        ud = it.get("UserData") or {}
        print(f"   {str(it.get('Name'))[:44]:46} played={str(ud.get('Played')):5} "
              f"unplayed={str(ud.get('UnplayedItemCount')):5} childCount={str(it.get('ChildCount')):4} "
              f"recursive={str(it.get('RecursiveItemCount')):5}")
        print(f"        {it.get('Path')}")

    for it in rows[:args.episodes]:
        eps = jf.get(f"/Items?ParentId={it['Id']}&Recursive=true&IncludeItemTypes=Episode&Limit=5&fields=Path") or {}
        print(f"\n  episodes of {str(it.get('Name'))[:40]!r}: {eps.get('TotalRecordCount')}")
        for ep in (eps.get("Items") or [])[:5]:
            print(f"     - {ep.get('Name')} | {ep.get('Path')}")

    print(f"\n=== Jellyfin log tail (last {args.log_lines} lines, filtered) ===")
    logs = jf.get("/System/Logs") or []
    if isinstance(logs, list) and logs:
        newest = sorted(logs, key=lambda x: x.get("DateModified") or "", reverse=True)[0]
        name = newest.get("Name")
        text = jf.get(f"/System/Logs/Log?name={urllib.request.quote(name)}", raw=True)
        lines = text.splitlines() if isinstance(text, str) else []
        interesting = [l for l in lines[-args.log_lines:]
                       if any(t in l.lower() for t in
                              ("error", "exception", "fail", "warn", "skip", "denied", "media2",
                               "tv shows", "unauthor"))]
        print(f"  log: {name} ({len(lines)} lines, {len(interesting)} interesting)")
        for l in interesting[-60:]:
            print("   ", l[:200])
    else:
        print("  (no logs listed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
