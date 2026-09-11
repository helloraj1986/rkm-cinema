#!/usr/bin/env python3
"""Verify, against the LIVE stack, that a reported position actually persists.

Runs the app's OWN provider code (``JellyfinLibraryProvider.set_playback_position``)
against the real Jellyfin with the real API key, then asserts:
  1. the position Jellyfin stores equals what was reported;
  2. the item shows up in Jellyfin's own Resume list;
  3. the app's /api/library/continue-watching returns it.

MUTATES the item's resume position — that is the thing under test.
Usage: python3 tools/verify_progress_reporting.py "<title>" <seconds>
"""
import sys
import time
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rkm_common import Jellyfin, app_base, http_json  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from services.library.jellyfin import JellyfinLibraryProvider  # noqa: E402

TITLE = sys.argv[1] if len(sys.argv) > 1 else "3 Deewarein"
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 1651.0
TICKS = int(SECONDS * 1e7)

jf = Jellyfin()
users = jf.get("/Users") or []
uid = next((u.get("Id") for u in users if (u.get("Name") or "").lower() == "admin"), None)
keys = (jf.get("/Auth/Keys") or {}).get("Items") or []
api_key = next((k.get("AccessToken") for k in keys if (k.get("AppName") or "") == "RKM Cinema"), None)
if not api_key:
    print("!! no 'RKM Cinema' API key found — refusing to guess"); sys.exit(2)

hits = (jf.get(f"/Users/{uid}/Items?searchTerm={urllib.parse.quote(TITLE)}&Recursive=true"
               f"&IncludeItemTypes=Movie&Fields=UserData") or {}).get("Items") or []
if not hits:
    print(f"!! no item matches {TITLE!r}"); sys.exit(2)
ITEM = hits[0]["Id"]
print(f"item      : {hits[0].get('Name')!r} ({ITEM})")
print(f"before    : {((hits[0].get('UserData') or {}).get('PlaybackPositionTicks') or 0) / 1e7:.1f}s")

# --- the app's own code path, against the live server --------------------
cfg = SimpleNamespace(JELLYFIN_URL=jf.base, JELLYFIN_API_KEY=api_key,
                      JELLYFIN_BROWSER_URL=jf.base)
prov = JellyfinLibraryProvider(config=cfg)
ok = prov.set_playback_position(ITEM, TICKS)
print(f"write     : JellyfinLibraryProvider.set_playback_position({SECONDS:.0f}s) -> {ok}")
if not ok:
    print("!! the app's write path did not land"); sys.exit(1)
time.sleep(1)

# --- 1. stored value -----------------------------------------------------
d = jf.get(f"/Users/{uid}/Items/{ITEM}?Fields=UserData")
ud = (d or {}).get("UserData") or {}
got = (ud.get("PlaybackPositionTicks") or 0) / 1e7
print(f"after     : {got:.1f}s  (played={ud.get('Played')})")
assert got == SECONDS, f"stored {got}s != reported {SECONDS}s"

# --- 2. Jellyfin's own Resume list --------------------------------------
resume = (jf.get(f"/Users/{uid}/Items/Resume?MediaTypes=Video&Limit=50") or {}).get("Items") or []
in_jf = any(r.get("Id") == ITEM for r in resume)
print(f"jellyfin Resume contains it: {in_jf}")
assert in_jf, "the item is not in Jellyfin's Resume list"

# --- 3. the app's endpoint ----------------------------------------------
cw = http_json(f"{app_base()}/api/library/continue-watching") or {}
titles = [i.get("title") for i in (cw.get("items") or [])]
print(f"app Continue Watching ({len(titles)}): {titles}")
assert any((t or "").lower().startswith(TITLE.lower()[:6]) for t in titles), \
    "the app's Continue Watching does not return it"

print(f"\nPASS: {TITLE!r} resumes at {SECONDS:.0f}s and appears in Continue Watching")
