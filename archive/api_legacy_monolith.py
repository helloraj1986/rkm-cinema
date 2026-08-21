#!/usr/bin/env python3
"""RKM Cinema API — secure backend for the watchlist dashboard.

Serves the browser as a single trusted endpoint; API keys for Radarr, Sonarr,
TMDB, TVDB, Plex and Jellyfin live ONLY in /workspace/media/.env (or /app/.env
inside the container) and are never exposed to the client.

Endpoints
  GET  /api/health    -> service availability + dashboard freshness
  GET  /api/config    -> public-safe config (updated time, hero mode, ...)
  GET  /api/status    -> per-title Radarr/Sonarr state (not_added / requested /
                         downloading / downloaded / unavailable)
  POST /api/download  -> {imdbId (or tmdbId), type} -> Radarr (movie) or Sonarr (tv)
  GET  /api/search?q= -> watchlist matches + live TMDB search when a key exists
  GET  /api/library   -> Plex (fallback Jellyfin) library counts + recently added

Runs with: uvicorn api:app --host 0.0.0.0 --port 8000
"""
import json
import os
import time
import urllib.parse
import urllib.request
import logging

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------- environment
def load_env():
    env = {}
    # 1. .env file (local/dev) - always read this first for all vars
    for path in ("/app/.env", "/workspace/media/.env"):
        try:
            for line in open(path):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
            if env:
                break
        except OSError:
            continue
    # 2. real environment (set by docker-compose env_file / -e) - overrides .env
    for k in ("RADARR_URL", "SONARR_URL", "RADARR_API_KEY", "SONARR_API_KEY",
              "TMDB_API_KEY", "TVDB_API_KEY", "PLEX_URL", "PLEX_TOKEN",
              "JELLYFIN_URL", "JELLYFIN_API_KEY", "PROWLARR_URL",
              "EMBY_URL", "EMBY_API_KEY",
              "QBITTORRENT_URL",
              "BROWSER_RADARR_URL", "BROWSER_SONARR_URL", "MEDIA_HOST",
              "RADARR_QUALITY_PROFILE_ID", "SONARR_QUALITY_PROFILE_ID"):
        v = os.environ.get(k)
        if v:
            env[k] = v
    return env

ENV = load_env()
WL_PATH = "/app/watchlist.json" if os.path.exists("/app/watchlist.json") else "/workspace/media/watchlist.json"

RADARR_BASE = (ENV.get("RADARR_URL") or "http://192.168.65.254:7878").rstrip("/")
SONARR_BASE = (ENV.get("SONARR_URL") or "http://192.168.65.254:8989").rstrip("/")
RADARR_KEY = ENV.get("RADARR_API_KEY", "")
SONARR_KEY = ENV.get("SONARR_API_KEY", "")
TMDB_KEY = ENV.get("TMDB_API_KEY", "")
PLEX_URL = (ENV.get("PLEX_URL") or "").rstrip("/")
PLEX_TOKEN = ENV.get("PLEX_TOKEN", "")
EMBY_URL = (ENV.get("EMBY_URL") or "").rstrip("/")
EMBY_API_KEY = ENV.get("EMBY_API_KEY", "")
_PLEX_SERVER_ID = ""   # cached machineIdentifier for Plex deep links
_EMBY_SERVER_ID = ""   # cached Emby serverId (System/Info Id) for deep links
JELLYFIN_URL = (ENV.get("JELLYFIN_URL") or "").rstrip("/")
JELLYFIN_KEY = ENV.get("JELLYFIN_API_KEY", "")
PROWLARR_URL = (ENV.get("PROWLARR_URL") or "").rstrip("/")
QBIT_BASE = (ENV.get("QBITTORRENT_URL") or "http://192.168.65.254:1701").rstrip("/")

_http_cache = {}          # url -> (expiry, payload)
_CACHE_TTL = 45           # seconds for /api/v3 lists
logger = logging.getLogger("rkm.api")


def http_json(url, headers=None, timeout=12, cache=False):
    """GET + decode + optional short TTL cache. Raises on non-200."""
    if cache:
        now = time.time()
        hit = _http_cache.get(url)
        if hit and hit[0] > now:
            return hit[1]
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    if cache:
        _http_cache[url] = (time.time() + _CACHE_TTL, data)
    return data


def safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def arr_headers(key):
    return {"X-Api-Key": key, "Accept": "application/json"}


def load_watchlist():
    try:
        return json.load(open(WL_PATH))
    except Exception:
        return {"pending": [], "recommended": [], "updated": ""}


app = FastAPI(title="RKM Cinema API", version="2.0", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class DownloadReq(BaseModel):
    imdbId: str = ""
    tmdbId: int | None = None
    type: str = ""          # "movie" | "tv" | "" (infer from watchlist)
    title: str = ""         # optional, for Radarr title-search fallback
    year: int | None = None # optional, for fallback disambiguation


def entry_by_imdb(imdb_id):
    wl = load_watchlist()
    for e in wl.get("pending", []) + wl.get("recommended", []):
        if e.get("imdbId") == imdb_id:
            return e
    return None


def is_series_for(imdb_id):
    wl = load_watchlist()
    for e in wl.get("pending", []) + wl.get("recommended", []):
        if e.get("imdbId") == imdb_id:
            return bool(e.get("isSeries"))
    return None


# ------------------------------------------------------------------ radarr
def radarr_health():
    if not RADARR_KEY:
        return False
    try:
        http_json(RADARR_BASE + "/api/v3/system/status", headers=arr_headers(RADARR_KEY), timeout=6)
        return True
    except Exception:
        return False


def radarr_movies():
    if not RADARR_KEY:
        return []
    return safe(lambda: http_json(RADARR_BASE + "/api/v3/movie", headers=arr_headers(RADARR_KEY), cache=True), [])


def radarr_queue():
    if not RADARR_KEY:
        return []
    try:
        d = http_json(RADARR_BASE + "/api/v3/queue?page=1&pageSize=200",
                      headers=arr_headers(RADARR_KEY), cache=True)
        return d.get("records", []) if isinstance(d, dict) else d
    except Exception:
        return []


# ------------------------------------------------------------------ qbittorrent
_qbit_cache = None          # (expiry, [torrents])
_QBIT_TTL = 10              # seconds — progress moves fast


def qbit_torrents():
    """All qBittorrent torrents (no auth on this setup). Returns [] on failure."""
    global _qbit_cache
    now = time.time()
    if _qbit_cache and _qbit_cache[0] > now:
        return _qbit_cache[1]
    try:
        req = urllib.request.Request(QBIT_BASE + "/api/v2/torrents/info",
                                     headers={"User-Agent": "RKM-Cinema-API/2.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            ts = json.load(r)
        _qbit_cache = (now + _QBIT_TTL, ts)
        return ts
    except Exception:
        return []


def qbit_match(title, year=""):
    """Find a qBittorrent torrent whose name plausibly matches a title (title token
    overlap, ignoring year/quality/group noise). Returns torrent dict or None."""
    import re as _re
    _STOP = {"the", "and", "for", "not", "but", "are", "all", "any", "was", "you",
             "your", "his", "her", "with", "from", "that", "this", "have", "has"}
    key = _re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    words = {w for w in key.split() if len(w) > 3 and w not in _STOP}
    if not words:
        return None
    best, best_score = None, 0
    for t in qbit_torrents():
        name = _re.sub(r"[^a-z0-9]+", " ", (t.get("name") or "").lower())
        nwords = set(name.split())
        score = len(words & nwords)
        if score > best_score:
            best_score, best = score, t
    # at least half the significant title words must overlap (>=1 word)
    if best and best_score >= 1 and best_score / len(words) >= 0.5:
        return best
    return None


def radarr_pick_first(imdb_id, tmdb_id=None):
    by_tmdb = {str(m.get("tmdbId")): m for m in radarr_movies()}
    if tmdb_id:
        m = by_tmdb.get(str(tmdb_id))
        if m:
            return m
    return None


def radarr_lookup_title(title, year=None):
    """Search Radarr by title/year. Returns list of candidate dicts."""
    if not title:
        return []
    term = str(title).strip()
    if year:
        term = term + f" {year}"
    try:
        return http_json(RADARR_BASE + "/api/v3/movie/lookup?term=" + urllib.parse.quote(term),
                         headers=arr_headers(RADARR_KEY), timeout=20) or []
    except Exception:
        return []


def radarr_add(imdb_id, title="", year=None):
    """Lookup by imdbId (with title/year fallback) in Radarr, then add.
    Returns (ok, state, message)."""
    res = http_json(RADARR_BASE + "/api/v3/movie/lookup?term=imdb:" + imdb_id,
                    headers=arr_headers(RADARR_KEY), timeout=20)
    m = (res or [{}])[0] if isinstance(res, list) else None
    candidates = []
    if not m or not m.get("tmdbId"):
        # IMDb lookup failed -> try title/year search (stale/ambiguous ID)
        candidates = radarr_lookup_title(title, year)
        if len(candidates) == 1:
            m = candidates[0]
        elif len(candidates) > 1:
            exact = next((c for c in candidates if year and c.get("year") == year), None)
            m = exact or candidates[0]
    if not m or not m.get("tmdbId"):
        msg = f"No Radarr match for imdb:{imdb_id}"
        if candidates:
            msg = ("Multiple Radarr matches — pick one: " +
                   "; ".join(f"{c.get('title')} ({c.get('year')}, tmdb:{c.get('tmdbId')})"
                             for c in candidates[:10]))
        return False, "unavailable", msg
    existing = radarr_pick_first(imdb_id, m.get("tmdbId"))
    if existing:
        return True, "requested", f"{existing.get('title')} is already in Radarr"
    profiles = http_json(RADARR_BASE + "/api/v3/qualityprofile", headers=arr_headers(RADARR_KEY), timeout=10)
    roots = http_json(RADARR_BASE + "/api/v3/rootfolder", headers=arr_headers(RADARR_KEY), timeout=10)
    # Allow override via RADARR_QUALITY_PROFILE_ID env var; fallback to first profile
    qp_override = ENV.get("RADARR_QUALITY_PROFILE_ID")
    if qp_override and str(qp_override).isdigit():
        qp = int(qp_override)
    else:
        qp = (profiles or [{}])[0].get("id", 1)
    root = (roots or [{}])[0].get("path", "")
    if not root:
        return False, "unavailable", "Radarr has no root folder configured"
    body = {"tmdbId": m["tmdbId"], "title": m.get("title", ""), "qualityProfileId": qp,
            "rootFolderPath": root, "monitored": True,
            "addOptions": {"searchForMovie": True}}
    req = urllib.request.Request(RADARR_BASE + "/api/v3/movie", data=json.dumps(body).encode(),
                                 headers={**arr_headers(RADARR_KEY), "Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=25) as r:
        created = json.load(r)
    return True, "requested", f"{created.get('title', 'Title')} added to Radarr — download starting"


# ------------------------------------------------------------------ sonarr
def sonarr_health():
    if not SONARR_KEY:
        return False
    try:
        http_json(SONARR_BASE + "/api/v3/system/status", headers=arr_headers(SONARR_KEY), timeout=6)
        return True
    except Exception:
        return False


def sonarr_series():
    if not SONARR_KEY:
        return []
    return safe(lambda: http_json(SONARR_BASE + "/api/v3/series", headers=arr_headers(SONARR_KEY), cache=True), [])


def sonarr_queue():
    if not SONARR_KEY:
        return []
    try:
        d = http_json(SONARR_BASE + "/api/v3/queue?page=1&pageSize=200",
                      headers=arr_headers(SONARR_KEY), cache=True)
        return d.get("records", []) if isinstance(d, dict) else d
    except Exception:
        return []


_sonarr_tvdb_cache = {}   # imdbId -> tvdbId


def sonarr_resolve(imdb_id):
    """Resolve imdbId -> tvdbId via Sonarr lookup (cached)."""
    if imdb_id in _sonarr_tvdb_cache:
        return _sonarr_tvdb_cache[imdb_id]
    try:
        res = http_json(SONARR_BASE + "/api/v3/series/lookup?term=imdb:" + imdb_id,
                        headers=arr_headers(SONARR_KEY), timeout=20)
        s = (res or [{}])[0] if isinstance(res, list) else None
        tvdb = s.get("tvdbId") if s else None
        if tvdb:
            _sonarr_tvdb_cache[imdb_id] = tvdb
        return tvdb
    except Exception:
        return None


def sonarr_lookup_title(title, year=None):
    """Search Sonarr by title/year. Returns list of candidate dicts."""
    if not title:
        return []
    term = str(title).strip()
    if year:
        term = term + f" {year}"
    try:
        return http_json(SONARR_BASE + "/api/v3/series/lookup?term=" + urllib.parse.quote(term),
                         headers=arr_headers(SONARR_KEY), timeout=20) or []
    except Exception:
        return []


def sonarr_add(imdb_id, title="", year=None):
    """Lookup by imdbId (with title/year fallback) in Sonarr, then add.
    Returns (ok, state, message)."""
    res = http_json(SONARR_BASE + "/api/v3/series/lookup?term=imdb:" + imdb_id,
                    headers=arr_headers(SONARR_KEY), timeout=20)
    s = (res or [{}])[0] if isinstance(res, list) else None
    candidates = []
    if not s or not s.get("tvdbId"):
        # IMDb lookup failed -> try title/year search (stale/ambiguous ID)
        candidates = sonarr_lookup_title(title, year)
        if len(candidates) == 1:
            s = candidates[0]
        elif len(candidates) > 1:
            exact = next((c for c in candidates if year and c.get("year") == year), None)
            if exact is None and title:
                lt = str(title).strip().lower()
                exact = next((c for c in candidates if str(c.get("title") or "").strip().lower() == lt), None)
            s = exact or (candidates[0] if candidates else None)
    if not s or not s.get("tvdbId"):
        msg = f"No Sonarr match for imdb:{imdb_id}"
        if candidates:
            msg = ("Multiple Sonarr matches — pick one: " +
                   "; ".join(f"{c.get('title')} ({c.get('year')}, tvdb:{c.get('tvdbId')})"
                             for c in candidates[:10]))
        return False, "unavailable", msg
    tvdb = s["tvdbId"]
    existing = [x for x in sonarr_series() if x.get("tvdbId") == tvdb]
    if existing:
        return True, "requested", f"{existing[0].get('title')} is already in Sonarr"
    profiles = http_json(SONARR_BASE + "/api/v3/qualityprofile", headers=arr_headers(SONARR_KEY), timeout=10)
    roots = http_json(SONARR_BASE + "/api/v3/rootfolder", headers=arr_headers(SONARR_KEY), timeout=10)
    langs = http_json(SONARR_BASE + "/api/v3/languageprofile", headers=arr_headers(SONARR_KEY), timeout=10)
    # Allow override via SONARR_QUALITY_PROFILE_ID env var; fallback to first profile
    qp_override = ENV.get("SONARR_QUALITY_PROFILE_ID")
    if qp_override and str(qp_override).isdigit():
        qp = int(qp_override)
    else:
        qp = (profiles or [{}])[0].get("id", 1)
    lang = (langs or [{}])[0].get("id", 1)
    root = (roots or [{}])[0].get("path", "")
    if not root:
        return False, "unavailable", "Sonarr has no root folder configured"
    body = {"tvdbId": tvdb, "title": s.get("title", ""), "qualityProfileId": qp,
            "languageProfileId": lang, "rootFolderPath": root, "monitored": True,
            "addOptions": {"searchForMissingEpisodes": True}}
    req = urllib.request.Request(SONARR_BASE + "/api/v3/series", data=json.dumps(body).encode(),
                                 headers={**arr_headers(SONARR_KEY), "Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=25) as r:
        created = json.load(r)
    return True, "requested", f"{created.get('title', 'Series')} added to Sonarr — downloads starting"


# ------------------------------------------------------------------ status
_INDEXER_MSG = None         # (expiry, message-or-None) — Radarr indexer outage


def radarr_indexer_issue():
    """Radarr /api/v3/health: does it currently complain search indexers are down?"""
    global _INDEXER_MSG
    if not RADARR_KEY:
        return None
    now = time.time()
    if _INDEXER_MSG and _INDEXER_MSG[0] > now:
        return _INDEXER_MSG[1]
    msg = None
    try:
        h = http_json(RADARR_BASE + "/api/v3/health", headers=arr_headers(RADARR_KEY), timeout=8)
        for item in h or []:
            src = (item.get("source") or "").lower()
            if "indexer" in src and item.get("type") in ("warning", "error"):
                msg = (item.get("message") or "Indexers unavailable").strip()
                break
    except Exception:
        msg = None
    _INDEXER_MSG = (now + 120, msg)
    return msg


def qbit_state(t):
    """Compact download-state from a qBittorrent torrent dict."""
    prog = round(float(t.get("progress") or 0) * 100)
    speed = float(t.get("dlspeed") or 0) / 1e6      # MB/s
    eta = int(t.get("eta") or -1)
    return {
        "progress": prog,
        "speed": round(speed, 2),
        "eta": eta if eta >= 0 else None,
        "qbitState": t.get("state") or "",
        "qbitName": (t.get("name") or "")[:60],
    }


def compute_statuses():
    """Return {imdbId: {...}} for every watchlist entry."""
    wl = load_watchlist()
    entries = wl.get("pending", []) + wl.get("recommended", [])
    out = {}
    r_ok = bool(RADARR_KEY) and safe(radarr_health, False)
    s_ok = bool(SONARR_KEY) and safe(sonarr_health, False)
    r_movies = radarr_movies() if r_ok else []
    r_queue = radarr_queue() if r_ok else []
    s_series = sonarr_series() if s_ok else []
    s_queue = sonarr_queue() if s_ok else []
    queue_by_movie = {str(q.get("movieId")): q for q in r_queue}
    queue_by_series = {str(q.get("seriesId")): q for q in s_queue}
    indexer_issue = radarr_indexer_issue()

    for e in entries:
        imdb = e.get("imdbId", "")
        is_series = bool(e.get("isSeries"))
        title = e.get("title", "")
        year = e.get("year")

        # --- Plex is the source of truth ---
        # If the title is already in Plex, it is available regardless of what
        # Radarr/Sonarr report (a stale/not_added *arr record is irrelevant).
        if _plex_has(title, year, is_series):
            plex_url, emby_url = _plex_emby_urls(e, is_series)
            out[imdb] = {"state": "available",
                         "service": "sonarr" if is_series else "radarr",
                         "detail": "Available in Plex",
                         "plexUrl": plex_url, "embyUrl": emby_url}
            continue

        # --- Not in Plex: fall back to the *arr / qBittorrent pipeline ---
        if is_series:
            tvdb = sonarr_resolve(imdb) if s_ok else None
            rec = next((x for x in s_series if str(x.get("tvdbId")) == str(tvdb)), None) if tvdb else None
            if not rec:
                out[imdb] = {"state": "not_added", "service": "sonarr"}
                continue
            q = queue_by_series.get(str(rec.get("id")))
            stats = rec.get("statistics") or {}
            downloaded = int(stats.get("episodeFileCount") or 0) > 0
            if downloaded:
                out[imdb] = {"state": "downloaded", "service": "sonarr", "detail": "In library"}
            elif q:
                out[imdb] = {"state": "downloading", "service": "sonarr", "progress": queue_pct(q)}
            else:
                out[imdb] = {"state": "requested", "service": "sonarr", "detail": "Requested"}
        else:
            rec = next((x for x in r_movies if str(x.get("tmdbId")) == str(e.get("tmdbId"))), None)
            if not rec:
                out[imdb] = {"state": "not_added", "service": "radarr"}
                continue
            q = queue_by_movie.get(str(rec.get("id")))
            if rec.get("hasFile"):
                out[imdb] = {"state": "downloaded", "service": "radarr", "detail": "In library"}
            elif q and q.get("status") != "completed":
                st = {"state": "downloading", "service": "radarr", "progress": queue_pct(q)}
                # enrich with real qBittorrent progress/speed when the download id lines up
                t = next((x for x in qbit_torrents() if x.get("hash") == q.get("downloadId")), None)
                if t:
                    st.update(qbit_state(t))
                out[imdb] = st
            elif q and q.get("status") == "completed":
                out[imdb] = {"state": "downloaded", "service": "radarr", "detail": "In library"}
            else:
                # Not in the Radarr queue — check qBittorrent directly (torrent may be
                # active while Radarr hasn't indexed it yet, or seeded/stopped).
                t = qbit_match(rec.get("title"), rec.get("year"))
                if t and float(t.get("progress") or 0) < 1.0:
                    out[imdb] = {"state": "downloading", "service": "radarr",
                                 **qbit_state(t), "detail": "Active in qBittorrent"}
                elif t and float(t.get("progress") or 0) >= 1.0:
                    out[imdb] = {"state": "downloaded", "service": "radarr",
                                 "progress": 100, "qbitState": t.get("state") or "",
                                 "detail": "Downloaded — awaiting import"}
                else:
                    detail = "Requested"
                    if indexer_issue:
                        detail = f"Waiting — search indexers down"
                    out[imdb] = {"state": "requested", "service": "radarr", "detail": detail}
    return out


def queue_pct(q):
    try:
        total = float(q.get("size") or 0)
        left = float(q.get("sizeleft") or 0)
        if total <= 0:
            return 0
        return max(0, min(99, int((1 - left / total) * 100)))
    except Exception:
        return 0


_plex_sections_cache = []          # [(section_type, section_key), ...]
_plex_sections_expiry = 0
_plex_titles_cache = {}            # (sec_type, sec_key) -> {lower-title: item}
_plex_titles_expiry = 0


def _plex_library(sec_type):
    """Return {lower_title: item} for one Plex section type, cached ~45s."""
    global _plex_sections_cache, _plex_sections_expiry, _plex_titles_cache, _plex_titles_expiry
    now = time.time()
    if not (PLEX_URL and PLEX_TOKEN):
        return {}
    hdr = {"Accept": "application/json"}
    try:
        if now > _plex_sections_expiry:
            d = http_json(PLEX_URL + "/library/sections?X-Plex-Token=" + PLEX_TOKEN,
                          headers=hdr, timeout=8)
            sc = []
            for sec in ((d.get("MediaContainer") or {}).get("Directory") or []):
                if (sec.get("type") or "") in ("movie", "show") and "key" in sec:
                    sc.append((sec.get("type"), str(sec["key"])))
            _plex_sections_cache = sc
            _plex_sections_expiry = now + 45
        # Refresh per-title cache when stale
        if now > _plex_titles_expiry:
            _plex_titles_cache = {}
            for st, sk in _plex_sections_cache:
                all_url = (PLEX_URL + "/library/sections/" + sk +
                           "/all?X-Plex-Token=" + PLEX_TOKEN + "&includeCollections=0")
                raw = safe(lambda: http_json(all_url, headers=hdr, timeout=15), {})
                items = (raw or {}).get("MediaContainer", {}).get("Metadata", []) if isinstance(raw, dict) else []
                _plex_titles_cache[(st, sk)] = {((it.get("title") or "").lower(), it.get("year")): it
                                                for it in items if it.get("type") == st}
            _plex_titles_expiry = now + 45
    except Exception as e:
        logger.warning("Plex library load failed: %s", e)
        return {}

    out = {}
    for (st, sk), items in _plex_titles_cache.items():
        if st == sec_type:
            out.update(items)
    return out


def _plex_has(title, year, is_series=False):
    """Check whether a title exists in Plex (source of truth). Returns match or None."""
    if not (PLEX_URL and PLEX_TOKEN):
        return None
    sec_type = "show" if is_series else "movie"
    titles = _plex_library(sec_type)
    tt = (title or "").lower().strip()
    # Exact title+year first
    if year is not None:
        item = titles.get((tt, year))
        if item:
            return item
    # Exact title, any year
    for (t, y), item in titles.items():
        if t == tt:
            return item
    # Substring fallback (careful with short titles)
    if len(tt) >= 4:
        for (t, y), item in titles.items():
            if tt in t or t in tt:
                if year is None or not y or y == year:
                    return item
    return None


def _plex_server_id():
    """Plex machineIdentifier (the id used in app.plex.tv deep links). Cached."""
    global _PLEX_SERVER_ID
    if _PLEX_SERVER_ID:
        return _PLEX_SERVER_ID
    if not (PLEX_URL and PLEX_TOKEN):
        return ""
    try:
        d = http_json(PLEX_URL + "/identity?X-Plex-Token=" + PLEX_TOKEN,
                      headers={"Accept": "application/json"}, timeout=8)
        mid = (d.get("MediaContainer") or {}).get("machineIdentifier") or ""
        if mid:
            _PLEX_SERVER_ID = mid
        return mid
    except Exception:
        return ""


def _emby_server_id():
    """Emby serverId (System/Info Id). Cached."""
    global _EMBY_SERVER_ID
    if _EMBY_SERVER_ID:
        return _EMBY_SERVER_ID
    if not (EMBY_URL and EMBY_API_KEY):
        return ""
    try:
        d = http_json(EMBY_URL + "/System/Info/Public", timeout=8)
        sid = d.get("Id") or d.get("ServerId") or ""
        if sid:
            _EMBY_SERVER_ID = sid
        return sid
    except Exception:
        return ""


_emby_items_cache = {}     # lower-title -> itemId
_emby_items_expiry = 0


def _emby_item_id(title, is_series=False):
    """Resolve an Emby item id from a title (cached ~45s). Returns str or ''."""
    global _emby_items_cache, _emby_items_expiry
    if not (EMBY_URL and EMBY_API_KEY):
        return ""
    now = time.time()
    if now > _emby_items_expiry:
        _emby_items_cache = {}
        _emby_items_expiry = now + 45
    tt = (title or "").lower().strip()
    if tt in _emby_items_cache:
        return _emby_items_cache[tt]
    try:
        # Need a user id for the search endpoint; fall back to /Items public.
        user_id = ""
        req = urllib.request.Request(EMBY_URL + "/Users?api_key=" + EMBY_API_KEY)
        with urllib.request.urlopen(req, timeout=8) as r:
            users = json.load(r)
        for u in users or []:
            if (u.get("Name") or "").lower() in ("rajeev", "admin", "main"):
                user_id = u.get("Id", "")
                break
        if not user_id and users:
            user_id = users[0].get("Id", "")
        q = urllib.parse.quote(tt)
        if user_id:
            url = f"{EMBY_URL}/Users/{user_id}/Items?api_key={EMBY_API_KEY}" \
                  f"&searchTerm={q}&Recursive=true&Limit=8"
        else:
            url = f"{EMBY_URL}/Items?api_key={EMBY_API_KEY}&searchTerm={q}&Recursive=true&Limit=8"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.load(r)
        # Prefer exact title match
        for it in (d or {}).get("Items", []) or []:
            want_series = (it.get("Type") == "Series")
            if want_series == is_series and (it.get("Name") or "").lower().strip() == tt:
                _emby_items_cache[tt] = str(it.get("Id", ""))
                return _emby_items_cache[tt]
        # Fallback: first matching type
        for it in (d or {}).get("Items", []) or []:
            if (it.get("Type") == "Series") == is_series:
                _emby_items_cache[tt] = str(it.get("Id", ""))
                return _emby_items_cache[tt]
    except Exception as e:
        logger.warning("Emby item lookup failed for %s: %s", title, e)
    return ""


def _emby_url_for(entry, is_series=False):
    """Build a working Emby deep link (#!/item?id=<id>&serverId=<sid>)."""
    title = entry.get("title", "")
    item_id = _emby_item_id(title, is_series)
    sid = _emby_server_id()
    base = "https://rkm-hp.tail8d5e8.ts.net:8096/web/index.html"
    if item_id and sid:
        return f"{base}#!/item?id={item_id}&serverId={sid}"
    # Fallback: search page
    q = urllib.parse.quote(title)
    return f"{base}#!/search?query={q}"


def _plex_emby_urls(entry, is_series=False):
    """Return (plex_url, emby_url) deep links for an available title."""
    title = entry.get("title", "")
    year = entry.get("year")
    m = _plex_has(title, year, is_series)
    plex_url = None
    sid = _plex_server_id()
    if m and m.get("ratingKey"):
        key = urllib.parse.quote(f"/library/metadata/{m.get('ratingKey')}", safe="")
        plex_url = (f"https://app.plex.tv/desktop/#!/server/{sid}/details?key={key}"
                    if sid else f"https://app.plex.tv/search?query={urllib.parse.quote(str(title))}")
    elif PLEX_URL and PLEX_TOKEN:
        plex_url = f"https://app.plex.tv/search?query={urllib.parse.quote(str(title))}"
    emby_url = _emby_url_for(entry, is_series)
    return plex_url, emby_url


# ------------------------------------------------------------------ routes
@app.get("/api/health")
def health():
    wl = load_watchlist()
    return {
        "ok": True,
        "updated": wl.get("updated", ""),
        "titleCount": len(wl.get("pending", [])) + len(wl.get("recommended", [])),
        "services": {
            "radarr": RADARR_KEY and safe(radarr_health, False),
            "sonarr": SONARR_KEY and safe(sonarr_health, False),
            "tmdb": bool(TMDB_KEY),
            "plex": bool(PLEX_URL and PLEX_TOKEN),
            "emby": bool(EMBY_URL and EMBY_API_KEY),
            "jellyfin": bool(JELLYFIN_URL and JELLYFIN_KEY),
            "qbit": safe(lambda: bool(qbit_torrents()), False),
        },
    }


@app.get("/api/config")
def config():
    wl = load_watchlist()
    return {
        "updated": wl.get("updated", ""),
        "heroMode": wl.get("hero_mode", "auto"),
        "rotation": wl.get("rotation", []),
        "services": {  # booleans only — never keys/URLs
            "radarr": bool(RADARR_KEY) and safe(radarr_health, False),
            "sonarr": bool(SONARR_KEY) and safe(sonarr_health, False),
            "tmdb": bool(TMDB_KEY),
            "plex": bool(PLEX_URL and PLEX_TOKEN),
            "emby": bool(EMBY_URL and EMBY_API_KEY),
            "jellyfin": bool(JELLYFIN_URL and JELLYFIN_KEY),
        },
    }


@app.get("/api/status")
def status():
    return {"statuses": compute_statuses(),
            "indexerIssue": radarr_indexer_issue()}


def _resolve_download_type(imdb_id, requested_type):
    """Determine movie|tv authoritatively so a movie never goes to Sonarr.

    Priority: explicit type -> watchlist isSeries -> Radarr/Sonarr lookup.
    """
    if requested_type in ("movie", "tv"):
        return requested_type
    inferred = is_series_for(imdb_id)
    if inferred is not None:
        return "tv" if inferred else "movie"
    # Look up in both services; prefer Radarr (movie) so a movie is never
    # misrouted to Sonarr.
    try:
        res = http_json(RADARR_BASE + "/api/v3/movie/lookup?term=imdb:" + imdb_id,
                        headers=arr_headers(RADARR_KEY), timeout=15)
        if isinstance(res, list) and res and res[0].get("tmdbId"):
            return "movie"
    except Exception:
        pass
    try:
        res = http_json(SONARR_BASE + "/api/v3/series/lookup?term=imdb:" + imdb_id,
                        headers=arr_headers(SONARR_KEY), timeout=15)
        if isinstance(res, list) and res and res[0].get("tvdbId"):
            return "tv"
    except Exception:
        pass
    # Last resort: movie (Radarr is the common case).
    return "movie"


@app.post("/api/download")
def download(req: DownloadReq):
    imdb = req.imdbId.strip()
    if not imdb and not req.tmdbId:
        raise HTTPException(status_code=400, detail="imdbId or tmdbId required")
    if not imdb:
        # tmdbId-only path (live TMDB search results): route by type, Radarr can lookup tmdb:
        if req.type == "tv":
            raise HTTPException(status_code=400, detail="TV downloads need an IMDb ID")
        # Radarr lookup supports term=tmdb:<id>
        try:
            res = http_json(RADARR_BASE + "/api/v3/movie/lookup?term=tmdb:" + str(req.tmdbId),
                            headers=arr_headers(RADARR_KEY), timeout=20)
            m = (res or [{}])[0] if isinstance(res, list) else None
            if not m or not m.get("imdbId"):
                raise HTTPException(status_code=404, detail="No Radarr match for this title")
            return run_download(m["imdbId"], "movie")
        except HTTPException:
            raise
        except Exception as ex:
            raise HTTPException(status_code=502, detail=f"Radarr unavailable: {ex}")
    media_type = _resolve_download_type(imdb, req.type)
    return run_download(imdb, media_type, req.title, req.year)


def run_download(imdb_id, kind, title="", year=None):
    if kind == "tv":
        if not SONARR_KEY:
            raise HTTPException(status_code=503, detail="Sonarr is not configured")
        ok, state, msg = safe(lambda: sonarr_add(imdb_id, title, year), (False, "unavailable", "Sonarr unreachable"))
    else:
        if not RADARR_KEY:
            raise HTTPException(status_code=503, detail="Radarr is not configured")
        ok, state, msg = safe(lambda: radarr_add(imdb_id, title, year), (False, "unavailable", "Radarr unreachable"))
    if not ok:
        code = 404 if "Multiple Radarr matches" in (msg or "") or "Multiple Sonarr matches" in (msg or "") else 502
        raise HTTPException(status_code=code, detail=msg)
    return {"ok": True, "state": state, "message": msg, "service": kind}


@app.get("/api/search")
def search(q: str = ""):
    q = q.strip()
    if not q:
        return {"watchlist": [], "tmdb": [], "tmdbKey": False}
    ql = q.lower()
    wl = load_watchlist()
    local = []
    for e in wl.get("pending", []) + wl.get("recommended", []):
        hay = " ".join([
            e.get("title", ""), e.get("category", ""), e.get("director", ""),
            e.get("snippet", ""), " ".join(e.get("cast", []) or []),
            str(e.get("year", "")),
        ]).lower()
        if ql in hay:
            local.append({
                "title": e.get("title", ""), "year": e.get("year"), "type": "tv" if e.get("isSeries") else "movie",
                "imdbId": e.get("imdbId", ""), "tmdbId": e.get("tmdbId"),
                "poster": e.get("poster", ""), "inWatchlist": True,
                "director": e.get("director", ""), "cast": e.get("cast", [])[:3],
                "snippet": e.get("snippet", ""),
            })
    live, live_key = [], bool(TMDB_KEY)
    if TMDB_KEY:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={urllib.parse.quote(q)}&language=en-US&page=1"
        try:
            d = safe(lambda: http_json(url, timeout=10), {"results": []})
            for r in (d.get("results") or [])[:8]:
                mtype = r.get("media_type")
                if mtype not in ("movie", "tv"):
                    continue
                live.append({
                    "title": r.get("title") or r.get("name") or "",
                    "year": int((r.get("release_date") or r.get("first_air_date") or "")[:4] or 0) or None,
                    "type": mtype,
                    "tmdbId": r.get("id"),
                    "poster": ("https://image.tmdb.org/t/p/w342" + r["poster_path"]) if r.get("poster_path") else "",
                    "overview": r.get("overview") or "", "inWatchlist": False,
                    "voteAverage": r.get("vote_average"),
                })
        except Exception:
            live = []
    return {"watchlist": local[:6], "tmdb": live, "tmdbKey": live_key, "servicesDown": not safe(radarr_health, False) and not safe(sonarr_health, False)}


@app.get("/api/library")
def library():
    """Plex first, Jellyfin/Emby fallback. Never hard-fails the dashboard."""
    plex_hdr = {"Accept": "application/json"}
    if PLEX_URL and PLEX_TOKEN:
        try:
            url = f"{PLEX_URL}/library/sections?X-Plex-Token={PLEX_TOKEN}"
            d = http_json(url, headers=plex_hdr, timeout=8)
            dirs = (d.get("MediaContainer") or {}).get("Directory") or []
            counts = {"movie": 0, "show": 0}
            for sec in dirs:
                st = sec.get("type")
                if st in ("movie", "show") and "key" in sec:
                    all_url = f"{PLEX_URL}/library/sections/{sec['key']}/all?X-Plex-Token={PLEX_TOKEN}&includeCollections=0"
                    n = int(safe(lambda: http_json(all_url, headers=plex_hdr, timeout=8).get("MediaContainer", {}).get("size", 0), 0) or 0)
                    counts[st] += n
            recent = []
            try:
                r = http_json(f"{PLEX_URL}/library/recentlyAdded?limit=8&X-Plex-Token={PLEX_TOKEN}", headers=plex_hdr, timeout=8)
                for item in (r.get("MediaContainer") or {}).get("Metadata") or []:
                    rk = item.get("ratingKey") or ""
                    key = urllib.parse.quote(f"/library/metadata/{rk}", safe="") if rk else ""
                    is_series = item.get("type") == "show"
                    recent.append({
                        "title": item.get("title", ""), "year": item.get("year"),
                        "type": "tv" if is_series else "movie",
                        "thumb": item.get("thumb") or "",
                        "ratingKey": rk,
                        "plexUrl": (f"https://app.plex.tv/desktop/#!/server/{_plex_server_id()}/details?key={key}"
                                    if rk and _plex_server_id() else ""),
                        "embyUrl": _emby_url_for({"title": item.get("title", ""), "year": item.get("year")}, is_series),
                    })
            except Exception:
                pass
            return {"provider": "plex", "available": True, "counts": counts,
                    "recent": recent, "server": "Plex",
                    "urls": {"plex": f"https://app.plex.tv/desktop", "emby": ""}}
        except Exception:
            pass
    if EMBY_URL and EMBY_API_KEY:
        try:
            d = http_json(f"{EMBY_URL}/Items/Counts?api_key={EMBY_API_KEY}", timeout=8)
            recent = []
            try:
                r = http_json(f"{EMBY_URL}/Items/Recents?api_key={EMBY_API_KEY}&Limit=8&Fields=PrimaryImagePath", timeout=8)
                for it in (r or {}).get("Items", []) if isinstance(r, dict) else []:
                    recent.append({
                        "title": it.get("Name", ""), "year": it.get("ProductionYear"),
                        "type": "tv" if it.get("Type") == "Series" else "movie",
                        "thumb": (it.get("PrimaryImagePath") or "").split("?")[0],
                        "id": it.get("Id", ""),
                    })
            except Exception:
                pass
            return {"provider": "emby", "available": True,
                    "counts": {"movie": d.get("MovieCount", 0), "show": d.get("SeriesCount", 0)},
                    "recent": recent, "server": "Emby",
                    "urls": {"plex": f"https://app.plex.tv/desktop",
                             "emby": "https://rkm-hp.tail8d5e8.ts.net:8096/web/index.html"}}
        except Exception:
            pass
    if JELLYFIN_URL and JELLYFIN_KEY:
        try:
            d = http_json(f"{JELLYFIN_URL}/Items/Counts?api_key={JELLYFIN_KEY}", timeout=8)
            return {"provider": "jellyfin", "available": True,
                    "counts": {"movie": d.get("MovieCount", 0), "show": d.get("SeriesCount", 0)},
                    "recent": [], "server": "Jellyfin",
                    "urls": {"plex": "", "emby": JELLYFIN_URL.rstrip("/") + "/web/index.html"}}
        except Exception:
            pass
    return {"provider": None, "available": False, "counts": {"movie": 0, "show": 0},
            "recent": [], "server": None,
            "urls": {"plex": "https://app.plex.tv/desktop", "emby": "https://rkm-hp.tail8d5e8.ts.net:8096/web/index.html"}}


@app.get("/api/plex/thumb")
def plex_thumb(path: str = "", width: int = 500):
    """Proxy a Plex thumbnail so the browser can show it without exposing the token."""
    if not (PLEX_URL and PLEX_TOKEN) or not path:
        return Response(status_code=404)
    # Only allow known image paths inside the media server.
    if ".." in path or "://" in path:
        return Response(status_code=400)
    url = (PLEX_URL.rstrip("/") + "/photo/:/transcode?width=" + str(width)
           + "&height=" + str(int(width * 1.5))
           + "&url=" + urllib.parse.quote("http://127.0.0.1:32400" + path, safe="")
           + "&X-Plex-Token=" + PLEX_TOKEN)
    try:
        req = urllib.request.Request(url, headers={"Accept": "image/*"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return Response(content=r.read(), media_type=r.headers.get("Content-Type", "image/jpeg"))
    except Exception:
        return Response(status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)