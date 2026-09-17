# Known issues — open defects, in his words

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

## 2 · Marking watched from a poster shows **two green ticks**

> *"on the poster when you click the right tick button (i think its for watched) there are two green
> ticks and then the button inside (details page) watched button becomes redundant"*

**Mechanism — already located, not yet fixed.** In `features/library/MediaCard.tsx` the played state is
drawn **twice**:

* `line 47` — the poster's status MARKER: `if (marker.kind === "watched") return <WatchedTick />` (the
  tick on the art, driven by `item.played`);
* `line ~196` — the bottom action row's watched TOGGLE, whose own state is also `item.played`.

Mark a title watched and both light up at once — two ticks for one fact. ⚠ The redundancy he names on
the DETAILS page is the same shape: the same fact is offered as a control in three places (card
marker, card toggle, details tile).

**Decide the rule first, then change code.** The question is not "which tick to delete" but **which
surface OWNS the watched state**: the marker is status (read-only, always visible), the toggle is
control (act on it), and a control should not look identical to a status. Likely answer: the marker
stays as STATUS on the art; the toggle keeps a neutral resting look and only shows its own "done"
state on press — but this is his call to make, not mine to assume.

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

## 7 · M4's **RequestSheet** cannot be built truthfully until one of these changes — his call

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

