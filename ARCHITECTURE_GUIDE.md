# RKM Cinema (rkm-cinema) — Architecture & Agent Reference

> **For a new agent starting on this codebase.** This is the *current* state of the
> code as written today (Sep 2026). The root `README.md` and `ARCHITECTURE.md` are
> **stale** — they predate the SQLite persistence flip, the `suggest` UI, the
> canonical service subpackages (`library/`, `acquisition/`, `recommendation/`,
> `reconciliation/`), the job scheduler, and half the API surface. Trust **this
> document**, and verify against the code. Where a doc and the code disagree, the
> **code wins**.
>
> Everything here was ground-truthed by reading the actual files.

---

## 1. TL;DR — what this is

A **self-hosted media discovery + download dashboard** ("your personal cinema"). It:

- Shows what's in your **Plex** library (Plex is the **source of truth** for availability) and Emby (shares the same library).
- Lets you **request** movies/series, which are added to **Radarr** (movies) / **Sonarr** (TV) and downloaded via **qBittorrent**.
- Tracks every title through a lifecycle: `requested → downloading → downloaded → available → recommended`.
- Produces deep "Watch on Plex / Watch on Emby" links (server web UI over Tailscale, **not** the cloud apps).
- Fetches posters/backdrops/genres from **TMDB** and official trailers by **scraping youtube.com** (no YouTube API key).
- Has a **"Suggest"** tab: user filters → TMDB discover → recommendations.

Access is private over **Tailscale**. Browser → nginx `:8123` → reverse-proxies `/api/*` → FastAPI container which holds all secrets.

**Stack:** FastAPI (Python 3.11) + vanilla-JS SPA (no framework, no build step) + SQLite/JSON persistence, on Docker Compose behind nginx. No auth on the API (private LAN/Tailnet only).

---

## 2. Deployment topology (containers, ports, volumes, secrets)

Deploy is one command on the Windows host (RKM-HP): `.\setup-watchlist.ps1` → `docker compose up -d --build`.

```
 Browser (any Tailnet device)
      │  http://rkm-hp.tail8d5e8.ts.net:8123
      ▼
 ┌──────────────────────────────────────────────┐
 │ web  (nginx:alpine)  container "rkm-cinema"   │  publishes 0.0.0.0:8123 -> 80
 │  serves index.html, api.js, app.js, app.css   │  (volume-mounts repo ./ read-only)
 │  + /dashboard-data.json (static)             │
 │  proxies /api/* -> api:8000                  │
 └───────────────┬──────────────────────────────┘
                 ▼
 ┌──────────────────────────────────────────────┐
 │ api  (rkm-cinema-api)  container              │  EXPOSE 8000 (internal only)
 │  CMD: uvicorn api.main:app --host 0.0.0.0 --port 8000 │
 │  holds ALL secrets (RADARR_KEY, PLEX_TOKEN...)│
 │  reads/writes /workspace/media (writable dir) │  <- data mount
 └───────┬──────────────────────┬───────────────┘
         │                      │
         ▼                      ▼
  /workspace/media/        Plex · Radarr · Sonarr · TMDB ·
  watchlist.db (SQLite)    YouTube · Emby · qBittorrent
  watchlist.json (mirror)
```

**Key files:**
- `Dockerfile` — `python:3.11-slim`; copies `api services domain core config infrastructure application jobs scripts`; `pip install -r requirements.txt`; `HEALTHCHECK` hits `/api/health`; `CMD uvicorn api.main:app`.
- `docker-compose.yml` — two services on a shared `rkm` bridge network:
  - **api**: `build: .`, `env_file: [../../.env]`, `expose: 8000`, healthcheck `/api/health`.
  - **web**: `nginx:alpine`, `ports: ["0.0.0.0:8123:80"]`, mounts `./:/usr/share/nginx/html:ro` + `./nginx/default.conf`.
- `nginx/default.conf` — SPA served no-cache; `location /api/ { proxy_pass http://api:8000; ... }`.

**The one critical volume** (this bug was already hit — don't regress it):

```yaml
volumes:
  - ../../media:/workspace/media:rw   # on the api service
```

It is a **writable DIRECTORY** mount, resolving to `/workspace/media` (compose lives in `projects/rkm-cinema`, so `../../` is `/workspace`). **Do not** change it to a single-file `:ro` mount on `watchlist.json`: repo saves are atomic `tmp + os.replace`, which fails on a read-only file, and on Docker Desktop a single-file bind mount pins the file's original inode so the container silently keeps reading a stale copy. The API's repository is picked to read `/workspace/media/watchlist.db` (or `.json`).

**Secrets:** injected via `env_file: ../../.env` (the canonical `/workspace/.env` = `D:\hermes_agent\hermes-workspace\.env`). `media/.env` is a WSL symlink — **Docker Desktop can't follow WSL symlinks**, so compose points at the real file. Secrets never reach the browser (nginx fronts `/api`).

⚠️ **No `.dockerignore` exists** — `__pycache__`, `*.bak*`, `archive/` bloat the build context. There are ~7 dead `app.js.bak*` files at the root too.

---

## 3. Repository layout (annotated, current)

```
/workspace/projects/rkm-cinema/
├── config/
│   ├── settings.py             # THE Config singleton (env → URLs, keys, TTLs, store switch)
│   └── recommendations.yaml    # Quality criteria (gates) — config, NOT Python  (§22)
├── core/                       # infrastructure primitives
│   ├── http_client.py          # urllib client: timeout, cache, retry, typed errors
│   ├── cache.py                # thread-safe TTLCache (monotonic clock)
│   ├── exceptions.py           # RKMError hierarchy + per-service *UnavailableError
│   └── logging.py              # structured/log-json setup, LogContext
├── domain/                     # 🧠 pure business layer — no HTTP, single source of truth
│   ├── enums.py                # MediaType, MediaStatus, DownloadResultState, RequestMediaState
│   ├── identity.py             # MediaIdentity → canonical media_id (<type>:<prov>:<id>)
│   ├── status.py               # ⭐ resolve_status() THE state machine + StatusFacts/Result/Snapshot
│   ├── state_machine.py        # ⚠️ compatibility RE-EXPORT shim of status.py (§43)
│   ├── resolver.py             # resolve_media_type(): the one movie-vs-TV authority
│   └── models.py               # DownloadResult (typed dataclass)
├── infrastructure/database/
│   ├── repository.py           # WatchlistRepository ABC + Json & Sqlite impls + build_repository()
│   └── db.py                   # SQLite Database wrapper (thread-local conns, WAL, FK on)
├── application/commands/
│   └── request_media.py        # idempotent request command (§15) — the only way into acquisition
├── services/                   # external integrations + app services
│   ├── base.py, plex.py, radarr.py, sonarr.py, emby.py   # low-level HTTP clients (+Emby facade)
│   ├── tmdb.py, youtube.py, trailers.py, qbittorrent.py  # providers
│   ├── watchlist.py, media_status.py, download.py, health.py, plex_check.py, recommendations.py
│   ├── library/                # ⭐ LibraryService + PlexLibraryProvider + EmbyLibraryProvider + WatchLinkResolver
│   ├── acquisition/            # ⭐ AcquisitionService (routes movie→Radarr/show→Sonarr) + providers
│   ├── recommendation/         # ⭐ RecommendationManager + CandidateGenerator + CriteriaEngine + Ranker
│   └── reconciliation/         # ⭐ Reconciler — the single fact-gatherer → MediaSnapshot
├── jobs/                       # scheduled work
│   ├── base.py                 # JobRunner (records runs in job_runs)
│   ├── reconcile.py            # reconcile job (status-only)
│   ├── daily_watchlist.py      # recommendation job
│   ├── add_watchlist.py        # ⚠️ legacy external-script wrapper (sys.argv-mutating)
│   └── scheduler.py            # in-process daemon scheduler (opt-in via WATCHLIST_SCHEDULER)
├── api/                        # FastAPI
│   ├── main.py                 # create_app(): CORS wildcard, 15 routers under /api
│   ├── models.py
│   └── routes/                 # health config status download search library quality
│                               #   plex_thumb suggest media watchlist reconcile jobs
├── scripts/                    # host-side cron + maintenance (hardcoded /workspace paths)
│   ├── add_watchlist_cron.py   # ⭐ THE live cron driver (6am, Plex-gated auto-add)
│   ├── rebuild_dashboard.py    # ⭐ THE dashboard builder (writes dashboard-data.json + index.html)
│   ├── daily_recommendations.py, auto_complete.py, migrate_json_to_sqlite.py, ...
├── tests/                      # 22 pytest files + 3 .mjs frontend harnesses
├── index.html / api.js / app.js / app.css   # the SPA (volume-mounted, no rebuild on change)
├── dashboard-data.json         # generated snapshot the SPA loads
├── watchlist.json              # ⚠️ STALE mirror — the live store is SQLite
├── Dockerfile / docker-compose.yml / nginx/default.conf / setup-watchlist.ps1
├── requirements.txt
├── ARCHITECTURE.md / README.md / PROGRESS.md  # ⚠️ stale (PROGRESS is huge; README/ARCH predate recent phases)
└── archive/                    # legacy monolith api_legacy_monolith.py + old throwaway scripts
```

> ⭐ = the canonical modern seam. **Add new code to these, not the legacy top-level equivalents.**

---

## 4. Config & environment (`config/settings.py`)

Singleton via `@lru_cache(maxsize=1) def get_config()`. One `Config` instance process-wide.

**Resolution order (gotcha):** build a dict, then
1. read the **first existing** CSV-path `.env` file from `["/workspace/.env", "/app/.env"]` (host `/workspace/.env` = `D:\.env`);
2. **real OS env vars override `.env` ONLY for keys in `_get_all_keys()`**.

**Full env-key allow-list (`_get_all_keys()`):**
`MEDIA_HOST, RADARR_URL, RADARR_API_KEY, SONARR_URL, SONARR_API_KEY, PLEX_URL, PLEX_TOKEN, TMDB_API_KEY, TVDB_API_KEY, JELLYFIN_URL, JELLYFIN_API_KEY, PROWLARR_URL, PROWLARR_API_KEY, QBITTORRENT_URL, RADARR_QUALITY_PROFILE_ID, SONARR_QUALITY_PROFILE_ID, PLEX_BROWSER_URL, EMBY_BROWSER_URL, WATCHLIST_STORE, WATCHLIST_DB_PATH, WATCHLIST_SCHEDULER, RECONCILE_INTERVAL_MIN, DAILY_JOB_HOUR, TMDB_CACHE_TTL, PLEX_SCAN_TTL`

**Values / defaults:**
- Defaults (`MEDIA_HOST` default `192.168.65.254`): `RADARR_URL=http://{host}:7878`, `SONARR_URL=:8989`, `PLEX_URL=:32400`, `QBITTORRENT_URL=:1701`. URLs are `.rstrip("/")`'d.
- `TMDB_CACHE_TTL` default **21600 s (6h)**; `PLEX_SCAN_TTL` default **3600 s (1h)**.
- `WATCHLIST_STORE` = `json|sqlite` (default `json`; **any invalid value silently reverts to `json`**). **In production `/workspace/.env` sets `WATCHLIST_STORE=sqlite` and `WATCHLIST_DB_PATH=/workspace/media/watchlist.db`** — SQLite is the live store.
- `WATCHLIST_SCHEDULER` truthy ∈ `{"1","true","yes","on"}` (default off). `RECONCILE_INTERVAL_MIN` default 10. `DAILY_JOB_HOUR` default 18.
- `validate_required()` → missing of `RADARR_API_KEY`, `SONARR_API_KEY`, `PLEX_TOKEN`.
- Helper booleans: `has_tmdb()`, `has_tvdb()`, `has_jellyfin()`, `has_emby()`, `has_youtube()`, `has_prowlarr()`.

**Gotchas:**
- `EMBY_URL`, `EMBY_API_KEY`, `YOUTUBE_API_KEY` are **read from `.env` but are NOT in `_get_all_keys()`** — a real env var won't override them; also `EMBY_URL` is not URL-normalized.
- Live `/workspace/.env` has `MEDIA_HOST=http://192.168.65.254` (with scheme). Harmless because every service URL is explicitly set, but if you derive a fallback URL from `MEDIA_HOST` it'd double up the scheme (`http://http://...`).

---

## 5. Domain vocabulary — the ground rules

The `domain/` package is declared **the single source of truth** for what a watchlist entry *is* and how its lifecycle transitions. No service/route may redefine these.

### 5.1 Enums (`domain/enums.py`)
- `MediaType`: `MOVIE="movie"`, `TV="tv"`. `from_request()` case-insensitive (`movie|film|radarr`→MOVIE; `tv|series|show|sonarr`→TV). `MediaType.arr_service` → `"sonarr"` if TV else `"radarr"`.
- `MediaStatus`: `NOT_ADDED, REQUESTED, DOWNLOADING, DOWNLOADED, AVAILABLE, RECOMMENDED, ERROR, AMBIGUOUS`.
- `DownloadResultState`: `REQUESTED, ALREADY_EXISTS, UNAVAILABLE, AMBIGUOUS`.
- `RequestMediaState`: `AVAILABLE, ALREADY_REQUESTED, REQUESTED, AMBIGUOUS, NOT_CONFIGURED, PROVIDER_UNAVAILABLE`.

### 5.2 Identity (`domain/identity.py`)
> **`title` is never the primary key.** A stable identity = **provider ID (TMDB > IMDb > TVDB) + media type**.

- `MediaIdentity(media_type, tmdb_id, imdb_id, tvdb_id)` — frozen dataclass; IDs coerced at construction (`"605"`, `605`, `605.0` → `605`; imdb prefixed with `tt`).
- `.media_id` → canonical string `"<type>:tmdb:<id>"` else `"<type>:imdb:<tt…>"` else `"<type>:tvdb:<id>"` else raises. e.g. `movie:tmdb:603`, `movie:imdb:tt0133093`, `series:tmdb:1396`.
- `.preferred()` → best id for *arr lookups (`tmdb:<id>` / raw imdb / `tvdb:<id>`).
- `parse_media_id(media_id)` → reverse; strict 3-part; `series|show|tv`→TV; raises on bad input. **Ambiguous/unresolvable identity is an explicit error, never a silent guess.**

### 5.3 Status state machine (`domain/status.py` ⭐)
`resolve_status(facts)` is **pure** (no HTTP). `domain/state_machine.py` is only a **re-export shim** — import from `domain.status`.

Resolution **exact order** — library availability always wins:

```
in_plex            → AVAILABLE      (+ Plex/Emby watch links, plexKey)
arr_has_file       → DOWNLOADED     ("In library")
qbit_active        → DOWNLOADING    (progress/speed/eta)
qbit_done          → DOWNLOADED     ("Downloaded — awaiting import")
arr_queue_active   → DOWNLOADING    (progress=arr_queue_percent)
arr_record_exists  → REQUESTED      ("Waiting — search indexers down" if indexer_issue)
else               → NOT_ADDED
```

Key dataclasses: `StatusFacts` (gather input), `StatusResult` (API/UI output), `MediaSnapshot` (canonical per-item object routes render — **routes never re-derive the state machine**), `Capabilities` (`can_download = status∈(NOT_ADDED,REQUESTED,AMBIGUOUS)`; `can_watch = AVAILABLE`). `allowed_transitions()` encodes conservative lifecycle moves.

> **A watch-link build failure is a *capability* problem and must never flip an AVAILABLE title to NOT_REQUESTED.** Availability is decided by `resolve_status` alone.

### 5.4 Media-type resolver (`domain/resolver.py`)
`resolve_media_type(...)` is the single authority: explicit `type` → watchlist `isSeries` → *arr lookup → default movie.

---

## 6. Persistence

### 6.1 The store switch
`build_repository(store)` in `infrastructure/database/repository.py` selects the backing store:
- `WATCHLIST_STORE=json` → `JsonWatchlistRepository` (atomic `tmp`+`os.replace`, path probes `/app/watchlist.json` then `/workspace/media/watchlist.json`; recommendation history in a **sidecar** `recommendations_history.json`, cap 3000, idempotent per `media_id`).
- `WATCHLIST_STORE=sqlite` → `SqliteWatchlistRepository` over `Database` (thread-local conns, `foreign_keys=ON`, WAL). Tables: `media`, `watchlist`, `job_runs`, `recommendations`. One row per entry keyed by `media_id`; rich fields in a JSON `payload` column; meta in a reserved `__meta__` row. `save()` is **DELETE-then-upsert full-replace** (idempotent, not incremental).

**In production today: SQLite is the authoritative store** (`WATCHLIST_STORE=sqlite`, `/workspace/media/watchlist.db` exists). The checked-in `watchlist.json` (7 entries) and `dashboard-data.json` (296 cards) are **stale mirror/old snapshots** — read the DB or a rebuilt dashboard file for truth.

### 6.2 watchlist.json entry shape (flat, camelCase)
Top level: `{ rotation_index, rotation[12], pending[], recommended[], updated }`. Per entry:
`title, year, category, lang, rt, imdb, isSeries, imdbId, tmdbId, cert, snippet, cast[], director, poster, trailerId, trailerTitle, added` (+ optional legacy `trailer` = a YouTube **search URL** when no trailerId resolved — 2 entries have it).

⚠️ Two identity notions coexist: `WatchlistService` **dedups by `imdbId`**; SQLite **keys storage by `media_id` preferring tmdb**. Persisted app entries use `snippet`/`tmdb_overview`/`tmdb_score`; the **dashboard projection** writes `overview`/`tmdbScore` — the frontend normalizes both.

### 6.3 dashboard-data.json (what the SPA loads)
Top keys: `app, version:2, generatedAt, updated, heroMode, refreshCron:"0 18 * * *", rotation, entries[]`. Each card (28 fields): `imdbId, tmdbId, tvdbId, title, year, type("movie"|"tv"), category, genres[], lang, cert, rt, imdb, tmdbScore(float), overview, cast[], director, runtime, poster, backdrop, trailerId, trailerTitle, trailerUrl(embed), added, source, state, detail, progress`. Built by `scripts/rebuild_dashboard.py`; guards against publishing 0 cards or missing `app.css`/`app.js`.

### 6.4 SQLite migration
`scripts/migrate_json_to_sqlite.py` is one-time + idempotent: JSON→SQLite, back up existing DB, carry recommendation seen-set, round-trip-verify counts, re-export watchlist.json as a mirror, rebuild dashboard. Warns if `WATCHLIST_STORE != "sqlite"`. Already run (migration complete).

---

## 7. The services layer — ⚠️ read this before touching it

There are **two overlapping design generations**. The modern spec establishes **seam subpackages**; several top-level modules live on only as backward-compatible facades, low-level HTTP clients the providers wrap, or genuine legacy orchestration. **This table is the answer to "which one do I edit?"** (verified by grepping real import sites).

| Concern | Legacy top-level | Modern seam | **Use this** |
|---|---|---|---|
| Plex | `plex.py` `PlexService` | `library/plex.py` `PlexLibraryProvider` | **Provider** (wraps `PlexService` as low-level client). One breach: `suggest.py` builds `PlexService` directly. |
| Emby | `emby.py` `EmbyService` | `library/emby.py` `EmbyLibraryProvider` | **Provider.** `EmbyService` is a **dead BC-facade** (0 app imports). |
| Library | (URL building in `plex.py`) | `library/service.py` `LibraryService` | **LibraryService** — unified facade (Plex+Emby = one logical library). |
| Radarr | `radarr.py` `RadarrService` | `acquisition/radarr.py` | **Provider** (routes call it). `RadarrService` stays live as low-level client + legacy `auto_complete.py`. |
| Sonarr | `sonarr.py` `SonarrService` | `acquisition/sonarr.py` | **Provider.** `SonarrService` stays live as low-level client. |
| Download | `download.py` `DownloadService` | `acquisition/service.py` `AcquisitionService` | **AcquisitionService** (routed). `DownloadService` is the thin legacy orchestrator over it. |
| Status | `media_status.py` `MediaStatusService` | `reconciliation/reconciler.py` `Reconciler` | **Reconciler.** `MediaStatusService` is a **dead BC-shim** (no app import). |
| Recommendations | `recommendations.py` `RecommendationService` | `recommendation/*` `RecommendationManager` + generator/criteria/ranker | **Manager** is the canonical pipeline. `RecommendationService` is still **live** as the enrichment+add completion used by `jobs/daily_watchlist.py` and `scripts/...` and `suggest.py`. |
| Plex check | `plex_check.py` | (none) | **Dead in app** — script-only utility (`verify_plex.py`). |

**`services/__init__.py` is the aggregator** — it re-exports every public name (including subpackage ones), so `from services import PlexLibraryProvider, LibraryService, AcquisitionService, ...` works even for names that aren't top-level modules. Many callers depend on this single surface.

### 7.1 The modern seams (⭐ — where new code goes)
- **`LibraryService`** (`services/library/service.py`) — providers are **views of ONE logical library**; `find()` returns first match (single AVAILABLE), `has()` bool gate, `find_all()` per-provider (Plex+Emby links), `watch_links()` → `WatchLinkResolver`. Degraded-state handling: 5-min fresh cache + **24h** `LIBRARY_CONFIRMATION_TTL` fallback confirmation when providers are down. Provider `.match()` matches by stable identity (guid/ratingKey/itemId/imdb/tmdb/tvdb) first, title+year only as fallback.
- **`AcquisitionService`** (`services/acquisition/service.py`) — **the** movie→Radarr / show→Sonarr router (`provider_for(media_type)`). `request()` idempotent (already-set → `already_exists`), `get_status()`, `quality_profiles()`, `indexer_issue()`, `preload()` (batch warm for reconcile), `invalidate()` on writes. `build_acquisition_service(config=...)` is the DI factory. Providers wrap the low-level `RadarrService`/`SonarrService`.
- **`Reconciler`** (`services/reconciliation/reconciler.py`) — the **single fact-gatherer**: identity → LibraryService + *arr + qBittorrent → `StatusFacts` → `resolve_status` → `MediaSnapshot`. Owns its dependency graph (mockable, LAN-free). **Process-level reconcile cache: keyed on watchlist-file mtime, 300s TTL** — `/api/status` and `/api/watchlist` use `compute_cached()`, `/api/reconcile` uses uncached `compute()`. A pure *arr write doesn't bump the file mtime, so `POST /api/media/{id}/request` explicitly clears the cache on success.
- **`RecommendationManager`** (`services/recommendation/manager.py`) — pipeline: candidate sources → normalize (`CandidateGenerator`) → `CriteriaEngine` (config gates) → seen-set dedup (history) → library gate → watchlist gate → `ranker.rank()` → persist. Idempotent: re-running never re-adds. Produces `RecommendationRunResult` with per-stage counts.
  - **`CriteriaEngine`** (`criteria.py`) reads `config/recommendations.yaml` (NOT hardcoded). Movie/Series gates: `min_tmdb_rating 7.0`, `min_vote_count 300/150`, `min_imdb 7.0/7.5`, `min_rt 75/80`, `rt_any:true`, genres .exclude `["horror"]` for movies, plus score weights (tmdb .6 / imdb .3 / recent_bonus .1). A `tmdb_score==0` or both-imdb-and-rt-unknown is treated as **unknown** (gate skipped), so TMDB-discover-only candidates can pass on TMDB rating alone. Failing candidates cap score at 49.9.
  - **`CandidateGenerator`** (generator.py) — sources + normalizes candidates (supersedes the stub `find_candidates()` in top-level `recommendations.py` which returns `[]`).

### 7.2 Caching summary (no retries anywhere; resilience = caching + fail-safe)
| Source | Cache TTL |
|---|---|
| Plex sections | 300 s |
| Plex full-library scan | `PLEX_SCAN_TTL` (default 3600 s) |
| Radarr/Sonarr movies/series/queue | 45 s |
| Radarr/Sonarr profiles / roots / langs | 600 s |
| *arr indexer health | 120 s |
| TMDB metadata | `TMDB_CACHE_TTL` (default 21600 s / 6 h) |
| qBittorrent torrents | 30 s |
| Library find | 300 s fresh + 24 h degraded fallback |
| Reconcile (`compute_cached`) | 300 s (mtime-invalidated) |

### 7.3 Low-level clients (live, wrapped)
- `RadarrService`/`SonarrService` — v3 HTTP clients, `X-Api-Key`, typed DTOs, lookup by imdb→tmdb/tvdb with **title(+year) fallback**, `add_*` returns `ambiguous` rather than guessing, `_http_cache` + typed caches, `_invalidate_after_write()`.
- `TMDBService` — `api.themoviedb.org/3`, IMDB rating via **OMDb public free key** (`trilogy`), `get_show_external_ids()` used by acquisition to resolve tmdb-only series ids (lighter than full detail; immune to the Sonarr lookup timeout).
- `YouTubeService` — **scrapes** `youtube.com/results` (`ytInitialData` JSON parse + heuristic), no API key; `validate_trailer` regex `[A-Za-z0-9_-]{11}`; embed URL builder.
- `QBittorrentService` — torrent list/progress (no auth on this setup), 30s cache.
- `WatchlistService` — `load()`/`save()`/state validation/`move_to_recommended()`; dedups by `imdbId`.

---

## 8. Jobs & scheduling

- **`JobRunner`** (`jobs/base.py`) — wraps any function, records each run in `job_runs`.
- **`ReconcileJob`** — status-only refresh.
- **`DailyWatchlistJob`** — recommendation generation (feeds watchlist).
- **`JobScheduler`** (`jobs/scheduler.py`) — in-process **daemon thread**, opt-in via `WATCHLIST_SCHEDULER=true`. Runs reconcile every `RECONCILE_INTERVAL_MIN` (10 min) and the daily job once/day at `DAILY_JOB_HOUR` (18). Started from FastAPI `on_event("startup")` via `start_if_enabled`.
- **`add_watchlist.py`** — ⚠️ legacy/unexported: mutates global `sys.argv`, shells out to `scripts/add_watchlist_cron.py` (which is why `scripts/` is COPY'd into the image).

> **In production the in-container scheduler is OFF** (`WATCHLIST_SCHEDULER` is unset in `/workspace/.env`). The actual driver is the **host Hermes cron job** `1965aeb4af2e` ("RKM Watchlist auto-add", **`0 6 * * *` AEST, last status OK**), which runs `python3 scripts/add_watchlist_cron.py`. That's the daily auto-add. (`scripts/auto_complete.py` and `scripts/daily_recommendations.py` are the older documented paths; `daily_recommendations.py` is largely a **scaffold** — `load_candidates_from_skill()` always returns `[]`.)

---

## 9. API surface (15 routers / 19 endpoints, all under `/api`)

| # | Method | Path | Purpose / called service |
|---|--------|------|--------------------------|
| 1 | GET | `/api/health` | Per-service health + freshness → `HealthChecker` + `WatchlistService` |
| 2 | GET | `/api/config` | Public-safe booleans (acquisition facade health, plex, tmdb, jellyfin) + watchlist meta |
| 3 | GET | `/api/status` | **Legacy** per-title state → `Reconciler.compute_cached()` (frontend fallback only) |
| 4 | POST | `/api/download` | **Legacy** add → `DownloadService`; 502/404(ambiguous)/503(not configured) |
| 5 | GET | `/api/search?q=` | Watchlist substring + live TMDB `/search/multi` (urllib, 10s) |
| 6 | GET | `/api/library` | Plex primary → Emby fallback counts/recent via `LibraryService` |
| 7 | GET | `/api/quality` | Radarr+Sonarr quality profiles via `AcquisitionService` |
| 8 | GET | `/api/plex/thumb?path=&width=` | ⭐ Proxy Plex artwork (token stays server-side) → raw image bytes; 404 on missing/bad |
| 9 | POST | `/api/suggest` | ⭐ Filters → TMDB discover, deduped, movie/TV interleaved, library-owned filtered out |
| 10 | POST | `/api/suggest/add` | ⚠️ **STUB** → `{"ok": False, "message": "Not implemented"}` (no-id variant) |
| 11 | POST | `/api/suggest/add/{tmdb_id}` | ⭐ Add a discovered title → `RecommendationService` + `WatchlistService` |
| 12 | GET | `/api/suggest/detail/{tmdb_id}` | ⭐ Card-click detail (full TMDB + IMDb rating), on-demand |
| 13 | GET | `/api/media/{media_id}` | ⭐ §18 resource (status+capabilities+watch links) → `Reconciler.get_snapshot()` |
| 14 | POST | `/api/media/{media_id}/request` | ⭐ Idempotent acquire → `request_media` command; 503/502/409/500; clears reconcile cache |
| 15 | GET | `/api/watchlist` | ⭐ Every entry as a §18 resource (cached) — the frontend's primary feed |
| 16 | POST | `/api/reconcile` | ⭐ Force **uncached** full reconcile |
| 17 | GET | `/api/jobs?limit=` | List recent `job_runs` |
| 18 | POST | `/api/jobs/{name}/run` | Trigger `daily_watchlist`/`reconcile`/`add_watchlist`; 404 unknown |

**Cross-cutting facts:**
- `docs_url=None, redoc_url=None` — **no Swagger/OpenAPI UI**.
- **CORS wildcard** (`allow_origins=["*"]`) + **no auth** on any route. Private-Tailnet-appropriate, but any origin can read the watchlist and trigger downloads/downloads if exposed.
- Two error styles coexist: legacy routes raise `HTTPException` (404/502/503); §18/suggest routes return in-body `ok`/`state` flags (and only HTTP for failure states: 409/502/503/500, 404 job). `api.js` `postJSON` parses `detail || message`.
- `api/routes/__init__.py`'s `__all__` is **stale** — lists only the 8 legacy routers, not `suggest/media/watchlist/reconcile/jobs` (main.py imports them directly).

**What the frontend actually calls** (from `api.js` + `app.js`): `GET /api/watchlist` (60s poll + refresh), `GET /api/status` (fallback), `POST /api/media/{id}/request`, `POST /api/download` (legacy fallback), `GET /api/config`, `GET /api/library`, `POST /api/reconcile` (defined, unused by app.js), `POST /api/jobs/add_watchlist/run` (refresh button inline), `POST /api/suggest`, `GET /api/suggest/detail/{id}`, `POST /api/suggest/add/{id}` (inline), `GET /static /dashboard-data.json`. `/api/plex/thumb` is hit as an `<img src>` proxy. Unused-by-UI methods: `getHealth`, `getQuality`, `getJobs`, `getMedia`, `reconcile`.

---

## 10. Application command (`application/commands/request_media.py`)
The **only way into the acquisition backend**. `request_media(media_id)` — idempotent, library-wins (→ `AVAILABLE` if already owned), explicit `AMBIGUOUS`, clears caches on success, `NOT_CONFIGURED` when no provider for the type. Returned `RequestMediaState` drives `POST /api/media/{id}/request` HTTP codes.

---

## 11. Frontend (vanilla JS SPA, no build step)

**Asset order in `index.html`** (also written to `dashboard.html`): `app.css` → `<div id="app">` → `api.js` (deferred) → `app.js` (deferred). `defer` guarantees api.js before app.js.

**`api.js`** (`window.API`, IIFE, all same-origin):
- Primitives `getJSON(url)` / `postJSON(url, body)` (parses `detail||message`, attaches `err.status`).
- `mediaIdOf(entry)` — mirrors backend identity rule.
- Phase-10 resource methods: `getWatchlist()`, `getMedia(id)`, `requestMedia(mediaId)`, `reconcile()`, `getJobs()`.
- Legacy fallback: `getStatusLegacy()`, `downloadLegacy(entry)`.
- Suggest: `suggest(filters)`, `suggestDetail(tmdbId, mediaType)`.
- Shared: `getConfig()`, `getLibrary()`, `getHealth()`, `getQuality()`, `search(q)`, `getDashboardData()` (fetches `/dashboard-data.json` — **not** under `/api`).

**`app.js`** (1844 lines) — state: `DATA` (dashboard JSON), `RES` (media_id→resource), `LEGACY_STATUS`, `USES_RESOURCE_API`, `INDEXER_ISSUE`, `LIB`, `SERVICES`, `currentView`, `heroOverride` (localStorage `rkm_hero`), `viewFilters`, suggest state + localStorage `rkm_suggest_history` (last 10). Views routed by `location.hash` → `VIEWS = {discover, suggest, movies, tv, watchlist, downloaded, library}`.
- `refreshStatus()` — `API.getWatchlist()` (primary) → fills `RES`, sets `USES_RESOURCE_API=true`; falls back to `getStatusLegacy()`.
- `postDownload(entry)` — `USES_RESOURCE_API ? API.requestMedia(mediaIdOf(entry)) : API.downloadLegacy(entry)`.
- `st(entry)` normalizes a resource to `{state,service,detail,progress,speed,eta,capabilities,watch,plexUrl,embyUrl,...}`. Predicates `canWatch`/`canDownload`/`isDownloaded`/`isBusy`.
- Renders: discover rows (`Tonight's Picks`, new, Highly Rated, Hidden Gems, Critically Acclaimed, top categories, per-director), hero, watchlist (chips + sort), downloaded, library, suggest grid, modal detail + trailer iframe. Lazy-grid infinite scroll (page 36) via `IntersectionObserver`.
- Download button is capability-driven (`downloadButton`): can_watch → Plex/Emby/Watch-Now links; downloaded→disabled Available; requested→disabled Requested; downloading→blue progress; can_download→gold "Download".

---

## 12. How to test

```bash
cd /workspace/projects/rkm-cinema
python -m pytest tests/ -q          # 22 pytest files, ~216 test functions, all mocked (no live LAN)
node tests/phase25_suggest_frontend.test.mjs   # frontend harnesses (node, no framework)
# also: phase11_frontend.test.mjs, phase18_frontend.test.mjs
```

`requirements.txt` = `fastapi>=0.110, uvicorn[standard]>=0.29, pydantic>=2.6, requests>=2.31, PyYAML>=6.0`. No SQLite driver (stdlib `sqlite3`), no pytest pin. The `.mjs` files load `api.js`/`app.js` in a `vm` sandbox and `exit` nonzero on failure.

---

## 13. Development workflow (how to add a feature — read this)

1. **Business rule (status / movie-vs-tv)?** → `domain/`. Wire fact-gatherers under `services/*`.
2. **New external integration?** → extend the relevant `services/` provider (Plex/Emby = `services/library/*`; *arr = `services/acquisition/*`; else the low-level client). **Never** in a route.
3. **New endpoint?** → add a thin handler in `api/routes/`, reuse a service, return a typed Pydantic model, register in `main.py`.
4. **UI?** → edit `app.js` (+ `api.js` if a new API call). **Volume-mounted — no Docker rebuild needed**, just refresh the browser.
5. **Persist something?** → go through `WatchlistRepository` (`build_repository()`), **never** touch the DB/file directly.
6. **Test it** → add a mockable test under `tests/`; run `python -m pytest tests/ -q`.
7. **Regenerate the dashboard** → `python3 scripts/rebuild_dashboard.py`.
8. **Deploy** → on RKM-HP: `cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema && .\setup-watchlist.ps1`. Verify `/api/health` and the dashboard.

---

## 14. Gotchas & landmines (the ones that actually bite)

1. **Docs are stale.** README/ARCHITECTURE omit the entire modern seam + suggest + SQLite + scheduler + half the endpoints. This doc is current; code wins.
2. **Two service generations.** Don't "fix" a dead seam (`EmbyService`, `MediaStatusService`, `plex_check.py`, the Emby helpers inside `services/plex.py`). Edit the providers/facades. Cleaning up the dead shims is a reasonable, low-risk refactor.
3. **SQLite is the live store; `watchlist.json` is a mirror.** Don't hand-edit the JSON and expect the app to see it. For truth read `/workspace/media/watchlist.db` or a rebuilt `dashboard-data.json`.
4. **The reconcile `/ Plex-scan cache.** `/api/status` and `/api/watchlist` hit a 300s reconcile cache keyed on file mtime. A pure *arr write doesn't bump mtime — `POST /api/media/{id}/request` clears it explicitly. Plex full-library scans are cached `PLEX_SCAN_TTL` (1h); without this one `/api/status` could trigger ~17 rescans and blow the request window.
5. **Don't revert the writable directory volume** (`../../media:/workspace/media:rw`) to a single-file `:ro` mount on `watchlist.json` — atomic `os.replace` fails and Docker pins the inode → silent stale data.
6. **`scripts/*` and `build_*.py` have hardcoded `/workspace/projects/rkm-cinema` paths.** They run on the **host/WSL**, not the container. A container-side dashboard rebuild can't write that path (this is why `add_watchlist`'s internal `rebuild_dashboard` subprocess can fail inside the container). Host cron drives rebuilds.
7. **Two scheduler paths, neither complete alone.** In-container scheduler (`WATCHLIST_SCHEDULER=true`) updates the store but never rebuilds `dashboard-data.json`; host cron rebuilds but uses host paths. Currently the host cron path is live, `WATCHLIST_SCHEDULER` is unset.
8. **`MEDIA_HOST` in the live `.env` carries an `http://` prefix.** Harmless now (all service URLs explicit) but beware building fallback URLs from it.
9. **No `.dockerignore` + ~7 dead `app.js.bak*` at the root** → bloated Docker context. `rebuild_verify.py` is **broken as written** (undefined names); `check_js.py` needs a `/tmp/live_dashboard.html` nothing produces; `tvdb_enrich.py` self-marks STAGED/UNTESTED.
10. **`EMBY_URL`/`EMBY_API_KEY`/`YOUTUBE_API_KEY` aren't in the env allow-list** — real env vars won't override `.env` for them; `EMBY_URL` isn't URL-normalized.
11. **No auth + wildcard CORS** on the whole API. Fine on a private Tailnet; do not expose to the public internet.
12. **`daily_recommendations.py` still imports both modern and legacy recommendation APIs** — a coexistence smell. The *real* daily driver is `add_watchlist_cron.py`.
13. **Trailer shapes vary.** Most entries `trailerId`+`trailerTitle`; a couple carry a legacy `trailer` YouTube **search URL**; the dashboard projection normalizes all to a `trailerUrl` embed.

---

## 15. Quick file index (where things live)

| Need | File |
|---|---|
| Config/env keys | `config/settings.py` |
| State machine | `domain/status.py` (not `state_machine.py`) |
| Media identity / media_id | `domain/identity.py` |
| Store switch, repo ABC | `infrastructure/database/repository.py` |
| Quality gates | `config/recommendations.yaml` + `services/recommendation/criteria.py` |
| Plex/Emby library | `services/library/*` (Provider) + `LibraryService` |
| Movie→Radarr / show→Sonarr routing | `services/acquisition/service.py` (`AcquisitionService`) |
| Status fact-gathering → snapshot | `services/reconciliation/reconciler.py` |
| Recommendation pipeline | `services/recommendation/manager.py` |
| Idempotent request | `application/commands/request_media.py` |
| Scheduler | `jobs/scheduler.py` |
| App factory + routers | `api/main.py`, `api/routes/*` |
| Frontend API client | `api.js` + `app.js` |
| Dashboard builder | `scripts/rebuild_dashboard.py` |
| Daily auto-add (live cron) | `scripts/add_watchlist_cron.py` + host cron `1965aeb4af2e` (`0 6 * * *`) |
| Deploy | `setup-watchlist.ps1` + `docker-compose.yml` |

This reference supersedes the stale `README.md`/`ARCHITECTURE.md` for day-to-day work.