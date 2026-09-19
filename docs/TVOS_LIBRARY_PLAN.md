# tvOS client — Phase B (Home / Browse / item detail) — plan

**Branch:** `feat/tvos-library`, cut from `dev` @ `23e1f9c` (2026-09-19).
**Scope:** Phase B of `APPLE_CLIENTS_PLAN.md` §4 — the tvOS app's *content* screens. Phase A (address →
sign-in → who's watching) is merged and accepted on his simulator; Phase C (the player) is not in this plan.

> Every number in this document came from a command run before it was written. Where a claim is a
> decision rather than a measurement, it says so.

---

## §0 — B0: the decision this plan starts from, and what it cost

Phase B is entirely about items, and **the frozen contract does not describe the item shape.** Measured
against `docs/api/openapi.v1.json` (read 2026-09-19):

| Route | What the contract says |
|---|---|
| `GET /api/library/folders` | ✅ typed — `LibrariesResponse.folders: LibraryFolder[]` |
| `GET /api/library/folders/{folder_id}/items` | ❌ `FolderItemsResponse.items` = `array` of `object`, `additionalProperties: true` |
| `GET /api/library` | ❌ `LibraryResponse.recent` = the same untyped shape |
| `continue-watching` · `recently-watched` · `series/{id}/episodes` · `jellyfin/detail` · `jellyfin/poster` | ❌ **no documented 200 schema at all** |

There is no `Item`/`MediaItem` schema among the contract's 58 schemas. So `check-tvos-models.py`'s R1–R3
cannot cover a single Phase B model: R1 fails an invented model and there is no schema to point at.

**His decision (2026-09-19): option 2 — the contract is NOT extended.** The reason given for rejecting
option 1 was the backend blast radius (`response_model` filters a response to the declared fields, so a
field omitted from a new model would silently vanish from a live response) against a web app that is
already working. That is a legitimate call on a working system, and this plan honours it: **no file under
`backend/` changes on this branch.**

⚠ **The consequence as it was stated — "Phase B then has no wire-format gate" — turns out to be avoidable,
and this is a measurement, not a preference.** See §1.

---

## §1 — The shape source that already exists (measured)

The item shape is undocumented *in the contract*. It is not undocumented in the repo. Measured:

| Source | What it is |
|---|---|
| `frontend/src/lib/api/client.ts` → `MediaItem` | **15 properties** (13 optional), written against the live API, rendered in production on his phone/desktop/iPad |
| … → `EpisodeShape` (8 props) + `EpisodesShape` | the `/library/series/{id}/episodes` shape |
| … → `ItemDetail` (19 props) | the `/api/jellyfin/detail` shape (B4) |
| `backend/services/library/jellyfin.py::_item_public` | the **producer** of the 13 core fields — 7 call sites |

`_item_public()` emits exactly 13 keys: `title`, `year`, `type`, `thumb`, `item_id`, `jellyfin_url`,
`played`, `playback_position`, `runtime`, `play_count`, `last_played`, `genres`, `added`. The TS
`MediaItem` is **those 13 plus two optional facets** (`kind`, `episode`) that the Continue-Watching path
adds on top (`jellyfin.py:404`, `:444`, `:475-476` — "the endpoint stays free-form — no contract change",
per `CONTINUE_WATCHING_EPISODES_PLAN` Option A). Episode resume rows come from a *second* producer,
`_episode_resume_public()`, and emit the same core shape.

⚠ Note the trap this shape carries: **library rows use `item_id`; global-search rows use `id`.** Same
repo, same-looking payloads, different key. That is exactly the "decodes silently to nil" class R2 exists
for, and it is why a gate is worth having here.

So the honest statement is: *the contract is silent, and there is a second, battle-tested description of
the same bytes.* Phase B is gated against that one.

---

## §2 — The gate: R6/R7 — "outside the contract" means "checked against the second source"

`NON_CONTRACT_MODELS` is extended from `name → reason` to `name → {reason, shape}`. `shape` names a
TypeScript interface in a frontend file. Two new rules apply to a model that declares one:

* **R6** — every JSON key the Swift model decodes is a property of that TS interface (no invented fields,
  no typos, no `item_id`/`id` swaps);
* **R7** — a Swift property that is **non-optional** must be non-optional in the TS interface, so
  `item_id: String` is legal (TS `item_id: string`) and `title: String` is legal, while `thumb: String`
  is not (TS `thumb?: string | null`) — optionality has to come from somewhere, and if the contract is
  not going to supply it, the TS interface does.

⚠ **R1 is NOT weakened.** A model still fails R1 unless it is named in `NON_CONTRACT_MODELS` *and* its
shape source resolves. Exempting by name stays a deliberate act with a written reason — the property the
current file is built around — rather than becoming "any model that happens to match a TS name passes".

⚠ **What this gate does and does not prove.** It proves the Swift and the TS agree. It does **not** prove
either agrees with the server — nothing in this sandbox can, with no Docker daemon and no signed-in
session. That limit is stated in the checker's own docstring rather than implied away, and the TS side is
the closest thing to a production-verified description this repo has.

---

## §3 — Phases

### B1 — models, gate, and the artwork question *(built)*
* `Core/Models/LibraryModels.swift` (new): `MediaItem`, `EpisodeContext`, `EpisodeItem`,
  `LibraryItemsResponse`, `FolderItemsResponse`, `LibraryRecentResponse`, `EpisodesResponse` — every key
  explicitly mapped in `CodingKeys`, optionality taken from §1.
* `Core/PosterURL.swift` (new, portable): the poster URL builder, mirroring the frontend's
  `posterUrl()` — `/api/jellyfin/poster?id=<item_id>&width=<w>`, with the width clamped to the range the
  server documents (it 422s outside 16…2000) and the id percent-encoded as a *query* value.
* `apple/scripts/check-tvos-models.py`: R6/R7 as §2, plus 4 new falsification mutations (10 total).
* `apple/scripts/check-tvos-core.py` (new) + `apple/scripts/tvos-core-tests/main.swift` (new): ⚠ **the
  plan's "typechecked and unit-asserted" was too weak, and this is what it became.** The two pure sources
  are compiled with `swiftc` and **executed** against fixtures shaped like the real payloads — 68 checks,
  10 rules falsified. It is the same pattern `check-offline-core.py` established for the iOS offline
  stack, and it is the difference between "it compiles" and "it behaves".
* `apple/scripts/check-apple-typecheck.sh`: the two new portable files added to the tvOS loop (8 files).
* ⚠ **The artwork question, recorded for the Mac round:** `GET /api/jellyfin/poster` is session-scoped, so
  whatever loads images must present the session cookie. `AsyncImage` shares `URLSession`'s cookie store —
  the cheapest option to try first — but a poster wall with no posters looks identical to a broken screen,
  so the load path gets its own log line rather than a silent empty `Image`. **Nothing in the sandbox can
  prove this either way**, and B1 does not claim it does: `PosterURL` builds the URL; whether the cookie
  travels is B2's first device question.
* ⚠ Two findings from building the gate, both worth keeping:
  1. **R6/R7's own parser had a hole on its first run** — an inline object's lines were matched against
     the PARENT interface too, so `MediaItem` came back with 19 properties instead of 15 and a Swift
     `number` on the item would have passed as a legitimate key. The check's *own output* exposed it
     (`not decoded: number, season, series_id, series_name`), the same way R2b did in Phase A.
  2. **`FolderItemsResponse` is a contract schema after all** (only its `items` is untyped), so it is
     checked against the contract, not the interface — and R3 forced `items` to be **optional**, because
     a pydantic `default_factory=list` is not a `default` in OpenAPI. The route always sends it; the
     contract does not promise it. `rows` is the coalescing accessor.

### B2 — Home: two horizontally scrolling rows *(built)*
`/api/library/continue-watching` + `/recently-watched`, on the focus engine.

* **`Core/HomeRails.swift`** (pure, **RUN**) — the Home's rules, **mirrored from the web app rather than
  invented**: `useHomeRows.ts` + `lib.ts` are what the phone/tablet/desktop Homes already render, so the TV
  cannot disagree with them about what "continue watching" means, what a card says underneath, or how long a
  rail is. `HomeSnapshot` turns the two responses into the screen's four states (loading / content / empty /
  failed), so the states are a value with tests instead of a tree of conditionals inside a `body`.
  ⚠ **`isContinueWatching` delegates to `MediaItem.isResumable`** — the web predicate and the model's are the
  same rule, and writing it twice is the defect this repo re-learns most often.
* **`Core/LibraryAPI.swift`** (ported) — the two endpoints, so no view spells a path.
* **`Core/HomeStore.swift`** (ported) — the two requests, and the `APIError` → sentence mapping. Sequential
  on purpose (see its header: `async let` would put `self` in two child tasks and the strict-concurrency
  fallout depends on a language mode this sandbox cannot reproduce).
* **`Core/PosterLoader.swift`** (ported) — the artwork fetch, **and the answer to B1's open question**: it
  logs, per poster, the HTTP status, the byte count, whether a **session cookie was attached**, and whether
  the answer came from the cache. `AsyncImage` was rejected because it cannot log, and on a TV a poster wall
  with no posters is indistinguishable from an empty library.
* **`Home/HomeView.swift` · `Home/RailView.swift` · `Home/PosterCard.swift`** (SwiftUI, Mac-only) — the
  screen, the rail and the card. Phase A's `SessionReadyView` placeholder is **deleted**, not kept beside
  them: the session readout it carried is the Home header's now, and a second screen showing the same facts
  is a second place for them to disagree.
* ⚠⚠ **`Core/RailFocus.swift` WAS WRITTEN AND THEN DELETED, and that is the notable finding of this phase.**
  The plan said "the row scrolls to keep the focused card visible", so a pure, tested file of rail
  arithmetic (reveal offsets, index stepping, clamping) was built for it. It was removed before landing:
  **tvOS's focus engine already scrolls an ancestor `ScrollView` to reveal the focused view**, so a
  hand-rolled `offset(x:)` would run *in addition to* the platform's and produce a jitter bug that looks
  like "the arrows are broken" and diagnoses as nothing. And because the claim could not be tested from this
  sandbox (no tvOS SDK), the phase took the failure mode that is **visible and one line to fix** — if the
  round shows a focused card going off the edge, add the offset deliberately — over one that is invisible
  and fights the system. ⚠ `RailView`'s header records this, so the next session does not rebuild it.
  **B3's 2-D grid is the genuinely different case** (column memory across rows is not free), and the plan is
  right about that one.
* ⚠ **Two defects the tests found in the code this phase was writing, both worth keeping:**
  1. **The placeholder's state table had a hole.** Checking `allFailed` before `isEmpty` left the mixed case
     (one row failed, the other honestly empty) rendering "Nothing to play yet" — a claim the app cannot
     make, since half its answer never arrived. `rails.isEmpty && hasAnyFailure` fixes it, and the mixed case
     is now a named check.
  2. **A check was a TAUTOLOGY.** The rail headings were asserted against `HomeSnapshot.recentlyPlayedTitle`
     — the same constant the mutation moved — so it stayed green. The falsification pass caught it; the
     assertions now use the literal words. ⚠ **Copy is a rule and must be pinned against the words, never
     against itself.**
* ⚠ **`AppModel.swift` was added to the typecheck list** — it decides which screen the app is on and nothing
  compiled it here until now. It passes.
* ⚠ **New copy, marked as such in the code:** the per-row failure sentences, the all-rows-failed screen and
  the empty-library screen. The web Home has no per-row failure state (a failed query collapses the page
  into its "no media server connected" screen, which is a *configuration* sentence) and renders nothing at
  all for an empty library — which on a TV with nothing else on it reads as a fault.

### B3 — Browse: the library list and the poster wall *(built)*
`/api/library/folders` → a folder → `/folders/{id}/items`.

* **`Core/BrowseRules.swift`** (pure, **RUN**) — mirrored from `features/library/lib.ts`: `libraryIconFor`,
  `libraryByFolderId`, **`libraryNavEntries`**, `folderCountLabel`, and the web's **`FIRST_PAINT_CARDS` /
  `MOUNT_STEP`** mounting plan. ⚠ `libraryNavEntries` is the rule his **iPad report of 2026-09-14** bought —
  an unresolvable library keeps its row, its icon and its warning rather than being silently dropped, which is
  how a library "disappears" on one surface and not another. `BrowseRules` names that report, so the TV
  cannot quietly reintroduce the narrower filter.
* **`Core/BrowseStore.swift`** (ported) — the library list and one folder's wall, with the same
  `APIError` → sentence mapping Home uses.
* **`Core/Models/LibraryModels.swift`** — `LibraryFolder`, `ConfiguredLibrary`, `LibrariesResponse`. ⚠ All
  three **are** contract schemas, so R1-R3 gate them fully; `LibrariesResponse` has **nothing** `required`, so
  `folders`/`libraries`/`warnings` are optional with coalescing accessors, and `ConfiguredLibrary.folderID` is
  optional because the contract neither requires nor defaults it.
* **`Browse/BrowseView.swift`** (SwiftUI, Mac-only) — both modes, reusing `PosterCard` from B2 so the two
  screens cannot draw different cards. Every state carries a focusable way out (`Back to Home`), and the
  mounting rule is what keeps a 400-title wall from being drawn in one go.
* **`LibraryAPI.swift`** gained `libraryFolders()` and `folderItems(folderID:)` — ⚠ **the folder path is this
  app's first PARAMETERISED endpoint**, which needed a real extension to `check-tvos-models.py`: R4 now turns
  a literal containing an interpolation into a pattern (each interpolation = one path component) and requires
  an **exact** match against a contract path, so `.../itemss` still fails while
  `"api/library/folders/\(folderID)/items"` passes. **Phase C's HLS endpoint needs the same rule**, which is
  why it was worth building properly rather than concatenating strings to please the checker.
* **`AppModel`** gained a `.browse` phase + `showBrowse()`/`showHome()`, and **both stores are rebuilt on
  every entry to `.library`** (a profile switch is a different library). ⚠ **A `TabView` was considered and
  NOT taken** — it would restructure the root view Phase A's round verified, for a navigation change no round
  has tested; the tab-bar question belongs with Phase D's polish.
* ⚠⚠ **The 2-D focus grid is NOT hand-rolled, and that is the finding — the plan expected it to be.** The
  plan said the grid "needs row/column memory so moving down from the middle of a row stays in the same
  column". Checked against how tvOS works: **`LazyVGrid` + focusable `Button`s get column memory and
  reveal-scrolling from the platform's focus engine for free** — the same finding as B2's deleted `RailFocus`,
  and a hand-rolled index map would fight it. What the app DOES own is **how much it draws**. ⚠ This could not
  be exercised from the sandbox, so: **falsifier — if the round shows the grid losing its column when moving
  down, that is a real defect, and the fix goes in the view (`@FocusState` + an index map), not in
  `BrowseRules`.**
* ⚠ **Still no item detail screen** (B4), so Select logs rather than doing nothing visible — B2's honesty rule.

### B4 — Item detail, read-only
`/api/jellyfin/detail?id=` (+ `/series/{id}/episodes` for a series). **Play is a placeholder in B** and
the screen must say so rather than doing nothing. Deliberately out of scope: request/download, Household
admin, subtitle vendor search, global search.

### B5 — the round
`./apple/scripts/mac-round.sh tvos --sim`, screenshot + the short summary. Screen-only verification is
Mac business: the SwiftUI views are **written here, never compiled here**.

---

## §4 — Out of scope on this branch
Backend changes (none — that is B0's decision) · the player (Phase C) · the tvOS app icon · the two
`RKMServerKit` duplicate links carried forward from Phase A.

## §5 — Options rejected, and why (so they are not relitigated)
| Option | Why not |
|---|---|
| Extend the contract with pydantic response models | **His call, 2026-09-19.** Correct in principle and mechanically small (`_item_public` has 7 call sites), but `response_model` filters the response, so the risk lands on a working web app for no user-visible gain today. |
| `swift-openapi-generator` | Needs `brew` + a SwiftPM plugin + a never-run script; unverifiable from this sandbox (rejected in Phase A, still true). |
| Hand-write the models with no gate | The one phase made of nothing but field names would have no wire-format check at all — and §1 shows a second source exists, so this would be choosing blindness. |

## §6 — Gates for this branch
`check-tvos-models.py` (incl. `--falsify`, **10/10**) · ⚠ **`check-tvos-core.py` (incl. `--falsify`,
**18/18**) — the one that RUNS the models, the poster URL and the Home's own rules (119 checks)** ·
`check-apple-typecheck.sh` (incl. the thirteen portable files) · `check-imports.py` (23 Swift files) ·
`check_md_links.py`. **No frontend/backend gate is claimed on this branch** unless a frontend/backend file
actually changes — saying so is the point. (The frontend's `client.ts` is *read* by R6/R7 as a shape source;
it is not modified, so no `vitest` run is claimed.)
