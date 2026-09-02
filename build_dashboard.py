#!/usr/bin/env python3
"""RKM Cinema — build pipeline v2.

watchlist.json  ->  dashboard-data.json (public, NO secrets)  +  index.html (shell)

Changes vs v1:
  - API keys/URLs are NO LONGER embedded in HTML. The browser talks to /api (FastAPI),
    which holds secrets server-side in .env. (Old v1 embedded RADARR_API_KEY etc.)
  - Presentation data is separated from code: app.js/app.css are static assets in the
    folder; only dashboard-data.json is regenerated per build (no JS rebuild needed).
  - Atomic writes (tmp + os.replace), 0-card publish guard, asset-existence guard.

Outputs (all under /workspace/projects/rkm-cinema/):
  dashboard-data.json   entries + meta for the SPA
  index.html            thin shell referencing ./app.css and ./app.js
  dashboard.html        identical copy (backward-compatible alias)

Usage:  python3 build_dashboard.py
"""
import json
import os
import re
import time
import urllib.parse

SRC = "/workspace/media/watchlist.json"
BASE = "/workspace/projects/rkm-cinema"
DATA_OUT = os.path.join(BASE, "dashboard-data.json")
HTML_OUT = os.path.join(BASE, "index.html")
ALIAS_OUT = os.path.join(BASE, "dashboard.html")

GENRE_HINTS = {  # category -> canonical genre labels (used when entry.genres absent)
    "Sci-Fi/Fantasy": ["Science Fiction", "Fantasy"],
    "Kids & Animation": ["Animation", "Family"],
    "Hindi/Indian Cinema": ["Drama", "Thriller"],
    "Classic/Essential": ["Classic"],
    "Documentary": ["Documentary"],
}


def load_watchlist():
    if not os.path.exists(SRC):
        return {"pending": [], "recommended": [], "rotation": [], "updated": ""}
    return json.load(open(SRC))


def normalize(e):
    """Map one watchlist entry -> rich SPA entry. Pure data, no secrets."""
    is_series = bool(e.get("isSeries"))
    title = e.get("title", "")
    year = e.get("year", "")
    cat = e.get("category", "")
    trailer_id = e.get("trailerId", "")
    trailer_title = e.get("trailerTitle", "")
    poster = e.get("poster", "")
    backdrop = e.get("backdrop", "")
    if trailer_id and not re.fullmatch(r"[A-Za-z0-9_-]{11}", str(trailer_id)):
        trailer_id = ""  # malformed ID never ships
    return {
        "imdbId": e.get("imdbId", ""),
        "tmdbId": e.get("tmdbId"),
        "tvdbId": e.get("tvdbId") or None,
        "title": title,
        "year": int(year) if str(year).isdigit() else year,
        "type": "tv" if is_series else "movie",
        "category": cat,
        "genres": e.get("genres") or GENRE_HINTS.get(cat, [cat] if cat else []),
        "lang": e.get("lang", ""),
        "cert": e.get("cert", ""),
        "rt": e.get("rt"),
        "imdb": e.get("imdb"),
        "tmdbScore": e.get("tmdbScore") or e.get("tmdb_rating"),
        "overview": e.get("overview") or e.get("snippet") or e.get("description") or "",
        "cast": e.get("cast", []) or [],
        "director": e.get("director", ""),
        "runtime": e.get("runtime"),
        "poster": poster,
        "backdrop": backdrop,
        "trailerId": trailer_id,
        "trailerTitle": trailer_title,
        "trailerUrl": (f"https://www.youtube.com/embed/{trailer_id}?autoplay=1&rel=0&color=white"
                       if trailer_id else
                       f"https://www.youtube.com/results?search_query="
                       f"{urllib.parse.quote(title + ' ' + str(year) + ' trailer')}"),
        "added": e.get("added", ""),
        "source": e.get("source", "watchlist"),
    }


def build():
    wl = load_watchlist()
    pending = wl.get("pending", [])
    recents = wl.get("recommended", [])
    entries = [normalize(e) for e in pending + recents]
    data = {
        "app": "RKM Cinema",
        "version": 2,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated": wl.get("updated", ""),
        "heroMode": wl.get("hero_mode", "auto"),
        "refreshCron": wl.get("refresh_cron", "0 18 * * *"),
        "rotation": wl.get("rotation", []),
        "entries": entries,
    }

    # ---- publish guard: never ship an empty/broken dataset ----
    if not entries:
        raise SystemExit("REFUSED to publish: 0 cards. Keeping last good dashboard-data.json.")

    # ---- asset guard: never ship a shell that references missing assets ----
    for asset in ("app.css", "app.js"):
        if not os.path.exists(os.path.join(BASE, asset)):
            raise SystemExit(f"REFUSED to publish: missing {asset}. Install it before building.")

    # ---- atomic publishes ----
    def atomic(path, text):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, path)

    atomic(DATA_OUT, json.dumps(data, indent=1))
    shell = INDEX_SHELL
    atomic(HTML_OUT, shell)
    atomic(ALIAS_OUT, shell)

    t = data["updated"]
    print(f"published dashboard-data.json ({len(json.dumps(data))} bytes, {len(entries)} entries)"
          f" + index.html/dashboard.html | updated={t} | heroes={data['heroMode']} |"
          f" trailerIds={sum(1 for e in entries if e['trailerId'])}")
    return len(entries)


INDEX_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#08090c">
<title>RKM Cinema — Your Personal Cinema</title>
<meta name="description" content="Your private streaming discovery dashboard. What should you watch next?">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="./app.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%2308090c'/><path d='M30 28v44l34-22z' fill='%23e8b86d'/></svg>">
</head>
<body>
<div id="app"></div>
<script src="./app.js" defer></script>
</body>
</html>
"""


if __name__ == "__main__":
    build()