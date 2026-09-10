"""Diagnose the "every show looks watched, episodes missing" symptom.

Hypothesis under test: Jellyfin reports a SERIES as Played=True when it has NO
episodes indexed (vacuous "all episodes played"), and our UI renders that as a
watched tick. This tool separates the two cases per series by counting episodes:

  - episodes > 0 and played      -> a genuine played state
  - episodes == 0 and played     -> the vacuous case (looks watched, has nothing)
  - episodes == 0 and not played -> an empty series folder
  - episodes > 0 and not played  -> the healthy "has content to watch" case

It also prints what OUR api returns for the same folder, so an app-side
mismatch is visible next to the raw Jellyfin state.

    python3 tools/diagnose_series_state.py
    python3 tools/diagnose_series_state.py --library "TV Shows" --show-empty 25
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
    req = urllib.request.Request(base.rstrip("/") + path, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return body.decode("utf-8", "replace") if raw else json.loads(body.decode() or "null")
    except urllib.error.HTTPError as e:
        return {"__http_error__": e.code, "body": e.read()[:200].decode("utf-8", "replace")}
    except Exception as e:
        return {"__error__": str(e)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", default="TV Shows")
    ap.add_argument("--show-empty", type=int, default=15, help="how many empty series to list")
    ap.add_argument("--app", default=None,
                    help="app base URL (auto-detected from here if omitted)")
    args = ap.parse_args()

    env = load_env()
    base = rc.jellyfin_base(env)

    # auth
    hdr = 'MediaBrowser Client="rkm-diagnose", Device="sandbox", DeviceId="rkm-diag-1", Version="1.0.0"'
    req = urllib.request.Request(
        base + "/Users/AuthenticateByName",
        data=json.dumps({"Username": env.get("RKM_JELLYFIN_ADMIN_USER") or "admin",
                         "Pw": env.get("RKM_JELLYFIN_ADMIN_PASSWORD") or ""}).encode(),
        headers={"Content-Type": "application/json", "X-Emby-Authorization": hdr},
        method="POST")
    with urllib.request.urlopen(req) as resp:
        token = json.loads(resp.read().decode())["AccessToken"]

    libs = get(base, "/Library/VirtualFolders", token)
    lib = next((v for v in libs if (v.get("Name") or "") == args.library), None)
    if not lib:
        print(f"no library named {args.library!r}")
        return 1

    series = get(base, f"/Items?ParentId={lib['ItemId']}&Recursive=true&IncludeItemTypes=Series"
                       f"&Limit=500&fields=Path", token).get("Items") or []
    print(f"=== {args.library}: {len(series)} series ===")
    print(f"{'series':46} {'eps':>5} {'played':>7} {'unplayed':>9}  verdict")

    buckets = {"content-to-watch": [], "all-played": [], "vacuous-watched": [], "empty-folder": []}
    for s in series:
        eps = get(base, f"/Items?ParentId={s['Id']}&Recursive=true&IncludeItemTypes=Episode"
                         f"&Limit=0&EnableTotalRecordCount=true", token).get("TotalRecordCount", -1)
        ud = s.get("UserData") or {}
        played = bool(ud.get("Played"))
        unplayed = ud.get("UnplayedItemCount")
        if eps == 0 and played:
            verdict = "VACUOUS WATCHED"
        elif eps == 0:
            verdict = "empty folder"
        elif played:
            verdict = "all episodes played"
        else:
            verdict = "has content to watch"
        key = {"VACUOUS WATCHED": "vacuous-watched", "empty folder": "empty-folder",
               "all episodes played": "all-played", "has content to watch": "content-to-watch"}[verdict]
        buckets[key].append((s.get("Name"), eps, played, unplayed, s.get("Path")))
        print(f"  {str(s.get('Name'))[:44]:46} {eps:5} {str(played):>7} {str(unplayed):>9}  {verdict}")

    print("\n=== summary ===")
    for k, v in buckets.items():
        print(f"  {k:18} {len(v)}")
    total = sum(len(v) for v in buckets.values())
    print(f"  (total {total})")

    if buckets["vacuous-watched"]:
        print(f"\n=== series with NO episodes that Jellyfin reports as PLAYED "
              f"(showing {min(args.show_empty, len(buckets['vacuous-watched']))}) ===")
        for name, _eps, _p, _u, path in buckets["vacuous-watched"][:args.show_empty]:
            print(f"   {str(name)[:50]:52} {path}")

    if buckets["empty-folder"]:
        print(f"\n=== series folders Jellyfin sees as EMPTY (showing "
              f"{min(args.show_empty, len(buckets['empty-folder']))}) ===")
        for name, _eps, _p, _u, path in buckets["empty-folder"][:args.show_empty]:
            print(f"   {str(name)[:50]:52} {path}")

    # where do the library's episodes actually live? (reconciles "5187 episodes"
    # with per-series counts of 0)
    sample = get(base, f"/Items?ParentId={lib['ItemId']}&Recursive=true&IncludeItemTypes=Episode"
                       f"&Limit=300&fields=SeriesId,SeriesName,Path,SeasonId", token) or {}
    eps = sample.get("Items") or []
    print(f"\n=== library episode sample: {len(eps)} of {sample.get('TotalRecordCount')} ===")
    by_series: dict[str, int] = {}
    for e in eps:
        key = e.get("SeriesName") or f"(no SeriesName; SeriesId={e.get('SeriesId')})"
        by_series[key] = by_series.get(key, 0) + 1
    for name, n in sorted(by_series.items(), key=lambda kv: -kv[1])[:20]:
        print(f"   {n:5}  {name}")
    if eps:
        first = eps[0]
        print("\n   one episode record:")
        for k in ("Name", "SeriesName", "SeriesId", "SeasonId", "ParentId", "Path"):
            print(f"     {k:12} {first.get(k)}")

    # Jellyfin's dedicated episodes endpoint vs the generic Items query, for a
    # series that shows 0 (the app's series page uses a query shape like this)
    empty_series = next((s for s in series if s.get("Name") in
                         (buckets["vacuous-watched"][0][0] if buckets["vacuous-watched"] else None,)), None)
    if empty_series:
        sid = empty_series["Id"]
        print(f"\n=== episode query shapes for {empty_series.get('Name')!r} (series id {sid[:8]}...) ===")
        for label, path in (
            ("/Shows/{id}/Episodes", f"/Shows/{sid}/Episodes?Recursive=true&Limit=5"),
            ("Items ParentId+Episode", f"/Items?ParentId={sid}&Recursive=true&IncludeItemTypes=Episode&Limit=5"),
            ("Items ParentId+Season", f"/Items?ParentId={sid}&Recursive=true&IncludeItemTypes=Season&Limit=5"),
            ("Items ParentId (any)", f"/Items?ParentId={sid}&Recursive=true&Limit=5"),
        ):
            res = get(base, path, token) or {}
            n = res.get("TotalRecordCount")
            names = [i.get("Name") for i in (res.get("Items") or [])][:5]
            print(f"   {label:24} total={n} {names}")

    # what does OUR api report for the same folder?
    print("\n=== our api's view of the same folder ===")
    app = args.app or rc.app_base(env)
    folders = get(app, "/api/library/folders")
    if isinstance(folders, dict) and "libraries" in folders:
        row = next((l for l in folders["libraries"] if l.get("name") == args.library), None)
        print(f"  library row: {row}")
        if row and row.get("folder_id"):
            items = get(args.app, f"/api/library/folders/{row['folder_id']}/items?limit=20")
            print(f"  items endpoint keys: {list(items)[:8] if isinstance(items, dict) else items}")
            full = (items.get("items") or []) if isinstance(items, dict) else []
            if full:
                print(f"  first item, raw: {json.dumps(full[0], indent=2)[:600]}")
                print("  played flags:",
                      [(it.get("title") or it.get("name") or it.get("item_id", "")[:8], it.get("played"))
                       for it in full[:10]])
    else:
        print(f"  (app probe failed: {folders})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
