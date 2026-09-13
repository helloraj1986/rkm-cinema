#!/usr/bin/env python3
"""Verify, against the LIVE stack, that a reported position actually persists.

Runs the app's OWN provider code (``JellyfinLibraryProvider.set_playback_position``)
against the real Jellyfin with the real API key, then asserts:
  1. the position Jellyfin stores equals what was reported;
  2. the item shows up in Jellyfin's own Resume list;
  3. the app's /api/library/continue-watching returns it.

MUTATES the item's resume position — that is the thing under test.
Usage: python3 tools/verify_progress_reporting.py "<title>" <seconds> [item_id]
       (item_id is REQUIRED whenever the title matches more than one row — e.g. a
        library holding two copies of the same film.)
"""
import sys
import time
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rkm_common import Jellyfin, app_client, app_base  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from services.library.jellyfin import JellyfinLibraryProvider  # noqa: E402

TITLE = sys.argv[1] if len(sys.argv) > 1 else "3 Deewarein"
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 1651.0
ITEM_ID = sys.argv[3] if len(sys.argv) > 3 else ""
TICKS = int(SECONDS * 1e7)

jf = Jellyfin()
users = jf.get("/Users") or []
uid = next((u.get("Id") for u in users if (u.get("Name") or "").lower() == "admin"), None)
keys = (jf.get("/Auth/Keys") or {}).get("Items") or []
api_key = next((k.get("AccessToken") for k in keys if (k.get("AppName") or "") == "RKM Cinema"), None)
if not api_key:
    print("!! no 'RKM Cinema' API key found — refusing to guess"); sys.exit(2)

# Resolve the item — but NEVER write to a guess. A bare `searchTerm` ranks by
# Jellyfin's fuzzy score, so "Spider-Man" resolved to Spider-Man (2002) while the
# user had actually played "Spider-Man: Into the Spider-Verse" (2026-09-11: that
# mistake wrote a phantom resume position to an unrelated film). Print every
# candidate and, unless EXACTLY ONE matched, demand the item id explicitly.
hits = (jf.get(f"/Users/{uid}/Items?searchTerm={urllib.parse.quote(TITLE)}&Recursive=true"
               f"&IncludeItemTypes=Movie,Series,Episode&Fields=UserData,Path") or {}).get("Items") or []
if not hits:
    print(f"!! no item matches {TITLE!r}"); sys.exit(2)

print(f"matches for {TITLE!r} ({len(hits)}):")
for h in hits:
    ud = h.get("UserData") or {}
    print(f"   {h['Id']}  {str(h.get('Name'))[:46]:48} "
          f"{(ud.get('PlaybackPositionTicks') or 0) / 1e7:8.1f}s  {str(h.get('Path'))[-42:]}")

if ITEM_ID:
    ITEM_ROW = next((h for h in hits if h["Id"] == ITEM_ID), None)
    if ITEM_ROW is None:
        print(f"\n!! {ITEM_ID} is not among the matches — check the id"); sys.exit(2)
elif len(hits) == 1:
    ITEM_ROW = hits[0]
else:
    print("\n!! ambiguous — re-run with the id of the row you mean, e.g.\n"
          f"   python3 tools/verify_progress_reporting.py {TITLE!r} {SECONDS:.0f} <item_id>\n"
          "   Nothing was written.")
    sys.exit(2)
ITEM = ITEM_ROW["Id"]
print(f"\nitem      : {ITEM_ROW.get('Name')!r} ({ITEM})")
print(f"before    : {((ITEM_ROW.get('UserData') or {}).get('PlaybackPositionTicks') or 0) / 1e7:.1f}s")

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
# The app's route needs a SESSION once `RKM_AUTH_REQUIRED` is armed — a tool signs in first.
client = app_client()
cw = client.get("/api/library/continue-watching") or {}
assert client.signed_in, f"could not sign in to the app: {client.error}"
titles = [i.get("title") for i in (cw.get("items") or [])]
print(f"app Continue Watching ({len(titles)}): {titles}")
assert any((t or "").lower().startswith(TITLE.lower()[:6]) for t in titles), \
    "the app's Continue Watching does not return it"

print(f"\nPASS: {TITLE!r} resumes at {SECONDS:.0f}s and appears in Continue Watching")
