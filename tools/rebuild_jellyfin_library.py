"""Rebuild ONE Jellyfin library (delete + re-create + rescan).

Why this exists: a library's ITEM TREE can end up detached inside Jellyfin's
database (records survive with SeriesId/SeasonId set but no valid parent chain),
which shows up as "a show has no episodes" and "every show looks watched" — the
serie's played flag is computed as "all episodes played", which is vacuously true
with zero reachable episodes. Files on disk are fine; the DB is not. Re-creating
the library from scratch is the clean fix.

Documented use (2026-09-10): rebuilding `TV Shows` after the /config volume was
re-pointed from another Jellyfin's library paths.

    # 1. inspect + write an inventory of everything about to be deleted
    python3 tools/rebuild_jellyfin_library.py --library "TV Shows" \
        --capture /workspace/DATA/backups/2026/09/tv-library-inventory.json

    # 2. actually do it (without --yes it only reports what it would do)
    python3 tools/rebuild_jellyfin_library.py --library "TV Shows" --yes

DESTRUCTIVE: the library's watch state goes with it. Take a state backup first on
the Windows side: .\\scripts\\backup-rkm-state.ps1
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
socket.setdefaulttimeout(60)


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
        hdr = 'MediaBrowser Client="rkm-rebuild", Device="sandbox", DeviceId="rkm-rebuild-1", Version="1.0.0"'
        res = self._req("/Users/AuthenticateByName", method="POST",
                        headers={"Content-Type": "application/json", "X-Emby-Authorization": hdr},
                        data=json.dumps({"Username": user, "Pw": password}).encode())
        if not isinstance(res, dict) or "AccessToken" not in res:
            print(f"FATAL: auth failed: {res}")
            sys.exit(1)
        self.token = res["AccessToken"]

    def _req(self, path: str, *, method=None, data=None, headers=None):
        h = dict(headers or {})
        if getattr(self, "token", None):
            h["X-Emby-Token"] = self.token
        try:
            req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
            with urllib.request.urlopen(req) as resp:
                body = resp.read()
                try:
                    return json.loads(body.decode() or "null")
                except json.JSONDecodeError:
                    return body.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return {"__http_error__": e.code, "body": e.read()[:300].decode("utf-8", "replace")}
        except Exception as e:
            return {"__error__": str(e)}

    def library(self, name: str):
        libs = self._req("/Library/VirtualFolders")
        if not isinstance(libs, list):
            return None
        return next((v for v in libs if (v.get("Name") or "") == name), None)

    def count(self, parent_id: str, kinds: str) -> int:
        res = self._req(f"/Items?ParentId={parent_id}&Recursive=true&IncludeItemTypes={kinds}"
                        f"&Limit=0&EnableTotalRecordCount=true")
        return res.get("TotalRecordCount", -1) if isinstance(res, dict) else -1


def capture(jf: Jellyfin, lib: dict, outfile: str) -> dict:
    """Everything about to be deleted, so the rebuild is not a blind action."""
    series = jf._req(f"/Items?ParentId={lib['ItemId']}&Recursive=true&IncludeItemTypes=Series"
                     f"&Limit=500&fields=Path,DateCreated,SeriesId,ProviderIds") or {}
    rows = []
    for s in series.get("Items") or []:
        eps = jf._req(f"/Items?ParentId={s['Id']}&Recursive=true&IncludeItemTypes=Episode"
                      f"&Limit=0&EnableTotalRecordCount=true")
        rows.append({
            "name": s.get("Name"), "id": s.get("Id"), "path": s.get("Path"),
            "date_created": s.get("DateCreated"), "played": (s.get("UserData") or {}).get("Played"),
            "provider_ids": s.get("ProviderIds"),
            "episodes_reachable_via_parent": eps.get("TotalRecordCount"),
        })
    inventory = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "library": {"name": lib.get("Name"), "item_id": lib.get("ItemId"),
                    "locations": [x.get("Path") if isinstance(x, dict) else x
                                  for x in (lib.get("Locations") or [])],
                    "collection_type": lib.get("CollectionType")},
        "counts": {"series": jf.count(lib["ItemId"], "Series"),
                   "episodes": jf.count(lib["ItemId"], "Episode"),
                   "seasons": jf.count(lib["ItemId"], "Season")},
        "series": rows,
    }
    p = Path(outfile)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    return inventory


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", default="TV Shows")
    ap.add_argument("--capture", help="write a JSON inventory of the library first")
    ap.add_argument("--yes", action="store_true", help="actually delete + re-create")
    ap.add_argument("--settle", type=int, default=20, help="seconds to wait before re-reading")
    args = ap.parse_args()

    env = load_env()
    jf = Jellyfin(f"http://host.docker.internal:{env.get('RKM_JELLYFIN_PORT') or '8098'}",
                  env.get("RKM_JELLYFIN_ADMIN_USER") or "admin",
                  env.get("RKM_JELLYFIN_ADMIN_PASSWORD") or "")

    lib = jf.library(args.library)
    if not lib:
        libs = [v.get("Name") for v in (jf._req("/Library/VirtualFolders") or [])]
        print(f"no library named {args.library!r}; found: {libs}")
        return 1

    name = lib.get("Name")
    locs = [x.get("Path") if isinstance(x, dict) else x for x in (lib.get("Locations") or [])]
    path = locs[0] if locs else ""
    print(f"library {name!r}: item_id={lib.get('ItemId')} type={lib.get('CollectionType')} path={path}")
    print(f"  series={jf.count(lib['ItemId'], 'Series')} seasons={jf.count(lib['ItemId'], 'Season')} "
          f"episodes={jf.count(lib['ItemId'], 'Episode')}")

    if args.capture:
        inv = capture(jf, lib, args.capture)
        print(f"  inventory written: {args.capture} ({len(inv['series'])} series recorded)")

    if not args.yes:
        print("\nDRY RUN - nothing changed. Add --yes to delete + re-create "
              f"'{name}' from {path!r} and rescan.")
        return 0

    print(f"\n== deleting library '{name}'")
    res = jf._req(f"/Library/VirtualFolders?name={urllib.parse.quote(name)}&refreshLibrary=false",
                  method="DELETE")
    print(f"   -> {res if isinstance(res, (str, dict)) and res != '' else 'ok'}")

    print(f"== re-creating '{name}' at {path} (type {lib.get('CollectionType') or 'tvshows'})")
    body = {"LibraryOptions": {"SaveLocalMetadata": True, "EnableInternetProviders": True},
            "RefreshLibrary": False}
    q = (f"/Library/VirtualFolders?name={urllib.parse.quote(name)}"
         f"&collectionType={lib.get('CollectionType') or 'tvshows'}"
         f"&refreshLibrary=false&paths={urllib.parse.quote(path)}")
    res = jf._req(q, method="POST", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"})
    print(f"   -> {res if res else 'ok'}")

    print("== triggering a library scan")
    jf._req("/Library/Refresh", method="POST")

    print(f"== waiting {args.settle}s, then re-reading")
    time.sleep(args.settle)
    new = jf.library(name)
    if not new:
        print("   ERROR: library missing after re-create")
        return 1
    print(f"   item_id={new.get('ItemId')} (changed: {new.get('ItemId') != lib.get('ItemId')})")
    print(f"   series={jf.count(new['ItemId'], 'Series')} seasons={jf.count(new['ItemId'], 'Season')} "
          f"episodes={jf.count(new['ItemId'], 'Episode')}")
    task = next((t for t in (jf._req("/ScheduledTasks") or [])
                 if (t.get("Name") or "") == "Scan Media Library"), {})
    print(f"   scan: state={task.get('State')} progress={task.get('CurrentProgressPercentage')}")
    print("\nA fresh library indexes over time; re-run this tool's counts, or "
          "tools/diagnose_series_state.py, once the scan reports Idle.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
