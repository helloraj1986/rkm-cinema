# Phase V — the Library (Browse grid) and Title (item detail) screens, to his second prototype

Plan committed BEFORE the build, per `feature-shipping-cycle.md`. **Every number in this file came from a
command run on 2026-09-20 against this repo**, not from a summary — the source is named beside it.

Design input (UNTRACKED in his checkout, not part of this phase's commit):
`tvos_ux/2. LibraryViewandItemDetailsView/` — `library-view.html`, `title-view.html`,
`tvos-ux-principles.md`, `tvos-library-view-spec.md`, `tvos-title-view-spec.md`, `README.md`.

## 0. What this phase is, and what it is not

The tvOS app already has both screens — `Browse/BrowseView.swift` (B3) and `Detail/DetailView.swift` (B4) —
and they were **accepted on his simulator**. Phase V is therefore a **redesign to his prototype's geometry**,
the way U6 was for Home and the Profile Switcher, and not a new feature.

⚠⚠ **His two files are a SOURCE, not a measurement** (the Phase U lesson, in this skill's own words). Every
factual claim in them is checked against the repo in §1 below, and three of them are **false against this
repo** — including the one his whole title screen is built around.

⚠ **Branch: this phase continues on `feat/tvos-ux`, NOT a fresh branch from `dev`.** V builds directly on
Phase U's artefacts — `TVTokens`/`DesignTokens`, the generated token tables, `Home/TopBar.swift`,
`Home/PosterCard.swift` and `Design/DesignColours.swift` — and `feat/tvos-ux` carries U unmerged
(`ed0173a`). Cut from `dev`, V would have to re-do U first. `docs/TVOS_UX_PLAN.md` still owns the U phases;
this file owns V.

## 1. The measurement — what his package claims, and what the repo says

| # | His package says | The repo says | Verdict |
|---|---|---|---|
| 1 | Colour tokens (`void #0A0B0D`, `surface #15171B`, `gold #E8B33D`, `gold-bright #FFD866`, `curtain #7A1F2B`, `text #F5F3EE`, `text-dim #9B9D9F`) | the brand tokens live in `frontend/src/styles/index.css` and `Design/DesignTokens.swift` is GENERATED from it, with a drift gate | **do not transcribe.** U6's rule: tokens come from the CSS, never from a spec's table. Not one colour in §3/§4 below is taken from his table. |
| 2 | Library sort control offers *Recently added / Title A–Z / Year / Rating* | `frontend/src/features/library/lib.ts:170` — *"**"Rating" is deliberately NOT offered here because list items have no community rating (only the detail fetch does)**"*, and `LIBRARY_SORT_OPTIONS` carries **8** sorts: `recent, title, title-desc, release, recently-played, progress, runtime, unwatched` | **his file is wrong, and the web app already made this exact call.** V1 offers the web's 8. |
| 3 | "Because you watched *The Mummy*" — selecting a card opens **that title's detail screen** | `frontend/src/features/library/SimilarRow.tsx` — the row is **not library items at all**. `filterLibraryRows(query.data.similar, localItems)` **DROPS every title already in the library**, and a card opens `SuggestDetailModal`, a TMDB page offering **Add to watchlist / Download**. `SimilarItem` carries a **TMDB `id`** and public CDN art — **no Jellyfin item id**, which is why `SimilarItem` can never open a library detail | **the row is an ACQUISITION surface, not a browse surface.** See §5. |
| 4 | Title screen: focus opens on **Play**, "the one-button path to watching" | the tvOS player is **Phase C, parked** (`Core/PlaybackAuth.swift` built, C2–C5 not started); `Detail/DetailView.swift` offers **no Play control at all** on purpose, and `docs/ARCHITECTURE.md` §11 forbids offering what the server will refuse | **HIS DECISION (2026-09-20, this session): no Play control.** Focus does not open on Play; see §4. |
| 5 | The library grid card is `aspect-ratio: 2/3`; the title screen's related card is `width:200px; aspect-ratio:2/3` | the Home's card (set 1) is `16/9` at `19u` — `Home/PosterCard.swift` | **both are true and they are different cards.** §3.2 resolves it the spec's own way ("the *exact same component*", §8) rather than by copying the file twice. |
| 6 | Cast shelf: circular avatars, initials on a coloured field | `Detail/DetailView.swift` draws **no headshots** (one proxy request per person), and `DetailRules.castRows` already caps at **10** (`ItemDetail.tsx::people.actors.slice(0, 10)`) | **his design and the app agree** — initials need no request. `has_image` stays unused. |
| 7 | Title meta line: `year · runtime · content rating · ★ rating` | `DetailRules.metaBits` (year · runtime-or-seasons · certification) **and** `DetailRules.ratingText(community_rating)`; the detail payload **does** carry `community_rating` and `official_rating` (`backend/services/library/jellyfin.py::_detail_from_item`) | **supported end to end. Already on the screen today.** |
| 8 | Library rows can show a rating / a rating badge | `_item_public()` (`jellyfin.py:667`) returns `title, year, type, thumb, item_id, jellyfin_url, played, playback_position, runtime, play_count, last_played, genres, added` — **no `CommunityRating`** | confirmed by reading the producer, not by trusting U7's note. Nothing on a library card may print a score. |
| 9 | Genre chips: a fixed list (*All, Action, Adventure, …*) | `libraryGenres(items)` derives the chips **from the folder's own rows**, alphabetical and unique; the same file's `libraryNavEntries` is *"the ONE place that decides what the library list contains"* — the rule TopBar's tabs already obey (falsifier F3 in Phase U) | **derive, never a literal list.** A chip his library has no titles for is a control that filters to an empty screen. |
| 10 | Top tab bar: `Home · Movies Kids · Movies · TV Shows · Watchlist · Discover · Suggest` | `Home/TopBar.swift` builds tabs from `BrowseRules.browseEntries`; `Watchlist`/`Discover`/`Suggest` have **no tvOS screen** (`docs/TVOS_UX_PLAN.md` §5) | the bar is **reused**, not re-drawn. The library screen marks its own library as the current tab. |
| 11 | Filtering "never moves focus off the filter row"; the grid's first poster is the default focus | tvOS owns this (the focus engine), and this repo has paid three times for writing focus maths anyway (`RailFocus` deleted, B3's grid, the plan's own warning) | **no focus arithmetic is written.** §3.4 says what the round must show instead. |

## 2. The unit — his second prototype brings NO `--u`, so one is pinned

Set 1 sizes everything off `--u: 1cqw`, which U6 pinned as `TVTokens.u = 19.2 pt`. **Set 2 has no `--u` at
all** — it is absolute CSS px (`padding:28px 64px`, `gap:46px 28px`, `font-size:19px`). A browser page's px
mean nothing on a 1920 × 1080 point canvas until an anchor is chosen, so:

> **`TVTokens.px = 1.26 pt`, derived from the one value the two prototypes must agree on — the page margin.**
> Set 1 fixes it at `4.2u` (= 80.64 pt, which `TVTokens.Metric.safeMargin` already carries); set 2 pads
> **every** band by `64px` (`.topbar`, `.filterbar`, `.grid-wrap`, `.actions`, `.synopsis`, `.shelf h2`,
> `.shelf-track`). So **64px ≡ 4.2u ⇒ 1px = 4.2/64 u = 0.065625u = 1.26 pt**, and every set-2 metric below is
> `px * <the number in the HTML>`.

⚠ **Checked against the one element both files draw — the top bar — and it lands within a point:** brand
`20px → 25.2 pt` vs set 1's `1.35u = 25.92 pt`; bar padding-V `28px → 35.28 pt` vs set 1's `1.7u = 32.64 pt`.
Set 2's tabs are **larger** than set 1's (`19px → 23.94 pt` vs `1.05u = 20.16 pt`), which is right: set 2 is
the later file and the library and title screens are the ones being built from it.

**Alternatives, with their cost, recorded so this is not relitigated:**
* **`1px = 1 pt`** (reading the prototype as a 1920-wide page, i.e. its px *are* points) — the margin becomes
  **64 pt** against Home's **80.64 pt**. A Home that indents by 81 pt beside a Library that indents by 64 pt is
  visible in one press of Back, and it is precisely the drift `TVTokens.swift` says this file exists to
  prevent. **Rejected.**
* **the principles doc's own "~28px at 1x floor"** as the anchor (`1px ≈ 1.47 pt`) — it would make the
  prototype's own 19 px tab read as 28 pt, i.e. it derives the scale from a *minimum* rather than from a
  *measurement*. **Rejected** as circular: the doc states a floor, not the drawing's scale.

⚠ The consequence, stated plainly: **the 6-column grid is preserved exactly and the margin is preserved
exactly, but the prototype's margin-to-page ratio is not** (a browser width was never stated, so it could not
be). If the round shows the whole screen too small or too large, this is **ONE constant** (`TVTokens.px`) —
do not re-derive per metric.

## 3. V1 — the Library screen (`Browse/BrowseView.swift`)

### 3.1 Structure (his `library-view.html`, top to bottom)

| Band | His CSS | Token |
|---|---|---|
| Top bar | `padding: 28px 64px`, `gap: 40px`, wordmark `20px`, tabs `19px`, active tab `border-bottom:3px gold` | **the existing `Home/TopBar.swift`** — not re-drawn (§1 row 10). Its own numbers stay from set 1. |
| Filter row | `gap:16px`, `padding: 8px 64px 28px`, chip `10px 22px` r999 `17px`, count `16px` pushed right (`margin-left:auto`, `padding-left:24px`) | `TVTokens.Grid.chip*`, `.countSize` |
| Grid | `padding: 8px 64px 120px`, `grid-title 15px`, `repeat(6, 1fr)`, `gap: 46px 28px` | `TVTokens.Grid.columns = 6`, `.rowGap`, `.columnGap`, `.gridTitleSize`, `.gridBottomPad` |
| Card | `aspect-ratio: 2/3`, `border-radius: 14px`, focus `scale(1.14)` + `0 18px 30px rgba(0,0,0,.55)`, `0 0 0 3px gold`, `0 0 34px rgba(232,179,61,.45)`; `.label` inset `14px 12px 12px` with a bottom-up black scrim, title `16px` w600, meta `13px` dim, opacity `0 → 1` + `translateY(6px → 0)` on focus | `TVTokens.Grid.card*` |
| Empty state | `padding: 80px 4px`, `h3 26px`, `p 17px` dim, one `.chip` = **Clear filter** | §3.3 |

### 3.2 The card — one artwork path, two cards (deliberately)

His §8: the grid card and the detail screen's shelves are *"the exact same component"*. His two HTML files
say the grid card is **2:3 with a reveal-on-focus label over the art** while set 1's shelf card is **16:9 with
the caption under the art** (U7). Both are his, so both are built, and the thing that must not be copied is
the *artwork pipeline*:

* ⚠⚠ **AS BUILT (amended): a new `Browse/LibraryGridCard.swift`, NOT a parameter on `PosterCard`.** The plan
  said "`PosterCard` gains a `shape` and a `caption`". The build showed that to be the wrong shape of change:
  the two cards share **no** caption structure (badge + state chip + progress bar + caption-under vs art-only
  + reveal-over), so one type with two modes would be a tree of conditionals inside the card the Home has
  already had accepted on his simulator. What IS shared, and must stay shared, is the part where a second copy
  becomes a second silent failure (`PosterCard.swift`'s own header): **`PosterImageView` → `PosterLoader` →
  `PosterURL` are untouched and used by both**, so there is one request, one log line, one fallback and one
  "no photo" mark for the whole app. ⚠ `Home/PosterCard.swift` was not modified at all in this phase.
* ⚠ The library grid card carries **no type badge, no state chip and no progress bar**, because his file
  draws none: at rest it is art only, and on focus it is art + `title` + `year · runtime`. Recorded rather
  than "improved".
* ⚠ The focus treatment is the prototype's own (`scale(1.14)`, the gold ring, the double shadow) through a
  new `LibraryCardStyle`, **not** the platform's `.card` style: his `.card.is-focused` draws a ring the
  platform does not, and the reveal needs a focus value the label can read (`@Environment(\.isFocused)`, the
  mechanism `TabButtonStyle` and the Profile tile already use on screen). ⚠ It is a `ButtonStyle` because
  **the style owns its box** — the U7b lesson — so the ring cannot land around the caption instead.

### 3.3 The rules — `Core/LibraryRules.swift` (NEW, `Foundation`-only, RUN in the harness)

Mirrored from `frontend/src/features/library/lib.ts`, which is what the desktop, the phone and the iPad
already render:

* `libraryGenres(_:)` — unique, code-unit sorted (§1 row 9).
* `filterLibraryItems(_:genre:sort:)` — the genre membership test **and the 8 sorts**, ported comparator for
  comparator, **including the tie-breaks**: unknown dates last, then `cmpRecentDesc`; `release` is year-desc
  then recent; `progress` is fraction-desc **and a played row scores 0**; `runtime` is longest-first with
  unknown last; `unwatched` puts unplayed first and falls back to recent.
* `sortOptions` — the web's 8 keys and labels, in its order.
* `filterCountLabel(shown:total:genre:)` — `"12 of 140 titles"` / `"4 titles in Action"`, matching the
  prototype's own count line and the web's `folderCountLabel` plural rule.
* ⚠ **No `q`.** `libraryFilterFromParams` ignores `q` — *"free-text search was removed from the folders
  (GLOBAL_SEARCH_PLAN) — global search owns text"* — and tvOS has no search screen at all.

### 3.4 What the view must NOT own

The focus behaviour (§1 row 11) and the mounting cap (already `BrowseRules.Mount`, 48 + 48). The **filter
must not drop the mounted cap**: filtering a 713-row folder must still mount 48 first (`LibraryFolderView`
resets its mount key on `${folderId}|${genre}|${sort}` — the identity, never the length).

## 4. V2 — the Title screen (`Detail/DetailView.swift`)

### 4.1 Structure (his `title-view.html`)

| Band | His CSS | Token |
|---|---|---|
| Backdrop hero | `height: 66vh; min-height: 520px`, art + `linear-gradient(to top, void 0%, rgba(10,11,13,.65) 32%, transparent 68%)`, emblem `280px` at `8% / 12%` at `0.16` opacity | `TVTokens.Title.heroHeightFraction = 0.66` (of the screen, as `vh` is), `.scrim*`, `.emblem*` |
| Title block | `padding: 0 64px 40px`, `max-width: 920px`; `h1 64px` w700; meta `19px` with a gold `★`; genre pill `6px 16px` r999 `15px` | `TVTokens.Title.titleSize/metaSize/pill*` |
| Synopsis | `padding: 40px 64px 8px`, `max-width: 62ch`, `19px`, `line-height: 1.6` | `TVTokens.Title.synopsis*` — ⚠ **62ch is a MEASURE, not a width**: converted with the prototype's own font size (62 × ≈0.5 em ≈ 31 × 19px ≈ 589px ≈ `u * 30.7`) and said so, because SwiftUI has no `ch`. |
| Cast shelf | `h2 24px` w600, track `gap:28px`, item `150px` r16, avatar `110px` circle, initials `32px` w700, name `16px` w600, role `14px` dim, focus `scale(1.1)` + gold ring | `TVTokens.Title.cast*` |
| Related shelf | — | **NOT BUILT.** §5. |
| Action row | `padding: 36px 64px 0`, `.btn 16px 30px` r14 `19px`, primary gold, focus `scale(1.08)` + ring | **NOT BUILT** (his decision, §1 row 4): the screen keeps B4's playback notice, restyled. |

### 4.2 The one behaviour change, and why it is honest

B4's screen opens with **no focusable content below the bar**, and the prototype's cast shelf is a
**horizontally scrolling row** — which on a TV is *unreachable* unless something in it can take focus (no
focus means no scroll). So the cast row is drawn as **one non-scrolling row** (`DetailRules.castRows` already
caps at 10, and 10 × `110px + 28px` ≈ `72u` of the `91.6u` content width), and **nothing on this screen is a
button** until Phase C lands:

* the cast avatars, the genre pills, the synopsis and the credits are **information**, not controls;
* the top bar's **Back** control is the default focus — B4's own rule, *"on a screen reached from somewhere
  else, the way back is the primary verb"* — so the screen is neither a focus trap nor a dead end.

⚠ **This is the phase's honest weak point and it is stated rather than hidden: on tvOS today the Title screen
can only be READ.** Its action row (Play, Trailer, Add to Watchlist, More) arrives with Phase C, and
`Trailer` **cannot** arrive with it — `ItemDetail` carries no trailer field at all (`Core/Models/DetailModels.swift`
decodes 21 keys; none is `RemoteTrailers`), so a Trailer control needs a wire change, i.e. its own phase.

## 5. What is NOT built, and the measurement behind each

1. **The "Because you watched" shelf — this phase.** On the web it is a *discovery* row that deliberately
   **removes** everything already in the library and offers **Add to watchlist** and **Download** (§1 row 3).
   Replicating it on tvOS means building an acquisition surface — a TMDB detail sheet plus two write actions
   (`useAddToWatchlist`, `useRequestMedia`) — which is a **new feature**, not this redesign, and tvOS has no
   watchlist/download screen for it to live on. ⇒ It is offered to him as its own phase. Drawing the shelf and
   refusing every press is the control `docs/ARCHITECTURE.md` §11 forbids.
2. **The Rating sort** — the web app already refuses it, in writing, for the same reason (§1 row 2).
3. **A rating badge on a library card** — `_item_public()` sends no rating (§1 row 8). This is the same
   three-file change U7 already offered him; it is not smuggled into a branch that promises *nothing to deploy*.
4. **The Play control and the action row** — his decision (§1 row 4).
5. **The prototype's JavaScript** — nearest-centre focus maths (`move()`), `scrollIntoView`, the top bar's
   `scrolled` class and the hover handlers. **Not ported.** tvOS's focus engine does the first two (`RailFocus`
   deleted, B3's grid, U6's rail); there is no hover on a TV; and the bar's compress-on-scroll is the same
   platform claim F6 already measures on the Home. ⚠ **The bar's collapse is NOT added to this screen either**,
   for exactly that reason.
6. **`Watchlist` / `Discover` / `Suggest` tabs** — no screens exist (`docs/TVOS_UX_PLAN.md` §5).

## 6. Gates — what changes in the gate set, in the SAME phase

| Gate | Change |
|---|---|
| `check-tvos-core.py` | `Core/LibraryRules.swift` joins `PURE_SOURCES` — **466 checks**, and **16 new mutations (102 in the table, the number the gate's own header reports)**, one per rule in §3.3: the genre order and its empty-name drop, the `All` chip's two halves, both count lines, **the grid's second margin** (the U7b shape), the fraction trim, the undated-row order, `played` scoring zero, recently-played's `played &&` clause, the sort's stability, the caption's runtime, the tab plan's current tab and the unresolved library's state, and the cast hue's key. ⚠⚠ **AND IT FOUND THREE PRE-EXISTING ENTRIES THAT WERE PROVING NOTHING** — two STALE (they reverted lines that had since been rewritten, and named check labels no check carries) and one WRONG (red, but on a stale expectation — the U7b era put `(6u)` into the label). All three are repaired, and each is proved red by hand against the check it names. |
| `tvos-core-tests/main.swift` | a new section per rule, fixtures shaped like the real rows — including a row with **no `added`** (it must sort last), a **played row carrying a position** (the only shape where `progress`'s `played` clause is observable) and **two undated rows in both orders** (which is what pins stability). ⚠ The fixture pair `newer`/`played` tie at 3600 s, and the first run of this section FAILED on the runtime expectation — the harness was wrong, the rule was right; the expectation was fixed, not the comparator. |
| `check-tvos-members.py` | 5 new `USES` rows and 5 new `TYPE_SOURCES` (incl. the NESTED `BrowseRules.LibraryTabPlan`, which needed the scan to match a declaration by its **last dotted component**), 2 new `VIEW_TYPES`, both new button styles added to rule 5's `STYLE_TYPES` list, and `LibraryRules`/`LibraryCopy` added to `NAMESPACES`. ⚠⚠ **AND A REAL FALSE POSITIVE FIXED: `TopBarTab(id: "detail:back", …)` made rule 2 report a label `TopBarTab` does not take, on a CORRECT tree** — a colon inside a string literal is not a label. Literals are now stripped before the labels are read, and the `--selftest` pins both halves (the literal stays silent, a genuinely wrong label still fires). |
| `check-apple-typecheck.sh` | `Core/LibraryRules.swift` added to the explicit list — a portable file no gate compiles is an unguarded file, and it was in `PURE_SOURCES` only. |
| `check-tvos-models.py` | unchanged: no wire model changes in this phase. |
| `check-design-tokens.py` | unchanged: no new colour. **Every colour on both screens is an existing `RKMColour`** — his `#E8B33D`/`#FFD866`/`#7A1F2B` table is not transcribed anywhere. |

## 7. The round (his Mac — SCREEN round, WITHOUT `-RKMDebugHUD`)

**What it can prove:** that the two screens compile at the 26.0 floor, and that the geometry reads like his
files. **What it cannot:** anything about real Apple TV hardware, and a `BUILD FAILED` proves nothing about
the layouts.

| # | Falsifier | What DISPROVES it |
|---|---|---|
| V-F1 | the library grid is **6 columns** of **2:3** cards with the prototype's gutters | cards are 16:9, or the column count changes with the row |
| V-F2 | a grid card shows **art only** until it is focused, then the title + `year · runtime` fade in **over** the art | the caption is visible at rest, or it sits under the card |
| V-F3 | the genre chips are **this library's own genres** and the count line is the web's | a fixed list, or a chip that filters to nothing |
| V-F4 | moving down a grid row and back **keeps the column** | focus jumps to the first card (then the platform is NOT doing it and the view genuinely needs a map) |
| V-F5 | the title screen's hero is **~two-thirds of the screen** with the title block over its lower part and a real backdrop | a 300 pt band, or the "no photo" marker |
| V-F6 | the cast row is **round initials**, fits without scrolling, and nothing on the screen is a dead control | avatars are missing, the row scrolls with no way to reach it, or a press does nothing |
| V-F7 | **no Play button anywhere on the title screen**, and Back has the default focus | a Play control is on screen (his decision, §1 row 4) |
| **V-F8** | the gold ring **encloses** the focused card on all four sides, and no black square shows at its bottom corners | the ring sits inside the card, or a black rectangle pokes out below it (⚠ **his first round found exactly this** — `accda68`) |
| **V-F9** | after picking a genre, **Down reaches the titles** | focus stays on the chip row (⚠ **his first round found exactly this** — `KNOWN_ISSUES.md` #11; the `GeometryReader` was removed in `accda68` and it is NOT yet proven to have been the cause) |

## 8. Open items handed to him with this phase

1. The **related shelf** as its own phase (a tvOS acquisition surface: TMDB detail + Add to watchlist + Request
   download), if he wants it.
2. The **rating on the wire** (`_item_public()` + the frontend `MediaItem` + the tvOS model + a deploy) — which
   would give him the Rating sort, the card badge, and the ★ on the grid.
3. **`Trailer`** — needs `RemoteTrailers` on the detail payload.

## 9. AS BUILT (recorded at the phase's own commit, 2026-09-20)

⚠ **One phase's worth of work in one commit, because both screens were asked for in one instruction** —
`docs/TVOS_LIBRARY_UI_PLAN.md` (this file) was committed first, on its own.

| | |
|---|---|
| **Files added** | `Core/LibraryRules.swift` (the pure rules: chips, filter, the eight sorts, the count, the grid's arithmetic), `Browse/LibraryGridCard.swift` (the 2:3 art-only card + `LibraryCardStyle`), `Browse/FilterChip.swift` (the chip + `ChipButtonStyle`) |
| **Files changed** | `Browse/BrowseView.swift` (rewritten: the top bar, the filter row, the grid, the empty/loading states), `Detail/DetailView.swift` (rewritten: the hero, the title block, the synopsis, the cast row; the states and the episode list kept), `Core/BrowseRules.swift` (`LibraryTabTarget` / `LibraryTabPlan` / `tabPlan`), `Core/DetailRules.swift` (`castHue`), `Design/TVTokens.swift` (`px`, `Grid`, `Title`), `Design/DesignColours.swift` (`castAvatar(hue:)`), `Home/HomeView.swift` (its tabs now come from `BrowseRules.tabPlan`) |
| **NOT touched** | `Home/PosterCard.swift`, `Home/HeroBand.swift`, `Home/TopBar.swift`, `Home/RailView.swift`, `Core/BrowseStore.swift`, `Core/DetailStore.swift`, and every wire model — **no `backend/`, `frontend/` or `nginx/` file changed, so nothing needs `apply`** |
| **Gates, on this commit** | `check-tvos-core.py` **466 checks / 0 failures** · `check-tvos-models.py` 113 keys / 17 endpoints · `check-apple-typecheck.sh` 21 portable files · `check-imports.py` 40 files · `check-tvos-members.py` 31 pairs, `--selftest` fires on all FIVE rules · `check-design-tokens.py` R1/R2/R3 · `check_md_links.py` 75 files · **`check-tvos-core.py --falsify`: PASS — 102/102 rules reverted, every one went red on the check it protects** (three runs to get there: the first two exposed four rotten entries of the gate's own — two STALE, one WRONG, plus the hero's meta separator — all repaired and each proved red by hand) |
| **⚠ NOT verified** | **not one SwiftUI view has been compiled anywhere** — no SwiftUI on Linux, so the two screens are written and unbuilt until his Mac round. Same status Phase U's views had. |

⚠ **The Title screen's top bar, AS BUILT, differs from his file in one deliberate way.** His `.topbar` is
`position:fixed` over the hero, hidden at rest and shown only near the top; here it is a normal band above the
hero and it never hides. The reasons, in order: (1) the collapse is a **scroll-position signal**, which is the
same class of platform claim as the Home's F6 and is deliberately measured there first; (2) a bar that hides
itself takes the only way out of the screen with it, and `docs/ARCHITECTURE.md`'s dead-end rule outranks a
cosmetic collapse. ⚠ **It carries ONE tab — `Back`, named by `AppModel.detailReturnLabel` — and the profile
avatar**, which is his own layout (`wordmark + ‹ Movies Kids`) and is what puts the default focus on the way
back rather than on a Play button that cannot work.

