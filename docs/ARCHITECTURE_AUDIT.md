# RKM Watchlist — Architecture Audit (Phase 1)

> **Gate deliverable for `RKM_Watchlist_Production_Refactor_Task.md`.** Per §3/§43.1 no
> rewrite begins until this audit is complete. Baseline: **56 tests passing** before any
> Phase 2+ code (`python3 -m pytest tests/ -q`).
>
> The repo already went through an earlier "single modular backend" refactor (2026-08-21):
> the monolithic `api.py` is archived, `domain/` + DI services + thin routes exist, and the
> web/nginx container proxies `/api` → FastAPI (`uvicorn api.main:app`). **This audit measures
> that starting point against the 26-phase production spec.**

---

## 1. Existing implementation (what is live today)

### API routes (`api/routes/*`, mounted in `api/main.py`)
| Route | File | Purpose |
|---|---|---|
| `GET /api/health` | `health.py` | Service health booleans |
| `GET /api/config` | `config.py` | Public-safe config (no secrets — verified) |
| `GET /api/status` | `status.py` | Per-title status via `MediaStatusService` + domain state machine |
| `POST /api/download` | `download.py` | Generic download → `DownloadService` |
| `POST /api/search` | `search.py` | TMDB + watchlist search |
| `GET /api/library` | `library.py` | Plex-first, Emby/Jellyfin fallback counts/recent |
| `GET /api/quality` | `quality.py` | Radarr/Sonarr quality profiles |
| `GET /api/plex/thumb` | `plex_thumb.py` | Proxied Plex thumbnails |

### Domain (`domain/`)
- `enums.py` — `MediaType` (MOVIE/TV), `MediaStatus` (NOT_ADDED/REQUESTED/DOWNLOADING/DOWNLOADED/AVAILABLE/RECOMMENDED), `DownloadResultState`.
- `state_machine.py` — `resolve_status(facts)`: **canonical** status resolver (Plex-available → AVAILABLE, else downloaded → DOWNLOADING, etc.). Already matches spec §12 in spirit.
- `resolver.py` — `resolve_media_type()`: single movie/tv routing rule.
- `models.py` — `DownloadResult`.

### Services (`services/`) — flat, DI-injectable `config`/`http`
- `base.py` — `BaseService` (DI, HTTP-error→exception mapping).
- `plex.py` — **`PlexService`**: full library scan (cached 60s), ownership by *title/year*, `plex_url_for`, and **embedded Emby** URL/item-ID helpers (`emby_url_for`, `_emby_item_id`, `_emby_server_id`).
- `emby.py` — **`EmbyService`**: `EmbyItem`, `has_media` by name/year. Exists but is **not** the same code path the live status/library flow uses (which goes through `PlexService`'s embedded helpers).
- `radarr.py` / `sonarr.py` — `RadarrService`/`SonarrService`: lookup/add by id or title/year, queue, profiles, indexer health. Cached.
- `qbittorrent.py` — `QBittorrentService`: active download match + progress.
- `download.py` — `DownloadService`: movie/tv routing + add + title-fallback + cross-service fallback + ambiguity.
- `media_status.py` — `MediaStatusService`: builds `StatusFacts` per entry and calls `resolve_status`.
- `watchlist.py` — `WatchlistService`: JSON persistence (atomic tmp+`os.replace`), full CRUD + state transitions.
- `recommendations.py` — `RecommendationService`: quality gates (hardcoded constants), Plex-ownership check, duplicate check, metadata/trailer enrichment, `add_to_watchlist`.
- `tmdb.py`, `youtube.py`, `trailers.py`, `plex_check.py` — metadata + trailer helpers.
- `config/settings.py` — centralized env config incl. `PLEX_BROWSER_URL`/`EMBY_BROWSER_URL` (spec §20 satisfied).
- `core/http_client.py` — shared client: **timeout + short-TTL cache + retry**. `core/exceptions.py` — typed errors. `core/logging.py` — JSON formatter + `log_event`/`LogContext`.

### Frontend
- `api.js` — centralized `API.*` client (spec §21 satisfied).
- `app.js` — renders cards; needs audit for capability-driven rendering (spec §19/§11).
- `index.html` / `dashboard.html` / `app.css` / `dashboard-data.json`.

### Jobs / scripts
- Host cron runs `scripts/daily_recommendations.py`; `scripts/rebuild_dashboard.py` rebuilds static JSON.
- **No in-container jobs, no `job_runs` tracking, no frequent reconciliation job.**

### Persistence
- **`watchlist.json` (versioned at `/workspace/media/watchlist.json`, `/app/watchlist.json` in container) is authoritative.** Read/written directly by `WatchlistService` and by scripts (`rebuild_dashboard.py`, `daily_recommendations.py`, `add_with_plex_check.py`). **No SQLite, no repository abstraction.**

---

## 2. Target implementation (spec §2 architecture)

| Target axis | Spec location |
|---|---|
| `application/commands/request_media.py`, `reconcile_media.py`; `queries/*` | §15, §2 |
| `domain/identity.py` (MediaIdentity, `media_id="movie:tmdb:12345"`) | §4 |
| SQLite store `infrastructure/database/` + schema (`media`, `watchlist`, `recommendations`, `library_items`, `acquisitions`, `watch_links`, `job_runs`) | §5 |
| `domain/status.py` canonical resolver on `MediaFacts` (not HTTP) | §12 |
| `services/library/service.py` + `LibraryProvider` abc + `plex.py` + `emby.py` + `watch_links.py` | §4/§7/§8/§10 |
| `services/reconciliation/reconciler.py` → `MediaSnapshot(status, capabilities, watch)` | §13 |
| `services/acquisition/service.py` + `radarr.py` + `sonarr.py` (single routing) | §14 |
| `services/recommendation/{generator,criteria,ranker,manager}.py` | §21 |
| `jobs/daily_watchlist.py` + frequent reconcile job + `job_runs` | §24/§26 |
| Resource-oriented API `/api/media/{media_id}`, `/media/{id}/request`, `/watchlist`, `/library`, `/recommendations`, `/reconcile`, `/jobs`, `/health` | §17/§18 |
| Capability-driven frontend (`status.capabilities.watch`) | §19/§20 |

---

## 3. Duplicate logic (spec: consolidate to ONE implementation each)

1. **Emby URL/item resolution** — built in THREE places:
   - `PlexService.emby_url_for` / `_emby_item_id` / `_emby_server_id` (`services/plex.py`)
   - `api/routes/library.py::_emby_browser_base` + inline Emby counts call
   - `domain/state_machine.WatchLinks` (holds emby fields)
   → **Spec target:** single `services/library/emby.py` provider + `watch_links.py`.
2. **Plex URL base logic** — TWO places: `services/plex.py` `_plex_browser_base` and `api/routes/library.py::_plex_browser_base`. → single library provider.
3. **Plex ownership / has_media** — `services/plex.py` `has_media` and `services/emby.py` `has_media` are near-identical title/year matchers. → unify under `LibraryService` with identity-based matching.
4. **Media-type routing** — `domain/resolver.py` (canonical) but `services/download.py` also branches `if media_type is TV: sonarr else radarr` inline. → one `AcquisitionService` routes.
5. **Status derivation** — `domain/state_machine.resolve_status` is canonical; NOT duplicated (good). But it is keyed by `imdbId` strings, not `MediaSnapshot`/`media_id`.

---

## 4. Risky / non-negotiable gaps (spec invariants) {#gaps}

| Gap | Spec violation | Fix |
|---|---|---|
| **Canonical identity** | No `MediaIdentity`; entries keyed by `imdbId`, matching by title/year (§1.1 "never title as identity") | Phase 2 `domain/identity.py`, normalize at ingestion, `media_id` string |
| **Persistent store** | JSON is authoritative; scripts read it directly (§5; §1 "not the rest") | Phase 3 SQLite + `WatchlistRepository`; JSON kept only as compat/export |
| **Library abstraction** | Plex+Emby coupled in one service; no `LibraryProvider` iface; providers not unified-as-one-library (§4/§9) | Phase 4/5 `services/library/` |
| **Watch-link containment** | Link build scattered; need `WatchLink{available,url,error}`; failure must not flip AVAILABLE→NOT_REQUESTED (§10/§14) | Phase 5 `watch_links.py` |
| **Idempotent request command** | `POST /api/download` re-adds; no re-check-library, no already-requested gate, no persisted acquisition (§1.4/§15/§9) | Phase 9 `application/commands/request_media.py` |
| **Configurable criteria** | Quality gates are hardcoded constants in `RecommendationService` (§22) | Phase 12 `criteria.py` + YAML config |
| **Recommendation history** | No persisted history → daily job can re-recommend (§23) | Phase 3 `recommendations` table + Phase 12 |
| **In-container jobs** | Host cron only; no `job_runs`, no frequent reconciliation (§24/§26) | Phase 13/14 |
| **Resource API** | Generic `POST /api/download`, `GET /api/status` (§17) | Phase 10 |
| **Degraded-capability model** | `capabilities{can_download,can_watch}` not in the response model (§18/§37) | Phase 10/18 |

Already compliant: centralized config (§20), no secrets in `/api/config` (§25), `api.js` boundary (§21), HTTP timeout/cache/retry (§28 partially), Plex-as-sovereign availability (§1.2), watch URLs via browser config (§11), tests LAN-free (56 green).

---

## 5. Files to delete / merge

| File | Action |
|---|---|
| `services/emby.py` | **Merge** its item/matching logic into `services/library/emby.py`, then remove |
| Emby+URL helpers inside `services/plex.py` (`emby_url_for`, `_emby_item_id`, `_emby_server_id`) | **Merge** into `services/library/emby.py` + `watch_links.py`, remove from Plex |
| `api/routes/library.py` inline `_plex_browser_base`/`_emby_browser_base` | **Merge** into library providers, thin route |
| `services/recommendations.py` hardcoded gates | **Replaced** by `services/recommendation/criteria.py` |
| `scripts/daily_recommendations.py` (host-cron business logic) | **Replaced** by `jobs/daily_watchlist.py` invoking `application`; keep script only as thin cron entrypoint per §26 |
| `archive/api_legacy_monolith.py` | **Keep** as historical reference only (spec §22.9) |

## 6. Implementation order (tied to spec §42)

`1 audit ✓ → 2 identity → 3 DB/repository → 4 library abstraction → 5 matching+watch-links → 6 status resolver → 7 reconciler → 8 acquisition abstraction → 9 request command → 10 API → 11 frontend → 12 recommendations → 13/14 jobs → 15 observability → 16-18 tests/cleanup/verify`.

**No frontend work until the state model is correct (§42). No parallel implementations (§43.3). Every phase keeps `pytest` green (§43.7).**