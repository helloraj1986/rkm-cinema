#!/usr/bin/env python3
"""Backfill TMDB artwork (poster + backdrop) for every watchlist entry.

The watchlist entries were created with stale/fabricated poster URLs that 404.
This re-fetches the authoritative poster/backdrop from TMDB by each entry's
tmdbId (movie or tv), updates watchlist.json, and rebuilds the dashboard.

Usage: python3 scripts/backfill_tmdb_artwork.py [--dry-run]
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, "/workspace/projects/rkm-cinema")

from config.settings import get_config

WL_PATH = "/workspace/media/watchlist.json"
IMAGE_BASE = "https://image.tmdb.org/t/p"


def tmdb_get(typ: str, tmdb_id: int, api_key: str) -> dict:
    url = f"https://api.themoviedb.org/3/{typ}/{tmdb_id}?api_key={api_key}"
    req = urllib.request.Request(url, headers={"User-Agent": "RKM-Cinema/3.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main():
    dry = "--dry-run" in sys.argv
    cfg = get_config()
    key = cfg.TMDB_API_KEY
    if not key:
        print("No TMDB_API_KEY configured — aborting.")
        return 1

    with open(WL_PATH) as f:
        data = json.load(f)

    changed = {"pending": 0, "recommended": 0}
    sections = ("pending", "recommended")

    for sec in sections:
        for e in data.get(sec, []):
            tmid = e.get("tmdbId")
            if not tmid:
                print(f"  SKIP {e.get('title')}: no tmdbId")
                continue
            is_series = bool(e.get("isSeries"))
            typ = "tv" if is_series else "movie"
            try:
                d = tmdb_get(typ, tmid, key)
            except Exception as ex:
                print(f"  {e.get('title')}: TMDB error {ex}")
                continue

            pp, bp = d.get("poster_path"), d.get("backdrop_path")
            poster = f"{IMAGE_BASE}/w500{pp}" if pp else ""
            backdrop = f"{IMAGE_BASE}/w1280{bp}" if bp else ""

            if poster and e.get("poster") != poster:
                e["poster"] = poster
                changed[sec] += 1
            if backdrop and e.get("backdrop") != backdrop:
                e["backdrop"] = backdrop
            # Also backfill a few useful metadata fields from TMDB when missing
            if not e.get("genres"):
                e["genres"] = [g["name"] for g in d.get("genres", [])]
            if not e.get("tmdb_score") or e.get("tmdb_score", 0) == 0:
                e["tmdb_score"] = float(d.get("vote_average") or 0)
            if e.get("snippet") and not e.get("tmdb_overview"):
                e["tmdb_overview"] = d.get("overview") or ""
            print(f"  {e.get('title')}: poster={'updated' if poster else 'NONE'} (tmdb {tmid})")

    print(f"\nTotal poster updates: pending={changed['pending']}, recommended={changed['recommended']}")

    if dry:
        print("DRY-RUN — not writing.")
        return 0

    with open(WL_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {WL_PATH}")

    # Rebuild dashboard
    from scripts.rebuild_dashboard import build
    build()
    print("Rebuilt dashboard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
