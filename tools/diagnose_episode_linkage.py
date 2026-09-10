"""Is the episode -> series linkage broken (or duplicated) in Jellyfin's DB?

Observed: a library reports N episodes, yet most series report zero when queried
by ParentId, and some show names appear BOTH in the episode sample and in the
"series with no episodes" list. Those cannot both be true unless the episode
records point at a DIFFERENT series item than the one the library lists.

This checks, for a given show name:
  1. how many SERIES items carry that name (duplicates?),
  2. which SeriesId the episode records carry,
  3. whether that id is one of the library's series items,
  4. what each of those items reports for ParentId / Path / LocationType,
  5. episode counts under each id, via both query shapes.

    python3 tools/diagnose_episode_linkage.py --show Yellowstone
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.parse
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


def get(base: str, path: str, token: str):
    try:
        req = urllib.request.Request(base.rstrip("/") + path, headers={"X-Emby-Token": token})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return {"__http_error__": e.code, "body": e.read()[:200].decode("utf-8", "replace")}
    except Exception as e:
        return {"__error__": str(e)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", default="Yellowstone")
    ap.add_argument("--library", default="TV Shows")
    args = ap.parse_args()

    env = load_env()
    base = f"http://host.docker.internal:{env.get('RKM_JELLYFIN_PORT') or '8098'}"
    hdr = 'MediaBrowser Client="rkm-link", Device="sandbox", DeviceId="rkm-link-1", Version="1.0.0"'
    req = urllib.request.Request(
        base + "/Users/AuthenticateByName",
        data=json.dumps({"Username": env.get("RKM_JELLYFIN_ADMIN_USER") or "admin",
                         "Pw": env.get("RKM_JELLYFIN_ADMIN_PASSWORD") or ""}).encode(),
        headers={"Content-Type": "application/json", "X-Emby-Authorization": hdr}, method="POST")
    with urllib.request.urlopen(req) as resp:
        token = json.loads(resp.read().decode())["AccessToken"]

    def jget(path: str):
        return get(base, path, token)

    libs = jget("/Library/VirtualFolders")
    lib = next((v for v in libs if (v.get("Name") or "") == args.library), None)
    if not lib:
        print(f"no library {args.library!r}")
        return 1
    print(f"library {args.library!r} ItemId={lib.get('ItemId')}")

    # 1. series items carrying the name, in the whole server (any parent)
    q = urllib.parse.quote(args.show)
    all_series = jget(f"/Items?Recursive=true&IncludeItemTypes=Series&SearchTerm={q}"
                           f"&Limit=50&fields=Path,DateCreated,ProviderIds") or {}
    print(f"\n=== SERIES items matching {args.show!r} anywhere on the server: "
          f"{all_series.get('TotalRecordCount')} ===")
    ids_in_lib = set()
    lib_series = jget(f"/Items?ParentId={lib['ItemId']}&Recursive=true"
                           f"&IncludeItemTypes=Series&Limit=500&fields=Path") or {}
    for s in lib_series.get("Items") or []:
        ids_in_lib.add(s.get("Id"))
    for s in all_series.get("Items") or []:
        print(f"   id={s.get('Id')} name={s.get('Name')!r} parentId={s.get('ParentId')} "
              f"inLibrary={s.get('Id') in ids_in_lib}")
        print(f"        path={s.get('Path')}")
        print(f"        played={((s.get('UserData') or {}).get('Played'))} "
              f"seriesId={s.get('SeriesId')} dateCreated={s.get('DateCreated')}")

    # 2. which SeriesId do the episodes carry?
    eps = jget(f"/Items?Recursive=true&IncludeItemTypes=Episode&SearchTerm={q}"
                    f"&Limit=200&fields=SeriesId,SeriesName,Path,SeasonId") or {}
    print(f"\n=== EPISODE records matching {args.show!r}: {eps.get('TotalRecordCount')} "
          f"(showing up to 200) ===")
    by_series: dict[str, int] = {}
    for e in eps.get("Items") or []:
        sid = e.get("SeriesId") or "(null)"
        by_series[sid] = by_series.get(sid, 0) + 1
    for sid, n in sorted(by_series.items(), key=lambda kv: -kv[1]):
        print(f"   SeriesId={sid} episodes={n} inLibrary={sid in ids_in_lib}"
              f"{' <-- DIFFERENT series item than the library lists' if sid not in ids_in_lib and sid != '(null)' else ''}")
    for e in (eps.get("Items") or [])[:3]:
        print(f"     e.g. {e.get('Name')!r} path={e.get('Path')}")

    # 3. every id we know about: how many episodes hang off it, both shapes?
    print("\n=== episode counts per candidate series id ===")
    for sid in sorted(by_series):
        if sid == "(null)":
            continue
        a = jget(f"/Items?ParentId={sid}&Recursive=true&IncludeItemTypes=Episode"
                       f"&Limit=0&EnableTotalRecordCount=true") or {}
        b = jget(f"/Shows/{sid}/Episodes?Recursive=true&Limit=0") or {}
        c = jget(f"/Items?ParentId={sid}&Recursive=true"
                       f"&Limit=0&EnableTotalRecordCount=true") or {}
        print(f"   {sid}: items+Episode={a.get('TotalRecordCount')} "
              f"/Shows/Episodes={b.get('TotalRecordCount')} any={c.get('TotalRecordCount')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
