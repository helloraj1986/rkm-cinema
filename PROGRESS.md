# RKM Watchlist — Session Handoff & Project Progress

> Last updated: 2026-08-21 (git repo creation + architecture docs)
> Live URL: **http://rkm-hp.tail8d5e8.ts.net:8123/** (Tailscale MagicDNS, tailnet-only — NEVER `tailscale funnel` it; page proxies /api → FastAPI which holds secrets server-side)
> Deploy path (Windows, RKM-HP): `cd D:\hermes_agent\hermes-workspace\media\watchlist; .\setup-watchlist.ps1` — the sandbox's `/workspace` maps to `D:\hermes_agent\hermes-workspace` (9p mount, confirmed via mountinfo 2026-08-18; NOT `D:\media`)
> Repo: **private `rkm-watchlist` on GitHub** (github.com/helloraj1986/rkm-watchlist)
> **Status:** local git repo initialised + initial commit `073126c` done (this session).
> **Push pending:** the `GITHUB_TOKEN` in `/workspace/.env` can **list** repos but **cannot create**
> new ones (HTTP 403 "Resource not accessible by personal access token" — a fine-grained-token
> scope limit, same as the knot-app setup). → **Step needed from Rajeev:** create an empty private
> repo named `rkm-watchlist` on GitHub (github.com/new → name `rkm-watchlist`, Private, no README),
> then tell me and I'll push with the token.

## ⚡ HOW TO PICK UP WORK HERE

- **Start with `ARCHITECTURE.md`** — it's the up-to-date map of how everything works and what each file does. Read the **"Two API layers"** section first: the **live** backend is the monolithic **`api.py`**; the modular **`api/`+`services/`** is the target refactor (used by scripts). Add/adjust routes in **`api.py`** for anything visible on the site, and mirror the change in the modular layer so they don't drift.
- **Adding a feature** → follow ARCHITECTURE.md §12 ("Adding a feature").
- **Quick checklist:** backend change → edit `api.py` (+ modular `api/routes/*` + `services/*`), then `python -m pytest tests/ -q`, then `scripts/rebuild_dashboard.py`, then deploy `.\setup-watchlist.ps1`. Frontend (`app.js`/`app.css`) is volume-mounted — no rebuild needed for UI-only changes.
- **Secrets** live in `/workspace/.env` (canonical). `.env` is git-ignored; use `.env.example` as the template. **Never commit real keys.**

## Latest session (2026-08-21) — git repo + docs

- Initialised git repo (`main`), added `.gitignore` (excludes `.env`, runtime data `watchlist.json`/`dashboard-data.json`/`index.html`/`dashboard.html`, caches, `*.tmp`) and `.env.example` (documented env template).
- Moved one-off/legacy dev scripts into `archive/` (kept out of the active tree).
- Rewrote **`ARCHITECTURE.md`** from scratch to match the **actual** codebase (was an aspirational "Target Architecture" doc): covers the two API layers, every endpoint in `api.py`, every modular service, the state machine, download/lifecycle flows, config, deployment, and a step-by-step "add a feature" guide.
- Updated **`README.md`** (accurate project structure + the two-layer warning + correct deploy paths + "no YouTube API key needed").
- Updated **`PROGRESS.md`** (this file) with a handoff block.
- **Deployed state note:** the running site is still the **monolithic `api.py`** build. All in-repo fixes made in the 2026-08-20 session (trailers, routing, Watch Now, Plex/Emby deep links, Plex-source-of-truth status, posters) are in the code but require `.\setup-watchlist.ps1` to go live.

---

## Latest session (2026-08-20) — 9 fixes

### 8f. Emby links — HTTPS scheme fix ✅
- **Bug:** Emby deep links were built with `http://`, but the Tailscale Emby server is **HTTPS-only** — so clicking returned "Client sent an HTTP request to an HTTPS server" (400). Confirmed: `http://rkm-hp.tail8d5e8.ts.net:8096` → 400, `https://...` → 200.
- **Fix:** all Emby URL builders (legacy `api.py` `_emby_url_for`, library `urls.emby`, modular `services/plex.py` `emby_url_for`, `api/routes/library.py`) now use `https://rkm-hp.tail8d5e8.ts.net:8096/web/index.html`. Verified: Banshees → `https://.../#!/item?id=67719&serverId=b54476...`.

### 8e. Emby Watch buttons — fixed deep-link format ✅
- **Bug:** Emby watch buttons used the search path `#!/search/<title>`, which doesn't deep-link to the item. The correct format is `#!/item?id=<itemId>&serverId=<serverId>`.
- **Fix:** backend now resolves the Emby **item id** for a title (via `/Users/<id>/Items?searchTerm=...`) and the **server id** (`/System/Info/Public` → `b54476cfb9054f389fcc0ce450f17c60`), then builds `#!/item?id=<id>&serverId=<sid>`.
- **Verified** for The Banshees of Inisherin → `#!/item?id=67719&serverId=b54476...`, exactly matching the URL Plex/Emby generates when you click the movie. Applies to legacy `api.py` (`_emby_url_for`, library `recent[]`), modular `services/plex.py` (`emby_url_for`/`_emby_item_id`/`_emby_server_id`), and frontend `libraryCard()` (uses backend-provided `embyUrl`).
- Note: Plex-library recents that are *seasons* resolve to the parent series item id in Emby (e.g. id 38373) — acceptable; movie/series top-level items resolve correctly.

### 8d. Plex is the source of truth for status ✅
- **Bug:** a title in Plex but with a stale/missing *arr record (e.g. `not_added` in Radarr yet present in Plex) showed `not_added`/`requested` because the status logic only reached `available`/`downloaded` when *arr reported `hasFile` — it never checked Plex first.
- **Fix (`api.py` + modular `api/routes/status.py`):** at the top of each entry evaluation, if the title exists in Plex it is immediately `available` with correct `plexUrl`/`embyUrl`, regardless of what Radarr/Sonarr report. Only titles *not* in Plex fall through to the *arr/qBittorrent pipeline.
- Added a ~45s-cached Plex library lookup (`_plex_library`) so repeated per-title checks don't re-scan 787 movies on every request (first status call ~2.4s, subsequent ~0.4s).
- **Verified:** Spider-Man, The Bear, Banshees, Mandalorian all now show `available` with working Plex links (they were `not_added` before).

### 8c. Plex Watch buttons — fixed deep-link format ✅
- **Two bugs in the generated Plex URLs:** (1) used the LAN host `192.168.65.254:32400` as the server id instead of the Plex **`machineIdentifier`** (`7780f37754c6ff144dd28c42b052e0187301dba1`); (2) passed a bare `key=320126` instead of the **URL-encoded `/library/metadata/320126`** (`%2Flibrary%2Fmetadata%2F320126`).
- **Fix:** backend now fetches and caches the machineIdentifier (`/identity`), builds `key=%2Flibrary%2Fmetadata%2F<ratingKey>`, and serves the correct `plexUrl` per item from `/api/library`. Verified the generated URL for The Mandalorian (key 320126) **exactly equals** the URL Plex itself produces when you click the show.
- Applies to: legacy `api.py` (`_plex_emby_urls`, library `recent[]`), modular `api/routes/status.py` + `services/plex.py` (new `server_id()`/`find_item()`/`plex_url_for()` helpers), and frontend `libraryCard()` (now uses the backend-provided `plexUrl` instead of building it client-side).

### 8b. Emby integration ✅
- Added `EMBY_URL=http://192.168.65.254:8096` + `EMBY_API_KEY` to `/workspace/.env` (user-provided key). The server at :8096 is **Emby** v4.9.5 (not Jellyfin).
- **Verified Emby API:** `Items/Counts` → **824 movies / 103 series / 5078 episodes** (shares the same library as Plex).
- Legacy `api.py`: added `EMBY_URL`/`EMBY_API_KEY` loading; `/api/library` now tries **Plex first** (richer view: recents + thumbnails + ratingKey deep links), then falls back to **Emby** for counts. Health/config report `emby: true`.
- Frontend: library cards show **both "▶ Plex" and "▶ Emby"** deep links; empty-state text updated. Since Plex and Emby share the library, Plex-primary gives the full view and Emby is a fully-working fallback.

### 8. Library fetch from Plex + click-to-watch buttons ✅
- **Root cause:** legacy `/api/library` called Plex **without** the `Accept: application/json` header, so Plex returned XML and JSON-parse failed → endpoint always returned `provider:null` (no library). 
- **Fix (`api.py`):** added the JSON header to all Plex library calls. Verified live: `/api/library` now returns real Plex data — **787 movies / 98 shows / 8 recent** with `ratingKey`.
- **Frontend (`app.js`):** library cards are now **clickable** — each recent item shows **"▶ Plex"** and **"▶ Emby"** buttons that deep-link to the item: Plex `app.plex.tv/desktop/#!/server/<host>/details?key=<ratingKey>` and Emby search via Tailscale MagicDNS. Thumbnails render through a new server-side proxy `/api/plex/thumb` (keeps the token secret; verified 200).
- **Emby note:** the server at `:8096` is **Emby** (v4.9.5) and now has a working API key (`EMBY_API_KEY` in `.env`), so both the Plex-primary library view **and** Emby fallback counts work — and every library card carries "▶ Plex" and "▶ Emby" watch buttons.

### 7. Watch Now buttons live-fix + Sonarr TV fallback ✅
- **`api.py` (legacy) status was returning HTTP 500** → that's exactly why no Plex/Emby buttons appeared: a `NameError` (`plexUrl` used as an unquoted dict key instead of `"plexUrl"`) broke `/api/status` for every request, so the frontend never got status data and never rendered the buttons. Fixed to string keys; verified `/api/status` now returns `available` with real `plexUrl`/`embyUrl` for in-Plex titles (Banshees, Mandalorian).
- **The Bear → "No Sonarr match for imdb"** — same root cause as the Radarr title: Sonarr's `imdb:tt10157119` lookup returns **0 results**, but a title search finds it (**tvdb 403294**). Added the same **title/year fallback** to `SonarrService.add_series` (+ `search_series`) and legacy `sonarr_add`. Verified: `The Bear` → added to Sonarr via title fallback (tvdb 403294).
- Card, hero, and modal buttons all render Watch-on-Plex/Emby for `available` state (frontend was already correct and volume-mounted).

### 5. Missing posters — TMDB artwork backfill ✅
- **Root cause:** many watchlist entries carried **fabricated/stale poster URLs** (e.g. `...9x9x9x9xX.jpg`, `...U9g3g7.jpg`) that 404 — the artwork was never validated against TMDB.
- **Fix:** new `scripts/backfill_tmdb_artwork.py` re-fetches the authoritative **poster + backdrop** from TMDB by each entry's `tmdbId` (movie or tv), updates `/workspace/media/watchlist.json` (the real API data source at the workspace root, per docker-compose mount), and rebuilds the dashboard.
- **Verified:** all 9 entries now have valid 200-returning TMDB posters. Also fixed a crash bug: `TMDBService` was raising `ServiceUnavailableError` with the wrong signature.

### 5b. Add-time self-healing posters ✅
- **Root cause:** `RecommendationService.enrich_metadata` copied `candidate.poster` verbatim and never overwrote it with TMDB — so any candidate carrying an empty/fabricated poster leaked straight into the watchlist at add-time.
- **Fix (`services/recommendations.py`):** enrichment now always sets `entry.poster` from the authoritative TMDB `poster` (movie or show), guarded by a new `_is_valid_poster()` — a real HEAD request requiring HTTP 200 + `image/*` content type. Fabricated/dead URLs are rejected.
- **Verified:** a candidate with `poster=...FAKE...9x9x9x9xX.jpg` is healed at enrich time → real `w500/6izwz...` TMDB poster. `_is_valid_poster`: valid→True, fabricated→False, empty→False.


### 4. "No Radarr match" — stale IMDb ID fallback (title search) ✅
- **Root cause:** the watchlist entry for *The Zone of Interest* had stale/wrong IDs — Radarr's `imdb:tt2197033` and `tmdb:457780` both returned **0 results**, while a **title search** found the correct movie (The Zone of Interest, 2023, **tmdb 467244**, imdb tt7160372).
- **Fix (`services/radarr.py`, `api.py`, `api/routes/download.py`, `api/models.py`, `app.js`):** when the stored IMDb lookup resolves nothing (or ambiguously), the backend now falls back to a **title (+year) search** in Radarr. Exact title/year match is preferred; multiple matches return a numbered "pick one" list with title · year · tmdbId for disambiguation (HTTP 404) instead of silently guessing or failing.
- `DownloadRequest` now carries optional `title`/`year`; the frontend sends them.
- Verified live: `tt2197033` + title/year → resolved to tmdb 467244 and added to Radarr.

### 1. YouTube trailer — NO API key required ✅
- **`services/youtube.py` rewritten** to scrape `youtube.com/results` directly (no YouTube Data API key).
- Parses `ytInitialData` JSON + fallback regexes; scores candidates for "official trailer" indicators, studio/distributor channel names, and verified badges; penalizes fan/noise videos.
- `has_youtube()` always True; `get_embed_url()` builds `youtube.com/embed/<id>` for **in-app playback**.
- Verified live: `Arrival` → `oGI9hSl0q-w` (Paramount official trailer); `Dune: Part Two` → `Way9Dexny3w` (official trailer).
- Frontend trailer button now **plays in-app** (opens the modal iframe) instead of opening a new YouTube tab.

### 2. Download routing — movies → Radarr, TV → Sonarr ✅
- Root cause: routing trusted the frontend `type` field; a missing/wrong type could send a movie to Sonarr.
- **`api.py` (legacy)**: added `_resolve_download_type()` — explicit type → watchlist `isSeries` → Radarr lookup (movie) then Sonarr lookup (series), defaulting to movie. A movie can no longer reach Sonarr.
- **`api/routes/download.py` (modular)**: same authoritative resolver + Radarr/Sonarr cross-fallback ("No Sonarr match" → retry as Radarr; "No Radarr match" → retry as Sonarr).
- Also fixed a latent bug: `RadarrService._get` / `SonarrService._get` now accept `timeout` (was raising `unexpected keyword argument` in modular download).
- Verified: `tt2543164` (Arrival, movie) → Radarr; `tt10157119` (The Bear, tv) → Sonarr; unknown → defaults to movie.

### 3. Plex/Emby "Watch" buttons for available content ✅
- **Legacy `api.py` status** now computes an `available` state (Radarr `hasFile`/Sonarr episodes downloaded AND present in Plex) and includes `plexUrl` + `embyUrl` deep links (Plex search/detail + Emby via Tailscale MagicDNS `rkm-hp.tail8d5e8.ts.net:8096`).
- **`app.js`**: hero + modal download buttons now render "Watch on Plex" / "Watch on Emby" / both for `available` state (cards already did).
- `services/emby.py` added as a service; config supports `EMBY_URL`/`EMBY_API_KEY` (`has_emby()`).

**Remaining before deploy:** run `setup-watchlist.ps1` on RKM-HP to ship backend changes; frontend files (app.js) go live via volume mount immediately.

## Status (2026-08-19)

- **NEW MODULAR ARCHITECTURE DEPLOYED**: Complete service layer with clean separation of concerns
  - `config/settings.py` - Centralized Config class (single source of truth for all env vars)
  - `core/http_client.py` - Shared HTTP client with caching, retry, structured errors
  - `core/logging.py` - Structured JSON logging
  - `core/exceptions.py` - Custom exception hierarchy
  - `services/plex.py` - Plex ownership verification (ground truth)
  - `services/radarr.py` - Movie management + quality profiles
  - `services/sonarr.py` - TV series management
  - `services/trailers.py` - TVDB v4 + TMDB trailer enrichment
  - `services/watchlist.py` - CRUD + state machine (atomic writes)
  - `services/recommendations.py` - Pipeline: category → gates → Plex → dedupe → enrich → add
  - `api/main.py` - FastAPI app factory with modular routes
  - `api/routes/` - Health, config, status, download, search, library, quality endpoints
  - `scripts/daily_recommendations.py` - Single orchestration entry point for daily cron
  - `scripts/auto_complete.py` - pending → recommended transition (hasFile + Plex)
  - `scripts/enrich_trailers.py` - Standalone trailer enrichment
  - `scripts/rebuild_dashboard.py` - Refactored build pipeline using services
  - Comprehensive test suite in `tests/`

- **Previous v2 stack still live** (needs redeploy to pick up new architecture):
  - `api` (FastAPI, :8000, secrets server-side) + `web` (nginx :8123)
  - qBittorrent status integration — DONE (code, needs redeploy)
  - PLEX_TOKEN in .env (user provided 2026-08-18)
  - .env consolidated: canonical `/workspace/.env` (= `D:\.env`); `/workspace/media/.env` is symlink
  - ⚠ Radarr indexers ALL down — The Father + 5 others at "requested"

- **7 pending titles** (same as before):
  | # | Title | Year | State |
  |---|---|---|---|
  | 0 | Arrival | 2016 | requested (waiting on indexers) |
  | 1 | The Grand Budapest Hotel | 2014 | requested (waiting on indexers) |
  | 2 | Mad Max: Fury Road | 2015 | requested (waiting on indexers) |
  | 3 | Prisoners | 2013 | requested (waiting on indexers) |
  | 4 | Nightcrawler | 2014 | requested (waiting on indexers) |
  | 5 | Whiplash | 2014 | not_added (user hasn't approved) |
  | 6 | The Father | 2020 | requested (waiting on indexers) |

- **Plex is ground truth for ownership** (user-ratified): all services now use Plex FIRST via PLEX_TOKEN

## New Architecture (modular service layer)

```
┌─────────────────────────────────────────────────────────────────┐
│                        DAILY CRON ORCHESTRATOR                   │
│  (scripts/daily_recommendations.py - single entry point)        │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         SERVICE LAYER                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   PlexSvc   │  │  RadarrSvc  │  │  SonarrSvc  │             │
│  │ (ownership) │  │  (movies)   │  │   (tv)      │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  RecoSvc    │  │ TrailerSvc  │  │ WatchlistSvc│             │
│  │ (recs+gates)│  │ (TVDB/TMDB) │  │  (CRUD+FSM) │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CORE / INFRASTRUCTURE                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Config    │  │    HTTP     │  │  Logging    │             │
│  │  (central)  │  │  (client)   │  │  (struct)   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EXTERNAL SERVICES                           │
│  Plex · Radarr · Sonarr · Prowlarr · TVDB · TMDB · qBittorrent  │
└─────────────────────────────────────────────────────────────────┘
```

## File inventory (`/workspace/media/watchlist/`)

| File | Purpose |
|---|---|
| `config/settings.py` | **Centralized Config class** - all env vars, validation, defaults |
| `core/http_client.py` | Shared HTTP client with caching, retry, structured errors |
| `core/logging.py` | Structured JSON logging setup |
| `core/exceptions.py` | Custom exception hierarchy (ServiceUnavailableError, DuplicateError, etc.) |
| `services/base.py` | BaseService with common patterns |
| `services/plex.py` | Plex ownership verification (has_movie, has_show, has_media) |
| `services/radarr.py` | Radarr movie management, quality profiles, queue, indexer health |
| `services/sonarr.py` | Sonarr series management, quality profiles, queue |
| `services/trailers.py` | TVDB v4 + TMDB trailer enrichment, validation |
| `services/watchlist.py` | Watchlist CRUD, state machine, atomic persistence |
| `services/recommendations.py` | Recommendation pipeline (category, gates, Plex check, enrich) |
| `services/__init__.py` | Unified exports |
| `api/main.py` | FastAPI app factory |
| `api/models.py` | Pydantic request/response models |
| `api/routes/health.py` | GET /api/health |
| `api/routes/config.py` | GET /api/config |
| `api/routes/status.py` | GET /api/status (per-title state + qBit progress) |
| `api/routes/download.py` | POST /api/download (Radarr/Sonarr + qualityProfileId) |
| `api/routes/search.py` | GET /api/search (watchlist + TMDB) |
| `api/routes/library.py` | GET /api/library (Plex/Jellyfin) |
| `api/routes/quality.py` | GET /api/quality (quality profiles for download chooser) |
| `scripts/daily_recommendations.py` | **Daily cron orchestration** - single entry point |
| `scripts/auto_complete.py` | **Auto-complete** - pending → recommended when hasFile + Plex |
| `scripts/enrich_trailers.py` | Trailer enrichment (probe, dry-run, enrich) |
| `scripts/rebuild_dashboard.py` | Dashboard build using WatchlistService |
| `tests/test_*.py` | 7 test modules covering critical workflows |
| `app.js` / `app.css` | Frontend (volume-mounted, live immediately) |
| `index.html` / `dashboard.html` | Slim shell loading app.js |
| `Dockerfile` / `docker-compose.yml` | api image + nginx web |
| `setup-watchlist.ps1` | Windows deploy (rebuild + up) |
| `nginx/default.conf` | no-store headers; `/api/` → api:8000 |
| `watchlist.json` | **Data** — at `/workspace/media/watchlist.json` |
| `ARCHITECTURE.md` | Detailed architecture documentation |
| `README.md` | Project overview, setup, usage |
| `PROGRESS.md` | This file |

## Config — `.env`

Canonical: **`/workspace/.env`** (= `D:\.env`). `/workspace/media/.env` is a symlink. Variable names only:

`MEDIA_HOST, RADARR_URL, RADARR_API_KEY, SONARR_URL, SONARR_API_KEY, PROWLARR_URL, PROWLARR_API_KEY, PLEX_URL, PLEX_TOKEN, JELLYFIN_URL, JELLYFIN_API_KEY, BROWSER_RADARR_URL, BROWSER_SONARR_URL, QBITTORRENT_URL, GITHUB_TOKEN, RADARR_QUALITY_PROFILE_ID, SONARR_QUALITY_PROFILE_ID, TMDB_API_KEY, TVDB_API_KEY`

**MISSING (next session):**
- `TVDB_API_KEY` — **user has this key**; paste into `.env` → `python3 scripts/enrich_trailers.py --probe` → enrich → rebuild.
- `TMDB_API_KEY` — optional; second trailer source + poster fallback.

---

## FEATURE 1: Auto-complete (pending → available when downloaded + in Plex) ✅ COMPLETE

**Goal:** when a pending title's file lands (qBittorrent 100% → Radarr import → Plex scan), auto-move it from `pending[]` to `recommended[]` with a completion date, and notify Rajeev in chat. No manual "drop N" needed.

**Implementation Completed:**

1. ✅ **API status endpoint** - Detects `available` state when both *arr hasFile AND Plex has title
   - Movies: `rec.hasFile and in_plex` → `state: "available"` with Plex/Emby deep links
   - TV Series: `downloaded and in_plex` → `state: "available"` with deep links
   - Keeps `downloaded` for content in *arr but not yet scanned into Plex

2. ✅ **Frontend rendering** - Updated `app.js`:
   - `STATE_LABEL` includes `available: 'Available'`
   - `dlStateMarkup()` shows "Available in Plex" for available state
   - `downloadButton()`, `heroDownloadButton()`, `downloadButton()` all handle `available` state
   - `rerenderDownloadButtons()` updated for available state styling
   - Watch Now dropdown functionality added for Plex/Emby links

3. ✅ **Auto-complete integration** - Updated `scripts/daily_recommendations.py`:
   - Runs `auto_complete.py` FIRST before processing new recommendations
   - Reports auto-completed entries in results
   - Returns completion count for cron logging

**Next Steps:**
1. Deploy new architecture - Run `setup-watchlist.ps1` on RKM-HP
2. Verify PlexService integration against live Plex
3. Test `/api/status` against known-owned titles
4. Verification pass - Rebuild dashboard and confirm no regressions## NEXT SESSION — FEATURE 6: Download quality choice (1080p vs 4K before adding)

**Goal:** when clicking Download on a card, let Rajeev pick the quality profile (e.g. 1080p vs 2160p/4K) instead of silently using the default.

**IMPLEMENTATION STATUS: Backend COMPLETE in new architecture**

The following are **already implemented**:

1. ✅ **RadarrService.get_quality_profiles()** - Returns profiles with id, name, items
2. ✅ **SonarrService.get_quality_profiles()** - Returns profiles with id, name, items
3. ✅ **RadarrService.add_movie(imdb_id, quality_profile_id)** - Accepts optional qualityProfileId
4. ✅ **SonarrService.add_series(imdb_id, quality_profile_id)** - Accepts optional qualityProfileId
5. ✅ **API endpoint GET /api/quality** - Returns Radarr + Sonarr profiles (no secrets)
6. ✅ **API endpoint POST /api/download** - Accepts `qualityProfileId` in request body
7. ✅ **DownloadRequest model** - Includes `qualityProfileId: int | None`

**Remaining tasks (do in order):**

1. **Deploy new architecture** - Run `setup-watchlist.ps1` on RKM-HP
2. **Frontend — quality chooser on Download** - In `app.js`:
   - Fetch `/api/quality` once (cache in `QUALITY`)
   - On `doDownload`, if entry not yet added and profiles > 1 → show chooser (modal/dropdown): "1080p (HD-720p profile)" / "4K" / "Default"
   - Remember last pick in `localStorage` (`rkm_qp`) as default
   - Pass `qualityProfileId` in `postDownload` body
   - Keep single-click path when only one profile exists
3. **Quality profile hygiene** - Check Radarr has sensible 1080p and 2160p profiles (see `progress_download_selection.md` — profile 3 = "HD-720p", 720p/1080p capped 2GB; 4K profile may not exist yet)
4. **Verification pass** - Add test title with each profile choice → confirm `/api/v3/movie` reflects chosen `qualityProfileId`; rebuild dashboard; live-curl

---

## FEATURE 7: Watch Now - Plex/Emby deep links ✅ COMPLETE

**Goal:** When a movie/series reaches `available` state (downloaded + in Plex), replace the "Download" button with a **"Watch Now"** action that offers both **Plex** and **Emby** deep links using Tailscale MagicDNS URLs.

**Implementation Completed:**

1. ✅ **API Model Update** (`api/models.py`):
   - Added `plexUrl: Optional[str]` and `embyUrl: Optional[str]` to `StatusEntry` model

2. ✅ **API Endpoint Enhanced** (`api/routes/status.py`):
   - Extended `/api/status` to compute Plex deep links when `rec.hasFile and in_plex` is true
   - Generate Plex deep link via ratingKey if available, otherwise search link
   - Generate Emby deep link via Tailscale MagicDNS
   - Returns `plexUrl` and `embyUrl` fields in status response

3. ✅ **Frontend Handler** (`app.js`):
   - Enhanced `downloadButton()` to show "Watch Now ▼" dropdown for available state
   - Handles both Plex and Emby URLs with data attributes
   - Click handler processes `watch-plex`, `watch-emby`, and `watchnow` actions
   - Opens links in new tab

4. ✅ **Build Script Fixed** (`scripts/rebuild_dashboard.py`):
   - Fixed to work with current `WatchlistEntry` model
   - Added safe defaults for missing fields

**Priority:** High — completes the lifecycle UX (Recommended → Download → Available → Watch)## TVDB v4 integration plan (resume here)

Endpoint shapes NOT yet live-verified from the sandbox (oEmbed blocked; use `scripts/enrich_trailers.py --probe` first):

1. `POST https://api4.thetvdb.com/v4/login` body `{"apikey":"<TVDB_API_KEY>"}` → `data.token` (JWT ~30 days). Cache to `/workspace/media/.tvdb_token`; re-login on expiry.
2. `GET /v4/search?query=<title>&type=movie|series&year=<year>` → match `remoteids[]` to known `imdbId` → TVDB `id`.
3. `GET /v4/movies/{id}/extended` or `/v4/series/{id}/extended` → `artworks`, `trailers`, `genres`, `runtime`, `overview`.
4. Extract YouTube ID from `watch?v=ID` / `youtu.be/ID` / `/embed/ID`. Only YouTube embeds; else search-link fallback.
5. Fallback: TMDB `/movie/{tmdbId}/videos` (site=YouTube, type=Trailer).
6. Rule: NEVER write an unverified `trailerId` — empty → search link.

**Implemented in `services/trailers.py`** - Complete with token caching, search, extended, trailer extraction, validation.

---

## Operations

- **Rebuild dashboard:** `cd /workspace/media/watchlist && python3 scripts/rebuild_dashboard.py`
- **Rebuild + verify:** `python3 rebuild_verify.py` (legacy, still works)
- **Repair if corrupted:** `python3 fix_all.py` (legacy)
- **TVDB enrich:** `python3 scripts/enrich_trailers.py` (probe first: `--probe`)
- **Auto-complete:** `python3 scripts/auto_complete.py [--dry-run]`
- **Daily recommendations:** `python3 scripts/daily_recommendations.py [--candidates file.json] [--dry-run]`
- **Deploy (Windows PowerShell):** `cd D:\hermes_agent\hermes-workspace\media\watchlist; .\setup-watchlist.ps1` — REQUIRED to ship api.py changes (image rebuild); frontend files go live via volume mount immediately.
- **Run tests:** `cd /workspace/media/watchlist && pytest tests/ -v`
- **Cron:** job `0cd1d3c2c872` "RKM Watchlist daily rec", `0 18 * * *` AEST, LLM-driven, loads `weekly-media-recommendations` skill. Prompt updated 2026-08-18: Plex-first library check, r.jina.ai score verification, qBittorrent-aware. Approval always the user's — cron never POSTs to *arr.

---

## Known issues / next-session checklist

1. **Deploy pending**: New modular architecture NOT yet in running container → run `setup-watchlist.ps1` on RKM-HP (also picks up PLEX_TOKEN + QBITTORRENT_URL).
2. **Radarr indexers all down** — The Father + 5 others sit at "requested"; nothing downloads until indexers recover. Radarr health check for recovery.
3. **TVDB_API_KEY not in .env** — user has it; paste → enrich Prisoners/Nightcrawler trailerIds (still missing).
4. **Plex check is now the ownership gate** — dashboard "Available" state (F1 task 3) will surface Plex-owned titles; currently only the cron/skill uses Plex.
5. **Validate trailer IDs in a browser** (oEmbed blocked from sandbox).
6. **Phone acceptance test** of the 15s-polling status UI after deploy; firewall rule for :8123 exists?
7. **Host path mapping:** sandbox `/workspace` = `D:\hermes_agent\hermes-workspace` (9p mount, NOT `D:\media`). Any doc/skill mentioning `D:\media\...` is stale.
8. **Legacy cleanup** - Old files (`api.py`, `build_dashboard.py`, `tvdb_enrich.py`, `rebuild_verify.py`, `fix_all.py`, etc.) can be archived after verifying new architecture works.

---

## Lessons log

- **2026-08-17:** `esc()` must `String(s ?? '')` (silent blank-page crash); posters center via `object-position`; atomic writes + publish guard against corruption; sandbox has NO Docker access (PS deploys) + inline mega-commands get blocklisted → write `.py` scripts.
- **2026-08-18:**
  - **PS 5.1 parse errors = encoding, not syntax.** UTF-8-no-BOM `.ps1` with em-dashes breaks: byte 0x94 reads as a smart quote, terminating strings mid-line ("missing terminator"). Scripts for Windows must be pure ASCII + CRLF.
  - **Docker Desktop cannot follow WSL symlinks.** After consolidating `.env`, compose `env_file: ../.env` hit `media\.env` (a WSL symlink) → "file cannot be accessed". Fix: `env_file: ../../.env` → the real canonical file at the workspace root. Sandbox-side scripts can use the symlink; Windows-side tooling must use the real path.
  - **Radarr ≠ ownership.** Plex had Spirited Away + Andhadhun that Radarr never tracked — Plex is ground truth; Radarr check alone created duplicate pending entries.
  - **qBittorrent is the real download truth.** Radarr queue can be empty while a torrent is active (or vice-versa) — status must read qBittorrent directly.
  - **urllib gotcha:** `timeout=` is a `urlopen()` kwarg, NOT `Request()` — qbit fetch failed silently (returned []) until fixed.
  - **Indexer outage = silent stall.** Requested titles sat static with no explanation; health-check awareness ("Waiting — search indexers down") is essential UX, not decoration.
  - **.env split was cruft** — consolidated to `D:\hermes_agent\hermes-workspace\.env` with `media/.env` symlink; compose env_file + hardcoded script paths keep working.
  - **Plex API shapes:** sections via `/library/sections`; movies = `<Video>` nodes, shows = `<Directory>` nodes in section dumps.
- **2026-08-19 (Architecture Refactor):**
  - **Service layer pattern works** - Clean separation makes testing, debugging, and maintenance vastly easier
  - **Centralized Config** - Single source of truth eliminates env loading bugs across scripts
  - **Atomic watchlist writes** - tmp + os.replace prevents corruption; validation before publish prevents empty dashboards
  - **State machine in WatchlistService** - Valid transitions enforced, prevents invalid states
  - **Structured logging** - JSON logs enable log aggregation and debugging
  - **Pydantic models for API** - Type safety, auto-documentation, validation
  - **Tests first** - Writing tests for plex ownership, radarr/sonarr routing, duplicates, trailers, status, e2e, errors caught design issues early