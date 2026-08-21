#!/usr/bin/env python3
"""TVDB v4 / TMDB enrichment for the RKM Watchlist.

STAGED + UNTESTED as of 2026-08-17 (endpoint shapes not yet live-verified from the sandbox).
Behavior:
  - No TVDB_API_KEY in /workspace/media/.env -> prints guidance and exits 0 (dormant).
  - --probe mode: test login + search + extended endpoints against live API, print shapes.
  - Normal mode: for each pending entry missing trailerId/trailerTitle, search TVDB by
    title+year, match remoteids[] to the entry's imdbId, fetch extended, extract the
    official YouTube trailer URL -> trailerId. Fallback to TMDB /movie/{tmdbId}/videos.
  - Never writes an unverified trailerId: only YouTube URLs are accepted.
  - Updates watchlist.json atomically (tmp + os.replace) and rebuilds the dashboard.
"""
import json, os, re, subprocess, sys, time, urllib.request, urllib.parse

WL = "/workspace/media/watchlist.json"
ENV = "/workspace/media/.env"
TOKEN_CACHE = "/workspace/media/.tvdb_token"
BASE = "/workspace/media/watchlist"

def load_env():
    env = {}
    for line in open(ENV):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env

env = load_env()
TVDB = env.get("TVDB_API_KEY", "")
TMDB = env.get("TMDB_API_KEY", "")

def http_json(url, headers=None, method="GET", body=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def tvdb_token():
    """Return a valid TVDB JWT, re-logging-in if needed."""
    # cached token?
    try:
        c = json.load(open(TOKEN_CACHE))
        if c.get("expires", 0) > time.time():
            return c["token"]
    except Exception:
        pass
    d = http_json("https://api4.thetvdb.com/v4/login", body={"apikey": TVDB},
                  headers={"Content-Type": "application/json"}, method="POST")
    token = d["data"]["token"]
    json.dump({"token": token, "expires": time.time() + 25 * 86400}, open(TOKEN_CACHE, "w"))
    return token

def yt_id_from_url(url):
    m = re.search(r"(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)([\w-]{11})", url or "")
    return m.group(1) if m else ""

def tvdb_trailer(tvdb_id, is_series):
    """Fetch extended record; return (trailerId, trailerTitle) from the first YouTube trailer."""
    kind = "series" if is_series else "movies"
    h = {"Authorization": f"Bearer {tvdb_token()}", "Accept": "application/json"}
    d = http_json(f"https://api4.thetvdb.com/v4/{kind}/{tvdb_id}/extended", headers=h)
    trailers = (d.get("data") or {}).get("trailers") or []
    for t in trailers:
        yt = yt_id_from_url(t.get("url", ""))
        if yt:
            return yt, t.get("name") or "Official Trailer"
    return "", ""

def tmdb_trailer(tmdb_id, is_series):
    if not TMDB:
        return "", ""
    try:
        kind = "tv" if is_series else "movie"
        url = f"https://api.themoviedb.org/3/{kind}/{tmdb_id}/videos?api_key={TMDB}"
        d = http_json(url)
        for v in d.get("results", []):
            if v.get("site") == "YouTube" and v.get("type") == "Trailer":
                return v["key"], v.get("name") or "Official Trailer"
    except Exception:
        pass
    return "", ""

def probe():
    print(f"TVDB key present: {bool(TVDB)} | TMDB key present: {bool(TMDB)}")
    if not TVDB:
        print("No TVDB_API_KEY in .env — nothing to probe. Add it and re-run.")
        return
    tok = tvdb_token()
    print("login OK, token len:", len(tok))
    # search a known title
    d = http_json("https://api4.thetvdb.com/v4/search?query=Prisoners&type=movie&year=2013",
                  headers={"Authorization": f"Bearer {tok}"})
    res = d.get("data") or []
    print("search results:", len(res))
    if res:
        r = res[0]
        print("first result keys:", sorted(r.keys()))
        print("remoteids:", r.get("remoteids"))
        print("tvdb id:", r.get("id"))
        ext = http_json(f"https://api4.thetvdb.com/v4/movies/{r['id']}/extended",
                        headers={"Authorization": f"Bearer {tok}"})
        dd = ext.get("data") or {}
        print("extended keys:", sorted(dd.keys()))
        print("trailers:", json.dumps((dd.get("trailers") or [])[:2], indent=1)[:400])
        print("artworks count:", len(dd.get("artworks") or []))
    print("PROBE OK — endpoint shapes printed above. If this fails, adjust tvdb_enrich.py before trusting enrichment.")

def enrich():
    if not TVDB and not TMDB:
        print("Neither TVDB_API_KEY nor TMDB_API_KEY in /workspace/media/.env.")
        print("Paste your key there (e.g. TVDB_API_KEY=xxxx) then run this again.")
        print("Placeholder lines are already staged at the bottom of .env.")
        return
    wl = json.load(open(WL))
    pend = wl.get("pending", [])
    changed = 0
    for e in pend:
        if e.get("trailerId"):
            continue  # carry forward — never clobber a good ID
        tid, ttitle = "", ""
        try:
            if TVDB:
                q = urllib.parse.quote(f"{e.get('title','')}")
                y = e.get("year", "")
                kind = "series" if e.get("isSeries") else "movie"
                d = http_json(f"https://api4.thetvdb.com/v4/search?query={q}&type={kind}&year={y}",
                              headers={"Authorization": f"Bearer {tvdb_token()}"})
                match = None
                for r in d.get("data") or []:
                    ids = [str(x.get("id", "")) for x in r.get("remoteids") or []]
                    if e.get("imdbId") in ids:
                        match = r; break
                if match:
                    tid, ttitle = tvdb_trailer(match["id"], e.get("isSeries"))
            if not tid:
                tid, ttitle = tmdb_trailer(e.get("tmdbId"), e.get("isSeries"))
        except Exception as ex:
            print(f"  {e.get('title')}: enrichment error -> {ex}")
        if tid:
            e["trailerId"] = tid
            e["trailerTitle"] = ttitle or "Official Trailer"
            changed += 1
            print(f"  ✓ {e.get('title')} -> {tid} ({ttitle})")
        else:
            print(f"  - {e.get('title')}: no verified trailer found (kept search-link fallback)")
        time.sleep(0.3)
    if changed:
        wl["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        tmp = WL + ".tmp"
        json.dump(wl, open(tmp, "w"), indent=2)
        os.replace(tmp, WL)
        print(f"watchlist.json updated ({changed} entries enriched) — rebuilding dashboard")
        subprocess.run(["python3", os.path.join(BASE, "build_dashboard.py")], cwd=BASE, timeout=120)
    else:
        print("No changes — watchlist.json untouched.")

if __name__ == "__main__":
    if "--probe" in sys.argv:
        probe()
    else:
        enrich()