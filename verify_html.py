#!/usr/bin/env python3
"""Verify dashboard.html integrity: cards, buttons, no unreplaced placeholders."""
import json, re

html = open("/workspace/media/watchlist/dashboard.html").read()
wl = json.load(open("/workspace/media/watchlist.json"))

print("== dashboard.html checks ==")
print("bytes:", len(html))
print("Download buttons (btn-add):", html.count("btn-add"))
print("Trailer buttons (btn-tube):", html.count("btn-tube"))
print("poster <img> tags:", html.count("<img"))
print("unreplaced __CONFIG__/__ENTRIES__:", html.count("__CONFIG__") + html.count("__ENTRIES__"))
print("settings panel present:", "settingsPanel" in html)
print("JS fetch to /api/v3/movie present:", "/api/v3/movie/lookup" in html)
print("JS fetch to /api/v3/series present:", "/api/v3/series/lookup" in html)
print("radarr root injected:", "D:\\\\RKM_MEDIA\\\\Movies" in html or "D:\\RKM_MEDIA\\Movies" in html)
print()
print("== watchlist.json ==")
print("pending:", len(wl["pending"]), "| rotation_index:", wl["rotation_index"], "| updated:", wl["updated"])
for p in wl["pending"]:
    print(f"  - {p['title']} ({p['year']}) | {p['category']} | {p['lang']} | IMDb {p['imdb']} | RT {p['rt']} | poster={'yes' if p.get('poster') else 'NO'} | trailer={'yes' if p.get('trailer') else 'no'}")