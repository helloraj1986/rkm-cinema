#!/usr/bin/env python3
"""Verify dashboard pieces: (1) Radarr/Sonarr CORS for file:// origin, (2) posters via IMDb og:image.
Updates watchlist.json posters + rebuilds dashboard if posters found."""
import json, os, re, subprocess, time, urllib.request

env = {}
for line in open("/workspace/media/.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()

RADARR = env.get("RADARR_URL", "http://192.168.65.254:7878").rstrip("/")
SONARR = env.get("SONARR_URL", "http://192.168.65.254:8989").rstrip("/")
RK = env.get("RADARR_API_KEY", "")
SK = env.get("SONARR_API_KEY", "")

def curl_headers(url, extra=None):
    cmd = ["curl", "-s", "-m", "15", "-D", "-", "-o", "/dev/null"]
    if extra:
        cmd += extra
    cmd += [url]
    return subprocess.run(cmd, capture_output=True, text=True).stdout

print("== CORS check (Origin: null = file://) ==")
for name, url, key in (
    ("Radarr lookup", RADARR + "/api/v3/movie/lookup?term=imdb:tt0245429", RK),
    ("Sonarr lookup", SONARR + "/api/v3/series/lookup?term=imdb:tt0903747", SK),
):
    h = curl_headers(url, ["-H", "Origin: null", "-H", f"X-Api-Key: {key}"])
    acao = [l for l in h.splitlines() if "access-control" in l.lower()]
    status = [l for l in h.splitlines() if l.startswith("HTTP/")]
    print(f"  {name}: {status[0] if status else '?'} | ACAO: {acao[0].split(': ',1)[1] if acao else 'MISSING (browser will block)'}")

print("\n== Poster fallback via IMDb og:image ==")
wl_path = "/workspace/media/watchlist.json"
wl = json.load(open(wl_path))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
changed = False
for e in wl.get("pending", []):
    if e.get("poster"):
        continue
    if not e.get("imdbId"):
        continue
    try:
        req = urllib.request.Request(f"https://www.imdb.com/title/{e['imdbId']}/", headers=UA)
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
        m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        if m:
            e["poster"] = m.group(1)
            changed = True
            print(f"  {e['title']}: poster OK ({e['poster'][:60]}...)")
        else:
            print(f"  {e['title']}: no og:image found")
    except Exception as ex:
        print(f"  {e['title']}: scrape failed ({ex})")
    time.sleep(1)

if changed:
    json.dump(wl, open(wl_path, "w"), indent=2)
    print("\nwatchlist.json updated with posters — rebuilding dashboard")
    subprocess.run(["python3", "/workspace/media/watchlist/build_dashboard.py"], capture_output=True, text=True)
    print("dashboard rebuilt")
else:
    print("\nno poster changes (placeholders will show)")