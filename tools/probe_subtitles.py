#!/usr/bin/env python3
"""Reconnaissance for the subtitle/OpenSubtitles plan — READ ONLY.

Answers, against the LIVE stack:
  1. Which subtitle endpoints does this Jellyfin expose (from its own OpenAPI)?
  2. Is any OpenSubtitles provider installed/configured (/Plugins)?
  3. What are the user's subtitle preferences (/Users/{uid}/Configuration)?
  4. What subtitle streams does an item actually carry (PlaybackInfo MediaStreams)?
  5. Does remote (provider) subtitle SEARCH work today, and at what cost?
Usage: python3 tools/probe_subtitles.py ["<title>"]
"""
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rkm_common import Jellyfin  # noqa: E402

TITLE = sys.argv[1] if len(sys.argv) > 1 else ""
jf = Jellyfin()
users = jf.get("/Users") or []
uid = next((u["Id"] for u in users if (u.get("Name") or "").lower() == "admin"), users[0]["Id"])

print("=== 1. subtitle endpoints in this Jellyfin's OpenAPI ===")
spec = jf.get("/api-docs/openapi.json") or {}
for path, ops in sorted((spec.get("paths") or {}).items()):
    if "subtit" in path.lower():
        print(f"   {'/'.join(sorted(k.upper() for k in ops if k in ('get','post','put','delete'))):16} {path}")

print("\n=== 2. installed plugins (is an OpenSubtitles provider present?) ===")
plugins = jf.get("/Plugins") or []
if not plugins:
    print("   (no plugins installed)")
for p in plugins:
    print(f"   {p.get('Name')!r:42} v{p.get('Version')} status={p.get('Status')} id={p.get('Id')}")

print("\n=== 3. user subtitle preferences ===")
cfg = jf.get(f"/Users/{uid}/Configuration") or {}
for k in sorted(cfg):
    if "subtitle" in k.lower() or "language" in k.lower():
        print(f"   {k} = {cfg[k]!r}")

print("\n=== 4. item subtitle streams (what the player already sees) ===")
it = None
if TITLE:
    hits = (jf.get(f"/Users/{uid}/Items?searchTerm={urllib.parse.quote(TITLE)}&Recursive=true"
                   f"&IncludeItemTypes=Movie,Episode&Fields=Path,MediaSources") or {}).get("Items") or []
    it = hits[0] if hits else None
if it is None:
    res = jf.get(f"/Users/{uid}/Items/Resume?Recursive=true&MediaTypes=Video&Limit=1")
    it = ((res or {}).get("Items") or [None])[0]
if it:
    print(f"   item: {it.get('Name')!r} ({it.get('Id')})")
    ms = (it.get("MediaSources") or [{}])[0]
    for s in (ms.get("MediaStreams") or []):
        if (s.get("Type") or "") == "Subtitle":
            print(f"      idx={s.get('Index')} {s.get('Language')} {s.get('DisplayTitle')!r} "
                  f"codec={s.get('Codec')} external={s.get('IsExternal')} "
                  f"path={(s.get('Path') or '')[-40:]}")
    print(f"      defaultSubtitleStreamIndex={ms.get('DefaultSubtitleStreamIndex')} "
          f"path={str(it.get('Path'))[-52:]}")

print("\n=== 5. remote (provider) subtitle search for that item ===")
if it:
    for lang in ("eng", "en"):
        try:
            rows = jf.get(f"/Items/{it['Id']}/RemoteSearch/Subtitles/{lang}")
            print(f"   RemoteSearch {lang}: {len(rows) if isinstance(rows, list) else rows}")
            for r in (rows or [])[:3]:
                print(f"      id={r.get('Id')!r} {r.get('Name')!r} provider={r.get('ProviderName')!r} "
                      f"lang={r.get('Language')!r} downloads={r.get('DownloadCount')} rating={r.get('CommunityRating')}")
            break
        except Exception as e:
            print(f"   RemoteSearch {lang}: FAILED -> {e}")
