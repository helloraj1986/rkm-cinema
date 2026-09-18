# Known issues — open defects, in his words

## ▶ STATUS AFTER HIS 2026-09-17 ANSWER ROUND — read this first

He answered every open item. What that means for this file:

| # | His answer | State |
|---|---|---|
| 1 | Reproduced on device: the ⋯ and Watched DO work, but **the Watched control shows no state and no feedback on tap** | **Half closed** — `features/library/WatchedAction.tsx` now says `Unwatched`/`Watched`, shows `Saving…` while in flight, and `useMutateItemState` toasts the server's sentence on failure. His device round confirms. ✔ **Re-measured 2026-09-18 (session 3):** the tile renders state-labelled at 320/390/430 (`tools/check_detail_mobile.py`, falsified) — the headless half is now evidence, not an assumption; ⚠ the TAP feedback still needs his phone. |
| 2 | **Rule decided:** the details view OWNS the watched control; the poster only reflects status — so the poster shows ONE tick | **CLOSED 2026-09-18** — landed. `MediaCard`'s toggle button and its ⋯ `Mark as watched/unplayed` item are gone (`onToggleWatched` deleted, not left optional), the tick MARKER stays, and the ⋯ row is right-aligned now that it has one child. The six call sites dropped the prop. Pinned by `tools/check_poster_watched.py` (one watched indicator per played poster, no watched control, no watched verb in the menu), and the harness probe was FIXED mid-way because it knew only the word "unwatched" while the removed control said "unplayed" — the falsification caught that, not a review. |
| 3 | **Corrected:** Settings is fine — the sideways scroll is on the **Switch Profile** view | **FIXED** — measured cause: the picker's nowrap subtitle (348px / 494px of min-content) floors the `place-items-center` grid track through the grid item's `min-width:auto`, so `scrollWidth` was 416 (picker) / **562 (Switch Profile)** at *every* width from 320 to 430. One token, `min-w-0` on the picker container, closes it to 0 and lets the subtitle ellipsise. ⚠ The root `overflow-x: clip` guard did not fix it — it was applied and the document still scrolled the full 172px. |
| 7 | NEW: **Cancel does nothing on an in-progress download** | **FIXED IN SOURCE (2026-09-18) — needs his device round.** Two Swift defects closed in `OfflineDownloads.swift`: a cancel during the packaging window now records the INTENT, marks the row `paused` and makes the run abandon instead of starting a task; and a real cancel's `NSURLErrorCancelled` branch now writes `.paused` (guarded `!= .ready`, so a Cancel at 99% cannot un-finish a whole file), which gives the planner a state to emit and flips the page's Cancel → Resume with no JS change. ⚠ Typecheck gate PASS (`apple/scripts/check-apple-typecheck.sh`), but that proves types and call shapes, **not behaviour** — no Mac, and nothing anywhere taps Cancel. See §7a for the log lines that decide (A) vs (B) on his phone. |
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

## 7a · The **Cancel** defect (§7's neighbour, different feature) — diagnosed, fix not yet landed

His report: *"Tapping Download on a title shows the circular progress indicator with a Cancel control,
but Cancel has no effect — the download continues and the UI state doesn't change."* Diagnosed
2026-09-17 by reading the whole chain, top to bottom.

**The WEB half is correct — do not go looking there.** `actionsFor(row)` returns `["cancel","delete"]`
for a downloading row (`offline/lib.ts:428‑441`), the tile calls `cancelTitle(itemId)`
(`DownloadButton.tsx:175`, ring at `:179‑181`), which goes through `session.ts:321‑325` →
`bridge.ts:122‑124` → `window.__rkmOffline.cancel(itemId)`, which the injected JS defines at
`OfflineBridge.swift:128` and routes to `perform()` (`:272‑290`) → `case .cancel:` (`:326‑337`) →
`downloads.cancel(itemId:)` (`OfflineDownloads.swift:510‑516`).

**Two defects, both in `OfflineDownloads.swift`:**

* **(A) line 511** — `guard let identifier = taskIdentifier(for: itemId) else { return }`. The task id is
  only written in `beginTask` (`:494`), but `plan()` publishes the record as **`.downloading`**
  (`:401‑405`) *before* `ensurePackaged` (`:412`, poll loop `:444‑459`, which can run for minutes). In
  that window the page offers a Cancel tile and there is **nothing to cancel** — the pipeline proceeds
  to `beginTask` and the download runs to completion. ⚠ And it returns **silently**: no log line, no
  state change, nothing for the page to notice.
* **(B) lines 1031‑1052** — when a task IS cancelled, the `NSURLErrorCancelled` branch logs
  `offline task cancelled (task N)` and **returns without writing `.paused` to the store**. The `defer`
  then calls `publish()`, which rebuilds from `store.records` — still `.downloading`. So
  `OfflineEventPlanner.decide` returns `.nothing`, the page is told nothing, and the Cancel tile and its
  frozen ring stay exactly as they were. The two sibling paths that DO write paused are
  `finishAsIncomplete` (`:1092‑1096`) and `handle` (`:804‑811`, `:822‑826`); `pause(record:)` (`:760‑767`)
  exists and is never called from the cancel path. **Delete only *looks* like it works** because it
  removes the record, which does change state.

**Which one is he hitting? One log line decides it** (his phone, no rebuild): tap Cancel while the ring
is climbing, then read `Library/Application Support/RKMCinema/Logs/rkm-ios.log`:
* neither `offline download cancelled by the user` (`:515`, below the guard — so its absence is the
  tell) nor `offline task cancelled (task N)` (`:1049`) → **(A)**, the packaging window;
* both present, row still "downloading" → **(B)**;
* row becomes `paused — resumable` → the claim is FALSE and this diagnosis is wrong.
Second-cheapest, no logs at all: after a Cancel that appears to do nothing, relaunch the app — if the
row only THEN becomes paused, the claim holds (`restore()` at `:616‑630` marks orphaned `.downloading`
records paused).

**The fix, when he authorises it:** (1) record the cancel intent so `run()` abandons after
`ensurePackaged` instead of starting `beginTask` — fixes (A); (2) in the `NSURLErrorCancelled` branch
write `state = .paused` + the partial bytes + a sentence, then `publish()` — the same write
`finishAsIncomplete` already performs, which fixes (B) and needs **no JS change**: `decide` then emits
`.state` and the page flips Cancel → Resume by itself. ⚠ The paused-write MUST be guarded "only if the
record is not already `ready`", or a Cancel tapped at 99% races `didFinishDownloadingTo` and turns a
whole file into "paused" (the same class of bug already documented at `:733‑743`).

**⚠ And it could not be verified here**, which is why it is not landed: no Mac/Xcode in the sandbox, no
Swift compiled or run, and nothing anywhere taps Cancel. Specifically:
* `offline/lib.test.ts` (34 tests) — the only cancel-related case asserts `actionsFor` RENDERS the
  control, never that a bridge call is made; no test under `frontend/src` references `__rkmOffline`.
* `tools/check_offline_page.py:183` asserts only `"Cancel" in buttons`; its six scenarios tap Download
  and Play, never Cancel.
* `tools/check_offline_download.py` (the on-device log gate, 654 lines) has no cancel pattern — so the
  B2 gate is structurally blind to this defect.
* The harness stub can't express a cancel at all: `offline-frame.tsx:148‑151` pushes `{c:"cancel"}` and
  resolves, stopping no timer and emitting no `state` event. **A stub that can say "the item is now
  paused" is the prerequisite for any off-device regression test of this.**

---

## 8 · Harness checks not clean at HEAD — TWO FIXED 2026-09-19, the third is his decision

Found 2026-09-18 by running the neighbouring browser checks after the poster-watched sweep. **Both were
measured against a STASHED tree (i.e. at `bedfd67`, with the sweep absent), so neither was caused by it.**

⚠ **Both of the first two turned out to be TOOL-SIDE, not app defects — and both are now fixed**
(2026-09-19, session 6; full record in `PROGRESS.md`). The app behaviour those scenarios assert was
correct all along — measured, not assumed. They are kept here with their outcome, because the *lesson*
is what the next session needs: a check that shares one browser page across many heavy navigations
fails on whichever scenario runs LAST, and moves on the next run.

| Check | Scenario | State |
|---|---|---|
| `tools/check_library_scan.py` | G — `?signedout=1` | **FIXED 2026-09-19.** Not the app: seven navigations on ONE page exhausted the browser's sockets (`net::ERR_INSUFFICIENT_RESOURCES` measured on the module requests), `library-frame.tsx` never executed, `window.__probe` was never defined — and G is LAST, which is why G was the scenario that died. Now a fresh page per scenario, and a readiness failure is REPORTED instead of crashing the run with a traceback. G's assertions run for real and PASS (7/7). Falsified: gate mutated to `return true` → C, D, E, G RED; unloadable frame → 9 named problems, exit 1, no traceback. |
| `tools/check_item_modal.py` | H | **FIXED 2026-09-19 — the recorded symptom had already MOVED.** Re-measured at HEAD: **H passes** and the failure was now **J** (`the library view never rendered`). Same cause: five heavy navigations on ONE page; the failing scenario moved between runs (J one run, H the next, `Page.goto: Page crashed` on a third) — which is the whole of the "at least partly flaky" note. Fixed the same way; **3 consecutive green runs**; falsified by removing the dialog's body portal → J RED with the exact geometry (`above: True`, scrim `2320x63`), and `--expect-broken` reports *"OK (falsified as expected): 2 problem(s) with the fix absent"*. |
| `tools/check_touch_actions.py` | phone, `watched` target | **OPEN — his decision**, unchanged. The tool still asserts the poster's watched TOGGLE (`button[aria-label^="Mark as"]`), which the **accepted #2 rule deleted**: the details view owns the watched control and the poster only REFLECTS status (`features/library/MediaCard.tsx`, `tools/check_poster_watched.py`). **STALE, not a regression.** The fix is one line — drop the `watched` entry from `TARGETS`, or invert it to assert the toggle's ABSENCE — but which one states what the phone's poster actions now ARE, so it stays his call rather than being quietly rewritten. Its other scenarios (`cta`, `menu`, `compact_row`, the desktop hover direction) pass. |

⚠ **A THIRD failing check was found by the same method in the same session — and that one was NOT
tool-side.** `tools/check_offline_page.py` scenario 2 was RED because the app had genuinely lost the
pre-commit size/rendition label (plan §4.6). He chose to RESTORE it (2026-09-19), it is fixed, and the
record — with the diagnosis — is in `PROGRESS.md`. The check is GREEN again, and it no longer anchors on
"any `<span>` in the panel": it addresses the affordance element by its own `data-testid`, because the
loose probe is what let a whole requirement vanish unnoticed.
