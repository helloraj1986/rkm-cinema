# Continue Watching — in-progress EPISODES — Plan

> Branch `feat/similar-titles-cw-episodes` (from `main` @ `8bb66d9`, created 2026-09-08).
> **Status: READY — execute next session (Phase 0 probe first, backend before frontend, gates green after each phase).**
> Known gap recorded in PROGRESS/skill since 2026-09-06: Continue Watching rows list only movies/series — in-progress EPISODES never surface.

## Goal

Continue Watching should include **partially-watched episodes** (e.g. "3 Body Problem S1E4 · 43%") so a half-finished episode is one click from resuming — matching Plex/Jellyfin's own resume behaviour. Today the RKM Home row + item-page resume data only roll up series-level UserData, which Jellyfin leaves at 0 even when episodes are mid-way.

## Current state (facts banked in skill `jellyfin-web-playback`)

- **Jellyfin `UserData` on a SERIES item does NOT roll up episode positions** (pos=0 even when episodes are mid-way) — that is why the current `continue_watching` (scan filter `position_ticks>0 and not played` over Movies+Series) can never see episodes.
- **Jellyfin's `/Users/{uid}/Items/Resume` DOES list in-progress items individually**, including EPISODES, each with full runtime + `UserData.PlaybackPositionTicks` (+ `SeriesName`, `ParentIndexNumber`/`IndexNumber`, `SeriesId`, thumb). The skill's API-verified reference already documents this.
- Current implementation: `JellyfinLibraryProvider.continue_watching(limit=12)` in `backend/services/library/jellyfin.py` — fetches the scan and filters Movies+Series. The bundled stack's Jellyfin HAS series now (3 Body Problem was used for HLS work), so Phase 0 is doable against the real bundled instance (host.docker.internal:8098), not just unit mocks.
- Frontend row: `LibraryHomeView` Continue Watching row renders `useContinueWatching()` cards via the shared card model — adding an `episode` kind needs card/type handling (badge "S1E4", resume %, primary action).

## Contract / API

Additive-only preference:

- Option A (recommended): **keep `GET /api/library/continue-watching` shape**, extend the emitted items with an optional `episode` facet: existing items gain `kind` (`movie|show|episode`) and episode entries get `episode: {number, season, series_id, series_name}` + standard play/resume facts (they already carry `id`, `played`, `position`, `runtime`). Additive dict keys on a free-form endpoint → **NO snapshot/types regen** (matches the `/api/library` free-form precedent; `types.ts` client hand-types updated instead).
- Option B: new `GET /api/library/continue-watching/episodes` additive path (contract 35 → 36). Only if Option A's item-shape ambiguity bites. Decide at Phase 1; prefer A to avoid contract churn.
- The series-level Continue Watching items stay (a series with ANY in-progress episode could also show as its own row via roll-up — decide v1: include per-episode rows only; series row roll-up is a nice-to-have).

## Phases

### Phase 0 — verify before building (live, bundled Jellyfin)
- Probe: authenticate (repo `.env` Jellyfin admin — skill pattern), pick an episode (3 Body Problem S1E4), POST progress so it has a real position, then call `/Users/{uid}/Items/Resume`; capture the episode item shape (fields: `Id`, `SeriesId`, `SeriesName`, `Name`, `IndexNumber`, `ParentIndexNumber`, `RunTimeTicks`, `UserData.PlaybackPositionTicks`, thumb `ImageTags.Primary`). Restore library state after.
- Confirm the provider's `_fetch_raw`/`_parse_item` can parse an episode item (episode type differs from Movie/Series parse paths — note `_parse_item` may need an `Episode` branch or a light dedicated parser).

### Phase 1 — backend
- `JellyfinLibraryProvider.continue_watching`: fetch `/Items/Resume` (limit-aware) + keep the existing scan-filter as a fallback/merge (dedupe by id); emit `kind: episode` entries with the episode facet. Series/movie rows unchanged in shape (additive `kind`/facet keys).
- Keep `continue_watching` semantics honest: only genuinely in-progress (`position>0`), never guessed; episodes with `Played` excluded.
- Tests (+~4): Resume-parsed episode entry shape + facet; merge dedupe; played-episode exclusion; series/movie entries unchanged (regression).
- Gates: pytest · ruff · snapshot **zero-diff** (Option A) or +1 (Option B).

### Phase 2 — frontend
- `client.ts`/types: episode facet; `lib.ts` helpers (`isEpisode`, episode label "S1E4", thumb URL from episode id) with unit tests.
- `ContinueWatchingRow`/card: episode cards show the episode's own thumb (Jellyfin poster proxy by episode id), a small **S1E4** badge + resume %; primary action = resume the EPISODE (existing per-episode stream path — `stream` proxy works per-episode-id; player resume via `start_time_ticks`/HLS `startPosition`). Secondary/deep-link = the series item page (or Jellyfin episode URL). Decide at implementation how card CLICK behaves (navigate to the series' `/library/item/:id` page vs instant-resume) — recommend: hover ▶ resumes instantly; card click opens the series page so the context/episodes list is visible.
- Hidden/graceful when empty; zero console errors.
- Gates: typecheck · vitest · build.

### Phase 3 — acceptance
- Live/headless: seed a real mid-episode position in the bundled Jellyfin → Home row shows the episode card with S1E4 + % and resume plays from the right spot (headless caveat: decode-independent assertions only; real eyeball is the acceptance).
- ⚠ Deploy `.\\bootstrap.ps1` → RKM-HP eyeball: watch part of an episode, go Home, see it in Continue Watching, resume at the right position. (Prod watchlist stack has real shows; the bundled stack has 3BP.)

## Out of scope

- Series-row roll-up ("continue S1E4 → show the SERIES in CW with its own %") — v1 lists episodes directly; roll-up is a follow-up.
- Recently-watched episode entries (this is Continue Watching only — in-progress, not history).
- Multi-user resume separation (roadmap item 6).

## Rollback

Per-phase commits, revertible. Option A keeps the endpoint free-form and additive, so no consumer breaks.

## Gates after EVERY phase

Backend: `cd backend && python -m pytest tests/ -q` · `ruff check api application config core domain infrastructure jobs services`. Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`. Contract: `python backend/scripts/snapshot_openapi.py` → zero-diff (Option A) or +1 path (Option B).
