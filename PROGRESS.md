# RKM Watchlist — Session Handoff & Project Progress

> Last updated: 2026-08-22 (**PRODUCTION REFACTOR in progress — Phases 1–3 done, next: Phase 4**)
> Live URL: **http://rkm-hp.tail8d5e8.ts.net:8123/** (Tailscale MagicDNS, tailnet-only — NEVER `tailscale funnel` it; page proxies /api → FastAPI which holds secrets server-side)
> Deploy path (Windows, RKM-HP): `cd D:\hermes_agent\hermes-workspace\media\watchlist; .\setup-watchlist.ps1` — the sandbox's `/workspace` maps to `D:\hermes_agent\hermes-workspace` (9p mount, confirmed via mountinfo 2026-08-18; NOT `D:\media`)
> Repo: **private `rkm-watchlist` on GitHub** (github.com/helloraj1986/rkm-watchlist)
> **Status:** ⚠️ **Big production refactor IN PROGRESS.** Groundwork (Phases 1–3) committed (`db1fc29`); the running site is still the OLD deployed image — do NOT redeploy mid-refactor.

## ▶ LATEST SESSION (2026-08-22) — refactor Phases 1–3 ✅ (audit → identity → persistent store)

**Driving spec: `RKM_Watchlist_Production_Refactor_Task.md`** (26-phase production architecture → desired-state media orchestration). This is THE checklist — follow its §42 implementation order strictly. **No separate task.md file is created; the spec lives in that one file.** Audit lives at `docs/ARCHITECTURE_AUDIT.md`.

**Baseline before this work:** 56 tests green. **After Phases 1–3: 74 tests green** (`python3 -m pytest tests/ -q`, all mockable — no LAN). Commit `db1fc29`.

### Phase 1 — Repository audit ✅ (`docs/ARCHITECTURE_AUDIT.md`)
- Documented existing-vs-target, **all duplicate logic**, risky gaps (no canonical identity, JSON-as-authoritative DB, no library/acquisition abstraction, hardcoded recommendation gates, host-cron only), and the exact file merge/delete plan.
- Key duplication to consolidate later: Emby URL resolution in **3 places**, Plex URL base in **2**, near-identical Plex/Emby has_media matchers, generic `POST /api/download` + `GET /api/status`.

### Phase 2 — Canonical media identity ✅ (`domain/identity.py`) — spec §4
- `MediaIdentity` (frozen dataclass, TMDB>IMDb>TVDB, normalized ints + `tt`-padded imdb) + `parse_media_id()`. `media_id` strings like `movie:tmdb:603` / `tv:imdb:tt0903747`. Never title-keyed; ambiguity = explicit error. Reuses existing `domain/enums.MediaType` (no parallel enum). 11 tests.

### Phase 3 — Persistent store + repository abstraction ✅ (`infrastructure/database/`) — spec §3/§5
- `db.py` — SQLite (stdlib `sqlite3`, no new deps) with the spec's 7-table schema: `media`, `watchlist`, `recommendations`, `library_items`, `acquisitions`, `watch_links`, `job_runs`. Rich dashboard fields round-trip via a `payload` JSON column.
- `repository.py` — `WatchlistRepository` ABC; `JsonWatchlistRepository` (default, backward-compat) + `SqliteWatchlistRepository` (real alternate store). Factory `build_repository()` keyed by config `WATCHLIST_STORE=json|sqlite`, DB path `WATCHLIST_DB_PATH`.
- `services/watchlist.py` now persists **only through the repository** — no business code reads `watchlist.json` directly (spec §5 mandate). `WatchlistService(path=...)` still works for tests/explicit JSON. `config/settings.py` gained `WATCHLIST_STORE` / `WATCHLIST_DB_PATH` (added to env-override key set).
- Verified the live 17-entry watchlist still round-trips through the repo-backed load.

### Testing note
- Local full suite needs `pip install -r requirements.txt` (fastapi) **and** `pip install httpx2` (for `fastapi.testclient`).

---

## ⚡ NEXT SESSION — RESUME EXACTLY HERE (Phase 4)

**Do NOT skip ahead / do NOT touch the frontend until the state model is done (§42 "do not skip ahead to frontend fixes while the underlying state model is incorrect"; §43.3 no parallel implementations; §43.7 keep `pytest` green after every phase).**

1. ⬅️ **Phase 4 — Library abstraction** (`services/library/`) — spec §4/§6/§7/§8 + audit §3-§4 gaps
   - Create `LibraryProvider` ABC: `health`, `find(identity)`, `recently_added`, `build_watch_link(match)`.
   - New `services/library/service.py` (`LibraryService` with Plex + Emby providers) + `plex.py` + `emby.py`.
   - **Consolidate** the 3 Emby URL builders (`PlexService.emby_url_for/_emby_item_id/_emby_server_id` + `api/routes/library.py` + state_machine) and the 2 Plex URL builders into these providers (audit §3). **Merge** `services/emby.py` matcher into `services/library/emby.py`.
   - Plex match must capture real identity: `ratingKey`, `machineIdentifier`, `guid`, `title`, `year`, `library_section` — and match by **stable ID**, not just title/year.
   - Treat Plex + Emby as providers of the **same** library (no duplicate "Plex available/Emby available" states).
2. **Phase 5 — Watch links** (`services/library/watch_links.py`): `WatchLink{provider, available, url, error}`; browser URLs config-driven (`PLEX_BROWSER_URL`/`EMBY_BROWSER_URL`); **watch-link failure must NOT flip AVAILABLE→NOT_REQUESTED**.
3. **Phase 6 — `domain/status.py`**: canonical resolver on `MediaFacts` (pure, no HTTP). Then **Phase 7** reconciler → `MediaSnapshot(status, capabilities, watch)`. **Phase 8** `services/acquisition/` (single routing). **Phase 9** `application/commands/request_media.py` (idempotent). …
4. Continue down the §42 list; **Phase 3's `job_runs` table is ready** for Phase 13/14 jobs.

See `docs/ARCHITECTURE_AUDIT.md` → "Implementation order (tied to spec §42)" for the full remaining map.

## ⚡ HOW TO PICK UP WORK HERE (pre-refactor context, superseded for the refactor task)

- **Current refactor source of truth = `RKM_Watchlist_Production_Refactor_Task.md` + `docs/ARCHITECTURE_AUDIT.md`** (this). For the *current live modular backend*, `ARCHITECTURE.md` is the up-to-date map. The **old two-API-layer split is GONE**: the monolithic `api.py` is archived (`archive/api_legacy_monolith.py`) and the live backend is **`uvicorn api.main:app`**. Edit the modular tree — `api/routes/*` (thin), `services/*` (business logic), `domain/*` (state machine + media-type resolver), `infrastructure/database/*` (persistence).
- **Adding a feature** → follow ARCHITECTURE.md §12 ("Adding a feature").
- **Quick checklist:** backend change → edit `api/routes/*` + `services/*` (+ `domain/*` for rules, `infrastructure/database/*` for persistence), then `python -m pytest tests/ -q` (must stay green), then `scripts/rebuild_dashboard.py`, then deploy `.\setup-watchlist.ps1`. Frontend (`api.js`/`app.js`/`app.css`) is volume-mounted — no rebuild needed for UI-only changes.
- **Secrets** live in `/workspace/.env` (canonical). `.env` is git-ignored; use `.env.example` as the template. **Never commit real keys.**

## Latest session (2026-08-21) — curated batch of 8 added ✅

- **Scope:** solid curated batch (movies + series), verified live, added to pending + dashboard rebuilt. User picked this.
- **Ownership gate:** pulled Plex ground truth — **774 movies (incl. 132 kids) + 100 shows** (section keys: Movies 13, Kids 19, TV Shows 15). Candidates were deduped against this BEFORE selection. Many popular titles (Interstellar, Dune Pt2, Parasite, Whiplash, Chernobyl, Severance, Beef already-in-pending, etc.) rejected as owned.
- **Batch added (8):** Knives Out(tt8946378), Blade Runner 2049(tt1856101), Ex Machina(tt0470752), There Will Be Blood(tt0469494) [4 films] + The Expanse(tt3230854), Shōgun(tt2788316), Ozark(tt5071412), Scam 1992(tt12392504) [4 series, Hindi]. → **17 pending total (10 movies / 7 series).**
- **Scores live-verified** via r.jina.ai (IMDb) + RT direct/aggregate (BR2049=88, Shōgun=94, Expanse=85, Ozark=86, Knives=92, ExMachina=86, TWBB=86; Scam 1992 IMDb 9.2, not on RT → rt:0). All pass gates (OR).
- **All 8 TMDB↔IMDb IDs cross-verified OK** (Radarr/Sonarr lookups will resolve). Posters + trailerIds live-validated (HTTP 200 image/*).
- **Wrote via atomic tmp+os.replace, deduped by imdbId, validated pending[].** Rebuilt dashboard → live `:8123` already serves 17 (volume-mounted, no redeploy needed).
- Remaining entry-level gap: **The Night Agent (rt 74 / imdb 7.0) still in pending** — breaks the series gate (needs RT≥85 OR IMDb≥8.0); pre-existing, flag to user if they act on it.

## Latest session (2026-08-21) — Watch-Now links fix (2 backend bugs) ✅ verified live

**Symptom:** page showed "Download" on titles already in the Plex library instead of Watch links.
**Root cause:** `/api/status` **timed out at 30s+**, so the frontend never received `available` state → fell back to Download. The UI already renders Watch Now/Plex/Emby for `available`; it was the backend that never answered.

Two compounding backend bugs (modular API, both deployed):
1. **No Plex library caching** — `PlexService.get_all_movies()/get_all_shows()` did a FULL Plex scan (774→790 movies + 100 shows) on **every entry**. `/api/status` calls `has_media` on all 17 pending → 17 full rescans → blew the window. `_library_cache` was declared but never used. **Fix:** wired it up with a 60s TTL (first scan ~1.3s, cached ~0.2s; full status pass 4.8s). Committed `820f772`.
2. **Sonarr None crash** — for unmatched TV entries, `stats = rec.statistics` ran even when `rec is None` → `AttributeError`. **Fix:** `getattr(rec, "statistics", None) or {}`. Committed `3d50b4b`.

**Verified against LIVE services from sandbox:** 17 entries resolved in 4.8s → 2 downloading / 8 available / 7 not_added. Available titles carry correct deep links (`app.plex.tv/.../7780f377...` + Emby `#!/item?id=…`). Tests: 39 pass (ignoring fastapi-only modules).

**⚠️ DEPLOY REQUIRED on RKM-HP** to ship both fixes into the running image:
```powershell
cd D:\hermes_agent\hermes-workspace\media\watchlist
.\setup-watchlist.ps1
```
Then hard-refresh the page (Ctrl+Shift+R). Verify `/api/status` returns <5s and owned titles show Watch Now instead of Download.

## Latest session (2026-08-21) — Watch deep-links fixed to point at server web UI ✅

**Symptom:** Plex/Emby Watch links "don't open anything."
**Root cause:** Plex deep-links pointed at **`app.plex.tv`** (Plex's cloud app) which requires account login + remote relay and rarely auto-opens the item. Also `plexKey` was set to the full URL instead of the numeric ratingKey. Emby already deep-linked into the local server's web UI correctly.
**Fix (commit `ecf4b58`):**
- **Plex links now point at the server's OWN web UI** on the browser-reachable Tailscale HTTPS host: `https://rkm-hp.tail8d5e8.ts.net:32400/web/index.html#!/server/{machineId}/details?key=/library/metadata/{ratingKey}` — **raw path, not `%2F`-encoded** (encoding broke Plex's hash router). Same idea Emby already uses. No cloud relay.
- **plexKey** now carries the numeric ratingKey (`320819`), not a URL.
- **Config-driven browser endpoints:** new optional `PLEX_BROWSER_URL` / `EMBY_BROWSER_URL` in `.env`; default safely to the Tailscale host (browser-reachable) even unset. LAN `PLEX_URL`/`EMBY_URL` (backend/API) are NOT used for deep links.
- `api/routes/library.py` hardcoded `app.plex.tv` + Emby URL cleaned up to the same config-driven builder.
- **New regression tests `tests/test_watch_links.py`** (7) + 2 library-cache tests in `test_plex_ownership.py` → **46 pure-logic tests pass**. Asserts: no app.plex.tv, raw `/library/metadata/`, numeric plexKey, Tailscale default fallback, search fallback, cached-scan reuse.
- **Live-verified:** available titles now emit `https://rkm-hp.tail8d5e8.ts.net:32400/web/index.html#!/server/7780f…/details?key=/library/metadata/320819` (web UI HTTP 200) + Emby item links.

**⚠️ DEPLOY REQUIRED on RKM-HP** (same as above): `cd D:\hermes_agent\hermes-workspace\media\watchlist; .\setup-watchlist.ps1`, then hard-refresh.
**Optional .env addition (not required — defaults work):** `PLEX_BROWSER_URL=https://rkm-hp.tail8d5e8.ts.net:32400` and `EMBY_BROWSER_URL=https://rkm-hp.tail8d5e8.ts.net:8096` if you want them explicit.

## ⚡ HOW TO PICK UP WORK HERE

- **Start with `ARCHITECTURE.md`** — it's the up-to-date map. The **old two-API-layer split is GONE**: the monolithic `api.py` is archived (`archive/api_legacy_monolith.py`) and the live backend is now the **modular FastAPI app** (`uvicorn api.main:app`). Edit the modular tree — `api/routes/*` (thin), `services/*` (business logic), `domain/*` (state machine + media-type resolver). There is exactly ONE implementation of each rule.
- **Adding a feature** → follow ARCHITECTURE.md §12 ("Adding a feature").
- **Quick checklist:** backend change → edit `api/routes/*` + `services/*` (+ `domain/*` for rules), then `python -m pytest tests/ -q` (must stay green), then `scripts/rebuild_dashboard.py`, then deploy `.\setup-watchlist.ps1`. Frontend (`api.js`/`app.js`/`app.css`) is volume-mounted — no rebuild needed for UI-only changes.
- **Secrets** live in `/workspace/.env` (canonical). `.env` is git-ignored; use `.env.example` as the template. **Never commit real keys.**

## Latest session (2026-08-21) — production-grade refactor ✅

**Goal:** eliminate the two-backend problem and make the modular architecture the single source of truth.

- **Domain layer added (`domain/`):** `enums.py` (`MediaType`, `MediaStatus`, `DownloadResultState`), `models.py` (`DownloadResult`), `state_machine.py` (`resolve_status()` — the ONLY availability resolution: Plex→available, *arr hasFile→downloaded, qBittorrent→downloading, *arr record→requested, else not_added), `resolver.py` (`resolve_media_type()` — single movie/tv resolver).
- **Services stabilized (DI):** all services now accept injectable `config`/`http` (testable, no real LAN). Extracted **`QBittorrentService`** and **`MediaStatusService`** from the fat status route.
- **Routes thinned:** `status.py` delegates to `MediaStatusService`; `download.py` delegates to new **`DownloadService`** (routing + add + title-fallback + cross-service fallback + "pick one" ambiguity → typed `DownloadResult`). Added **`/api/plex/thumb`** route (via `PlexService.get_thumb`) so modular cutover doesn't break thumbnails.
- **Fixed latent bugs found by tests:** `UnboundLocalError` in both `RadarrService.add_movie` & `SonarrService.add_series` when no quality-profile override set; silent-guess ambiguity now returns **`ambiguous`** instead of picking a wrong title; `WatchlistService.update_status` to `recommended` now moves the entry out of pending into history.
- **Docker migration (Phase 5):** `Dockerfile` now copies `api/ services/ domain/ core/ config/` + `requirements.txt` and runs **`uvicorn api.main:app`**. `WatchlistService` auto-resolves `/app/watchlist.json` (container) vs `/workspace/media/watchlist.json` (sandbox). Verified the copied Docker tree imports and exposes all 8 endpoints.
- **Frontend (Phase 7):** new **`api.js`** centralized API client (`API.getJSON/getStatus/download/...`); `app.js` delegates all `/api/*`+`/dashboard-data.json` calls to it. `api.js` wired into `index.html` + `dashboard.html`. No rendering/behavior change.
- **Legacy removed (Phase 6):** `api.py` → `archive/api_legacy_monolith.py` (+ `archive/README.md`).
- **Tests: 47 passing, all mockable (no live LAN):** domain state machine, media-type resolver, Radarr/Sonarr routing + title fallback + ambiguity, download status, error handling, Plex ownership, duplicate prevention, trailer validation, recommendation pipeline, and API endpoints (`tests/test_api.py`).

**⚠️ DEPLOY REQUIRED:** all of the above is committed but the running site is still the OLD monolithic image. Run `.\setup-watchlist.ps1` on RKM-HP to build & start the modular backend (`uvicorn api.main:app`). Then verify `/api/health`, `/api/config`, `/api/status`, `/api/library`, `/api/plex/thumb`, download flow, and Plex/Emby watch buttons per ARCHITECTURE.md §11.

---

## Previous sessions

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