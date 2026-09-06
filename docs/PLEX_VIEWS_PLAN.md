# Plex-Style Views & Navigation Plan — dedicated item pages + sidebar folders

Status: **EXECUTED 2026-09-07 — Phases 0–2 DONE (`34e4dfa`, frontend-only).**
The user approved implementing this plan; the preplay overlay became true
Plex-style navigation: URL-backed item pages (`/library/item/:id`, Back works,
deep-linkable) + sidebar **Home · Movies · TV Shows** folders. Phase 0–1 shipped
(see `PROGRESS.md`); Phase 2's acceptance is the user's RKM-HP eyeball after
rebuilding `web` — `.\\bootstrap.ps1` or
`docker compose -p rkm-bundled up -d --build web` (live-data headless
acceptance was deferred: the bundled-Jellyfin admin password in
`rkm.config.toml` was stale → 401). The optional later slices in §4 remain
future work.

---

## 1. Why / gap vs today

The preplay **overlay** (`ItemDetail.tsx`, `fixed inset-0 z-50`) was the fast
path and is confirmed working, but the user wants **Plex web's navigation
model**:

- Click a card → the item opens in its **own dedicated view/page** (URL-backed,
  browser Back works, deep-linkable), not a modal over the grid.
- The **left sidebar** lists browsable sections — **Movies**, **TV Shows**
  (Plex's "folders") — each rendering that type's poster grid.
- Everything else (metadata, Resume/Play, cast, season-grouped episodes) stays
  as built — it's the *chrome around it* that changes.

## 2. Current state (facts, verified 2026-09-06)

- Single view: `web/src/features/library/LibraryView.tsx` renders Continue
  Watching + Recently Watched + a Full Library grid of **all** types
  (`/api/library/items` returns both, `MediaItem.type` = `movie`|`tv`).
- Detail = `ItemDetail.tsx` overlay; open state is component state
  (`setDetail(item)` in `LibraryView`), not a route — no URL, no Back.
- Router (`app/router.tsx`): `/library` only. Sidebar (`app/layout/Sidebar.tsx`)
  links: Settings / Library / Discover / Watchlist / Search / Suggest
  (Discover+ are `PortedPlaceholder`s — legacy owns them until parity).
- Player (`features/playback/Player.tsx`) is already a full-screen overlay —
  it can stay on top of a routed page (Plex does the same).
- No backend/contract work is expected: type filtering can be done client-side
  from the cached `/api/library/items` response (both types already fetched).

## 3. Design (Plex-inspired, no new deps, additive to frozen `/api`)

### Routing (URL is the source of truth)

| Route | View |
|---|---|
| `/library` | Redirect → `/library/home` (keeps old links working) |
| `/library/home` | Continue Watching + Recently Watched + Recently Added ("Home") |
| `/library/movies` | Poster grid, movies only (sidebar "Movies" folder) |
| `/library/shows` | Poster grid, TV only (sidebar "TV Shows" folder) |
| `/library/item/:id` | **Dedicated detail page** — the item's own window |

- `useLibraryItems()` stays the single source; Movies/Shows/Home views filter
  with the existing `isSeries(item)` helper + the cached continue/recent
  queries — **zero backend/contract change**.
- Sidebar gains a library group:
  `Home · Movies · TV Shows` (Plex-style folder section), with active-state
  highlighting per route (`NavLink end` for `/library/home`). Other links stay.
- The grid **stops opening the overlay**; card click (and hover ▶ for movies)
  does `navigate('/library/item/' + id)`. Series hover ▶ also navigates to the
  item page (episodes live on the page).

### Item page (`ItemDetailPage`) — overlay → full page

- Reuse the whole visual/content core of `ItemDetail.tsx` (hero, poster, meta,
  Resume(%), Play/from-beginning, watched toggle, Jellyfin link, synopsis,
  cast, season-grouped episodes). Changes are chrome + behaviour:
  - Root becomes a normal scrollable `<div>` inside the AppShell (no
    `fixed inset-0` backdrop); keep the dark cinematic hero.
  - Replace ✕/Esc-close with a **Back button** (navigates `-1`) + Esc =
    `navigate(-1)`; scrolling to top on item change; loading/error states keep
    the grid-style fallback.
  - `useItemDetail(id)` from the URL param — still fetched on demand + cached
    per item; opening the same item twice is instant and Back restores the
    grid without refetch (React Query cache).
  - Movie Play/Resume & series episode Play/Resume mount the existing
    full-screen `Player` **above the page** (exactly as Plex plays over the
    item page); Up-Next queue unchanged.
- Component shape: keep `ItemDetail`'s internals (split if needed into
  `ItemHero`/`EpisodeList`), add `ItemDetailPage.tsx` as the routed wrapper.

### Card parity (Plex badges/quick actions) — unchanged behaviour

- Cards keep hover ▶ (movies), watched toggle, Jellyfin link, ✓ badge, amber
  resume bar; the ONLY change is the click target: navigate to the item page.

## 4. Phases (each ends committed + green, mirroring PLEX_UI_PLAN)

1. **Phase 0 — Routes + views split (½–1 day).** Add
   `/library/home|movies|shows` views + `/library/item/:id` placeholder;
   `LibraryView` splits into `LibraryHomeView` (continue/recent/added) +
   `LibraryFolderView` (type-filtered grid, "N titles" + scan button lives on
   Home or per-folder as suits); Sidebar library group + active states;
   `/library` redirect. Query keys unchanged (shared `useLibraryItems` cache).
   Tests: pure filtering helpers (`libraryItemsByType`), view wiring.
2. **Phase 1 — Dedicated item page (1–1½ days).** `ItemDetailPage.tsx` route
   (from URL id), Back/Esc, scroll-top, Player-on-top; delete the overlay state
   path from `LibraryView`; cards navigate. Keep `ItemDetail` internals where
   they fit; retire overlay-only chrome. Tests: routing helper tests,
   component-level pure helpers; vitest + tsc + build gates.
3. **Phase 2 — Polish + headless acceptance (½–1 day).** Verify: deep link
   `/library/item/<id>` renders directly; Back returns to the folder/Home;
   sidebar Movies/TV Show active states + correct filtering (movie card never
   in Shows); Resume/Play from the page starts the HLS player at the right
   position; Esc/Back closes player first, then leaves the page; 0 console
   errors. `.\\bootstrap.ps1` deploy note for the user check.
4. Optional later slices (not v1): "Recently added" per folder, genre
   quick-chips on folder headers, in-page search within a folder (roadmap
   item 4 territory), sort controls, row/card size switch.

## 5. Acceptance

1. Clicking any card navigates to that title's **own page** (URL changes, Back
   works, refresh keeps you there); no overlay in the library flow.
2. Left sidebar browses **Movies** and **TV Shows** folders like Plex; grids
   filter correctly and stay fast (shared cache, no refetch).
3. Item page shows everything the overlay did (metadata/Resume/cast/episodes)
   and Play/Resume behaves identically; player overlays the page.
4. Watched/resume badges and mark-watched invalidation still work across all
   three surfaces (Home rows, folder grids, item page).
5. No backend/contract change; no new npm dependencies.

## 6. Out of scope / notes

- Watchlist / Discover / Search / Suggest stay on `/legacy/` until their own
  React-parity ports (sidebar placeholders remain for those).
- Multi-library/source switching, user profiles, Plex-style "on deck" hero,
  trailers / more-like-this (need TMDB server-side), person detail pages.
- `/api/library/items?type=` server filter NOT needed for v1 (client-side
  split of the already-fetched list); revisit only if a folder grows huge.
- Parked alongside: Bazarr auto-subtitles (OpenSubtitles account), preplay
  footer media-facts line, trailer/similar rows (PLEX_UI_PLAN §5).
