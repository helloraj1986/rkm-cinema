#!/usr/bin/env python3
"""Fill posters from Radarr/Sonarr lookup images (grounded, no extra keys).
Also verify the OPTIONS preflight for the dashboard's POST add flow (file:// origin)."""
import json, os, subprocess, time, urllib.request, urllib.parse

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

def lookup_poster(base, key, path):
    try:
        req = urllib.request.Request(base + path, headers={"X-Api-Key": key})
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.load(r)
        items = res if isinstance(res, list) else res.get("records", [])
        if not items:
            return ""
        it = items[0]
        for im in (it.get("images") or []):
            if im.get("coverType") == "poster" and im.get("remoteUrl"):
                return im["remoteUrl"]
        return it.get("remotePoster") or ""
    except Exception as e:
        return ""

wl_path = "/workspace/media/watchlist.json"
wl = json.load(open(wl_path))
changed = False
for e in wl.get("pending", []):
    if e.get("poster"):
        continue
    if e.get("isSeries"):
        term = f"imdb:{e.get('imdbId')}" if e.get("imdbId") else ""
        p = lookup_poster(SONARR, SK, "/api/v3/series/lookup?term=" + urllib.parse.quote(term)) if SK and term else ""
    else:
        term = f"imdb:{e.get('imdbId')}" if e.get("imdbId") else ""
        p = lookup_poster(RADARR, RK, "/api/v3/movie/lookup?term=" + urllib.parse.quote(term)) if RK and term else ""
    if p:
        e["poster"] = p
        changed = True
        print(f"  ✓ {e['title']}: {p[:70]}")
    else:
        print(f"  ✗ {e['title']}: no poster via lookup (placeholder)")
    time.sleep(0.3)

if changed:
    json.dump(wl, open(wl_path, "w"), indent=2)
    print("\nrebuilding dashboard…")
    r = subprocess.run(["python3", "/workspace/media/watchlist/build_dashboard.py"], capture_output=True, text=True)
    print((r.stdout or r.stderr).strip())

print("\n== POST preflight check (browser add flow from file://) ==")
for name, base, key, path in (
    ("Radarr movie add", RADARR, RK, "/api/v3/movie"),
    ("Sonarr series add", SONARR, SK, "/api/v3/series"),
):
    cmd = ["curl", "-s", "-m", "10", "-o", "/dev/null", "-D", "-", "-X", "OPTIONS",
           "-H", "Origin: null", "-H", "Access-Control-Request-Method: POST",
           "-H", "Access-Control-Request-Headers: content-type,x-api-key",
           "-H", f"X-Api-Key: {key}", base + path]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    status = out.splitlines()[0] if out.startswith("HTTP") else "?"
    acao = [l.split(": ", 1)[1].strip() for l in out.splitlines() if "access-control-allow-origin" in l.lower()]
    print(f"  {name}: {status} | ACAO: {acao[0] if acao else 'MISSING'}")