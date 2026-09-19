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

### B1 — models, gate, and the artwork question *(this commit)*
* `Core/Models/LibraryModels.swift` (new): `MediaItem`, `LibraryItemsResponse`, `FolderItemsResponse`,
  `LibraryRecentResponse`, `EpisodeItem`, `EpisodesResponse` — every key explicitly mapped in
  `CodingKeys`, optionality taken from §1.
* `Core/PosterURL.swift` (new, portable): the poster URL builder, mirroring the frontend's
  `posterUrl()` — `/api/jellyfin/poster?id=<item_id>&width=<w>` with percent-encoding. Pure Foundation,
  so it is typechecked and unit-asserted here; artwork *loading* is not.
* `apple/scripts/check-tvos-models.py`: R6/R7 as §2, plus falsification mutations for both.
* `apple/scripts/check-apple-typecheck.sh`: add the two new portable files to the tvOS loop.
* ⚠ **The artwork question, recorded for the Mac round:** `GET /api/jellyfin/poster` is session-scoped, so
  whatever loads images must present the session cookie. `AsyncImage` shares `URLSession`'s cookie store —
  the cheapest option to try first — but a poster wall with no posters looks identical to a broken screen,
  so the load path gets its own log line rather than a silent empty `Image`.

### B2 — Home: two horizontally scrolling rows
`/api/library/continue-watching` + `/recently-watched`. ⚠ Focus FIRST: a row is a 1-D focus path, the card
grows on focus, the row scrolls to keep the focused card visible. ⚠ **No hover, no pointer** — everything
the web app does on hover must be on focus or on a button. Progress bars + per-item state are what make
this screen worth having; a bare poster wall is not.

### B3 — Browse: the 2-D focus grid
`/api/library/folders` → a folder → `/folders/{id}/items`. ⚠ The focus engine's hard case: the grid needs
row/column memory (down from the middle of a row stays in the same column) and a cap on what it draws.
⚠ Everything drawn over the grid must be checked for focus participation — Phase A's HUD bug, same class.

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
`check-tvos-models.py` (incl. `--falsify`) · `check-apple-typecheck.sh` (incl. the two new portable files)
· `check-imports.py` · `check_md_links.py`. **No frontend/backend gate is claimed on this branch** unless a
frontend/backend file actually changes — saying so is the point.
