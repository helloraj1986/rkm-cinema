# Plex-Style UI Revamp Plan — cards + detail ("preplay") screen

Status: **DECIDED 2026-09-06, NOT STARTED — user approved the approach and asked
for the plan to be tracked from PROGRESS.md. Start here next session; Phase 1
(backend detail endpoint) first.**

---

## 1. Why

Browsing + playback should feel like Plex:

- **Cards today are thin** — poster, year, play-count, a Mark-watched button;
  clicking the poster *plays directly* (movie) or opens the episode picker
  (series). There is no "about this title" surface.
- **Plex's model:** click a card → a rich preplay screen (backdrop hero, poster,
  synopsis, rating, genres, cast, big Play/Resume button) → then play. We want
  that, **without making the app heavy**.

Live probe (bundled Jellyfin 10.11.11, 2026-09-06) proved Jellyfin already
exposes everything needed per item via one call —
`/Users/{uid}/Items/{id}?Fields=Overview,Genres,People,CommunityRating,
CriticRating,OfficialRating,Studios,Taglines,ProviderIds,ProductionYear,
RunTimeTicks,UserData,MediaSources,…`:

| Plex preplay element | RKM today | Source (verified live) |
|---|---|---|
| Backdrop hero + poster | ✅ backdrop/poster proxy exists | `BackdropImageTags`, `ImageTags.Primary` |
| Title, year, runtime | ✅ partial (card) | ✓ |
| Synopsis | ❌ not surfaced | `Overview` ✓ |
| Genres chips | ❌ | `Genres` ✓ |
| Star / community rating | ❌ | `CommunityRating` (e.g. 7.47) ✓ |
| Content rating | ❌ | `OfficialRating` (TV-MA / AU-MA 15+) ✓ |
| Studio | ❌ | `Studios` (e.g. Netflix) ✓ |
| Cast row (actors/directors/writers) | ❌ | `People` with ids ✓ |
| Big Play / Resume + resume % | ✅ (grid-only) | `UserData.PlaybackPositionTicks` ✓ |
| Mark watched | ✅ | ✓ |
| Episode list inside series preplay | ✅ EpisodePicker | episodes endpoint ✓ |
| Trailer / More-like-this | ❌ | no trailer in Jellyfin; TMDB call needed → out of v1 |

→ ~90% of a Plex preplay view = **one additive backend endpoint** +
a detail component + a card revamp.

## 2. Design (Plex-inspired, kept light)

### Cards (revamp, not rewrite)

- Poster 2:3, rounded; **whole card clickable → opens detail** (playing moves
  into the detail screen, like Plex). Quick-play can stay on hover.
- **Hover:** card lifts, poster zooms subtly, dark gradient overlay, centred
  circular **play** button + secondary actions (Mark watched / open Jellyfin)
  fade in.
- **Watched** = ✓ badge (Plex-style tick, top-right); **resume** = amber
  progress bar along the bottom + % badge.
- Card stays metadata-clean (year/type subtle) — detail holds the rest.
- Grid mechanics unchanged (TanStack Query, lazy images) → no weight change.

### Detail / "preplay" overlay (new `ItemDetail.tsx`)

- Opens over the app (own scroll); close = Esc / backdrop / ✕.
- Mirrors Plex preplay: blurred **backdrop** fills the top; **poster**
  bottom-left overlapping; metadata column:
  - Title · year • runtime • content rating • ★ rating • genres chips • studio
  - **Resume bar** when in progress; primary **▶ Play** / **▶ Resume (45%)**;
    secondary **Play from beginning**; Mark watched; Jellyfin link.
  - **Synopsis**.
  - **Cast** row (actor headshots via same-origin person-image proxy, lazy,
    capped ~8) + Director/Writer credits below.
  - **Episodes** (series only): reuse episode picker data, Plex-ish ordering,
    Play/Resume per episode.
  - Small footer: resolution/codec/audio facts (from playback-info) — a Plex
    "details" touch.
- Detail data fetched **only on open** (query cache per item).

### Out of scope v1 (weight/complexity; possible later)

Trailers · "More like this"/similar rows (needs server-side TMDB) ·
hover-previews/marquee animations · person pages · click-to-play + info-button
hybrid (we adopt Plex's click-for-detail model; revisit if disliked).

## 3. Phases

### Phase 1 — Backend detail endpoint (½ day)

- `JellyfinLibraryProvider.item_detail(item_id)` — normalise the single-item
  fetch into a player-ready shape:
  `{type, name, year, runtime, overview, genres[], community_rating,
  official_rating, studios[], people{actors[],directors[],writers[]},
  backdrop_tags?/has_backdrop, primary_aspect, play{played,resume_ticks,
  play_count}}` (episode items also carry series context ids/names).
- Additive route `GET /api/jellyfin/detail?id=` (frozen-contract discipline:
  snapshot regen, `types.ts`, provider+route tests).
- Person images: confirm `/Items/{personId}/Images/Primary` shape; expose via
  the existing poster proxy pattern (`kind=Person` or a `person` id param) —
  additive.

### Phase 2 — Frontend: ItemDetail + card revamp (1–1½ days)

- `features/library/ItemDetail.tsx` preplay overlay (design above).
- `MediaCard` revamp: hover play + click→detail + Plex badges; quick actions.
- `LibraryView` wiring: cards open detail; play buttons start the player
  (existing `Player` untouched); episodes list inside series detail reuses the
  picker data path.
- Query keys + cache per item; no new npm packages.

### Phase 3 — Verify + ship (½ day)

- Headless check: open detail → metadata renders; Play/Resume starts the HLS
  player at the right position; series episodes list works; Esc closes.
- Gates: backend pytest + ruff; snapshot/types regen; vitest/tsc/build.
- Commit code, then `docs(status)` PROGRESS record, push. User deploys
  `.\\bootstrap.ps1` and checks on RKM-HP.

## 4. Acceptance

1. Click any card → full Plex-style detail within ~1 s (cached after first
   open), accurate metadata (synopsis/rating/genres/cast/studio).
2. Detail Play / Resume starts playback exactly where Plex would (resume pos /
   from 0 / series → chosen episode).
3. Cards look Plex-like and grid stays fast; watched/resume badges correct.
4. App weight unchanged in practice (detail fetched on demand only).

## 5. Out of scope / notes

- Trailer + similar rows deferred (TMDB server-side cost).
- Person headshots capped; person *pages* out.
- Reuses frozen `/api` (one additive path) — no secret leaks, same proxy
  discipline as the HLS work.
