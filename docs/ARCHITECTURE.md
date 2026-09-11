# RKM Watchlist — Architecture

> ⚠ **2026-09-08:** repo restructured into a monorepo (`REPO_STRUCTURE_PLAN.md`)
> and the legacy vanilla app removed (branch `chore/remove-legacy-app`):
> **`backend/`** holds the FastAPI app + tests, **`frontend/`** the React/TS shell
> (renamed from `web/`) — now the only UI; the `/legacy` route, `frontend/legacy/`
> and the `rebuild_dashboard.py` static dashboard generator are gone (archived in
> `tools/archive/`). Deploy/infra + docs stay at the root. The authoritative
> project tree + commands live in `../README.md`.

> **Single codebase.** The monolithic `api.py` has been archived
> (`tools/archive/api_legacy_monolith.py`) and the production backend is now the
> modular FastAPI app: **`uvicorn api.main:app`** (see `backend/Dockerfile`). There is
> exactly ONE implementation of each business rule. Add features to the modular
> tree, not a parallel monolith.

---

## 1. What this is

A self-hosted **media discovery + download dashboard**. It:
- Shows what's in your **Jellyfin** library (source of truth for availability) and recently added.
- Lets you **request** movies/series, which are added to **Radarr** (movies) or **Sonarr** (TV) and downloaded via **qBittorrent**.
- Tracks each title through a lifecycle: requested → downloading → downloaded → available → recommended (history).
- Deep-links each available title straight into **Jellyfin**'s own web UI, and plays it in-app (same-origin HLS/MSE) where the server exposes an item id.
- Fetches **posters/backdrops/genres** from **TMDB** and **trailers** by scraping `youtube.com` (no YouTube API key).

Access is private over **Tailscale**. The browser talks to nginx on :8124; nginx proxies `/api/*` to the FastAPI container, which holds all secrets.

---

## 2. High-level layout

```
 Browser (Tailnet device)
      │  http://rkm-hp.tail8d5e8.ts.net:8124
      ▼
 ┌──────────────────────────────┐
 │  nginx (web container) :8124 │   serves the React shell (frontend/)
 │  ─ proxies /api/* → api:8000 │
 └──────────────┬───────────────┘
                ▼
 ┌──────────────────────────────┐
 │  FastAPI  api  container     │   uvicorn api.main:app  (modular)
 │  /api/health /config /status │   holds RADARR_KEY, SONARR_KEY, JELLYFIN_KEY…
 │  /api/download /search       │
 │  /api/library /jellyfin/*    │
 │  /api/quality                │
 └───────┬──────────┬───────────┘
         │          │   read /write
         ▼          ▼
 ┌────────────┐  ┌───────────────────────────────┐
 │ watchlist  │  │  External: Jellyfin·Radarr     │
 │ .json (ro) │  │  Sonarr·TMDB·qBittorrent·YT    │
 └────────────┘  └───────────────────────────────┘
```

---

## 3. Repository layout

```
rkm-cinema/                       (full annotated tree in ../README.md)
├── backend/                      FastAPI app + pytest suite + Dockerfile
│   ├── api/                      main.py app factory + routes/ (thin routers)
│   ├── services/                 external integrations + app services
│   │   ├── library/ acquisition/ recommendation/ reconciliation/  (canonical)
│   │   ├── radarr.py sonarr.py tmdb.py youtube.py
│   │   ├── qbittorrent.py watchlist.py media_status.py recommendations.py
│   ├── domain/                   business layer: state machine + resolver
│   ├── core/  config/  infrastructure/  application/  jobs/
│   ├── scripts/                  daily pipeline + rebuild + probes
│   ├── provisioner/              bundled-stack Jellyfin provisioner
│   └── tests/                    unit + API tests (mockable, no live LAN)
├── frontend/                     React 18 + TS + Vite shell (the only UI)
├── docs/                         architecture, plans, ADRs, API contract,
│                                 OPERATIONS.md, PROGRESS.md, ARCHITECTURE.md
├── nginx/  scripts/  tools/      web config; backup/restore; diagnostics
├── docker-compose.yml  bootstrap.ps1  bootstrap.sh  render_config.py  rkm-cinema.ps1
└── README.md  .env (single config)  .env.example (committed template)
```

Run everything from the subdirs: `cd backend && python -m pytest tests/ -q`,
`cd frontend && npm run typecheck && npx vitest run && npm run build`.
Deploy stays at the root (`.\\bootstrap.ps1`, wrapped by `.\\rkm-cinema.ps1 deploy`).

---

## 4. Dependency direction (the contract)

```
 Frontend (app.js)
      ↓  /api/*
 API routes (api/routes/*)         thin: validate → call service → map response
      ↓
 Domain + app services (services/)  business rules once, in one place
      ↓
 External service clients (services/*, core/http_client)  isolated URL/auth/HTTP
      ↓
 Jellyfin · Radarr · Sonarr · TMDB · qBittorrent · YouTube
```

Rules:
- Routes **never** call external APIs directly or build raw `urllib` calls.
- Services **never** leak secrets; browser never sees keys/URLs (nginx fronts `/api`).
- The `domain/` state machine + resolver are the **single owners** of status and movie/tv rules.

---

## 5. Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service up/down flags (radarr, sonarr, tmdb, qbit, jellyfin) |
| `GET /api/config` | Public-safe booleans + dashboard freshness (never keys/URLs) |
| `GET /api/status` | Per-title state via the `Reconciler` → `domain.status.resolve_status()`; includes `jellyfinUrl` + `jellyfinItemId` |
| `POST /api/download` | Add movie→Radarr / series→Sonarr via `DownloadService` (title fallback, "pick one" ambiguity) |
| `GET /api/search` | Watchlist + live TMDB search |
| `GET /api/library` | Library counts + recently-added (first provider that answers); per-item thumb |
| `GET /api/jellyfin/poster` | Same-origin artwork proxy (person/backdrop variants too) — the api key stays server-side |
| `GET /api/quality` | Radarr/Sonarr quality profiles for the download dialog |

---

## 6. Media status state machine

The canonical resolution lives in `domain/state_machine.py::resolve_status`:

```
 the server has it → AVAILABLE        (with the watch link + item id)
 else *arr has file → DOWNLOADED
 else qBittorrent active → DOWNLOADING (progress/speed/eta)
 else *arr queue  → DOWNLOADING
 else *arr record exists → REQUESTED ("waiting — indexers down" if health says so)
 else             → NOT_ADDED
```

**The media server (Jellyfin) is the source of truth** for availability. A title
it holds is `available` even if its *arr record is stale/missing. The `Reconciler`
gathers the external facts and feeds them to `resolve_status`; the domain module
decides. The `WatchLinks` value object carries `library_available`, `watch_url`
and `server_item_id` (the server's own item id, not a URL) for
`available`/`downloaded` titles.

> **Performance guard:** the Jellyfin provider caches its full item listing (60 s
> window) and the reconciler caches its whole result on the watchlist file's
> mtime. The status pass asks for every watchlist entry; without those caches one
> `/api/status` request re-scanned the library per entry and blew the request
> window.

---

## 7. Download flow

1. Frontend `POST /api/download` → `DownloadService.download(...)`.
2. Media type resolved by **`domain/resolver.py`** (single authoritative rule):
   explicit `type` → watchlist `isSeries` → Radarr/Sonarr lookup → default movie.
3. `RadarrService.add_movie` / `SonarrService.add_series`:
   - Lookup by `imdb` first; if it resolves nothing, **fall back to title (+year) search**.
   - Unique match → used. Multiple matches, none exact → **`ambiguous`** ("pick one" list), never a silent guess.
4. Cross-service fallback: a "No Radarr match" on a real series retries Sonarr (and vice-versa).
5. `DownloadResult` (typed domain object) maps to `DownloadResponse` with predictable HTTP codes (404 ambiguous, 502 unavailable, 503 not configured).

---

## 8. Watch links (Jellyfin only)

There is exactly ONE media server (Jellyfin, bundled) and it is the only source of
watch links — the Plex/Emby providers were removed on 2026-09-11
(`adr/ADR-0004-remove-plex-emby-support.md`).

Two ways to watch an available title, both same-origin:

- **In-app playback** (`jellyfinItemId`): the recorded item id drives
  `/api/jellyfin/stream|hls` through the same proxy the browser already talks to,
  so no token or cross-origin request is involved.
- **Deep link** (`jellyfinUrl`): `{browser base}/web/index.html#!/details?id={itemId}`
  on the browser-reachable host. The base is config-driven — `JELLYFIN_BROWSER_URL`
  (defaults to the Tailscale MagicDNS HTTPS host, see `TAILSCALE_HOSTING.md`). The
  container-internal `JELLYFIN_URL` is the api's own address and is **never** used
  to build a user link.

The `/api/status` payload therefore carries `jellyfinUrl` + `jellyfinItemId`; the
reconciler's snapshot keeps a `watch` map keyed by provider name, holding the
`jellyfin` entry's `available` / `url` / `item_id`.


## 9. External integrations

| Service | Responsibility |
|---|---|
| `RadarrService` | Movies, `lookup_movie`, `search_movies` (title fallback), `add_movie`, profiles/queue, indexer health |
| `SonarrService` | Series, `lookup_series`, `search_series` (title fallback), `add_series`, tvdb resolve, profiles/queue |
| `TMDBService` | Movie/show details, posters/backdrops/genres, search |
| `YouTubeService` | Scrape youtube.com for the official trailer (no API key) |
| `QBittorrentService` | Torrent list + download-state (used by status) |
| `TrailerService` | Legacy trailer fallback |
| `WatchlistService` | Atomic watchlist persistence + state validation |
| `MediaStatusService` | Per-entry status via the domain state machine |
| `DownloadService` | Movie/tv routing + add + fallback orchestration |
| `RecommendationService` | Quality gates, library/duplicate checks, enrichment, add |

All services accept injectable `config`/`http` (constructor DI) and are unit-tested
with fakes — **no test touches the live LAN**.

---

## 10. Config & data

- **`config/settings.py`** — single `Config` singleton from the repo `.env` (+ env overrides). Provides `has_jellyfin()`, `has_tmdb()`, `validate_required()`, etc. **Never returns secrets via `/api/config`.** Exposes the browser-reachable `JELLYFIN_BROWSER_URL` used only for deep-links (falls back to the Tailscale host when unset), and the ONE media-server rule `resolve_media_server()` — jellyfin is the default AND the fallback for a blank/unknown value, so a missing key can never select a retired backend. `validate_required()` deliberately does **not** demand a media-server credential (a fresh install has none until the provisioner writes it; `/api/health` reports that state).
- **`watchlist.json`** — source of truth; volume-mounted into the container at `/app/watchlist.json`. `WatchlistService` auto-resolves the correct path (container vs sandbox).
- **`dashboard-data.json`** — published snapshot the SPA loads (built by `scripts/rebuild_dashboard.py`).
- **`.env`** — canonical at `/workspace/.env`, never committed; see `.env.example`.

---

## 11. Frontend (app.js → api.js)

- `api.js` — centralized API client (`API.getJSON`, `API.download`, `API.getStatus`, …). Loaded before `app.js` as a plain global.
- `app.js` — rendering, state, UI. Delegates ALL `/api/*` and `/dashboard-data.json` calls to `API`. No direct `fetch` to backend endpoints anywhere else.
- Served statically by nginx; **volume-mounted** so UI changes need no Docker rebuild.

---

## 12. Deployment

- Deploy (RKM-HP / Windows): `.\\bootstrap.ps1` (or `.\\rkm-cinema.ps1 deploy`) → `docker compose -p rkm-bundled up -d --build`.
- Two containers: `api` (FastAPI modular, holds secrets) + `web` (nginx :8124, static + `/api` proxy), plus the bundled `jellyfin` media server.
- **The media server is reached over Tailscale** (HTTPS via the MagicDNS host); deep-links must target the browser-reachable `JELLYFIN_BROWSER_URL` host, not the container-internal `JELLYFIN_URL` (see §8).

---

## 13. Adding a feature (recommended path)

1. **Business rule (status/movie-tv)?** → put it in `backend/domain/` (state machine or resolver). Wire service gatherers in `backend/services/`.
2. **External integration?** → add a method on the relevant `backend/services/*` client; never in a route.
3. **Route?** → add a thin handler in `backend/api/routes/`, reuse a service, return a typed Pydantic model.
4. **UI?** → update the React shell (`frontend/src/`).
5. **Test it** → add a mockable pytest under `backend/tests/`; run `cd backend && python -m pytest tests/ -q`.
6. No static dashboard rebuild exists any more — the React shell reads the live `/api` (the old `rebuild_dashboard.py` static generator was removed with the legacy app).
7. Deploy with `.\bootstrap.ps1` (the bundled api + web + Jellyfin stack); verify `/api/health` + the dashboard.

---

## 14. Testing

- `backend/tests/` cover: the status resolver + state machine, media-type resolver, Radarr/Sonarr routing + title fallback + ambiguity, duplicate prevention, error handling, trailer validation, the library provider + factory (one backend: Jellyfin), the `LibraryService` collapse and watch-link failure containment, the reconciler, recommendation pipeline, and API endpoints.
- All tests use **injected fakes** — no real LAN, no real API keys required.
- Run: `cd backend && python -m pytest tests/ -q` (all green; count moves with the suite — see `PROGRESS.md` for the current number).
