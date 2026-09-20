# Known issues — open defects, in his words

## ▶ STATUS AFTER HIS 2026-09-17 ANSWER ROUND — read this first

He answered every open item. What that means for this file:

| # | His answer | State |
|---|---|---|
| 1 | Reproduced on device: the ⋯ and Watched DO work, but **the Watched control shows no state and no feedback on tap** | **Half closed** — `features/library/WatchedAction.tsx` now says `Unwatched`/`Watched`, shows `Saving…` while in flight, and `useMutateItemState` toasts the server's sentence on failure. His device round confirms. ✔ **Re-measured 2026-09-18 (session 3):** the tile renders state-labelled at 320/390/430 (`tools/check_detail_mobile.py`, falsified) — the headless half is now evidence, not an assumption; ⚠ the TAP feedback still needs his phone. |
| 2 | **Rule decided:** the details view OWNS the watched control; the poster only reflects status — so the poster shows ONE tick | **CLOSED 2026-09-18** — landed. `MediaCard`'s toggle button and its ⋯ `Mark as watched/unplayed` item are gone (`onToggleWatched` deleted, not left optional), the tick MARKER stays, and the ⋯ row is right-aligned now that it has one child. The six call sites dropped the prop. Pinned by `tools/check_poster_watched.py` (one watched indicator per played poster, no watched control, no watched verb in the menu), and the harness probe was FIXED mid-way because it knew only the word "unwatched" while the removed control said "unplayed" — the falsification caught that, not a review. |
| 3 | **Corrected:** Settings is fine — the sideways scroll is on the **Switch Profile** view | **FIXED** — measured cause: the picker's nowrap subtitle (348px / 494px of min-content) floors the `place-items-center` grid track through the grid item's `min-width:auto`, so `scrollWidth` was 416 (picker) / **562 (Switch Profile)** at *every* width from 320 to 430. One token, `min-w-0` on the picker container, closes it to 0 and lets the subtitle ellipsise. ⚠ The root `overflow-x: clip` guard did not fix it — it was applied and the document still scrolled the full 172px. |
| 7 | **Cancel does nothing on an in-progress download** | ✅ **CONFIRMED FIXED ON HIS DEVICE 2026-09-19** — *"cancel of an in progress works now"*. The entry and its diagnosis are closed below; the record of the fix is in `PROGRESS.md` (session 6, Part 2/3). |
| 5 | **Rule decided:** the rail excludes the hero, by title ID, as one shared `lib.ts` utility with a unit test | **CLOSED** — `library/lib.ts::withoutHero()` + `useHomeRows`; both Homes inherit it; 5 tests; falsified positionally (4 went RED). |
| 6 | Cannot reproduce; appears resolved | **CLOSED** — no blank state observed on his round. |

⚠ The entries below are kept verbatim (his words) while their fixes land; anything actually fixed is
deleted from here and recorded in `PROGRESS.md`, per this file's own rule at the top of the next
section.

⚠ **This file is for OPEN DEFECTS ONLY.** Anything fixed here must be deleted from this file and
recorded in `PROGRESS.md` instead. Each entry keeps his wording, then what is already known about
where it lives — so the next session starts from evidence rather than from a blank page.

Opened 2026-09-17 from his iPhone/iPad round on `feat/mobile-m3-library` (now merged to `dev`).

---

## 1 · The details page's **More** (⋯) and **Watched** buttons do nothing

> *"there are few bugs in details page like more button is not working neither watched button"*

**What is already known.** Both controls sit in the action row of `features/library/ItemDetail.tsx`
(`IconAction` tiles + a `PopupMenu` trigger). ⚠ In the SANDBOX (Chromium, 390×844) the ⋯ tile **does**
open a non-empty menu — measured: `['Play', 'Mark as unplayed', 'View details', 'Open in Jellyfin']`
— and the Watched tile renders with a live `onClick`. So whatever breaks it is **iOS-specific** and
this must be reproduced on the device before changing code.

**Where to look first — in this order:**

0. ⚠⚠ **(2026-09-18, session 5 — CHECKED AND FIXED, but read it before diagnosing anything here.)**
   A REAL tap never reached a control inside a **`Sheet`** at all: `Sheet` captured the pointer on
   `pointerdown`, and since that handler is on the panel it captured gestures that STARTED on a
   button — the pointerup retargeted to the panel, so the browser dispatched `click` to the PANEL and
   the button never heard it. Measured in Chromium: a real click on the suggest sheet's Download did
   nothing while `element.click()` from the console ran the handler. **The ⋯ tile opens a SHEET**, so
   every item in it was inert — and no check had ever clicked inside a sheet, which is exactly why it
   survived. Fixed (`shouldArmDrag`, `DRAG_ARM_PX = 8`). ⚠ It is device-unverified: his round must
   confirm a tap inside the sheet works now.

1. **`PopupMenu`'s positioning.** `measure()` assumes a 224px menu and clamps to
   `window.innerWidth/innerHeight`. iOS's *visual* viewport is shorter than the layout viewport while
   the toolbar is up, so a menu computed to fit can be placed **below the fold** — it opens, and he
   sees nothing. That is indistinguishable from "not working", and it is the leading suspect.
2. **`Watched`'s mutation.** The tile calls the outlet's `toggleWatched`, which goes through
   `useMutateItemState()` → `invalidateQueries(["library"])`. If the POST 204s but the refetch is
   dropped, the state never changes on screen. ⚠ Remember the `204` rule: a `204` is SUCCESS with no
   body (`lib/api/client.ts`), and `POST /api/jellyfin/progress` answers exactly that.
3. **A tap that never lands.** Both controls are inside the flex-wrap action row. Check nothing
   overlays them on a device — the row sits under the backdrop hero in `ItemDetail`.

**Do NOT "fix" this by rebuilding the row.** It was verified working in the browser; reproduce it on
his phone first, with him holding the device.

---

## 3 · iPhone Settings still scrolls sideways — the guard is not a fix

> *"Settings page on ipad looks good but still scrolls on iphone"*

**What is already known.** Every settings route at 390px reports `scrollWidth === 390` — no element
overflows, measured on his own data through the live API. `[data-layout="mobile"] { overflow-x: clip }`
in `styles/index.css` therefore ships as a **GUARD**, not a diagnosis.

**Still needed from him:** the exact screen and the exact gesture (`"swiping left on the Downloads
list after the sheet closes"`, say). Without that, the guard only hides the offender — and if his
phone still pans, something is scrolling a container the root rule cannot clip.

---

## 5 · A Continue Watching title can appear TWICE on one page — hero *and* first card in the rail

⚠ Found by reading the code while fixing the double-heading bug, not reported by him, and **not
changed** — the answer is a product decision, not a defect I get to pick.

`ContinueWatchingRow` filters the Continue Watching items and renders **all** of them. When the hero
IS a Continue Watching pick (which is the usual case — that is how `pickHomeHero` chooses), that same
title is therefore also the first card in the rail below it: once big, once as a card.

* **Desktop:** has always done this.
* **Phone:** only when there are 2+ Continue Watching titles — my screen renders the rail only above
  `cwItems.length > 1`, so a single in-progress title appears exactly once.

**The decision needed from him:** does the hero also belong in the rail (current behaviour, both
layouts), or is the rail *"everything except what the hero is already showing"*? ⚠ The second is what
most streaming apps do, and because it is a RULE it belongs in `lib.ts` and would then apply to both
Homes at once — not patched into one screen.

---

## 6 · Home can come up blank after a profile pick (pre-existing)

Not reported by him; found while measuring (§ above). After a fresh profile pick, the Home queries can
sit unfired until a reload. ⚠ **The DESKTOP Home does the same thing in the same harness run**, so it
is pre-existing and unrelated to the mobile work — recorded here so it is not rediscovered as new, and
so it can be given its own investigation rather than being quietly worked around.

---

## 7 · M4's **RequestSheet** — option (b) is BUILT (2026-09-18); (c) is still his call

⚠ **STATUS 2026-09-18 (session 5):** option **(b) is built** on `feat/mobile-request-and-similar` —
the request's own sentence and, for a 409, its candidate titles render as a READ-ONLY list inside
the title's suggest sheet (`AmbiguousMatches`), on the phone and in the desktop dialog. It is
deliberately read-only and that is a fact about the SERVER, not a preference: a candidate carries a
title and a year and **no id**, so a pick-one control would have nothing to re-request with. Option
**(c)** — carry an id (ideally `tmdbId`) on each candidate and accept a chosen one on the request
path — remains a BACKEND phase and remains his decision. The client half is now done, so (c) is a
server change plus one prop.

⚠ Found in the backend/client ground truth while starting M4 (2026-09-17). The wireframe (§7.4) shows
a request flow with a quality list and an ambiguity list. Two facts stand in the way, and BOTH are
things this app does not currently have:

1. **There is no quality parameter to choose.** `POST /api/media/{id}/request` takes the media id and
   nothing else; the profile is whatever the *arr instance is configured with server-side. The
   wireframe's "◉ 1080p HD (2.1 GB) / ○ 720p / ○ 4K" would therefore be a control that cannot act —
   exactly the defect M3-part-4 removed from the details page. (`GET /api/quality` DOES exist and
   returns profiles, so the data is reachable — but nothing accepts a chosen one on the request path.)
2. **The ambiguous case cannot be actioned from the client.** The server answers **409** with
   `detail: {message, candidates: [{title, year}]}` — see `backend/api/routes/media.py:112`. The
   candidates carry **no id**, so "pick one" has nothing to re-request with. `_candidates()` in
   `request_media.py` flattens the provider's result to title/year only.

**So the honest options, for him to choose:**

* **(a) Nothing yet** — the phone keeps today's behaviour (Add → Download with the server's own
  message on failure). Zero code, and no control that lies.
* **(b) A sheet that shows what the server said** — the request's own sentence, and for a 409 the
  candidate titles as a READ-ONLY list ("2 titles matched — this app cannot choose for you yet"). Small
  client work, still no invented capability.
* **(c) Make it real, backend first** — carry an id (and ideally `tmdbId`) on each candidate and accept
  a chosen candidate id on the request path; then a pick-one list is actionable. That is a backend
  phase with tests, not a mobile phase.

Recorded rather than guessed: this is the first thing in M4 that the mobile work cannot settle by
itself, and it is his call which of the three it is.

⚠ **Second finding, same ground truth (checked while waiting on the decision): option (b) needs a small
CLIENT change too.** `ApiError` (frontend/src/lib/api/client.ts:357) carries only the server's `detail`
as a **string** — and for a 409 the server's `detail` is an OBJECT `{message, candidates}`. So today the
candidate list does not reach the browser at all: the error is raised with the client's own
`METHOD path -> status` fallback. Showing the candidate titles read-only therefore needs `ApiError` to
keep the structured payload (an additive field; the existing `detail` string behaviour stays exactly as
it is for every screen that reads it). Still no invented capability — but (b) is a client change plus the
sheet, not the sheet alone.

⚠ This also means the 409 currently reaches a mobile screen as a sentence a person cannot act on **and
cannot even read**: "POST /api/media/… -> 409" is not a sentence. Whatever is chosen, the 409's own
message should be shown — that much is a defect, not a preference.

---

## 7a · ✅ CLOSED 2026-09-19 — the Cancel defect, CONFIRMED FIXED ON HIS DEVICE

His words: *"cancel of an in progress works now"*. The entry is deleted rather than kept, per this
file's own rule; the two Swift defects and their fix are recorded in `PROGRESS.md` (session 6).

⚠ Worth keeping one sentence from the diagnosis, because it is the *class*: a native cancel returned
**silently** while the page was told nothing — the same shape as **#9** below. When a control is tapped
and nothing changes, the first question is whether the native side told the page at all.

---

## 8 · CLOSED 2026-09-19 — the three harness faults (records in `PROGRESS.md`)

All three are fixed, and **none of them was ever an app defect except the third**:

| Check | Was | Now |
|---|---|---|
| `tools/check_library_scan.py` G | one page shared across 7 navigations → sockets exhausted (`net::ERR_INSUFFICIENT_RESOURCES`), frame never ran, and G failed because it is LAST | fixed; 7/7, falsified both ways |
| `tools/check_item_modal.py` H | same cause (5 heavy navigations). ⚠ The recorded symptom had already MOVED to J — re-measure before repairing | fixed; 3 consecutive green runs; falsified via the dialog portal |
| `tools/check_touch_actions.py` watched | asserted a poster watched TOGGLE his accepted #2 rule deleted | **INVERTED on his decision** — it now asserts the toggle's ABSENCE, and `--selftest` proves a returning toggle goes RED |

⚠ **The lesson, kept because the next session will meet it again:** a check whose SUBJECT was deliberately
deleted must be inverted, not left failing and not quietly deleted — an inverted check is the only thing
that keeps a deleted control deleted. And a check that shares one page across many navigations fails on
whichever scenario runs last, so the failing scenario MOVES.

---

## 13 · The title screen — *"still zoomed: only part of the page is visible"*

**✅ FIXED IN PHASE W (2026-09-20) — AND THE FAULT WAS NOT ON THE TITLE SCREEN AT ALL: EVERY screen was drawn
in a box 9.1 % narrower than the design it was transcribed from.** `KNOWN_ISSUES` #13 was open from round 6
(`"THE WHOLE PAGE IS ZOOMED IN AND I CAN ONLY SEE A PORTION OF THE PAGE.. MAY BE IT'S A RESOLUTION ISSUE IN
DETAILS PAGE"`) through rounds 7–9, and the three attempted fixes before this one — the cast row's width, the
cast row's cap, and the focus default — were each a correct fix to a real defect that was not this one.

**The measurement, and the reading of it that round 9 got half right.** Round 9's file log said
`screen = 1760x960 pt at x=80 y=60`, and round 9 concluded *"nothing is off-screen and nothing is over-wide"* —
true of the box, and **the box was the bug**. Those 1760 × 960 are tvOS's **safe area**; every prototype this app
is built from is a full-screen page that indents by `4.2 %` of the screen itself (`4.2u` = set 2's `64px`). So
the app was applying a safe margin **on top of** a design that already has one:

| | arithmetic | result |
|---|---|---|
| the box his designs are drawn against | `1920 − 2 × 80.64` | **1758.7 pt** |
| the box the app drew them in | `1760 − 2 × 80.64` | **1598.7 pt** — **9.1 % narrower** |
| the title's first glyph | `80 + 80.64` | **160.64 pt** in, where his file puts it at **80.64** |
| the hero | `712.8` of a **960 pt** box | **74.3 %**, where his `66vh` means 66 % |
| ⇒ where `Play` landed | `932 of 960` | **off the bottom edge** — so the screen opened scrolled with its hero cut |

⚠ **Not one number in the token table was wrong.** `u` (19.2 pt) and `px` (1.26 pt) were always derived from
the 1920 × 1080 canvas; the canvas is simply what the screens were never given. **The fix is one
`ignoresSafeArea()` on the routing `ZStack` in `App/AppRootView.swift`**, plus the title screen's own rewrite to
his file's structure (`docs/TVOS_TITLE_SCREEN_PLAN.md`).

**His 4K question is answered by the layout being panel-independent:** tvOS gives every device the same
1920 × 1080 **point** space — a 4K Apple TV renders those points at `scale = 2.0` — so no screen needs a panel
check. **Artwork was the one exception** (the backdrop route's `1600 px` default is 2.4× short of a full-width
hero on 4K); `PosterURL.width(points:scale:route:)` now asks for 3840 px on a 4K panel and 1920 px on a 1080p
one.

**⚠ AWAITING HIS ROUND — what to check, in order (`TVOS_TITLE_SCREEN_PLAN.md` §6, W-F1…W-F7):**

1. **the whole page is on screen at once** — no clipped first letter, and the action row above the bottom edge;
2. **the hero reaches both screen edges** (no 80 pt gutter of near-black down either side) and the title block
   sits over its lower part;
3. `Play` is reachable, starts the film, and the arrows reach the top bar from it (round 8's own fix, still
   unconfirmed on his screen);
4. the bar **floats over** the hero and `Back` still leaves the screen;
5. the cast row is one row of round initials that fits;
6. the backdrop is **sharp** on a 4K panel;
7. **the app's own file log says `detail-size: screen = 1920x1080 pt at x=0 y=0`** — if it still says
   `1760x960 at x=80 y=60`, the double inset is back and this phase did not land.
   `find "$(xcrun simctl get_app_container booted com.helloraj1986.RKMCinemaTV data)" -name rkm-tvos.log`
8. **⚠⚠ AND W2's OWN FALSIFIER, WHICH IS THE SAME LOG: `detail-size: page`.** It must read **≤ 1080** — the
   page fits, so the cast row is on screen without scrolling. If it reads MORE, the fit is out and **one**
   constant moves: `Title.heroHeightFraction` (0.29), or `Metric.lineHeightRatio` (1.2) if every band is out by
   the same few percent. ⚠ The title page **cannot** be scrolled (every band below `Play` is information), which
   is why this is a fit and not a scroll.
9. **the Home's first screen: bar + hero + ONE whole rail + the top ~69 % of the next** — `HomeRules` computes
   exactly that. ⚠ **Three rails is not a tuning problem, it is impossible**: `3 × 389.4 + 2 × 38.4 = 1245.0` of
   rails in a `964.8` pt area before the hero is counted. Two whole rails need `Shelf.cardWidth` at ~`14u` (his
   cards are `19u`) — one token, offered and NOT taken.

**⚠ THE TRADE THIS ACCEPTS, AND IT IS THE ONE THING THAT COULD REOPEN THIS:** the design's margin is **80.64 pt**
from the panel edge and Apple's tvOS guidance is **90 pt**, so a television cropping more than 4.2 % of the frame
(older panels crop 2–5 %) can clip the outer edge of the margin. That is the same exposure his HTML has when a
browser draws it full screen, and the knob is **`Metric.safeMargin` — one number**.

---

## 16 · ✅ FIXED, AWAITING HIS ROUND — *"i can only see 1/3rd of the poster"*

His words, 2026-09-20: *"i can only see 1/3rd of the poster"*.

**The band had fallen back to the item's 2:3 POSTER and was drawn `fill` into a 1920 × 313 band.** The fallback
itself is correct — it is the WEB app's own chain (`PosterLoader.fallBackToPoster`: a missing 16:9 backdrop
becomes the poster, the one artwork every item has) — and it is what makes a title with no keyart show something
rather than a black band. **What was wrong is the drawing:** a 2:3 image asked to FILL a 6:1 band is scaled
until its *height* covers the band, which cuts **60 % of its width** — the middle third, exactly what he saw.

**⇒ `Core/PosterRules.swift` (new, pure, RUN on Linux): a portrait image in a landscape band is shown WHOLE over
a blurred, dimmed copy of itself** (`ArtworkTreatment.ambient`) — no crop, no black bars, and **no extra
request** (it is the bytes already in hand, drawn twice). Everything else fills as before: a 16:9 backdrop in a
16:9 band, a 2:3 poster in a 2:3 card, a square image, and an image whose size the platform did not report. Six
cases pinned in the harness and a mutation behind each direction of the predicate.

⚠ This also changes the **Home's** card and hero-band fallback for poster-only titles — the same treatment,
because it is the same predicate and the same defect shape. Recorded because it is a visible change to a screen
he had already accepted.

---

## 14 · The 4K question — *"so what happens now on 4k screen"*

His ask, 2026-09-20. **Two separate things, and only one of them is layout.**

**1 · The LAYOUT is panel-proof by construction, and that is a fact about tvOS, not a design choice.** tvOS hands
every device the same **1920 × 1080 points** — an Apple TV 4K draws those points at `scale = 2.0`. So a `0.29`
hero is 313 pt on a 1080p set and 313 pt on a 4K one (626 px vs 313 px); nothing reflows, nothing re-scales, and
every number in `TVTokens` is a percentage of the canvas rather than a pixel count. ⇒ **No screen needs a panel
check.** What IS panel-dependent is the *safe-area inset* (he measured `80/60` on the simulator; Apple documents
`90/60`; older panels crop 2–5 %), which W1 turned into one number: `Metric.safeMargin`.

**2 · ARTWORK was panel-dependent, and is now correct on the title screen.** The backdrop route's `1600 px`
default is the WEB app's number and is **2.4× short of a full-width hero on a 4K panel**;
`PosterURL.width(points:scale:route:)` now asks for `1920 × displayScale` — **3840 px on 4K**, 1920 px on 1080p,
clamped by the route's own 4000 ceiling. ⚠ **`Home/HeroBand.swift` still asks for the old 1600 px and is soft on
a 4K panel — a one-line follow-up, offered and NOT taken.**

**⚠⚠ 3 · THE OPEN ONE, AND IT WOULD MAKE *EVERYTHING* SOFT: IS THE APP IN 4K COMPATIBILITY MODE?** Apple's own
Apple-TV-4K guidance, verbatim: *"**the first step is to add a 2x launch image. Until you do so, tvOS is going to
run your app in compatibility mode**"* — i.e. the whole UI drawn at 1080p and upscaled, in which case a
correctly-sized 3840 px hero changes nothing. ⚠ **Measured against this repo (`Assets.xcassets`, 2026-09-20): the
catalogue carries `AccentColor` and the app-icon set ONLY — there is NO launch image of any kind, and the app
icon set has its `1x`/`2x` slots declared with NO image files in them.** The project also sets
`INFOPLIST_KEY_UILaunchScreen_Generation = YES` with `GENERATE_INFOPLIST_FILE = NO`, and that key is an **iOS**
one (`Config/Info.plist` even carries a note saying so).

⚠⚠ **SO THIS IS SETTLED BY MEASUREMENT, NOT BY ARGUMENT — the app now logs its own answer on every launch:**

```
display: scale=<n> — 2.0 = drawn at 4K (3840x2160 px of these 1920x1080 points);
                     1.0 = drawn at 1080p and upscaled, i.e. COMPATIBILITY MODE
poster|backdrop <id> -> 200, <bytes> bytes, …, w=<3840 on a 4K panel · 1920 on 1080p>
```

⚠ Read them from the FILE log (the HUD panel cannot be scrolled):
`find "$(xcrun simctl get_app_container booted com.helloraj1986.RKMCinemaTV data)" -name rkm-tvos.log`

**If `scale` reads 1.0 on his Apple TV 4K**, the fix is an asset change and NOT a layout one: a `LaunchImage`
(1x 1280×768 + 2x 2560×1536) — a black one matches the app's own `#08090B` void and is design-neutral — plus 2×
app-icon/top-shelf artwork, which is a branding decision and therefore his. **⚠ NOT done in this session: it
could not be verified from here, and the launch image is the first frame anyone sees.**

---

## 9 · The detail screen's **Download** button gives no feedback — but the download starts

> *"the download button when clicked … there is no feedback although download does start in the background
> where it appears in the watchlist … so this is kind of ui bug"*

**Reported 2026-09-19 from his phone, right after the §9 caption landed — so this is that same surface:**
the detail screen's action row, the `DownloadButton` tile, and the `DownloadNotice` caption under it.

⚠ **NOT INVESTIGATED YET, and no code was written** — by his instruction. What is already known, for
whoever picks this up:

* the caption (`DownloadNotice`, `data-testid="download-affordance"`) renders **only while there is no row**,
  deliberately (session 6 Part 4): with a row, the row's own status is meant to carry the mode. So if a row
  does not appear promptly, the caption disappears and **nothing on screen says a download began**;
* the row is **not optimistic** — it comes from native state through the bridge (`window.__rkmOffline` →
  `features/offline/session.ts` → `DownloadButton`/`DownloadsView`), and the page asks native for `list`
  rather than assuming. `OfflineEventPlanner` is the only thing that tells it anything changed;
* ⚠ **Confirm where he actually saw it** before assuming which surface failed: he says "the watchlist",
  which may mean the Downloads screen, the library, or Jellyfin — the three are different code paths;
* ⚠ Same class as the closed **7a**: native works, the page is told nothing. First question is not "why is
  the UI wrong" but "was an event emitted at all".

**Cheapest investigation when we take it up:** reproduce on the phone with the debug overlay on, filter the
console for `offline`, and read what the bridge emitted in the seconds after the tap — the overlay's `off`
line IS the downloader's own state, so page and device can be compared directly.

---
