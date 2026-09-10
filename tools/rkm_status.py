"""One-glance status of the whole bundled stack (read-only).

    python3 tools/rkm_status.py

Prints: is the api up, can it see Jellyfin, what libraries are configured and do
they resolve, is a library scan running and how far along, and how much is
indexed. This is the "is anything wrong, and where" command -- the individual
diagnostic tools explain a problem once this has pointed at one.

Exit code 1 when something is actually broken (api down, a library unresolved),
so it is safe to use as a health gate.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rkm_common as rc  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="RKM bundled stack status")
    ap.add_argument("--jellyfin-url", default=None, help="override (default: auto)")
    ap.add_argument("--app-url", default=None, help="override (default: auto)")
    args = ap.parse_args()

    env = rc.load_env()
    app = args.app_url or rc.app_base(env)
    problems: list[str] = []

    print(f"repo     : {rc.repo_root()}")
    print(f"dashboard: {app}")
    print(f"jellyfin : {args.jellyfin_url or rc.jellyfin_base(env)}")

    health = rc.http_json(f"{app}/api/health", timeout=10)
    print("\n== api ==")
    if not isinstance(health, dict) or "__error__" in health:
        print(f"  UNREACHABLE ({health})")
        print("  -> start it:  .\\bootstrap.ps1")
        return 1
    services = health.get("services") or {}
    print(f"  ok={health.get('ok')}  degraded={health.get('degraded')}")
    print(f"  jellyfin={'ok' if services.get('jellyfin') else 'DOWN'}"
          f"  radarr={services.get('radarr')}  sonarr={services.get('sonarr')}"
          f"  tmdb={services.get('tmdb')}")
    if not services.get("jellyfin"):
        problems.append("the api cannot reach Jellyfin (check the API credential)")

    folders = rc.http_json(f"{app}/api/library/folders", timeout=25)
    print("\n== libraries ==")
    if not isinstance(folders, dict) or "__error__" in folders:
        print(f"  UNREADABLE ({folders})")
        problems.append("the api could not read the library folders")
    else:
        for lib in folders.get("libraries") or []:
            mark = "OK  " if lib.get("ok") else "FAIL"
            print(f"  {mark} {str(lib.get('name')):16} {str(lib.get('path')):26}"
                  f" {lib.get('warning') or ''}")
            if not lib.get("ok"):
                problems.append(f"library '{lib.get('name')}' is unresolved")
        print(f"  server folders: {[(f.get('name'), f.get('path')) for f in folders.get('folders') or []]}")
        for w in folders.get("warnings") or []:
            print(f"  warning: {w}")
            problems.append(w)

    jf = rc.Jellyfin(args.jellyfin_url, env)
    print("\n== jellyfin ==")
    if not jf.token:
        print("  could not authenticate (RKM_JELLYFIN_ADMIN_USER / PASSWORD in .env)")
        problems.append("Jellyfin authentication failed")
    else:
        task = jf.scan_task()
        if task:
            prog = task.get("CurrentProgressPercentage")
            print(f"  scan: {task.get('State')}"
                  f"{f' {prog:.1f}%' if isinstance(prog, (int, float)) else ''}")
            last = task.get("LastExecutionResult") or {}
            if last:
                print(f"        last run: {last.get('Status')} ended {last.get('EndTimeUtc')}")
        for lib in jf.libraries():
            lid = lib.get("ItemId")
            locs = [x.get("Path") if isinstance(x, dict) else x for x in (lib.get("Locations") or [])]
            print(f"  {str(lib.get('Name')):16} {str(locs[0]) if locs else '':26}"
                  f" movies={jf.count(lid, 'Movie'):5} series={jf.count(lid, 'Series'):5}"
                  f" episodes={jf.count(lid, 'Episode'):6}")

    print("\n== verdict ==")
    if problems:
        for p in problems:
            print(f"  ATTENTION: {p}")
        print("  diagnose with:  .\\rkm.ps1 diagnose")
        return 1
    print("  everything looks healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
