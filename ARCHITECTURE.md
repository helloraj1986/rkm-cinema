# RKM Watchlist — Architecture

> **Single codebase.** The monolithic `api.py` has been archived
> (`archive/api_legacy_monolith.py`) and the production backend is now the
> modular FastAPI app: **`uvicorn api.main:app`** (see `Dockerfile`). There is
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
 │  nginx (web container) :8123 │   serves index.html/api.js/app.js/app.css
 │  ─ proxies /api/* → api:8000 │   (static files volume-mounted from repo)
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
watchlist/
├── api/
│   ├── main.py              app factory: CORS, wires all routers
│   ├── models.py            Pydantic request/response models
│   └── routes/              one thin router per concern:
│       health config status download search library quality plex_thumb
├── services/               external integrations + app services
│   ├── base.py              BaseService (DI-ready: config/http injectable)
│   ├── plex.py              Plex: library, ownership, deep-links, thumb proxy
│   ├── radarr.py            Radarr: movies, lookup/add (title fallback), profiles
│   ├── sonarr.py            Sonarr: series, lookup/add (title fallback), tvdb resolve
│   ├── emby.py              Emby client / counts / deep-links
│   ├── tmdb.py              TMDB metadata + artwork
│   ├── youtube.py           YouTube trailer scraping (no API key)
│   ├── trailers.py          Legacy trailer fallback (TVDB/TMDB/oEmbed)
│   ├── qbittorrent.py       qBittorrent torrents + download-state
│   ├── watchlist.py         Watchlist CRUD, atomic writes, state validation
│   ├── media_status.py      MediaStatusService → domain state machine
│   ├── download.py          DownloadService → movie/tv routing + add + fallback
│   └── recommendations.py   Recommendation pipeline (rotation, gates, enrich)
├── domain/                  business layer (no HTTP/FastAPI)
│   ├── enums.py             MediaType, MediaStatus, DownloadResultState
│   ├── models.py            DownloadResult (typed)
│   ├── state_machine.py     resolve_status(): THE state machine + WatchLinks
│   └── resolver.py          resolve_media_type(): single movie/tv resolver
├── core/                    infrastructure
│   ├── http_client.py       shared HTTP client (retry/cache/structured errors)
│   ├── exceptions.py        typed app exceptions
│   └── logging.py           structured logging
├── config/settings.py       centralized env config (singleton, no secret leaks)
├── scripts/                 daily pipeline + rebuild + hygiene scripts
├── tests/                   unit + API tests (mockable, no live LAN)
├── frontend (root):         index.html, api.js, app.js, app.css (volume-mounted)
├── requirements.txt         production backend deps
├── Dockerfile               runs uvicorn api.main:app
├── docker-compose.yml       api + web (nginx) containers
└── archive/                 legacy monolith + old throwaway scripts
```

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

## 8. External integrations

| Service | Responsibility |
|---|---|
| `PlexService` | Library counts, ownership (`has_media`), recently-added, `get_thumb` proxy, deep-link builders (`plex_url_for`, `emby_url_for`) using the Plex machineIdentifier + encoded `/library/metadata/<rk>` key |
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

## 9. Config & data

- **`config/settings.py`** — single `Config` singleton from `/workspace/.env` (+ env overrides). Provides `has_emby()`, `has_tmdb()`, `validate_required()`, etc. **Never returns secrets via `/api/config`.**
- **`watchlist.json`** — source of truth; volume-mounted into the container at `/app/watchlist.json`. `WatchlistService` auto-resolves the correct path (container vs sandbox).
- **`dashboard-data.json`** — published snapshot the SPA loads (built by `scripts/rebuild_dashboard.py`).
- **`.env`** — canonical at `/workspace/.env`, never committed; see `.env.example`.

---

## 10. Frontend (app.js → api.js)

- `api.js` — centralized API client (`API.getJSON`, `API.download`, `API.getStatus`, …). Loaded before `app.js` as a plain global.
- `app.js` — rendering, state, UI. Delegates ALL `/api/*` and `/dashboard-data.json` calls to `API`. No direct `fetch` to backend endpoints anywhere else.
- Served statically by nginx; **volume-mounted** so UI changes need no Docker rebuild.

---

## 11. Deployment

- Deploy (RKM-HP / Windows): `.\setup-watchlist.ps1` → `docker compose up -d --build`.
- Two containers: `api` (FastAPI modular, holds secrets) + `web` (nginx :8123, static + `/api` proxy).
- Emby on :8096 is **HTTPS-only** over Tailscale; Emby links must use `https://`.

---

## 12. Adding a feature (recommended path)

1. **Business rule (status/movie-tv)?** → put it in `domain/` (state machine or resolver). Wire service gatherers in `services/`.
2. **External integration?** → add a method on the relevant `services/*` client; never in a route.
3. **Route?** → add a thin handler in `api/routes/`, reuse a service, return a typed Pydantic model.
4. **UI?** → update `app.js` (+ `api.js` if it's a new API call). Volume-mounted, no rebuild.
5. **Test it** → add a mockable test under `tests/`; run `python -m pytest tests/ -q`.
6. If the dashboard needs fresh data, run `scripts/rebuild_dashboard.py`.
7. Deploy with `.\setup-watchlist.ps1`; verify `/api/health` + the dashboard.

---

## 13. Testing

- `tests/` cover: domain state machine, media-type resolver, Radarr/Sonarr routing + title fallback + ambiguity, duplicate prevention, error handling, trailer validation, Plex ownership, recommendation pipeline, and API endpoints.
- All tests use **injected fakes** — no real LAN, no real API keys required.
- Run: `python -m pytest tests/ -q` (from the repo root). **47 tests, all green.**
