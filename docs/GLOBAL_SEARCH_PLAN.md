# Global Search & Media Discovery — Execution Plan (`feat/intelligent-search`)

Branch from `main` @ `b3e645c`. Goal (user spec 2026-09-10): **one intelligent
global search** — the persistent top-bar search is THE entry point; it answers
*"do I own this?"* first and hands back the most useful next action (Watch /
Continue / View Details / Add–Download), never a duplicate TMDB row for
something already in the library. The current multiple search boxes (sidebar
`/search` page, folder free-text boxes) are consolidated away.

Design language: reuse the premium cinematic shell (Dialog a11y patterns,
surface tokens, 10px uppercase micro labels, accent actions). `/api` stays
**additive-only** (ADR-0001): the old `/api/search` route is untouched; a new
additive endpoint serves the global journey.

---

## Reality map (verified in code 2026-09-10)

- **"My Library" = provider library** (Jellyfin on the bundled stack; Plex/Emby
  supported). Movies + Series (+ their episodes) live there with playback facts.
  The **watchlist** (`data.pending/recommended`) is a separate TMDB-sourced
  "suggested/requested" list — NOT ownership. Ownership = the item exists in the
  provider library (Jellyfin `UserData` gives played/position per item).
- Existing surfaces to consolidate:
  - `frontend/src/app/layout/Header.tsx` — the top-bar search. Today it
    **navigates to `/search?q=`** on typing (`SEARCH_DEBOUNCE`); `/` + ⌘K focus it.
  - `frontend/src/features/search/SearchView.tsx` + route `/search` (sidebar tab).
  - `frontend/src/features/library/LibraryFolderView.tsx` /
    `LibraryToolbar.tsx` — Movies/TV folder free-text `q` (+ genre/sort/compact).
  - `frontend/src/app/layout/Sidebar.tsx` (Search tab), `MobileNav.tsx`
    (Search tab), `router.tsx` (route).
- Backend today: `GET /api/search` = watchlist matches + TMDB multi (used by
  SearchView). Library API is provider-based: `/api/library`, `/api/library/items`
  (all_items poster wall), `/api/library/continue-watching`,
  `/api/library/series/{id}/episodes`, `/api/jellyfin/detail|similar|person|poster`.
  Jellyfin provider (`services/library/jellyfin.py`) already pulls
  `Overview,Genres,People,CommunityRating…` and `ProviderIds.Tmdb` (Similar rows
  prove TMDB-id ownership matching works). Provider interface
  (`services/library/service.py`) is the seam for a new `search(q)` method.
- Player/action context lives in `LibraryLayout` (owns the full-screen Player +
  `startMovie/startEpisode/switchEntry`). The Header sits ABOVE that, so overlay
  actions that need playback will **navigate** (see §Actions).

---

## UX architecture (what we build)

### The overlay (primary surface)
- Header search becomes a **command-palette-style dropdown** (no navigation on
  type). Typing debounces (~180 ms) into the new global endpoint.
- Sections, in this order (only non-empty ones render):
  1. **In your library** — Movies | TV shows | Episodes, each row: poster,
     title, meta line + contextual state, ONE primary action + "Details".
  2. **People / Genres / Collections** (when the term matches local metadata) —
     rows that lead to the matching titles, not playable rows.
  3. **Discover (TMDB)** — ONLY rendered when there is **no strong owned match**
     (see dedupe). Row copy is unmistakably "Not in your library" with
     **Add to library / Download**.
- Keyboard: ↑/↓ move, Enter activates primary (or Details), Esc closes, `/`/⌘K
  focus from anywhere (already wired in Header). Overlay closes on navigation.
- Mobile: the MobileNav Search tab becomes a trigger that opens the same overlay
  (full-width sheet) instead of a separate route.
- Deep-link fallback: old `/search?q=` is redirected to home; a one-time read of
  `?q=` on boot can seed the overlay query for shareable search links.

### Result-state mapping (the most-important rule)
Every owned row carries the state needed to pick the primary action client-side:

| State | Primary action | Notes |
|---|---|---|
| Movie/show unwatched | ▶ Watch Now | → item page w/ `?play=1` |
| Movie/show in progress | ▶ Continue Watching (`S01 E05 · 32 min left`) | resume from UserData position |
| Movie/show completed | ▶ Watch Again | position 0 replay |
| TV show (no show-level pos) | ▶ Play / Next Episode | series "Play" deep-link starts `nextPlayableEpisode` |
| Episode owned | ▶ Resume / Play | direct to episode play |
| Not in library (TMDB) | ＋ Add to Library / Download | discovery row only |

### Dedupe / intent rules
- **Ownership first**: search the local library. Strong owned match exists when
  a returned owned item's normalized title equals the query OR (for discovery
  candidates) its TMDB provider id matches an owned item → suppress that TMDB row.
- **Only then TMDB**: if no strong owned match → run TMDB multi search (reusing
  the shared `TMDBService` client path), excluding any candidate whose tmdb id /
  normalized title already appears in owned results.
- Intent affordances: actor/director/genre/year terms are answered by the
  provider's native search (Jellyfin `searchTerm` matches People/Genres text) and
  surface People/Genres sections that link to their titles; episodes match by
  name. Where the provider can't do that natively (Plex tier), the plan degrades
  honestly (title matches over the catalog; People/Genre sections simply absent).

### Actions
- Owned "Watch/Continue": `navigate('/library/item/{id}?play=1')` (+
  `?episode={id}` when the row is an episode, `?autoplay=1` naming below).
  `ItemDetailPage` already sits inside `LibraryLayout` and owns
  `startMovie/startEpisode` — on mount with `?play=1` it calls the right starter,
  reusing resume/next-episode logic (`startPosition`, `nextPlayableEpisode`).
  Player overlays exactly as today.
- "View Details": plain navigate to the item page (same target without `play=1`).
- People/Genre rows: navigate to a **search-results-for-tag** surface = the
  existing folder URL state (`/library/movies?genre=…`) — people/actor drill-down
  goes to item pages via a provider "person" view (episode/person API already
  exists — verify in Phase 0; if not viable, Person rows open their top titles
  via the person endpoint response).
- Discovery "Add / Download": reuse the established suggest → watchlist →
  `/api/media/…/request` acquisition path (same actions + toasts as SuggestCard
  today) with a "not in your library" pill on the row.

---

## Backend (additive; contract 36 → 37 paths)

New provider method on the `LibraryService` seam + each provider:
`search_items(q: str, limit: int) -> {movies, series, episodes, people, genres, collections, query}` —
normalized rows with `{id, title, year, kind, genres, poster?, series_id/series_name
+ season/episode for episodes, played, position (UserData), runtime}`.
- **Jellyfin**: `GET /Users/{uid}/Items?searchTerm={q}&Recursive=true&
  IncludeItemTypes=Movie,Series,Episode&Fields=<existing fields>+ProviderIds`
  (verified pattern from `jellyfin.py`), plus a **Person/Genre/Collection pass**
  (`IncludeItemTypes=Person,Genre,BoxSet`) to classify intent matches. Phase 0
  live-probes exact behaviour before finalizing (repo rule: probe before code).
- **Emby**: same endpoints family (native Search); **Plex**: catalog filter
  fallback (title/actor/genre over `all_items`), no episode/person sections.
- Service aggregate: first provider with results wins (mirrors `all_items`).

New route `GET /api/search/global?q=` (`backend/api/routes/search_global.py`):
`{query, library: {movies, series, episodes, people, genres, collections},
 discovery: [tmdb rows…], strong_match: bool}`. Dedupe/strong-match scoring
server-side (tmdb provider-id set built from the same search + title
normalization) so the client never sees duplicates and **discovery is empty when
a strong library match exists**. Reuses `TMDBService.search_multi` + the exact
model shapes already used by `/api/search`. Additive → openapi snapshot regen
(36 → 37 paths), types regen, +pytest, contract zero-diff on the other 36.

## Frontend

- `lib/api/client.ts`: types + `searchGlobal(q)`.
- New `features/search/GlobalSearch.tsx` (Header-owned overlay; dropdown panel,
  sections, state pills, actions, keyboard nav; reuses `Dialog` a11y where
  sensible). Pure helpers (ranking/state-label/action-for-row) → `lib.ts` +
  unit tests.
- `Header.tsx`: replace navigate-on-type with overlay; keep `/`+⌘K; seed from
  `?q=` once.
- `router.tsx`: `/search` → `Navigate` to `/library/home`; delete SearchView +
  sidebar Search tab; MobileNav Search → overlay trigger.
- `LibraryFolderView/LibraryToolbar`: remove the free-text `q` box (genre/sort/
  compact stay; URL `q` param support dropped with its param helpers/tests
  updated); Movies/TV folders keep their filter toolbar — that is filtering, not
  global search.
- `ItemDetailPage`: honour `?play=1` (+ optional episode target) to auto-start
  the player for Watch/Continue deep-links.

## Phases & gates (commit + green gates after EVERY phase)

- **Phase 0 — probe + data contract.** Live-probe Jellyfin searchTerm behaviour
  (titles/episodes/people/genres/BoxSets + UserData fields) via the repo probe
  harness against the real bundled Jellyfin if reachable, else against recorded
  fixtures; lock the normalized row shape; write provider fake fixtures.
- **Phase 1 — provider search.** `search_items()` on Jellyfin/Emby/Plex + service
  aggregate + normalize + strong-match/dedupe helpers. pytest · ruff · no route.
- **Phase 2 — endpoint.** `/api/search/global` + models + dedupe + tests +
  snapshot 36→37 + client types. pytest · ruff · contract.
- **Phase 3 — overlay.** GlobalSearch component + Header wiring + state-action
  helpers + keyboard nav + MobileNav trigger. vitest · tsc · build.
- **Phase 4 — consolidation removals.** SearchView/route/sidebar removed; folder
  toolbar `q` removal (+ params/tests); deep-link seeds; item `?play=1`.
  vitest · tsc · build (full suite).
- **Phase 5 — acceptance prep.** Headless smoke of overlay (owned → actions;
  non-owned → discovery Add; episodes/people sections), PROGRESS record.

## RKM-HP acceptance checklist (final)
- ⌘K (or `/`) from anywhere → type "3 body problem" → **In your library** row with
  ▶ Continue Watching (or Next Episode) + Details; NO Download; NO duplicate TMDB row.
- Type a title you DON'T own → DISCOVER section with "Not in your library" + Add;
  Add works (toast + watchlist/arr path).
- Actor / genre / partial-spelling queries return sensible owned results.
- Movies/TV folder pages: no free-text search box (genre/sort remain); sidebar
  has no Search tab; mobile Search button opens the overlay.
- `View Details` lands on the item page; `Watch/Continue` starts playback at the
  right spot. Merge `feat/intelligent-search` → main + push + FF `experiment`.

## Honest caveats
- Collections = provider **BoxSets** only when present; absent → section hidden.
- People/Genre deep "smart" queries depend on provider search fidelity — verified
  in Phase 0 and capped honestly per provider (Plex tier simpler).
- Dedupe is title-normalization + tmdb-id based; remakes/same-name-different-year
  are treated as distinct (title match requires same year when available).
