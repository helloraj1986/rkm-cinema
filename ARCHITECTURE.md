# RKM Watchlist — Architecture

> **Accuracy note — read this first.** There are TWO API codebases in this repo.
> The one that is **actually deployed** (the Dockerfile copies `api.py` at the repo
> root and runs `uvicorn api:app`) is the **monolithic `api.py`**. The modular
> `api/` package + `services/` modules are the **target refactor**: mostly written
> and tested, used by the offline scripts, but **not yet swapped in as the web
> backend**. See "Two API layers" before adding routes so you edit the live one.

---

## 1. What this is

A self-hosted **media discovery + download dashboard**. It:
- Shows you what's in your **Plex** library (source of truth) and recently added.
- Lets you **request** movies/series, which get added to **Radarr** (movies) or
  **Sonarr** (TV) and downloaded via **qBittorrent**.
- Tracks each title through a lifecycle: requested → downloading → downloaded →
  available → recommended (history).
- Deep-links each available title straight into **Plex** or **Emby** to watch.
- Fetches **posters/backdrops/genres** from **TMDB** and **trailers** by scraping
  `youtube.com` (no YouTube API key).

Access is private, over **Tailscale** only (MagicDNS). The browser talks to nginx
on :8123; nginx proxies `/api/*` to the FastAPI container, which holds all secrets.

---

## 2. High-level layout

```
 Browser (Tailnet device)
      │  http://rkm-hp.tail8d5e8.ts.net:8123
      ▼
 ┌──────────────────────────────┐
 │  nginx (web container) :8123 │   serves app.js/app.css/index.html
 │  ─ proxies /api/* → api:8000 │   (static files volume-mounted from repo)
 └──────────────┬───────────────┘
                ▼
 ┌──────────────────────────────┐
 │  FastAPI  api  container     │   THE DEPLOYED BACKEND = root api.py
 │  /api/health /config /status │   (holds RADARR_KEY, PLEX_TOKEN, etc.)
 │  /api/download /search       │
 │  /api/library /plex/thumb    │
 └───────┬──────────┬───────────┘
         │          │   read /write
         ▼          ▼
 ┌────────────┐  ┌───────────────────────────────┐
 │ watchlist  │  │  External: Plex·Radarr·Sonarr  │
 │ .json (ro) │  │  TMDB·Emby·qBittorrent·YouTube  │
 └────────────┘  └───────────────────────────────┘
```

---

## 3. Two API layers (READ THIS FIRST)

| | **Legacy monolith (LIVE)** | **Modular refactor (target)** |
|---|---|---|
| File(s) | `api.py` at repo root (all routes+logic in one file) | `api/main.py` + `api/routes/*.py` + `services/*.py` |
| Deployed? | **Yes** — Dockerfile copies `api.py` and runs `uvicorn api:app` | **No** — not wired into the Docker image yet |
| Used by | The running dashboard (everything you see) | Offline scripts: `scripts/rebuild_dashboard.py`, `scripts/daily_recommendations.py`, `scripts/auto_complete.py`, `scripts/add_with_plex_check.py`, `scripts/verify_plex.py` |
| Tests | — | `tests/test_*.py` exercise the modular services |

**So:** to change behavior **you see on the site**, edit **`api.py`**. To change the
recommenders/rebuild **scripts**, edit the modular `services/` + `scripts/`.
The plan is to eventually swap the web backend to the modular `api/` package.

> Both layers duplicate roughly the same logic (status, download, library). Keep
> fixes in BOTH when a bug touches shared behaviour.

---

## 4. The mono `api.py` (live backend) — what each endpoint does

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service up/down flags (radarr, sonarr, tmdb, plex, emby, jellyfin, qbit) |
| `GET /api/config` | Public-safe booleans + dashboard freshness (never keys/URLs) |
| `GET /api/status` | Per-title lifecycle state (not_added/requested/downloading/downloaded/available) + `plexUrl`/`embyUrl` watch links |
| `POST /api/download` | Add movie→Radarr or series→Sonarr; resolves stale/ambiguous IDs by title fallback |
| `GET /api/search` | Search watchlist + live TMDB (multi-search) for adding |
| `GET /api/library` | Plex library counts + recently-added (Emby fallback); each item gets plexUrl/embyUrl/thumb |
| `GET /api/plex/thumb` | Server-side proxy for Plex thumbnails (keeps the token secret) |

### Inside `api.py` — key helpers
- `_resolve_download_type(imdb, type)` — decides movie vs TV for routing.
- `_plex_has / _plex_library` — the **Plex-as-source-of-truth** check (cached ~45s).
- `_plex_server_id / _emby_server_id / _emby_item_id / _emby_url_for` — build correct
  Plex (`#!/server/<machineId>/details?key=%2Flibrary%2Fmetadata%2F<rk>`) and Emby
  (`#!/item?id=<id>&serverId=<sid>`) deep links.
- `compute_statuses()` — lifecycle resolution order: **Plex first**, then *arr/qBittorrent.
- `radarr_add / sonarr_add (+_lookup_title)` — add with title/year fallback + "pick one" ambiguity lists.

---

## 5. Modular target (`api/` + `services/`) — what each module is for

### `services/` — the domain layer
| Module | Responsibility |
|---|---|
| `plex.py` | Plex client: library, ownership, recently-added, deep-link helpers (`server_id`, `find_item`, `plex_url_for`, `emby_url_for`) |
| `radarr.py` | Radarr client: movies, lookup/add (with title fallback), quality profiles, queue |
| `sonarr.py` | Sonarr client: series, lookup/add (title fallback), tvdb resolve, profiles |
| `tmdb.py` | TMDB metadata: movie/show details, posters/backdrops/genres, search |
| `youtube.py` | Scrape youtube.com for the **official trailer** (no API key) |
| `trailers.py` | Legacy trailer fallback (TVDB/TMDB/oEmbed) |
| `emby.py` | Emby client / counts |
| `recommendations.py` | Recommendation pipeline: rotation, quality gates, enrichment, validation |
| `watchlist.py` | Watchlist CRUD + state machine, atomic writes |
| `base.py` | `BaseService` shared HTTP/config/retry plumbing |
| `plex_check.py` | Thin Plex ownership helper |

### `api/` — the FastAPI app (target backend)
- `main.py` — app factory, CORS, wires all routers.
- `routes/health.py config.py status.py download.py search.py library.py quality.py` — one router per concern.
- `models.py` — Pydantic request/response models (`DownloadRequest`, `StatusEntry`, `LibraryResponse`, …).

### `core/` — infrastructure
- `settings.py` is in `config/`; `http_client.py` (shared HTTP + retry/cache), `logging.py`, `exceptions.py`.

---

## 6. Lifecycle / state machine

```
PENDING ──► REQUESTED ──► DOWNLOADING ──► DOWNLOADED ──► AVAILABLE ──► RECOMMENDED
                                        (qBittorrent  (hasFile,     (in Plex =
                                          progress)     *arr)         source of truth)
```

**The rule in `compute_statuses` (and modular `status.py`):**
1. If the title is **in Plex** → `available` (with watch links). **Plex wins.**
2. Else if Radarr/Sonarr `hasFile` → `downloaded`.
3. Else if in *arr/qBittorrent queue → `downloading` (with %).
4. Else `requested` / `not_added`.

This means a title that exists in Plex shows as **available** even if its *arr
record is stale/missing — that was the fix for "requested but it's actually in Plex".

---

## 7. Download flow (with title-fallback safety)

1. Frontend `POST /api/download` with `{imdbId, type, title?, year?, tmdbId?}`.
2. `api.py` resolves movie vs TV (`_resolve_download_type`), then calls
   `radarr_add`/`sonarr_add`.
3. Each looks up by `imdb:<id>` first; **if it 404s/returns nothing**, falls back to a
   **title (+year) search** in Radarr/Sonarr (prevents "No Radarr/Sonarr match" for
   stale IDs e.g. The Bear / The Zone of Interest).
4. A unique match is used; multiple matches return a numbered "pick one" list; a movie
   can never be routed to Sonarr by mistake.

---

## 8. Scripts (`scripts/`)

| Script | Purpose | Run by |
|---|---|---|
| `rebuild_dashboard.py` | Regenerate `dashboard-data.json` + `index.html` from the watchlist (publisher guard, atomic writes) | manual / cron |
| `daily_recommendations.py` | Daily recommendation pipeline (rotation, gates, enrichment, add) | cron |
| `auto_complete.py` | Move pending→recommended when downloaded + in Plex | cron |
| `enrich_trailers.py` / `fetch_trailers.py` / `fix_trailer_ids.py` / `validate_trailers.py` | Trailer enrichment & hygiene | manual |
| `backfill_tmdb_artwork.py` | Re-fetch posters/backdrops from TMDB by tmdbId | manual (after an outage) |
| `add_with_plex_check.py` / `verify_plex.py` | Add/verify against Plex | manual |

---

## 9. Data & config

- **`watchlist.json`** — source of truth for the watchlist (volume-mounted `:ro` into
  the container). Lives at the workspace root, not committed to git.
- **`dashboard-data.json`** — baked/published snapshot the SPA loads (generated by
  `rebuild_dashboard.py`; git-ignored).
- **`.env`** — all secrets (RADARR_API_KEY, PLEX_TOKEN, EMBY_API_KEY, TMDB_API_KEY…).
  Canonical file at `/workspace/.env`; mounted into the container. **Never committed.**
  See `.env.example` for the full list.
- **`/workspace/.env` is the canonical secrets file.**

---

## 10. Config knobs (`.env`)

See `.env.example`. Highlights:
- `MEDIA_HOST` = LAN IP of the media box.
- `RADARR_/SONARR_*` = URLs + API keys; `*_QUALITY_PROFILE_ID` optional overrides.
- `PLEX_URL`+`PLEX_TOKEN` = source of truth + thumbnails.
- `EMBY_URL`+`EMBY_API_KEY` = Emby (HTTPS-only over Tailscale on :8096).
- `TMDB_API_KEY` = metadata/artwork. (No YouTube key needed — trailers scraped.)
- `QBITTORRENT_URL` = download progress.

---

## 11. Deployment & networking

- **Repo** → mounted at `/workspace/media/watchlist` (maps to `D:\hermes_agent\hermes-workspace\media\watchlist`).
- **Deploy** (RKM-HP, Windows): `.\setup-watchlist.ps1` → `docker compose up -d --build`.
- **Two containers:** `api` (FastAPI, holds secrets) + `web` (nginx :8123, serves
  static + proxies `/api`).
- **Tailscale only** — `http://rkm-hp.tail8d5e8.ts.net:8123`. Never `tailscale funnel`.
  Emby on :8096 is HTTPS-only over Tailscale.

---

## 12. Adding a feature (recommended path)

1. Decide which layer: **live-site behaviour → `api.py`**; **recommender/scripts →
   modular `services/`+`scripts/`**. For anything that appears in the dashboard,
   patch **both** `api.py` (live) *and* the modular equivalent so they don't drift.
2. Add/use a service method in `services/` when it's media-logic (Radarr/Sonarr/
   Plex/TMDB/Emby/YouTube), then expose it via a route in both layers.
3. If it touches the UI, extend `app.js`/`app.css` (volume-mounted, no rebuild needed).
4. Add tests under `tests/` for the modular service; run `python -m pytest tests/ -q`.
5. Regenerate `dashboard-data.json` with `scripts/rebuild_dashboard.py`.
6. Deploy with `.\setup-watchlist.ps1`, verify via `/api/health` + the dashboard.

---

## 13. Testing

- `tests/` cover the modular services: Plex ownership, Radarr/Sonarr routing,
  duplicate prevention, trailer validation, download status, error handling, E2E.
- Some tests are integration-style and hit live LAN services (they need the real
  environment; pass with the `.env` populated).
- Run: `python3 -m pytest tests/ -q` (from the repo root).
