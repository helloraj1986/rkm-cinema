# Library & Discovery Plan — search / filters / sort on the new folder views (roadmap item 4)

Status: **EXECUTING 2026-09-07.** Approved as "next" after Plex-style views &
navigation (Phases 0–2, `34e4dfa`). Scope here is **v1: in-library search,
genre filter + sort** on the Movies / TV Shows folder views (+ Home), built on
the shared `useLibraryItems` cache. "Because you watched"/similar needs
server-side TMDB enrichment and is scoped as **v2 (deferred)**.

---

## 1. Why / gap vs today

The library now has true Plex-style navigation (Home + Movies + TV Shows
folders + item pages), but the folders are static poster walls: no way to
search the library, narrow by genre, or re-order (unwatched / newest / title).
Roadmap item 4 ("library & discovery — in-library search, filters/sort
(unwatched/newest/type/genre), Because you watched") fills that in.

## 2. Current state (facts, verified 2026-09-07)

- `/api/library/items` returns every Movie + Series with playback facts but
  **no genres and no "added" date** — `JellyfinItem`/`_item_public` only carry
  name/year/thumb/ids/played/position/runtime/play_count/last_played.
  `_parse_item` receives `Fields=PrimaryImageAspectRatio,ProductionYear,
  ProviderIds,UserData` only — Jellyfin returns `Genres` (name strings) and
  `DateCreated` (ISO) when requested, same as the detail fetch already proves.
- Folders split the cached list client-side (`libraryItemsByType`); the same
  list is the single source for Home rows — so controls over that list are
  instant and need **no new fetch**.
- Frozen `/api` (ADR-0001): additive-only. `/api/library/items` has no
  `response_model` → adding dict keys does not change the OpenAPI schema.
  `types.ts` is machine-generated; `client.ts` hand-types the narrow surface
  (`MediaItem`) and is where the new optional fields land.
- Emby/Plex providers do not implement `all_items` (route falls back to `[]`),
  so folder-view filtering only ever runs over Jellyfin items — no parity work.

## 3. Design

### Backend (additive, Jellyfin provider only)

- `JellyfinItem` gains `genres: list[str]` + `date_added: str` (ISO, "" when
  absent). `_get_items` adds `Genres,DateCreated` to the requested Fields;
  `_parse_item` populates both; `_item_public` emits
  `genres: [...]` and `added: "ISO"|None` (None when unknown — never a guess).
- Same fields ride `recently_added`/`continue_watching`/`recently_watched`
  automatically (shared `_item_public`). No route change, no schema change.

### Frontend (pure helpers + folder toolbar)

- `features/library/lib.ts` (+ unit tests):
  - `itemGenres(items)` → union of all genres, alphabetical (chip source).
  - `librarySortOptions` — `recent` (Recently added), `title` (A–Z),
    `unwatched` (Unwatched first).
  - `filterLibraryItems(items, kind, {q, genre, sort})` → type split + case
    -insensitive title search + genre membership + sort. Sorts are stable:
    recent = `added` desc (unknown-dates last); title = localeCompare;
    unwatched = unplayed first, then `added` desc.
- `LibraryFolderView` gains a compact toolbar: search input (client-side over
  the cached list — instant, no debounce/backend), genre chip row (from the
  kind's own list), and a sort `<select>`. Empty states update ("No matches
  for …").
- `MediaItem` in `client.ts` gains optional `genres?: string[]` and
  `added?: string | null`.
- Home unchanged in v1 (its rows already reflect state; type/genre browsing is
  the folders' job).

### v2 (deferred, not in this pass)

- "Because you watched" / similar rows — needs server-side TMDB enrichment +
  an additive endpoint; separate plan.
- Genre quick-chips per-folder counts, row/card size switch, recently-added
  section per folder (sort covers it), server-side filter if a folder grows
  huge (PLEX_VIEWS_PLAN §6 note stays).

## 4. Phases

1. **Phase 0 — backend fields (½ day).** JellyfinItem genres/date_added +
   Fields + parse + `_item_public`; regression tests (parse captures both;
   all_items emits them; absent → [] / None). Gates: full pytest + ruff.
2. **Phase 1 — frontend controls (1 day).** Pure helpers + tests; folder
   toolbar (search/genre/sort); MediaItem fields; empty-state copy. Gates:
   vitest + tsc + build.
3. **Phase 2 — acceptance + deploy.** Backend+frontend → `.\\bootstrap.ps1`
   (or `docker compose -p rkm-bundled up -d --build api web`) on RKM-HP; user
   eyeball: search narrows instantly, genre chips filter correctly, sort
   orders truthfully (recent uses real added dates), movie card never in
   Shows, badges/state still move.

## 5. Acceptance

1. Typing in a folder's search box narrows the grid live (title match,
   case-insensitive) — no new fetch, no backend call.
2. Genre chips filter that folder to the selected genre; chips come from that
   folder's own titles.
3. Sort orders truthfully: Recently added (by Jellyfin `DateCreated`), A–Z,
   Unwatched first; unknown dates sort last, never fabricated.
4. Everything still works when the filter yields nothing (clear "no matches"
   state + one-click clear).
5. No regressions: vitest + tsc + build + full pytest + ruff green; contract
   snapshot unchanged (no schema change).

## 6. Out of scope / notes

- Legacy parity ports (Discover/Watchlist/Search/Suggest → React) are the
  **next programme after this item** (user approved "item 4 then parity");
  own plan doc when started.
- Bazarr auto-subs (needs OpenSubtitles account) stays parked; bundled-
  Jellyfin admin password in `rkm.config.toml` is stale (401) — update when
  next live-data acceptance is wanted.
