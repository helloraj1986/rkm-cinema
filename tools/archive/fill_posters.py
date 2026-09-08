#!/usr/bin/env python3
"""Fill posters via iTunes Search API (no key needed). artworkUrl100 -> 600x600.
Updates watchlist.json posters, rebuilds dashboard."""
import json, os, re, subprocess, time, urllib.request, urllib.parse

def itunes_poster(title, year, media="movie"):
    q = urllib.parse.quote(f"{title} {year}")
    url = f"https://itunes.apple.com/search?term={q}&media={media}&entity={media}&limit=5"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            d = json.load(r)
        for res in d.get("results", []):
            name = (res.get("trackName") or res.get("collectionName") or "").lower()
            rel = (res.get("releaseDate") or "")[:4]
            if title.lower()[:8] in name and (not year or rel == str(year) or not rel):
                art = res.get("artworkUrl100", "")
                if art:
                    return art.replace("100x100", "600x600")
    except Exception:
        pass
    return ""

wl_path = "/workspace/media/watchlist.json"
wl = json.load(open(wl_path))
changed = False
for e in wl.get("pending", []):
    if e.get("poster"):
        continue
    kind = "tvShow" if e.get("isSeries") else "movie"
    p = itunes_poster(e.get("title", ""), e.get("year", ""), kind)
    if p:
        e["poster"] = p
        changed = True
        print(f"  ✓ {e['title']}: {p[:70]}")
    else:
        print(f"  ✗ {e['title']}: no iTunes artwork (placeholder stays)")
    time.sleep(0.5)

if changed:
    json.dump(wl, open(wl_path, "w"), indent=2)
    print("\nrebuilding dashboard…")
    r = subprocess.run(["python3", "/workspace/media/watchlist/build_dashboard.py"], capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
else:
    print("\nno posters updated")