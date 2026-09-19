# tvOS UX — the Profile Switcher and the Home — plan

⚠ **Every number and every file path in this file came from a command run on 2026-09-19**, on branch
`feat/tvos-ux` cut from `dev` (`0d75e1f`) — measured here, or computed here (the WCAG ratios in §2b).
**Claims about Apple's platform are quoted from Apple's own documentation, cited where they appear** — they are
not recollection, and none of them has been tested on this machine. The design input is his, and it is committed
alongside this plan:

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

**2. tvOS 26 is available to us — the spec's Liquid Glass section is reachable, and the target does NOT have to
move.** `TVOS_DEPLOYMENT_TARGET = 17.6` (four times, `apple/tvos/RKMCinemaTV.xcodeproj/project.pbxproj`) is a
*compatibility floor*, not a toolchain limit: **Xcode 26.6 is what built this project** (`PROGRESS.md:2558`), and
`apple/scripts/test-mac-round.sh:272` fixtures a **`-- tvOS 26.5 --`** simulator with an `Apple TV 4K (3rd
generation)`. So the tvOS 26 SDK is already in place.

Apple's own guidance (`developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass`) settles the
rest in our favour:

* Liquid Glass requires **tvOS 26.0+** and Xcode 26.0+ — both satisfied;
* *"Apple TV 4K (2nd generation) and newer models support Liquid Glass effects. **On older devices, your app
  maintains its current appearance**"* — the degradation is **the platform's own**, so `if #available(tvOS 26, *)`
  gives glass on his TV and today's look everywhere else, **with the deployment target left at 17.6**;
* *"In tvOS, adopt standard focus APIs. … standard buttons and controls take on a Liquid Glass appearance when
  focus moves to them … consider applying these effects to custom controls … by adopting the standard focus
  APIs."* — which is §3's rule arriving from Apple's side: **use `.buttonStyle(.card)` and the glass is free.**

⇒ **DECIDED (his call, 2026-09-19): RAISE THE FLOOR TO 26.0.** One code path, no `#available` branching, and
Liquid Glass unconditionally — his Apple TV is a **4K 2nd generation or newer**, which is exactly the hardware
Apple says gets the glass.

⚠ **The cost, stated plainly, because it is a real one:** the app will not install on tvOS 17–25, so the 17.6
floor this client has shipped with through Phases A and B is gone. If an older Apple TV ever appears in the
house, this is the line that broke it.

⚠ **And it is a `project.pbxproj` edit.** That file carries a standing warning in this repo — *never touch it* —
but that rule is about **file membership** under synchronized groups, not build settings. A deployment-target
change (four occurrences of `TVOS_DEPLOYMENT_TARGET`) is a legitimate build-setting edit and is the correct way
to make it; it is not the thing the rule forbids.

⚠⚠ **It is also the phase's one change that CANNOT be verified in this sandbox.** There is no Xcode here, so a
new deployment floor can only be proven by his Mac build — and it can surface deprecations the 17.6 floor was
hiding. That makes it a **first thing the round must confirm**, not a footnote.

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

* **Vocabulary.** ⚠ **DECIDED (his call, 2026-09-19): the app's existing words win** — `"Password protected"`,
  `"Administrator — asks for a password"`, `"No password"`, `"Disabled — cannot be selected"`. The spec's
  `"Profile · password"` / `"Administrator · password"` set is **not adopted**, and for the reason this repo
  keeps re-learning: two vocabularies for one idea is the fault `HomeSnapshot`'s own comment warns about for rail
  headings — and the spec's set cannot express the disabled case at all, which the app's can.
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

### 2b. The tvOS-specific layer — measured, and much smaller than a palette

He asked whether the colour tones should be tvOS-specific. **Yes — but the arithmetic says only one token
actually needs to change, so a second palette would be inventing work.** Computed on 2026-09-19 from the real
tokens against `--bg #08090b` (WCAG 2.1 relative luminance; normal text needs **4.5:1**, large text **3.0:1**):

| Token | vs `--bg` | Verdict |
|---|---|---|
| `--text-primary` `#f5f5f7` | **18.29:1** | AAA — do not touch |
| `--accent` `#ffc400` | **12.47:1** | AAA — the brand accent is fine on a TV |
| `--text-secondary` `#a7aab2` | **8.57:1** | AAA |
| `--danger` `#ff5b5b` | 6.54:1 | AA |
| **`--text-muted` `#70747e`** | **4.26:1** | ⚠ **AA-large only — and it fails outright on every surface it actually sits on** |

```
--text-muted on:   --surface-1 4.01:1 · --surface-2 3.83:1 · --card 3.76:1 · --surface-3 3.57:1
```

**That is the whole palette problem, and it is one token.** `--text-muted` is used for de-emphasised captions —
exactly the smallest text on the screen — and it is below AA on all four surfaces, before a 10-foot viewing
distance makes small text harder still. Derived fix, **same hue and saturation, lightness lifted only**
(`HLS 0.467 → 0.532`):

| | `#70747e` | **`#81858f`** |
|---|---|---|
| on `--bg` | 4.26:1 | **5.39:1** |
| on `--surface-1` | 4.01:1 | **5.08:1** |
| on `--surface-2` | 3.83:1 | **4.85:1** |
| on `--card` | 3.76:1 | **4.76:1** |
| on `--surface-3` | 3.57:1 | **4.52:1** |

⇒ **`#81858f` clears AA on every surface the app puts it on**, and stays recognisably the same grey.

⚠ **DECIDED (his call, 2026-09-19): tvOS only — the web keeps `#70747e`.** ⚠ The consequence to hold onto: the
tvOS app now **deliberately holds a value the web app does not**, which is precisely what §2's drift gate must
permit. So the gate covers the **generated** `DesignTokens.swift` only; `TVTokens.swift` is hand-written and
lives outside it, and its entire job is to carry justified differences. A value that migrates from the second
file into the first stops being a tvOS decision and becomes a brand change.

⚠ Worth telling the web side eventually anyway: `#70747e` is a genuine accessibility miss *there* — it is the
app's own caption colour, below AA on every surface. Fixing it on the phone is a separate, one-line change, and
this plan deliberately does not make it (nothing here writes `frontend/`).

⚠ **What is deliberately NOT in this layer, and why:**
* **the brand hue.** `#ffc400` at 12.47:1 is not a contrast problem, and a tvOS-only accent would make the TV app
  a *different product* from the one on the phone. The spec's `#F2B93A` was not a tvOS adjustment — it was the
  wrong colour (§0.1).
* **the surface ladder is not a contrast question at all.** `--surface-*`/`--card` measure 1.06–1.19:1 against
  `--bg` **by design** — they are elevation, not text. ⚠ But that is the honest reason the spec reaches for glass
  panels: a 1.1:1 elevation step is essentially invisible from a couch. **On tvOS 26 that job belongs to the
  system's Liquid Glass materials, not to a colour token** — so `glass` should not exist as a hex in the tvOS
  layer at all, and the spec's `rgba(24,24,27,0.66)` + `backdrop-filter` is exactly the hand-rolled version
  Apple's guidance tells us to replace.
* **focus ring and CTA treatment.** Platform (§3).

⇒ So the tvOS layer is **`TVTokens.swift`**: hand-written, tvOS-only, small, and **every entry carries its
reason** — one adjusted token to start, plus the tvOS-only spacing/safe-margin/type-scale constants that were
never in the CSS. If a value differs from the web, that difference is visible in one file with an argument
attached, which is the point.

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
**plus the hand-written `Design/TVTokens.swift`** (the tvOS-only layer of §2b — the adjusted `--text-muted` and
the spacing/safe-margin/type-scale constants that were never in the CSS), plus a check that regenerating is a
no-op. ⚠ The tvOS project uses **synchronized groups** — a file's presence IS its target membership, so **never
touch `project.pbxproj`** for membership; adding the file is enough. Add both to `check-apple-typecheck.sh`'s
list in the same commit.

⚠ **BUILT 2026-09-20, with three additions the plan did not name — recorded here because a plan reads as fact
to the next session:**
* **`apple/scripts/check-design-tokens.py`** is the drift gate (the generator's `--check` is its R1), and it
  carries two more rules and a `--falsify` pass that proves all three can go red: **R2** no tvOS source may
  name the web app's `DesignTokens.Colour.textMuted` (that is what `TVTokens` overrides), and **R3** no hex
  literal or `Color(red:)` outside `Design/` — the CSS's own *"never scatter arbitrary colours"*.
* **`Design/DesignColours.swift`** — a THIRD file, and deliberately outside every gate (no SwiftUI on Linux,
  so nothing here can compile it). Its whole content is the four-component → `Color` conversion and the
  `RKMColour` names, so there is **no rule in it to be wrong**; `RKMColour.muted` reads `TVTokens` and every
  other name reads the generated table.
* **The buildspec's type scale is NOT adopted**, and `TVTokens` says why: it is prose, its colour table (the
  checkable part) was wrong in 8 of 10 values, and the accepted screens' sizes are what his round verified.
  Retro-fitting a scale across screens this phase does not touch is Phase D polish — half a scale would be
  the second copy §1a warns about.

⚠ **U1 also carries the two changes that are not tokens**, because both are "tell the truth about the build"
work and belong with the build settings: the **deployment-target bump to 26.0** (§0.2, the one legitimate
`project.pbxproj` edit) and the **`README.md:73` fix** (`17.0` → the real value, now `26.0`). ⚠ The target bump
is the phase's only change **no gate here can verify** — no Xcode in this sandbox — so it is confirmed by his
Mac build and nothing else.

### U2 — the Profile Switcher
The delta in §1a, on the existing accepted screen: the circular initials avatar, the lock badge, the row, the
eyebrow, `Add profile`, `Manage profiles`. ⚠ Carries §1a's two hazards: **one set of words** (and the decision
is his), and **every per-profile fact read from the server**, never from the spec's example.

⚠ **BUILT 2026-09-20** (`21f2ad8`). The rules are a new pure file — `Core/ProfileRules.swift` (initials, the
accepted subtitle vocabulary, the VoiceOver label, the eyebrow, and the administrator gate matched **by ID,
never by name**) — so they are EXECUTED here on Linux rather than only seen on a TV. ⚠ **One scope call the
plan did not name: `Add profile` / `Manage profiles` open a panel that states where profiles are actually
managed.** Both routes exist server-side, so offering the controls is not offering what the server refuses —
but this app has no admin WRITE path at all (no model, no client method, no screen), and building one is a
phase of its own, not a side effect of a redesign. The alternative (hiding the controls) would have the app
pretend the feature does not exist. ⚠ And **`TVTokens.Metric.profileTitle = 64`** is adopted here, one of
exactly two sizes taken from the buildspec's type scale (the other is the hero's) — the rest of the scale is
prose and is not retro-fitted across screens this phase does not touch.

### U3 — the Home top bar and the hero
The delta in §1b: `TopBar` from **`BrowseRules.libraryNavEntries`**, the hero band, the card badge/play/progress
affordances. ⚠ No focus arithmetic (§3).

⚠ **BUILT 2026-09-20** (`0052d4f`). Three things the build decided, all recorded because a plan reads as fact:
* **The badge is the web's own rule, not the buildspec's word.** The episode code when there is one, otherwise
  the **tv/film glyph** (`HomeRules.typeIcon` → `LibraryIcon.systemImage`, the mapping MOVED out of
  `BrowseView` so the two screens cannot drift). The buildspec's `MOVIE` word is a second vocabulary for one
  fact, and a word badge on the TV beside a glyph on the phone is exactly what §1a's vocabulary decision
  refuses. **The play glyph is NOT built at all** — nothing plays until Phase C, and a play triangle that does
  nothing is the control `docs/ARCHITECTURE.md` §11 forbids. It lands with the player.
* **The hero's primary button does not play either.** A series' primary opens its own screen (the web's
  `primaryGoesToPage` — a series is explored, not played, so it gets no second `Details` button); anything
  else shows **B4's** Playback placeholder and names the verb it WILL offer (`DetailCopy.nextUp`). Reusing B4's
  two sentences is deliberate: a second "playback arrives later" wording is a second vocabulary for one fact.
* **`PosterURL` gained the backdrop route** rather than a second builder — the same trap, the same clamp, the
  same empty-id refusal, so the hero's 16:9 artwork goes through the same session-cookie path and the same log
  line as every poster. ⚠ Both route words are string literals beginning `api/`, so **R4 checks both against
  the frozen contract**.

⚠ **And it costs a request:** `GET /api/library/items` exists purely for `pickHomeHero`'s LAST tier, so the
Home now makes five small sequenced requests instead of two (`HomeStore.load`'s note). The alternative was to
let the TV pick a hero the phone would not, which is a second implementation of a rule rather than one call.

### U4 — the third rail
`Recently Added` — a new `HomeRailID` case, the third fetch in `HomeStore` (`GET /api/library`, whose response
B1 already models as `LibraryRecentResponse`), and `HomeRules.recentlyAddedItems` wired where it was written to
go. ⚠ `HomeRails`' comment says the third row *"lands with the rail it needs"* — this is that moment, and the
snapshot/state tests exist to be extended, not replaced.

⚠ **BUILT 2026-09-20.** The fetch itself landed in **U3** (the hero's second tier needs the same response), so
U4 is the rail: the `HomeRailID` case, the third `rails` entry, its heading pinned against the web's literal
words, the rail's own failure line in the footer, and the **one-sided exclusion** pinned by a test — the hero
is taken out of Continue Watching and **never** out of Recently Added (a title can be both the hero and the
newest thing in the library). ⚠ **`HomeRailLimit.recentlyAdded = 16` and `HomeRules.recentlyAddedItems` had
been written, tested and UNUSED since B1** — this wired them rather than inventing a third number.

### U6 — match the prototype *(added 2026-09-20, after he saw the first build)*

⚠ **His words:** *"can you improve the UX, as per the html given to you — the current one doesn't even look
like what is seen in the html."* He is right, and the reason is measurable: U2/U3 took the buildspec's
**words** but kept the app's existing **geometry**, so the screens matched the plan's §1a table and not the
prototype he actually drew.

⚠⚠ **THE FIX IS THE PROTOTYPE'S OWN SCALE, NOT A SET OF HAND-CONVERTED NUMBERS.** Every size in
`rkm-cinema-tvos-concept.html` derives from `--u: 1cqw` — one percent of the screen's width — so adopting
`TVTokens.u = 19.2 pt` (tvOS renders in a fixed 1920 × 1080 point space) makes every value in the TV app
readable against a line of his HTML, and keeps the two screens from drifting apart. **The metrics now live in
`TVTokens.Hero` / `.Bar` / `.Shelf` / `.Profile` / `.Metric`, each transcribed as `u * <the number in the
file>`.**

What actually changed on screen:

| | Before U6 (from §1a's table) | After U6 (the prototype) |
|---|---|---|
| **Card** | 2:3 poster, 260 pt wide | **16:9 keyart, `19u` (365 pt)**, `0.7u` radius, badge top-left, gold play chrome bottom-right, progress bar along the artwork's bottom edge |
| **Card subtitle** | meta line under the art | unchanged — the web's own `cardMetaLine` (year · runtime / `S1E3 · Series`) |
| **Artwork route** | `poster` (2:3) | **`backdrop` (16:9), with a one-step fall back to the poster** (`PosterLoader.fallBackToPoster`) — a poster-only library would otherwise be a wall of "no photo" marks |
| **Hero** | 460 pt, title 68, eyebrow 16 | **`32u` (614 pt)**, copy bottom-aligned, title `3.6u` (69) weight 800 capped at 60 %, eyebrow `1u` bold gold, meta `1.05u`, bar `26u × 0.35u`, gold primary + 12 %-white secondary |
| **Top bar** | glass, 26 pt brand, `.bordered` tabs | **`.regularMaterial` under the prototype's `--glass-strong` tint**, `RKM·CINEMA` wordmark at weight 800 with its gold dot, `1.05u` tabs with the **focused tab inverted to black-on-gold**, `2.6u` circle buttons and the gradient avatar |
| **Profile screen** | centred row, flat `surface3` avatars, 54 pt title | **the prototype's own light**: a `profileGlow` radial over `--bg`, title at `4.4u` (84), `10.4u` gradient avatars (`#2A2A2E → #161618`) with `3.4u` gold-bright initials, a `2.2u` lock badge with a black ring, `0.72` unfocused / `1.14` + `-0.3u` focused, and the pill row at `1.05u` |
| **Shelves** | 42 pt between rows, 32 pt heading | **`2u` between sections, `1.5u` bold heading, `1.3u` card gap, `4.2u` insets** — and that same `4.2u` is now the app's margin everywhere |
| **Motion** | `.easeOut(0.15)` | the prototype's own curves: `cubic-bezier(.2,.9,.3,1)` at `0.28s` for tiles, `ease-out 0.2s` for tabs, CTA and icons |

⚠ **THREE THINGS THAT ARE STILL DELIBERATELY NOT PORTED, each with its reason:**
* **the prototype's JavaScript.** It hand-rolls nearest-neighbour up/down focus (lines 546-561) and calls
  `scrollIntoView` on every focus move (line 518). tvOS's focus engine does both — `RailFocus.swift` was
  deleted for the first and B3's `LazyVGrid` got the second free — so porting them would be the third time
  this repo pays for the same mistake. **F4** is the falsifier that keeps us honest.
* **the Search icon and the `Watchlist` / `Discover` / `Suggest` tabs.** Those screens do not exist on tvOS
  yet (§5), and a control whose every press must be refused is the fault `docs/ARCHITECTURE.md` §11 names.
* **the prototype's `S1·E3` badge spelling.** The badge uses the app's own `episodeItemCode` (`S1E3`) because
  the card prints `S1E3 · Series name` underneath it — `S1·E3` above and `S1E3` below would be two spellings
  of one code on one card. ⚠ One line to change if he wants the dot; say so rather than let it drift.

⚠⚠ **AND THE FIRST BUILD THAT RAN SHOWED A REAL UX BUG — the focus ring around the label rather than the
button** (his report: *"homescreen → scrolling to details button → the ux has bug"*). A `ButtonStyle` sees only
`configuration.label`, so chrome applied to the `Button` is chrome the style cannot wrap: `CtaButtonStyle` and
`PillButtonStyle` drew the ring while their callers drew the box. **Both styles now own their box**
(`CtaButtonStyle(kind:)`, `PillButtonStyle(kind:)`), which removes the class, and **rule 5 of
`check-tvos-members.py`** refuses box chrome applied to a `Button` whose style already draws it.

⚠⚠ **AND U6'S SECOND ROUND FAILED ON A NAME, WHICH IS WHY THE MEMBERS GATE HAS A RULE 4.** `ButtonStyle`
declares an associatedtype requirement `Body`, so the helper views nested inside U6's four new `ButtonStyle`
conformers collided with it — `type 'TabButtonStyle' does not conform to protocol 'ButtonStyle'`. Phase A's
tile style had been called `TileBody` for exactly that reason and the rule was forgotten; the four are now
`TabChrome` / `IconChrome` / `CtaChrome` / `PillChrome`, and **`check-tvos-members.py` refuses a nested
`struct Body`**, so the next instance costs a gate run instead of a round.

⚠ **One thing the prototype adds that this phase did NOT build:** the hero's slow background drift
(`@keyframes drift`, 26 s). It needs real artwork behind it and Reduce Motion handling, and it is exactly the
"ambient motion" the buildspec §1 asks for — Phase D polish, recorded so it is not mistaken for an oversight.

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
| F7 | **the build succeeds at the new 26.0 floor**, and a focused card shows Liquid Glass | `BUILD FAILED`, or a deprecation the 17.6 floor was hiding — ⚠ this is the ONLY change in the phase the sandbox cannot test (§0.2) |

⚠ **What the round CANNOT prove:** nothing about real Apple TV hardware (the simulator is not an Apple TV), and
**a failed build proves nothing about the layouts** — a `BUILD FAILED` is a build round, and F1–F7 were never
attempted.

---

## §5 — Out of scope on this branch

The player (Phase C — its C1 is already built and parked on `feat/tvos-player`, see below) · **the web UI**
(nothing here changes `frontend/`; the CSS is *read* by the token generator, never written) · subtitles · search
· the Discover/Suggest/Watchlist **screens** (they become tabs, which is all §1c asks for) · the tvOS app icon
· **Liquid Glass beyond the platform's own focus treatment** — no `GlassEffectContainer` and no custom glass
until a screen actually needs a shape the system will not give it (§0.2: the standard focus APIs already do it).

⚠ **README drift found while measuring, and it should be fixed in U1's commit:** `apple/tvos/README.md:73` states
`TVOS_DEPLOYMENT_TARGET = 17.0` while the project carries **17.6**. That is this repo's "one rule in two places"
in documentation — the same fault as the stale resume-block headline — and the README is the line a next session
actually reads.

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
| `python3 apple/scripts/check-imports.py apple/tvos/RKMCinemaTV --selftest` | the gate that sees the SwiftUI views' IMPORTS |
| `python3 apple/scripts/check-tvos-members.py` (added 2026-09-20, after the round failed) | the gate that sees the views' MEMBER ACCESS — the first member each listed view variable names, against the type that declares it |
| `python3 tools/check_md_links.py` | this file, and the two design assets it names |
| `cd frontend && npx vitest run` · `npm run typecheck` | ⚠ expected **unchanged** — if either moves, `frontend/` was touched against §5 |
| `cd backend && python -m pytest tests/ --capture=no -q` | ⚠ expected **unchanged** — no `backend/` file is touched by this phase, which is the point |

⚠ **Nothing to deploy.** Only `apple/` and `docs/` change, so the api and web images are untouched and his
running stack is unaffected — the same scope as Phases A and B.
