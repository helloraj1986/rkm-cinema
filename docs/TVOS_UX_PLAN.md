# tvOS UX — the Profile Switcher and the Home — plan

⚠ **Every number and every file path in this file came from a command run on 2026-09-19**, on branch
`feat/tvos-ux` cut from `dev` (`0d75e1f`). The design input is his, and it is committed alongside this plan:

* `tvos_ux/1. UserProfileSelection_HomePage/rkm-cinema-tvos-concept.html` — the clickable prototype (572 lines)
* `tvos_ux/1. UserProfileSelection_HomePage/rkm-cinema-tvos-buildspec.md` — the build spec (219 lines)

⚠ The prototype is a **browser simulation of a Siri Remote**, and §3 is about the one part of it that must
NOT be ported.

---

## §0 — Four things measurement changed in the spec (read this first)

The spec was written without this codebase in front of it and **says so** — it labels its assumptions. Four of
them are wrong, and each one would have cost a round:

**1. The colour tokens are not this app's colours.** The spec's §1 table says it is *"Extracted from the current
web UI so both platforms stay visually identical"*. It is not. Measured against
`frontend/src/styles/index.css` (which `frontend/tailwind.config.js` cites as sourced from
`RKM-CINEMA_NEW_UX/RKM_Cinema_Premium_Media_Library_Design_Spec.md`):

| Role | Spec says | This app actually is | `index.css` |
|---|---|---|---|
| background | `#08080A` | **`#08090b`** | `--bg` |
| card | `#17171A` | **`#17191e`** | `--card` |
| elevated | `#1B1B1E` | **`#1b1e24`** | `--surface-3` |
| text secondary | `#ABABB2` | **`#a7aab2`** | `--text-secondary` |
| de-emphasised | `#75757C` | **`#70747e`** | `--text-muted` |
| **brand accent** | **`#F2B93A`** | **`#ffc400`** (hover `#ffd43b`) | `--accent` |
| avatar initials | `#FFD873` | `#ffd43b` | `--accent-hover` |
| danger | `#FF6B5E` | `#ff5b5b` | `--danger` |
| hairline | `rgba(255,255,255,0.09)` | `rgba(255,255,255,0.08)` | `--border` |

The accent is the one that matters: **gold `#F2B93A` is not the brand colour.** Half the spec's focus and CTA
treatment is specified in a colour this app does not use. §2 fixes this at the root rather than by hand-editing
a table.

**2. The target is tvOS 17.6, not tvOS 26.** `TVOS_DEPLOYMENT_TARGET = 17.6`, four times, in
`apple/tvos/RKMCinemaTV.xcodeproj/project.pbxproj`. So the spec's §5 — *"tvOS 26 adopts Liquid Glass … use
`Material` / the system glass materials"* — is written against an SDK this target cannot reach. Whether to raise
the deployment target is **his decision and needs his Xcode version**; it is not a decision this plan can take,
and it is the one open question the phase starts with (§3).

**3. Both screens already exist, and both were accepted on his simulator.** This is a **redesign with a
measurable delta**, not a new build:

* `apple/tvos/RKMCinemaTV/Auth/ProfilesView.swift` (11 KB) — Phase A screen 2, accepted
* `apple/tvos/RKMCinemaTV/Home/HomeView.swift` + `RailView.swift` + `PosterCard.swift` — Phase B2, accepted

The spec's §3 and §4 read as though they are new. §1 is the delta, and it is much smaller than the spec implies —
and, in two places, it is a **regression** the plan must not make (§1's ⚠ notes).

**4. `ASSUMPTION: the existing iOS app is SwiftUI` — it is not.** The iOS app is a **`WKWebView` shell**; the
page makes every `/api` call and there is no SwiftUI view layer, no view models, and nothing to "share via a
shared framework target". What the Apple clients genuinely share is `apple/Shared` (`RKMServerKit`: the server
address and the log), which the tvOS target already imports. So the spec's §0 table row *"View models /
business logic — share via a shared framework target"* has nothing to share, and the tvOS side keeps its own
`Core/` rules — which is the arrangement that has been working for three phases.

⚠ **One more, and it is the good news:** the spec's **"Recently Added" shelf is already sanctioned by this repo.**
`HomeRails.swift:18-20` says, in the app's own words: *"**Also not here: Recently Added.** `useHomeRows` composes
a third rail from `GET /api/library` … a third row is a screen decision, not a defect, and it lands with the rail
it needs rather than being built dead now."* The decision is being made now. And the rule is already written,
tested and gated — `HomeRules.recentlyAddedItems` and `HomeRailLimit.recentlyAdded = 16` exist and are currently
**unused**. U4 wires them; it does not invent them.

---

## §1 — The delta, measured

### 1a. Profile Switcher — `Auth/ProfilesView.swift` vs the spec

| | Already there | The spec adds |
|---|---|---|
| Title | `"Who's watching?"` at 54 pt | same words at **64 pt** (§1 type scale) |
| Subtitle | `"Signed in as <name>"` | an **eyebrow** above the title: `"N profiles on this server · Signed in as X"` |
| Avatar | SF Symbol — `person.crop.circle.fill`, `star.circle.fill` for admin | **circular tile with gold initials** (`ME`, `RA`, `RK`, `SH`) |
| Lock | `lock.fill` glyph **beside** the symbol | a **badge on the avatar's bottom-right** |
| Layout | `LazyVGrid`, tiles `frame(width: 360)`, leading-aligned | a centred **horizontal row** |
| Focus | `ProfileTileStyle` button style, `@Environment(\.isFocused)` | scale **1.14**, unfocused siblings at **~0.72** opacity, white focus ring |
| Actions | **`Sign out`** (exists) | **`Manage profiles`** pill, and an **`Add profile`** tile |
| Per-profile subtitle | `"Administrator — asks for a password"`, `"Password protected"`, `"No password"`, `"Disabled — cannot be selected"` | `"Administrator · password"`, `"Profile · password"`, `"Profile"` |
| Password entry | an **overlay**, deliberately not a sheet (its own comment says why: a modal has to own focus to be dismissible with Back) | a push to a PIN/keyboard screen |

⚠⚠ **Two real hazards here, and both are the repo's most-repeated defect:**

* **Vocabulary.** The app already has one set of words for exactly these states; the spec introduces a second.
  That is *"a second vocabulary for one idea"* — the same fault `HomeSnapshot`'s own comment warns about for rail
  headings. **One set wins**, and the honest default is the app's existing strings, which the spec's table
  simplifies into something the server does not exactly say (`"Profile · password"` cannot distinguish a
  disabled profile from a plain one, and the app's `"Disabled — cannot be selected"` can).
* **The spec's example data is HARDCODED and must not be.** It shows `meenu`/`raj`/`rkm` locked and `sharanya`
  not, and labels `rkm` `Administrator`. Those facts come from the **server** — `profile.has_password` and
  `profile.is_admin` — and `ProfilesView` already reads them. Hardcoding the example would ship a screen that
  lies the first time somebody changes a password.

⚠ **`Add profile` / `Manage profiles` are ADMIN functions and the server DOES back them** (measured):
`POST /api/admin/users`, `POST /api/admin/users/{id}/rename`, `/password`, `/policy`, `DELETE /api/admin/users/{id}`
(`backend/api/routes/admin_users.py`). So they are not "offering what the server will refuse" — **provided** they
are gated on the signed-in account being the administrator, which is a server-side answer, not a UI guess.

### 1b. Home — `Home/HomeView.swift` vs the spec

| | Already there | The spec adds |
|---|---|---|
| Structure | `RailView` rails from `HomeSnapshot.rails`, `PosterCard` | **top bar**, **hero band**, and a **third rail** |
| Rails | `Continue Watching` (a filter — *"filter, never re-order"*, no cap) and `Recently Played` (cap 14) | **`Recently Added`** (cap 16 — the rule exists, unwired) |
| Card | 16:9 poster, title, subtitle; four screen states (`loading` / `content` / `allFailed` / `empty`) | episode/type **badge** (`S2·E4`, `MOVIE`), play glyph, bottom **progress bar** |
| Hero | — | eyebrow, title, meta line, progress bar, `Resume` + `Details` |
| Top bar | — | brand, tab row, search + avatar buttons; **recede to ~55 % when focus leaves it** |

⚠⚠ **The top bar's tabs must NOT be the spec's hardcoded list.** The spec names
`Home · Movies Kids · Movies · TV Shows · Watchlist · Discover · Suggest`. Measured, the web's nav is
`frontend/src/app/layout/Sidebar.tsx` (§1c) and the **libraries are per-profile and dynamic** — and this repo
already ports that rule: `BrowseRules.libraryNavEntries` is documented in `BrowseRules.swift:62` as *"the ONE
place that decides what the Browse list contains"*, mirroring `frontend/src/features/library/lib.ts`. The top
bar reads **that**, so a profile's libraries and the Browse screen can never disagree. A literal array in a tab
bar would be the third copy of a rule this repo has already consolidated twice.

### 1c. The real navigation (measured, `frontend/src/app/layout/Sidebar.tsx`)

| Group | Entries | tvOS destination |
|---|---|---|
| Browse | `Home` → `/library/home` | primary tab |
| Libraries | **dynamic** — `libraryNavEntries`: the profile's libraries (`Movies Kids`, `Movies`, `TV Shows`, …) | primary tabs, from the shared rule |
| Collections | `Watchlist` → `/watchlist`, `Discover` → `/discover`, `Suggest` → `/suggest` | secondary tabs, same row |
| — | `Search` | icon button, right of the row |
| — | `Settings` → `/settings` (sidebar footer) | **into the profile menu**, per the spec — correct, and the reason is the spec's own: tvOS top bars stay short |
| — | `Downloads` | ⚠ **not a tab.** `Sidebar.tsx:48-54` shows it *only where it can work* (the iOS shell) — a link whose every control must be refused is worse than no link. tvOS is not that shell. |

---

## §2 — One token source, GENERATED, with a drift gate

The spec's §1 asks for the right thing (*"put these in one shared source of truth rather than hand-copying hex
values into each screen"*) and then hand-copies the wrong values. Doing it properly is also **more** enforceable
than the spec asks, because this repo already has the pattern:

> **Generate `DesignTokens.swift` from `frontend/src/styles/index.css`, and gate it the way
> `npm run generate:types` gates the TS types — regenerate and require `git diff --exit-code`.**

That is the same trade `docs/api/openapi.v1.json` already makes for the wire format: **one source, generated
consumers, and a gate that fails the moment they drift.** It means the tvOS app cannot hold a colour the web app
does not, and a future brand change is one CSS edit plus a regeneration instead of a hunt through two targets.

⚠ **Scope it honestly:** the CSS custom properties are the source; the *semantic* names (`--accent`,
`--text-secondary`) map to Swift enums directly. Values that exist only in the spec's prose and not in the CSS —
the 8 pt grid, safe margins, type scale — are **tvOS values** and belong in the plan as constants with a stated
derivation, never as a second token file pretending to be generated. A generator for a hand-written number is
worse than no generator.

---

## §3 — The platform: two behaviours, and only one of them is ours to write

⚠⚠ **The prototype's own JavaScript hand-rolls two things tvOS already does, and this repo has paid for
porting exactly these twice.**

`rkm-cinema-tvos-concept.html` lines 546-561 implement up/down focus movement by measuring
`getBoundingClientRect()` and choosing the **nearest centre** — a hand-written 2-D focus map. Lines 517-522 call
**`scrollIntoView`** to bring a focused card into view. In a browser, both are necessary. **On tvOS they are not:**

* `RailFocus.swift` was written for the rail-scroll case in Phase B and **DELETED before landing** — *"tvOS's
  focus engine already scrolls an ancestor `ScrollView` to reveal the focused view"*, and a hand-rolled
  `offset(x:)` runs *on top of* the platform's and produces a jitter that reads as "the arrows are broken".
* B3's 2-D grid was predicted to be *"the ONE focus case the platform does not solve for you"*. It was not:
  `LazyVGrid` of focusable `Button`s gets **column memory and reveal-scrolling from the engine**.

⇒ **U2 and U3 write no focus arithmetic.** The rail is a `ScrollView` of focusable cards; the grid is a
`LazyVGrid`. What the app owns is *what it draws and when*, never where the focus ring lands.

⚠ **The one behaviour that IS ours:** the top bar receding to ~55 % when focus is elsewhere. That needs the app
to observe focus leaving the bar, and **whether SwiftUI on tvOS can observe that cleanly is a hypothesis** — it
goes in the round's falsifiers rather than into an assertion here. If it cannot, the honest fallback is a
`.buttonStyle(.card)`-style platform effect, not a hand-rolled dim.

⚠ **And the spec's own §5 advice is the right advice** — *"respect system focus effects … rather than fully
hand-rolling scale/shadow animations"*. That is consistent with everything above: `.buttonStyle(.card)` and the
platform's focus lift first, hand-rolled only where the platform has nothing.

---

## §4 — Phases

### U1 — the token source *(pure, gateable, and the thing both screens need)*
`apple/scripts/generate-design-tokens.py` + the generated `apple/tvos/RKMCinemaTV/Design/DesignTokens.swift`,
plus a check that regenerating is a no-op. ⚠ The tvOS project uses **synchronized groups** — a file's presence
IS its target membership, so **never touch `project.pbxproj`**; adding the file is enough. Add it to
`check-apple-typecheck.sh`'s list in the same commit.

### U2 — the Profile Switcher
The delta in §1a, on the existing accepted screen: the circular initials avatar, the lock badge, the row, the
eyebrow, `Add profile`, `Manage profiles`. ⚠ Carries §1a's two hazards: **one set of words** (and the decision
is his), and **every per-profile fact read from the server**, never from the spec's example.

### U3 — the Home top bar and the hero
The delta in §1b: `TopBar` from **`BrowseRules.libraryNavEntries`**, the hero band, the card badge/play/progress
affordances. ⚠ No focus arithmetic (§3).

### U4 — the third rail
`Recently Added` — a new `HomeRailID` case, the third fetch in `HomeStore` (`GET /api/library`, whose response
B1 already models as `LibraryRecentResponse`), and `HomeRules.recentlyAddedItems` wired where it was written to
go. ⚠ `HomeRails`' comment says the third row *"lands with the rail it needs"* — this is that moment, and the
snapshot/state tests exist to be extended, not replaced.

### U5 — his round, on the MacBook Pro
A **screen** round, **without** `-RKMDebugHUD YES`. Falsifiers, written before the round rather than after:

| # | Falsifier | What disproves it |
|---|---|---|
| F1 | the Profile row reads as **one choice**: focused tile up + ringed, the others dimmed | everything looks equally bright — the dim rule is not applying |
| F2 | **every** profile's lock/admin state matches the server | a profile that has a password shows none (hardcoded example data — §1a) |
| F3 | the top bar's tabs are **this profile's** libraries | the spec's fixed list is on screen instead |
| F4 | moving down a shelf and back **keeps the card's column** | focus jumps to the first card — the platform is NOT doing it, which means a hand-rolled map is genuinely needed after all |
| F5 | a real poster draws in the hero and the rail (**B4's falsifier, still unmeasured**) | the "no photo" marker |
| F6 | the top bar dims when focus leaves it | it stays at full opacity — then §3's fallback applies |

⚠ **What the round CANNOT prove:** nothing about real Apple TV hardware (the simulator is not an Apple TV), and
**a failed build proves nothing about the layouts** — a `BUILD FAILED` is a build round, and F1–F6 were never
attempted.

---

## §5 — Out of scope on this branch

The player (Phase C — its C1 is already built and parked on `feat/tvos-player`, see below) · **the web UI**
(nothing here changes `frontend/`; the CSS is *read* by the token generator, never written) · subtitles · search
· the Discover/Suggest/Watchlist **screens** (they become tabs, which is all §1c asks for) · the tvOS app icon ·
any decision about the deployment target (§0.2 — his, and it needs his Xcode) · `ATVStyle`/Liquid Glass
materials until that decision is made.

⚠ **Parked, and it must not be lost:** `feat/tvos-player` carries **C1 — the playback credential**
(`PlaybackAuth.swift`, 320 checks / 55 mutations red, pushed as `6919626`). It is pure, self-contained and
independent of this branch. The order he asked for is **UX first**, so this plan is cut from `dev` and Phase C
resumes after — and whoever resumes it should check `docs/TVOS_PLAYER_PLAN.md` §3 before rebasing, because C5
(the backend carrier) is deliberately **not built**.

---

## §6 — Options rejected, so they are not relitigated

* **Hand-copying the spec's hex table into a Swift file.** It is wrong in eight of ten values (§0.1), and a
  hand-copied table has no way to notice the web changing. Rejected for the generated source + drift gate.
* **Porting the prototype's focus JavaScript** (nearest-centre up/down, `scrollIntoView`). Rejected by
  measurement, twice over: `RailFocus.swift` was deleted for this and B3's grid got it free (§3).
* **The spec's hardcoded tab list.** Rejected: libraries are per-profile and the rule is already ported into
  `BrowseRules.libraryNavEntries`.
* **The spec's hardcoded profile example data.** Rejected: these are server facts the accepted screen already
  reads.
* **Building `Add profile` / `Manage profiles` as client-only affordances.** They are real server routes
  (`admin_users.py`), so they are allowed — but they are **admin-gated**, and a tile that appears for a
  non-admin is a control the server refuses.
* **Raising the deployment target to 26 as part of this phase.** It is a platform decision with a toolchain
  dependency on his Mac, not a screen decision.

---

## §7 — Gates for this branch

| Gate | Why |
|---|---|
| the token-drift check (new, U1) | regenerate from `index.css` and require no diff — the whole point of §2 |
| `python3 apple/scripts/check-tvos-models.py` | any new model key must still match the frozen contract |
| `python3 apple/scripts/check-tvos-core.py` (+ `--falsify`, backgrounded, ~10 min) | U4's rail rules must **run**, not merely compile |
| `bash apple/scripts/check-apple-typecheck.sh` | ⚠ add every new portable file in the **same** commit it lands |
| `python3 apple/scripts/check-imports.py apple/tvos/RKMCinemaTV --selftest` | the ONLY gate that can see the SwiftUI views |
| `python3 tools/check_md_links.py` | this file, and the two design assets it names |
| `cd frontend && npx vitest run` · `npm run typecheck` | ⚠ expected **unchanged** — if either moves, `frontend/` was touched against §5 |
| `cd backend && python -m pytest tests/ --capture=no -q` | ⚠ expected **unchanged** — no `backend/` file is touched by this phase, which is the point |

⚠ **Nothing to deploy.** Only `apple/` and `docs/` change, so the api and web images are untouched and his
running stack is unaffected — the same scope as Phases A and B.
