#!/usr/bin/env python3
"""Probe: why is '3 Deewarein' missing from Continue Watching?

Read-only. Compares three views of the same fact:
  1. Jellyfin's OWN Resume list (/Users/{uid}/Items/Resume)
  2. the playable item's UserData (PlaybackPositionTicks / Played)
  3. the app's /api/library/continue-watching payload
"""
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rkm_common import Jellyfin, app_client, app_base, load_env  # noqa: E402

TITLE = sys.argv[1] if len(sys.argv) > 1 else "3 Deewarein"

jf = Jellyfin()
print(f"jellyfin base: {jf.base}  token: {'yes' if jf.token else 'NO'}")

users = jf.get("/Users")
uid = None
if isinstance(users, list):
    for u in users:
        print(f"  user: {u.get('Name')!r} id={u.get('Id')}")
        if (u.get("Name") or "").lower() == "admin":
            uid = u.get("Id")
uid = uid or (users[0].get("Id") if isinstance(users, list) and users else None)
print(f"using user id: {uid}")

# --- 1. the item, with EVERYTHING we need to judge it ---------------------
q = urllib.parse.quote(TITLE)
found = jf.get(f"/Users/{uid}/Items?searchTerm={q}&Recursive=true"
               f"&IncludeItemTypes=Movie&Fields=UserData,Path,ProviderIds,MediaSources")
items = (found or {}).get("Items") or []
print(f"\n--- search {TITLE!r}: {len(items)} hit(s) ---")
target = None
for it in items:
    ud = it.get("UserData") or {}
    print(f"  {it.get('Name')!r} ({it.get('ProductionYear')}) id={it.get('Id')}")
    print(f"      Played={ud.get('Played')} PositionTicks={ud.get('PlaybackPositionTicks')} "
          f"PlayCount={ud.get('PlayCount')} LastPlayed={ud.get('LastPlayedDate')}")
    print(f"      path={it.get('Path')}")
    print(f"      UserData keys={sorted(ud.keys())}")
    if (it.get("Name") or "").lower().startswith("3 deewarein") or "deewarein" in (it.get("Name") or "").lower():
        target = it

# --- 2. Jellyfin's own Resume list ---------------------------------------
resume = jf.get(f"/Users/{uid}/Items/Resume?MediaTypes=Video&Limit=50"
                f"&Fields=UserData,Path")
rows = (resume or {}).get("Items") or []
print(f"\n--- Jellyfin /Items/Resume: {len(rows)} item(s) ---")
for r in rows:
    ud = r.get("UserData") or {}
    print(f"  {r.get('Name')!r} type={r.get('Type')} pos={ud.get('PlaybackPositionTicks')} played={ud.get('Played')}")

if target is not None:
    tid = target.get("Id")
    in_resume = any((r.get("Id") == tid) for r in rows)
    print(f"\n=== VERDICT for {TITLE!r} ({tid}) ===")
    print(f"  in Jellyfin Resume list: {in_resume}")
    ud = target.get("UserData") or {}
    print(f"  PlaybackPositionTicks : {ud.get('PlaybackPositionTicks')}")
    print(f"  Played                : {ud.get('Played')}")

# --- 3. the app's payload -------------------------------------------------
# The app's routes need a SESSION once `RKM_AUTH_REQUIRED` is armed: a tool is not a browser,
# so it signs in first — on the tools' own device id, so the browser's token is not rotated away.
app = app_base()
client = app_client(base=app)
if not client.signed_in:
    print(f"  cannot read the app: {client.error}")
cw = client.get("/api/library/continue-watching")
apps = (cw or {}).get("items") or []
print(f"\n--- app /api/library/continue-watching: {len(apps)} item(s) ---")
print(f"  titles: {[i.get('title') for i in apps]}")
if target is not None:
    print(f"  {TITLE!r} present in app payload: "
          f"{any((i.get('title') or '').lower().find('deewarein') >= 0 for i in apps)}")
