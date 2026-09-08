# Similar Titles ("Because you watched") — Plan

> Branch `feat/similar-titles-cw-episodes` (from `main` @ `8bb66d9`, created 2026-09-08).
> **Status: READY — execute next session (backend first, gates green after each phase).**
> Roadmap item 4 v2 — server-side TMDB enrichment for a "Because you watched" row on the item detail page.

## Goal

On an item's page (`/library/item/:id`), show a **"Because you watched <title>" row** of similar titles fetched from TMDB server-side, like Plex/Netflix. The client-only library cache cannot do this — it needs TMDB's similarity graph, which requires the item's **TMDB id** (not always present in the cache) and server-side calls (key stays server-side).

## Current state (verified 2026-09-08)

- TMDB `/movie/{id}/similar` and `/tv/{id}/similar` **live-verified**: both return `results[]` capped ~20, each with `id`, `title` (movie) / `name` (tv), `release_date` / `first_air_date`, `vote_average`, `poster_path`, `backdrop_path`. Movie sample (550): first hit id 135254 etc. TV sample (1396): first hit id 1814 etc.
- `TMDBService` (`backend/services/tmdb.py`) is the canonical client: `_request(endpoint, params)` (key server-side, error-shape standard), `_cached(key, loader)` (its caching seam), plus `genre_names`, `get_movie_details`, `get_show_details`, `search_movie/show`. **No `similar` method yet** — add `get_similar(tmdb_id, media_type)` here.
- Library item shape (`services/library/jellyfin.py` `_item_public`): id/name/type/year/…/genres/added/play facts. Similar needs the Jellyfin item → **TMDB id** link. The provider's raw Jellyfin item carries `ProviderIds.Tmdb`; `item_detail` (added for the preplay overlay, Phase 1 of PLEX_UI_PLAN) is the natural place to surface it (`tmdb_id` on detail) or resolve internally.
- Existing route patterns to mirror: `GET /api/jellyfin/detail?id=` + `GET /api/jellyfin/person?id=` (additive paths, `docs/api/openapi.v1.json` 35 paths today → +1).
- TMDB poster/backdrop URLs (`https://image.tmdb.org/t/p/w500/…`) are public (no key on the image CDN) and are already used directly by the Suggest flow — no proxy needed for similar-card art.

## Contract / API

Additive only (ADR-0001, `/api` frozen):

- `GET /api/jellyfin/similar?id=<jellyfin item id>&limit=10` → `{similar: [{id(tmdb), title, year, kind: movie|show, score, poster, backdrop}]}`
  - Route calls `LibraryService.item_similar(item_id, limit)`; Jellyfin provider: fetch the item (or reuse detail) → `ProviderIds.Tmdb` → `TMDBService.get_similar(tmdb_id, type)` → map to the display shape.
  - 404 when the item has no TMDB id or isn't a movie/series; 503 when Jellyfin unconfigured (mirror detail route semantics).
  - Server drops titles already in the local library **only if cheap** (Jellyfin title scan compare is optional v1 — the React side can also filter against the shared `useLibraryItems` cache). Decide at implementation: prefer React-side filtering (zero extra backend cost).
- Contract snapshot regen (`python backend/scripts/snapshot_openapi.py`) + `npm run generate:types` (frontend/ types.ts) — expect 35 → 36 paths.

## Phases

### Phase 0 — verify before building
- Probe (extend `scripts/probe_jellyfin_detail.py` or a small stdlib script): item_detail for one movie + one series — confirm `ProviderIds.Tmdb` is returned and which field shape (`ProviderIds` under `Fields=ProviderIds`). If the bundled library item lacks Tmdb (rare), fall back to the `tmdb` provider id from Jellyfin's `ProviderIds` map key (`Tmdb`).
- Confirm `GET /api/jellyfin/similar` route shape against a known movie (Fight Club → TMDB 550 style similar list with 10 rows).

### Phase 1 — backend
- `TMDBService.get_similar(tmdb_id, media_type)` (movie → `/movie/{id}/similar`, show → `/tv/{id}/similar`), cached (TTL consistent with other TMDB metadata caches), returns normalised list (never raw).
- `JellyfinLibraryProvider.item_similar(item_id, limit)` (or via existing `item_detail` plumbing) → tmdb id → TMDBService → display rows `{id, title, year, kind, score, poster, backdrop}`; not-a-movie/series or no-tmdb → `[]`/None (never fabricated).
- Route `GET /api/jellyfin/similar?id=` in `api/routes/` + wire in `api/main.py`; register; snapshot + types regen.
- Tests (+~6): service normalisation per media type, cache hit, route 200/404/503, mapping year/kind/score fallbacks, no-tmdb → 404 (soft).
- Gates: `cd backend && python -m pytest tests/ -q` · ruff · snapshot **+1 path only**.

### Phase 2 — frontend
- `client.ts` `getSimilar(itemId)` + types; pure `lib.ts` helper for row model if needed (unit-tested).
- `ItemDetailPage`/`ItemDetail.tsx`: render a **"Because you watched <title>"** horizontal row under the detail metadata (only for movies/series; hidden when the fetch returns empty or errors silently). Card = poster + year + score; click navigates to that TMDB item? — **v1 scope: no navigation to non-library titles** (they may not be in the library). Decide at implementation: either a subtle "not in your library" treatment or reuse the Search/Suggest detail modal path (TMDB-based, already exists for Suggest) for full cards — **recommended: reuse the Suggest-style detail modal** so cards are actionable (Add/Download when *arr is configured), otherwise the row is decoration.
- Gates: `cd frontend && npm run typecheck && npx vitest run && npm run build`.

### Phase 3 — acceptance
- Headless/live: serve dist like nginx → open a movie detail page → row renders 10 real TMDB titles with posters, zero console errors; series page likewise.
- ⚠ Deploy `.\\bootstrap.ps1` on RKM-HP → eyeball a movie + a series item page ("Because you watched" row present, cards look right). RKM-HP eyeball = acceptance (established).

## Out of scope (this pass)

- Similar for Plex/Emby providers (prod watchlist mode) — route/ABC default `[]`; additive slot left for later.
- "Recommendation engine" quality gates — this is TMDB-similar only, not the internal recommender.
- Preplay footer media-facts line (deferred earlier, still deferred).

## Rollback

Each phase is a separate commit (`git revert <commit>`). Backend is additive (no existing path modified); frontend is a hidden/conditional row. Nothing destructive.

## Gates after EVERY phase

Backend: `cd backend && python -m pytest tests/ -q` · `ruff check api application config core domain infrastructure jobs services`. Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`. Contract: `python backend/scripts/snapshot_openapi.py` → expected **+1 path, zero unrelated diff**.
