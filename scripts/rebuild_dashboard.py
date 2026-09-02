#!/usr/bin/env python3
"""Rebuild dashboard - generate dashboard-data.json + index.html from watchlist.json."""
import json
import os
import re
import time
import urllib.parse
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, "/workspace/projects/rkm-cinema")

from config.settings import get_config
from services import WatchlistService, WatchlistEntry


GENRE_HINTS = {
    "Sci-Fi/Fantasy": ["Science Fiction", "Fantasy"],
    "Kids & Animation": ["Animation", "Family"],
    "Hindi/Indian Cinema": ["Drama", "Thriller"],
    "Classic/Essential": ["Classic"],
    "Documentary": ["Documentary"],
}


def normalize_entry(entry: WatchlistEntry) -> dict:
    """Map one watchlist entry -> rich SPA entry. Pure data, no secrets."""
    is_series = entry.isSeries
    title = entry.title
    year = entry.year
    cat = entry.category
    trailer_id = entry.trailerId or ""
    trailer_title = entry.trailerTitle or ""
    poster = entry.poster or ""
    backdrop = entry.backdrop or ""

    # Validate trailer ID format
    if trailer_id and not re.fullmatch(r"[A-Za-z0-9_-]{11}", str(trailer_id)):
        trailer_id = ""

    # Genres: use entry.genres, fallback to category hints if empty
    genres = entry.genres if entry.genres else GENRE_HINTS.get(cat, [cat] if cat else [])

    # Overview: prefer tmdb_overview, then snippet, then fallback
    overview = entry.tmdb_overview or entry.snippet or f"{title} ({year}) - {entry.category}"

    # tmdbScore: use entry.tmdb_score, fallback to imdb
    tmdb_score = entry.tmdb_score if entry.tmdb_score > 0 else (float(entry.imdb) if entry.imdb else 0.0)

    # tvdbId: not in WatchlistEntry
    tvdb_id = None

    # source: use entry.source
    source = entry.source

    return {
        "imdbId": entry.imdbId,
        "tmdbId": entry.tmdbId,
        "tvdbId": tvdb_id,
        "title": title,
        "year": int(year) if str(year).isdigit() else year,
        "type": "tv" if is_series else "movie",
        "category": cat,
        "genres": genres,
        "lang": entry.lang,
        "cert": entry.cert,
        "rt": entry.rt,
        "imdb": entry.imdb,
        "tmdbScore": tmdb_score,
        "overview": overview,
        "cast": entry.cast or [],
        "director": entry.director,
        "runtime": entry.runtime,
        "poster": poster,
        "backdrop": backdrop,
        "trailerId": trailer_id,
        "trailerTitle": trailer_title,
        "trailerUrl": (f"https://www.youtube.com/embed/{trailer_id}?autoplay=1&rel=0&color=white"
                       if trailer_id else
                       f"https://www.youtube.com/results?search_query="
                       f"{urllib.parse.quote(title + ' ' + str(year) + ' trailer')}"),
        "added": entry.added,
        "source": source,
        # Status fields (populated by API at runtime)
        "state": entry.state,
        "detail": entry.detail,
        "progress": entry.progress,
    }


def build():
    """Build dashboard data and HTML shell."""
    wl = WatchlistService()
    data = wl.load()

    pending = data.pending
    recents = data.recommended
    entries = [normalize_entry(e) for e in pending + recents]

    output = {
        "app": "RKM Cinema",
        "version": 2,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated": data.updated,
        "heroMode": data.hero_mode,
        "refreshCron": data.refresh_cron if hasattr(data, 'refresh_cron') else "0 18 * * *",
        "rotation": data.rotation,
        "entries": entries,
    }

    # Publish guard: never ship an empty/broken dataset
    if not entries:
        raise SystemExit("REFUSED to publish: 0 cards. Keeping last good dashboard-data.json.")

    # Asset guard: never ship a shell that references missing assets
    BASE = Path("/workspace/projects/rkm-cinema")
    for asset in ("app.css", "app.js"):
        if not (BASE / asset).exists():
            raise SystemExit(f"REFUSED to publish: missing {asset}. Install it before building.")

    # Atomic publishes
    def atomic_write(path: Path, text: str):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text)
        tmp.replace(path)

    DATA_OUT = BASE / "dashboard-data.json"
    HTML_OUT = BASE / "index.html"
    ALIAS_OUT = BASE / "dashboard.html"

    atomic_write(DATA_OUT, json.dumps(output, indent=1))
    shell = INDEX_SHELL
    atomic_write(HTML_OUT, shell)
    atomic_write(ALIAS_OUT, shell)

    t = data.updated
    print(f"published dashboard-data.json ({len(json.dumps(output))} bytes, {len(entries)} entries)"
          f" + index.html/dashboard.html | updated={t} | heroes={output['heroMode']} |"
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
<script src="./api.js" defer></script>
<script src="./app.js" defer></script>
</body>
</html>
"""


if __name__ == "__main__":
    build()