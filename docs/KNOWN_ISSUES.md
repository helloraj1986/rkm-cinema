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

## 10 · tvOS Library grid — the focus ring did not enclose the card, and the bottom corners showed black squares

> *"when i hover over card by navigating, the yellow line should be covering the card, check the ux, also on
> the card on the bottom left and right i can see square shape black background corners possibly coming from
> the backgroound color check that as well"*

**FIXED 2026-09-20 on `feat/tvos-ux` (`accda68`) — awaiting his eye.** ⚠ **One cause, two symptoms**, and both
are visible in a zoom of his own screenshot:

* `Browse/LibraryGridCard.swift`'s `LibraryCardStyle` applied `.scaleEffect` **before** the ring overlay, so the
  ring was drawn on the **unscaled** label while the card grew to `1.14` *out of* it — the artwork and the
  caption stuck out past the ring on every side, worst at the bottom. His CSS has it the other way round: a
  transform scales the element **and its box-shadow**. ⇒ the ring and the shadows now sit inside the transform;
* the caption's scrim is a `Rectangle` and was an `.overlay` on a view that had **already** been clipped, so its
  square corners landed on the artwork's rounded ones. ⇒ one `clipShape` now closes over art **and** caption —
  his own rule (`border-radius` + `overflow:hidden` on the card).

⚠ Recorded in `PROGRESS.md`; **not yet confirmed on his screen**, so it stays here until he says so.

## 11 · tvOS Library grid — after picking a genre, Down cannot reach the titles

> *"when i filter by cliking on any tags, it rightly filters the titles but then i cant come to the titles by
> pressing down arrow on my keyboard...it satys on the tag itself, i can move between the tags but cant select
> the titles. i can select the titles only when the all tags is being selcted"*

**OPEN — cause NOT proven, and deliberately not guessed at. One change made, offered as a hypothesis.**

What is known, and what discriminates:

* the chips row and the grid are both live — with **All** selected he reaches the cards and their focus ring
  draws (his own screenshot is that state), so the cards ARE focusable in this structure;
* the condition is the **filter**: filtering is exactly when the grid's content becomes **shorter than the
  viewport**. With All (140 titles) the wall is 8+ rows; with a genre it may be one or two;
* so the ONE structural difference between this grid and the app's **working** pattern (the Home's rails, where
  Down into a shelf works) was a `GeometryReader` wrapped around the focusable, **lazily** laid-out grid. A
  `LazyVGrid` decides which rows to materialise from the size it is **proposed**; a `GeometryReader` reports its
  size only after layout. ⇒ **the reader is gone** (`accda68`): the card width now comes from
  `TVTokens.u * 100` — the canvas is 100u wide by the definition of `u`, so no measurement was ever needed, and
  the harness pins that identity.
* ⚠⚠ **If Down still cannot enter the grid after this, the reader was not it.** The next step is NOT another
  blind change: it is a **screenshot of the filtered state** (does the grid render? is it the empty state? how
  tall is it?) plus one answer — **does a second Down press a moment later work?** (a stale focus-candidate
  list behaves that way; a layout problem does not).

