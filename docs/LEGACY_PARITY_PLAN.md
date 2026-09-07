# Legacy Parity Plan — Discover / Watchlist / Search / Suggest → React shell

Status: **EXECUTED 2026-09-07 — Phases 0–3 shipped in one session** (plan doc
commit + backend `…` + frontend `…`; see `PROGRESS.md` for the record).
Remaining: RKM-HP deploy + user eyeball (`.\\bootstrap.ps1` — api + web both
changed), then roadmap item 4 v2 ("Because you watched") queued behind this.

---

## 1. Why / gap vs today

The React shell (`web/`, Phase 4 cutover) owns `/` — Settings + the Plex-style
Library group (Home / Movies / TV Shows / item pages). Everything else the
legacy app used to do at the top level is still legacy-only:

- **Discover** (hero + curated "Tonight's Picks"-style rows + Continue Watching)
- **Watchlist** (the recommendation-engine grid with chips/sort/state actions)
- **Search** (header combobox over `/api/search`)
- **Suggest** (TMDB discover filters + results + add/download)

`router.tsx` renders these four as `PortedPlaceholder` stubs and the sidebar's
**More** group links to them; `app.js` still owns the real views at `/legacy/`.
PROGRESS.md queues "legacy parity — port Discover/Watchlist/Search/Suggest
from /legacy/ to React" as the approved next programme (own plan doc when
started). This plan is that doc.

## 2. Current state (facts, verified 2026-09-07)

- React shell: React 18 + TS + Vite + Tailwind + TanStack Query; typed client
  `web/src/lib/api/client.ts` + machine-generated `types.ts` over the frozen
  `/api` snapshot (`docs/api/openapi.v1.json`, ADR-0001 additive-only).
  Library slices already ported: Home/folders/item page + player + watched.
- Legacy view data model (app.js): one big `DATA` object (rich entries from
  `/dashboard-data.json` — posters, backdrops, IMDb/RT/TMDB scores, synopsis,
  director/cast, trailer, genres/category) + `RES` resources (keyed by
  canonical media_id from `GET /api/watchlist` — status/capabilities/watch
  links) + `LIB`/`LIBALL`/`LIBWATCH` (library rows). Cards merge both.
- **`/dashboard-data.json` is NOT baked into the React origin.** The `web`
  image only contains `web/dist`; nginx `location /` serves the SPA. The React
  shell cannot depend on a static generated file — parity needs a **live**
  source for the rich entries.
- Live API that already exists: `GET /api/watchlist` (thin §18 resources —
  no poster/backdrop/scores/overview), `GET /api/search` (watchlist + TMDB
  groups), `POST /api/suggest` + `/api/suggest/detail/{id}` +
  `/api/suggest/add/{id}` (TMDB discover + IMDb detail), `GET /api/library*`
  (Jellyfin/Plex rows — already ported), `POST /api/media/{id}/request`
  (downloads), `/api/config` (services + heroMode).
- The authoritative watchlist store (SQLite) already carries the rich fields;
  `scripts/rebuild_dashboard.py:normalize_entry()` maps a `WatchlistEntry` to
  the exact `WatchlistEntryResponse` shape (`api/models.py`) that the UI needs
  — but that mapper lives in a *script*, not a service module.
- Frontend test conventions: pure helper modules under each `features/*/lib.ts`
  unit-tested in vitest node env (no jsdom dep); client tests mock fetch.

## 3. Design

### 3.1 Shared rich-entry seam (backend, additive)

- New **`services/dashboard.py`** — canonical display mapper
  `GENRE_HINTS` + `to_rich_entry(entry) -> dict` (moved verbatim from
  `scripts/rebuild_dashboard.normalize_entry`; the script keeps its public
  `normalize_entry` name by delegating to it). One mapping for every consumer
  (dashboard rebuild + the new API route).
- New additive route **`GET /api/watchlist/entries`** in `api/routes/watchlist.py`:
  loads the repo via `WatchlistService().load()` (same seam as the script) and
  returns `WatchlistEntriesResponse { updated, entries: WatchlistEntryResponse[] }`
  for `pending + recommended`. Reuses the existing `WatchlistEntryResponse`
  model → **one new schema, one new path** on the frozen contract.
- Result: the React shell gets a **live** rich-entry source; no static-file
  dependency, no nginx change, and `/api/watchlist` (thin resources) stays the
  companion for per-title state — exactly the legacy `DATA + RES` split.

### 3.2 Frontend — one shared `watchlist` feature slice + four thin views

New `web/src/features/watchlist/` owns the shared model so Discover/Watchlist/
Search/Suggest never duplicate entry→state logic:

- `client.ts` additions (+ types): `getWatchlistEntries`, `getWatchlist`,
  `search`, `suggest`, `suggestDetail`, `suggestAdd`, `requestMedia`
  (+ `WatchlistEntry`, `MediaResource`/`WatchLink`, `SearchHit`, `Suggest*`
  types). All same-origin `/api/*`.
- `lib.ts` pure helpers mirroring legacy app.js (unit-tested):
  - identity: `mediaIdOf(entry)` (`type:tmdb:` → `type:imdb:` → `type:tvdb:`)
  - state: `resourceFor(entry, resources)` + `deriveState(entry, resource)` →
    `{state, capabilities, watch}` (legacy `st()` semantics, incl. the
    services-healthy default `not_added`)
  - actions: `canDownload`, `isDownloaded`, `isBusy`
  - rows: `daySeed()`, `seededShuffle()`, `pickHero(entries, mode)`,
    `buildRows(entries)` (Tonight's Picks / New to Watchlist / Highly Rated /
    Hidden Gems / Critically Acclaimed / top-3 categories / "Because you
    Like <director>", max 8 rows, ≥2-item rows only)
  - watchlist: `filterWatchlist(entries, resources, {type, sort})` — chips
    All/Movies/TV/Downloaded/Not Downloaded + sort recent/rating/release/title
  - format: `fmtRuntime(min)`, `fmtRating`
- `api.ts` hooks: `useWatchlistEntries`, `useWatchlistResources`,
  `useSearch`, `useSuggest`, mutations `useAddSuggest` (+ optimistic upsert
  into the entries cache + resource invalidation), `useRequestMedia`.
- `WatchCard.tsx` — legacy `cardMarkup` parity in the Tailwind design system:
  badges (★ IMDb / RT% / MOVIE|TV), bright "in library" tick, Jellyfin
  resume/watched marker, hover actions (Download → request; Watch on
  Plex/Emby/Jellyfin ext links; Play in RKM / Episodes → the item's
  `/library/item/:id` page when the Jellyfin watch link carries an `item_id`;
  Trailer) + title/meta footer. Whole card opens the detail modal.
- `WatchlistDetail.tsx` — legacy `openModal` parity (backdrop, floating
  poster, chips, scores, synopsis, director/cast/added facts, trailer embed
  or Search-YouTube fallback, state-driven action row).
- `WatchCardRow.tsx` — legacy `rowMarkup` (heading + horizontal row).
- Tiny zustand toast store (`features/watchlist/toast.ts`) so add/download/
  errors surface like legacy toasts without prop-drilling.

Views (thin, route-wired in `router.tsx`, sidebar unchanged):

1. **`DiscoverView`** (`/discover`): hero (`pickHero` with `/api/config`
   heroMode; backdrop + chips + scores + overview + trailer/download action)
   + `WatchCardRow`s from `buildRows` + **Continue Watching** + **Recently
   Added** library rows (existing `useContinueWatching`/`useLibraryRecent` +
   `MediaCard`, navigating to item pages) + My Library strip with counts
   → link to `/library/home`.
2. **`WatchlistView`** (`/watchlist`): "N of M titles" head, chip row +
   sort `<select>`, lazy page-in (first 36 + sentinel button), state-aware
   `WatchCard` grid, empty states per chip, My Library strip.
3. **`SearchView`** (`/search`): page-level combobox (180 ms debounce), groups
   **Watchlist** + **Live results (TMDB)** (row: poster/title/year/type/
   director/cast + Download), ArrowUp/Down/Enter/Escape selection, row click →
   `WatchlistDetail` (entry matched by imdbId/tmdbId, else an ad-hoc stub),
   no-match state, `servicesDown`/`tmdbKey` note when TMDB is off.
4. **`SuggestView`** (`/suggest`): filters (All/Movies/TV chips, genre chips,
   year from/to, min rating, sort, count), Search + Clear, **Recent** history
   chips (last 10, localStorage `rkm_suggest_history`), results grid
   (score badge, On-Watchlist/In-Library badges, Add + Download buttons,
   whole-card click → detail modal via `/api/suggest/detail`), Add → upsert
   rich entry into the cache; Download → add + `POST /api/media/{id}/request`.

### 3.3 What parity deliberately does NOT copy

- Legacy `movies`/`tv`/`downloaded` top-level tabs are superseded in the new
  IA by the Library folders + Watchlist chips (they are not in the sidebar).
- Header combobox → a dedicated `/search` route (the shell's sidebar owns
  nav); same API + interactions.
- Lazy infinite-scroll → a simple "load more" sentinel (same 36/page cadence).
- No new npm deps; no nginx/Dockerfile change; `/api` frozen + additive only.

## 4. Phases

1. **Phase 0 — plan + shared rich-entry seam (½ day).** `services/dashboard.py`
   (`to_rich_entry`); `scripts/rebuild_dashboard.py` delegates; route
   `GET /api/watchlist/entries` + `WatchlistEntriesResponse`; contract
   snapshot regen; route/regression tests (shape matches rebuild output;
   empty repo → `[]`). Gates: full pytest + ruff.
2. **Phase 1 — shared watchlist slice (1 day).** client types + fns; hooks;
   `lib.ts` pure helpers (+ unit tests mirroring legacy row/build/filter
   logic); `WatchCard`/`WatchlistDetail`/`WatchCardRow`; toast store. Gates:
   vitest + tsc + build.
3. **Phase 2 — the four views (1 day).** Discover, Watchlist, Search, Suggest
   components + routes; delete `PortedPlaceholder` usage for them. Gates:
   vitest + tsc + build (full).
4. **Phase 3 — acceptance + record + deploy.** Static headless smoke of the
   built dist (route render + no console errors where a live backend is
   available); PROGRESS.md record; push; RKM-HP `.\\bootstrap.ps1` +
   user eyeball list.

## 5. Acceptance

1. `/discover` shows a hero + curated rows + Continue Watching + library
   strips; row logic matches legacy (same picks, seeded daily).
2. `/watchlist` chips + sort filter the live entry list; cards carry truthful
   state (Download/Watch/Available/Downloading) from the resource API and
   watched/resume markers when a Jellyfin link is present.
3. `/search` returns Watchlist + TMDB groups with keyboard nav; activating a
   row opens its detail; Download requests the media.
4. `/suggest` filter → results → Add (watchlist + immediate upsert) and
   Download (add + request) work; history chips re-run saved filters.
5. No regressions: vitest + tsc + vite build + full pytest + ruff green;
   contract snapshot regenerated (additive: +1 path); types.ts regenerated
   with zero manual drift.
6. RKM-HP deploy via `.\\bootstrap.ps1` (api + web both changed), then the
   user eyeballs the four views (bundled stack: 2 movies + the same watchlist).

## 6. Out of scope / notes

- Roadmap item 4 v2 ("Because you watched"/similar, server-side TMDB
  enrichment) stays queued *after* parity.
- Legacy `app.js`/`api.js` are kept at `/legacy/` (retirement waits for
  full parity sign-off across all four views).
- Multi-user/auth, quality-profile pickers, and Bazarr auto-subs remain
  parked/unchanged.
