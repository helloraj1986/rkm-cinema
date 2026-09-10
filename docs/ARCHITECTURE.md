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
- Shows what's in your **Plex** library (source of truth for availability) and recently added.
- Lets you **request** movies/series, which are added to **Radarr** (movies) or **Sonarr** (TV) and downloaded via **qBittorrent**.
- Tracks each title through a lifecycle: requested → downloading → downloaded → available → recommended (history).
- Deep-links each available title straight into **Plex** or **Emby** to watch (both share the same library).
- Fetches **posters/backdrops/genres** from **TMDB** and **trailers** by scraping `youtube.com` (no YouTube API key).

Access is private over **Tailscale**. The browser talks to nginx on :8123; nginx proxies `/api/*` to the FastAPI container, which holds all secrets.

---

## 2. High-level layout

```
 Browser (Tailnet device)
      │  http://rkm-hp.tail8d5e8.ts.net:8123
      ▼
 ┌──────────────────────────────┐
 │  nginx (web container) :8123 │   serves the React shell (frontend/)
 │  ─ proxies /api/* → api:8000 │
 └──────────────┬───────────────┘
                ▼
 ┌──────────────────────────────┐
 │  FastAPI  api  container     │   uvicorn api.main:app  (modular)
 │  /api/health /config /status │   holds RADARR_KEY, PLEX_TOKEN, EMBY_KEY…
 │  /api/download /search       │
 │  /api/library /plex/thumb    │
 │  /api/quality                │
 └───────┬──────────┬───────────┘
         │          │   read /write
         ▼          ▼
 ┌────────────┐  ┌───────────────────────────────┐
 │ watchlist  │  │  External: Plex·Radarr·Sonarr  │
 │ .json (ro) │  │  TMDB·Emby·qBittorrent·YouTube  │
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
│   │   ├── plex.py radarr.py sonarr.py emby.py tmdb.py youtube.py
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
├── docker-compose.yml  bootstrap.ps1  bootstrap.sh  render_config.py  rkm.ps1
└── README.md  .env (single config)  .env.example (committed template)
```

Run everything from the subdirs: `cd backend && python -m pytest tests/ -q`,
`cd frontend && npm run typecheck && npx vitest run && npm run build`.
Deploy stays at the root (`.\\bootstrap.ps1` / `.\\run-rkm-cinema.ps1`).

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
 Plex · Radarr · Sonarr · Emby · TMDB · qBittorrent · YouTube
```

Rules:
- Routes **never** call external APIs directly or build raw `urllib` calls.
- Services **never** leak secrets; browser never sees keys/URLs (nginx fronts `/api`).
- The `domain/` state machine + resolver are the **single owners** of status and movie/tv rules.

---

## 5. Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service up/down flags (radarr, sonarr, tmdb, plex, emby, jellyfin, qbit) |
| `GET /api/config` | Public-safe booleans + dashboard freshness (never keys/URLs) |
| `GET /api/status` | Per-title state via `MediaStatusService` → `domain.state_machine.resolve_status()`; includes `plexUrl`/`embyUrl` watch links |
| `POST /api/download` | Add movie→Radarr / series→Sonarr via `DownloadService` (title fallback, "pick one" ambiguity) |
| `GET /api/search` | Watchlist + live TMDB search |
| `GET /api/library` | Plex counts + recently-added (Emby fallback); per-item plexUrl/embyUrl/thumb |
| `GET /api/plex/thumb` | Server-side proxy for Plex thumbnails (keeps token secret) |
| `GET /api/quality` | Radarr/Sonarr quality profiles for the download dialog |

---

## 6. Media status state machine

The canonical resolution lives in `domain/state_machine.py::resolve_status`:

```
 Plex has media   → AVAILABLE        (with Plex/Emby watch links)
 else *arr has file → DOWNLOADED
 else qBittorrent active → DOWNLOADING (progress/speed/eta)
 else *arr queue  → DOWNLOADING
 else *arr record exists → REQUESTED ("waiting — indexers down" if health says so)
 else             → NOT_ADDED
```

**Plex is the source of truth** for availability. A title in Plex is `available`
even if its *arr record is stale/missing. `MediaStatusService` gathers the
external facts and feeds them to `resolve_status`; the domain module decides.
The `WatchLinks` value object carries `plex_url`, `plex_key` (numeric ratingKey,
not a URL), and `emby_url` for `available`/`downloaded` titles.

> **Performance guard:** `PlexService.get_all_movies()/get_all_shows()` cache the
> full library scan for **~60s**. The status pass calls `has_media` for every
> watchlist entry; without this cache one `/api/status` request triggered 17 full
> rescans and blew the request window. First scan ~1.3s, cached ~0.2s.

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

## 8. Watch deep-links (Plex / Emby)

Deep-links point **into the local server's own web UI** on the browser-reachable
**Tailscale MagicDNS HTTPS** host — **not** Plex's `app.plex.tv` cloud app.
The cloud app needs account login + remote relay and rarely auto-opens the item;
the server's `/web/index.html` on the Tailnet host opens the item directly with no
relay, using the same scheme the Emby links always used.

- **Plex:** `https://rkm-hp.tail8d5e8.ts.net:32400/web/index.html#!/server/{machineId}/details?key=/library/metadata/{ratingKey}`
  - Machine ID = Plex `machineIdentifier` (`/identity`), cached.
  - `key` is the **raw** `/library/metadata/<rk>` path — **never `%2F`-encoded**
    (encoding broke Plex's hash router). This is the #1 reason old links did nothing.
  - No ratingKey found → fall back to `/web/search?query={title year}`.
- **Emby:** `https://rkm-hp.tail8d5e8.ts.net:8096/web/index.html#!/item?id={itemId}&serverId={serverId}`
  - Item id resolved via Emby search (per-title, cached), server id via `/System/Info/Public`.
- **Browser-reachable base** is config-driven: `PLEX_BROWSER_URL` / `EMBY_BROWSER_URL`
  (optional, defaults to the Tailscale host). LAN `PLEX_URL`/`EMBY_URL` are the
  backend/API addresses and are **never** used to build user links. The builder
  falls back to the documented Tailscale host automatically if unset.
- `plexKey` in the status payload is the **numeric ratingKey** (e.g. `320819`),
  used where a raw key is needed; `plexUrl` is the full deep link.

---

## 9. External integrations

| Service | Responsibility |
|---|---|
| `PlexService` | Library counts, ownership (`has_media`), recently-added, `get_thumb` proxy, library-scan caching (~60s TTL), deep-link builders (`plex_url_for` → Plex **server web UI** on the browser-reachable Tailscale host; `emby_url_for` → Emby web UI), `plex_key_for` (numeric ratingKey) |
| `RadarrService` | Movies, `lookup_movie`, `search_movies` (title fallback), `add_movie`, profiles/queue, indexer health |
| `SonarrService` | Series, `lookup_series`, `search_series` (title fallback), `add_series`, tvdb resolve, profiles/queue |
| `TMDBService` | Movie/show details, posters/backdrops/genres, search |
| `EmbyService` | Emby library counts + deep links (`/web/index.html#!/item?id=..&serverId=..`) |
| `YouTubeService` | Scrape youtube.com for the official trailer (no API key) |
| `QBittorrentService` | Torrent list + download-state (used by status) |
| `TrailerService` | Legacy trailer fallback |
| `WatchlistService` | Atomic watchlist persistence + state validation |
| `MediaStatusService` | Per-entry status via the domain state machine |
| `DownloadService` | Movie/tv routing + add + fallback orchestration |
| `RecommendationService` | Quality gates, Plex/duplicate checks, enrichment, add |

All services accept injectable `config`/`http` (constructor DI) and are unit-tested
with fakes — **no test touches the live LAN**.

---

## 10. Config & data

- **`config/settings.py`** — single `Config` singleton from `/workspace/.env` (+ env overrides). Provides `has_emby()`, `has_tmdb()`, `validate_required()`, etc. **Never returns secrets via `/api/config`.** Exposes browser-reachable `PLEX_BROWSER_URL` / `EMBY_BROWSER_URL` used only for deep-links (fall back to the Tailscale host when unset).
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

- Deploy (RKM-HP / Windows): `.\run-rkm-cinema.ps1` → `docker compose up -d --build`.
- Two containers: `api` (FastAPI modular, holds secrets) + `web` (nginx :8123, static + `/api` proxy).
- **Plex and Emby are both HTTPS-only** over Tailscale (`:32400` / `:8096`); deep-links must use `https://` and target the browser-reachable `PLEX_BROWSER_URL`/`EMBY_BROWSER_URL` host (see §8).

---

## 13. Adding a feature (recommended path)

1. **Business rule (status/movie-tv)?** → put it in `backend/domain/` (state machine or resolver). Wire service gatherers in `backend/services/`.
2. **External integration?** → add a method on the relevant `backend/services/*` client; never in a route.
3. **Route?** → add a thin handler in `backend/api/routes/`, reuse a service, return a typed Pydantic model.
4. **UI?** → update the React shell (`frontend/src/`).
5. **Test it** → add a mockable pytest under `backend/tests/`; run `cd backend && python -m pytest tests/ -q`.
6. No static dashboard rebuild exists any more — the React shell reads the live `/api` (the old `rebuild_dashboard.py` static generator was removed with the legacy app).
7. Deploy with `.\run-rkm-cinema.ps1` (prod) or `.\bootstrap.ps1` (bundled stack); verify `/api/health` + the dashboard.

---

## 14. Testing

- `backend/tests/` cover: domain state machine, media-type resolver, Radarr/Sonarr routing + title fallback + ambiguity, duplicate prevention, error handling, trailer validation, Plex ownership, Plex library-scan caching, **Plex/Emby watch deep-link format** (`tests/test_watch_links.py`), recommendation pipeline, and API endpoints.
- All tests use **injected fakes** — no real LAN, no real API keys required.
- Run: `cd backend && python -m pytest tests/ -q`. **292 tests, all green** (API/e2e modules verified in the container where fastapi is installed).
