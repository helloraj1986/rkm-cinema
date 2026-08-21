#!/usr/bin/env python3
"""Verify actual watchlist.json state + validate trailer IDs via YouTube oEmbed (keyless)."""
import json, time, urllib.request

# 1. actual disk state
raw = open("/workspace/media/watchlist.json").read()
print("bytes:", len(raw))
try:
    wl = json.loads(raw)
    print("keys:", list(wl.keys()))
    pend = wl.get("pending", [])
    print("pending len:", len(pend))
    for i, p in enumerate(pend):
        print(f"  [{i}] {p.get('title')} | {p.get('year')} | trailerId={p.get('trailerId', 'NONE')} | imdb={p.get('imdbId')}")
except Exception as e:
    print("JSON INVALID:", e)

# 2. validate candidate trailer IDs via oEmbed (returns 200 + title if valid video)
print("\n== trailer ID validation (YouTube oEmbed) ==")
CANDIDATES = {
    "Spirited Away": "5R6FVcO45F00",
    "Arrival": "3WzW4kk6pBM",
    "Andhadhun": "Jm9NwiA9bDg",
    "The Grand Budapest Hotel": "Gp_-6k2YcWA",
    "Mad Max: Fury Road": "0A2nUNmcyRI",
}
for name, vid in CANDIDATES.items():
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
        with urllib.request.urlopen(url, timeout=12) as r:
            d = json.load(r)
        print(f"  ✓ {vid} | {name} -> oembed title: {d.get('title','?')[:50]}")
    except Exception as e:
        print(f"  ✗ {vid} | {name} -> {e.__class__.__name__}")
    time.sleep(0.4)