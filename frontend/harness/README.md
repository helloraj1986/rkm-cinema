# Player layout harness (sandbox, not shipped)

The in-app player's job is to fit a *viewport*, and the sandbox has no Docker /
Jellyfin to play a real movie against. This harness mounts the **real** `<Player>`
component with a stubbed API so the layout can be measured in a real browser.

Nothing here ships: `vite build` only builds `/index.html`, so these files are inert
in the web image. They exist so that "the controls fit the screen" is a number, not
an opinion — see `docs/PLAYER_LAYOUT_PLAN.md` §1.

## Run it

```bash
cd frontend
npx vite --port 5199 --strictPort &          # dev server (harness is served from /harness/)

# optional: a real 16:9 file so the <video> reports genuine intrinsic dimensions
curl -sSL -o public/harness-sample.mp4 \
  https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4

cd .. && python3 tools/measure_player_layout.py --shots /tmp/shots
```

⚠ **Restart the dev server after editing app source.** Vite's watcher does not fire on
this mount (WSL2/Docker), and an orphaned `vite` holding port 5199 keeps serving the
pre-edit module — the measurement then reports the OLD layout and looks like your fix
did nothing. Check before trusting a run:

```bash
pgrep -f "[b]in/vite" | xargs -r kill -9   # ⚠ NOT `pkill -f "vite --port 5199"` — see below
cd frontend && npx vite --port 5199 --strictPort &
curl -s http://localhost:5199/src/features/playback/Player.tsx | grep -c rkm-player__dock
```

⚠ **The `[b]` is not a typo.** `pgrep -f "bin/vite"` matches its OWN command line — the pattern is in
it — so the kill lands on the shell running the command (exit 137) while looking like it worked. The
bracket form makes the pattern not match itself. Same trick for any `pkill -f` you write here.

⚠⚠ **THE RESTART IS THE TRAP, AND `pkill -f "vite --port 5199"` DOES NOT DO IT.** That pattern matches the
*npm wrapper* and the *sh* it spawns, so it kills those and leaves the `node …/bin/vite` child alive and
holding the port; a new `npx vite --strictPort` then **exits with code 1**, and the OLD process keeps
answering — with the pre-edit module still in its in-memory graph, because the watcher (above) never
invalidates it. Measured cost, 2026-09-17: a harness frame that should have answered 713 rows kept
answering **1**, and a "before" measurement read as if the app rendered nothing. ⚠ `--strictPort` is not
a guard against this; it only tells you the port is busy if you read the exit code.
**Kill the `node` process, then prove the SERVER is fresh by reading the module you just edited** — a new
file is served fresh even by a stale server, so read one you CHANGED, not one you added.

`tools/measure_player_layout.py` prints a PASS/FAIL table for 10 device sizes and
exits non-zero if any viewport fails. It asserts: the shell == the viewport, the dock
is fully inside it, nothing pokes outside, the transport row never clips its own
content, every rendered control is ≥32px and on-screen, the header policy matches the
viewport height, and (with `--fullscreen`) that real element fullscreen still leaves
the shell == the screen.

## What it stubs

| App call | Harness answer |
|---|---|
| `GET /api/jellyfin/playback-info` | mp4 / h264 / 960×540 + 1 audio + 1 subtitle track → `direct` mode |
| `GET /api/jellyfin/progress` | `{ ok: true }` |
| `GET /api/jellyfin/subtitle` | a 20 s WebVTT cue (exercises the subtitle overlay) |
| `GET /api/jellyfin/backdrop` | 404 (seeded-art / no-image path) |
| media URL (`/api/jellyfin/stream/...`) | rewritten to `/harness-sample.mp4` when present |

Query params: `?kind=series|movie` (movie = no episode queue), `?src=<url>` to point
the media element somewhere else.

`window.__probe()` (defined in `player-frame.html`) returns the measurements the tool
asserts on: shell / video / dock / row rects, `100dvh`, document scroll size, and every
element that pokes outside the viewport.

## Sign-in flow harness (`login-frame.html`)

`tools/check_login_flow.py` drives the SESSION rules in a real browser, mounting the real
`AuthProvider`, `RequireSession`, `LoginView` and `Header` over a stubbed api (the app's own
pages are not involved — a fake Home stands in, because Phase 1 changes none of them):

| Scenario | What it proves |
|---|---|
| `?enforce=0&signedIn=0` | Phase 1's world: the app renders SIGNED OUT, the bar offers Sign in, a wrong password shows the generic error **without** signing the app out, a correct one lands signed in — and (Phase B) on **"Who's watching?"**, which must then be answered before the app appears |
| `?enforce=1&signedIn=0` | the server refuses app calls ⇒ the login view, and app content **never appears** (asserted with a MutationObserver, so enabling enforcement cannot flash the shell before bouncing you out) |
| `?enforce=1&signedIn=1` | a valid session is left alone by the guard |
| blank password (scenario D) | a Jellyfin account with **no password** can sign in — the form must not block an empty submit (a `required` field silently made such accounts unusable) |

The stub is SESSION-AWARE: enforcement refuses only an unsigned caller — and a BLANK password
authenticates, because a household account can legitimately have no password. A cruder stub that
refused everything (or one that refused blank passwords) made a correct app look broken during
development; if a scenario fails, check the stub before the app.

`window.__probe()` and `window.__authCalls` expose what rendered and every stubbed call.
⚠ **Restart the dev server after editing app source** (the same watcher trap as above): a
stale module gave a false FAIL here until the vite PID holding :5199 was killed.

## `household-frame.html` — the Household screen (Phase 1b, redesigned 2026-09-13)

`python3 tools/check_household_ui.py` mounts the REAL `HouseholdView` + its modals (plus the real
query client and auth provider) over a stubbed api and drives it in a browser. Eight scenarios, and
they are the acceptance list of the redesign (HOUSEHOLD_UX_PLAN §3/§5) rather than a smoke test:

| Scenario | What it asserts |
|---|---|
| A `?admin=1` | the four layers render: the header (eyebrow + his copy + Add member), the **summary counts** (3 members / 2 active / 2 libraries, derived from the payload), and the cards (badges `YOU`/`ADMINISTRATOR`/`DISABLED`/`NO PASSWORD`, chips, "Never signed in"); **your own card has NO ⋯ menu and says why** |
| B `?admin=0` | a non-administrator session sees the requirement stated plainly — no cards, no add modal, and **no write is attempted** |
| C | the **Library access modal**: a subset posts exactly the ticked ids; the chip AND the summary card follow the SERVER's next answer; and ⚠ "Every library" posts the **full id list**, never `[]` (the trap the inline form had — see below) |
| D | the **password modal**: a mismatch is refused **before any request**, the title matches the button that opened it, and a match sends only `{new_password}` |
| E | **Rename** from the ⋯ overflow: the rails refuse an unchanged or duplicate name with **no request sent**, the write carries only `{name}`, and an ordinary member never gains the role |
| F | **Remove** from the ⋯ overflow: only the exact typed name arms the button, and the DELETE carries it |
| G | the **Add member modal**: every library ticked by default, and a **blank password** + only the ticked folders reach the API |
| H | the **modal contract**: Tab cannot leave the dialog (focus trap), Escape closes it, a backdrop click closes it, and closing writes nothing |

`window.__calls` records every request (url, method, body) and `window.__probe()` reports the cards
(badges, chips, buttons, whether the ⋯ exists), the three summary values, which modal is open, its
title and text, where focus is, and any `role="alert"` text.

Four things this frame learned the hard way:

* ⚠ **The stub must read a `library_ids` write the way the SERVER does.** `POST …/policy` passes the
  list straight to `set_folder_access(ids)`, whose `enable_all` defaults to **False** — so `[]` means
  **NO libraries**, not "every library" (the request model's own docstring: *None* = every, *[]* =
  none). The frame mutates the fixture from that rule, so scenario C catches the `[]` bug instead of
  hiding it, and the chip honestly reads the granted NAMES after an "Every library" save (the route
  has no way to express `EnableAllFolders=true`).
* ⚠ **The stub must answer `403` to a non-administrator** for `/api/admin/users` and
  `/api/admin/libraries` — a kinder stub makes a broken screen look correct, which is this repo's
  most expensive repeating bug.
* `/api/auth/profiles` carries the **server's own row** for the profile in effect (`current` with
  `is_admin`), because the header's account menu gates Household on it.
* Give a probe a **testid, not a class**: the first version read the chips with
  `span.rounded-full` and picked up the avatar circle (whose text is the person's initials), so
  every chip assertion was off by one element. The chips carry `data-testid="library-chip"` now.

⚠ **Restart the dev server after editing app source.** This mount's vite watcher does not fire, and
an orphaned server keeps serving the PRE-EDIT modules — that cost a whole run here (four failures
that were already fixed on disk). Check before believing any result:
`kill -9 $(ss -ltnp | grep 5199 | grep -oP 'pid=\K[0-9]+')`, start one vite, then
`curl -s http://localhost:5199/src/features/admin/HouseholdView.tsx | grep -c 'summary-members'`.

## `poster-watched-frame.html` — WHAT A POSTER MAY SAY ABOUT WATCHED STATE (2026-09-18)

His rule, from `KNOWN_ISSUES` §2: *"on the poster when you click the right tick button (i think its for
watched) there are two green ticks and then the button inside (details page) watched button becomes
redundant"*. One fact was drawn twice on one card — the tick MARKER on the art and a green TOGGLE in the
bottom row, both driven by `item.played`.

**The details view owns the watched control; the poster only REFLECTS status.** `python3
tools/check_poster_watched.py` mounts the REAL `MediaCard` three times (a played film, an unplayed film,
a played series — BOTH states on purpose, or "the marker follows `played`" cannot be told from "the
marker is always drawn") and asserts the rendered shape:

| Assertion | What it means |
|---|---|
| A | the frame really rendered — three cards, art and a ⋯ trigger on each (else "no toggle" is true of a blank page) |
| B | a played card draws the fact ONCE: `markers + toggles == 1`, and exactly one marker |
| C | **no** card draws a watched CONTROL (`Mark as watched` / `Mark as unplayed`) |
| D | the ⋯ menu offers no watched verb, and still offers Replay + View details |
| E | an unplayed card shows no marker |
| F | the marker is INSIDE the artwork (status on the poster, not a control in the action row) |
| G | the ⋯ trigger is at the row's RIGHT edge — the row lost its left-hand child, so `justify-between` would silently move the menu left |

⚠ **Falsified against the pre-fix source**, and the first attempt was NOT good enough: run with the old
`MediaCard` restored (plus a frame that passes `onToggleWatched`) it reported **6 problems**, including
B on both played cards — *"draws the watched fact 2 time(s) — 1 marker + 1 control"*, the report
verbatim. ⚠ Before that, the probe matched only the word `unwatched`, while the REMOVED control said
**`Mark as unplayed`** for a played title — so it was blind to the duplicate on exactly the played card
the report is about, and only the unplayed fixture came back red. Match the verb, not one spelling.

⚠ Both TMPDIR traps apply here, in opposite directions: `swiftc` must build in `~/tmp`, but Chromium
refuses to launch when `TMPDIR` points at `/root` (SIGTRAP, *"Target page, context or browser has been
closed"*). Run playwright checks with `TMPDIR` unset.

## `nav-frame.html` — navigation access + the account menu (2026-09-12, reworked 2026-09-13)

`python3 tools/check_nav_access.py` mounts the REAL `Header`, `Sidebar` and `MobileNav` over a
stubbed api and proves the account destinations are offered to **administrators only**, from **every
trigger**, while the nav carries no duplicates:

| Query | What it proves |
|---|---|
| `?admin=1` | the account menu — opened from the header avatar AND from the sidebar footer — offers **Household · Account & password · Switch profile · Settings · Sign out** (the mockup's order, and the sidebar NAV no longer lists the first two) |
| `?admin=0` | both triggers still offer **Account & password** and **Settings**, and **neither** offers Household |
| `?admin=0` | the navigation fires **zero** `/api/admin/*` calls |
| `?admin=1` | the mobile sheet is **navigation only** (both account screens moved into the menu) |
| `?admin=1` | the phone reaches both screens from the header avatar, and the menu fits the viewport |

⚠ The entry was called **My password** until 2026-09-13, when the redesign (HOUSEHOLD_UX_PLAN §2)
renamed it **Account & password** — his mockup's label, same destination (`/settings/password`).
`Settings` joined the menu at the same time; the route is session-scoped, not administrator-only,
so the check asserts a member is offered it too.

Three things this frame learned the hard way:

* **It never loaded the app's stylesheet** (2026-09-13). Everything above passed anyway — visibility
  is asserted by TEXT — but every screenshot and any geometry measurement of this frame was
  *unstyled*: the account menu measured full-width, and the mobile "More" button was clickable at
  1280px where CSS hides it. It now imports `../src/styles/index.css` like the other frames, and the
  check uses a **phone viewport** for the mobile surfaces.
* **The stub must send what the server really sends.** While `current` was a name-only row
  (`is_admin` always false), the gate hid Household from the ADMINISTRATOR too, and this frame
  reported green because it invented an `is_admin` the server could not produce. `current` here IS
  the profile's row now, mirroring `/api/auth/profiles` (pinned by
  `TestProfiles::test_the_current_profile_carries_the_SERVERS_own_answer`).
* The account menu is **portalled to `<body>`**, so `window.__probe()` picks it out by excluding the
  mobile sheet's `role="menu"`.

## `library-frame.html` — the library scan control (Phase E, 2026-09-13)

`python3 tools/check_library_scan.py` mounts the REAL `LibraryLayout` + `LibraryHomeView` +
`LibraryFolderView` and proves the rule Phase E put on the scan: **the app must not OFFER what the
server refuses.** `GET /api/library/scan` and `POST /api/jobs/{name}/run` are
`require_admin_session` — strict *even while* `RKM_AUTH_REQUIRED` is false — so a member's "Scan
Library" button answers 403 on today's stack.

| Query | What it asserts |
|---|---|
| `?admin=1` | the hero's scan control is **present** (the wiring, not just the rule, is under test) |
| `?admin=1&empty=1` | the empty state's scan button is present — the path where it is the only action there is |
| `?admin=0` | **no** scan control, and **zero** `/api/library/scan` calls |
| `?admin=0&empty=1` | no button, and the reason is stated instead ("Scanning is an administrator action") |
| `?admin=0&folder=1&empty=1` | the folder view's own copy of the control is gated the same way |
| `?admin=1` + click | exactly **one** `/api/library/scan` call — hiding the control must not be the fix |
| `?signedout=1` | the library still renders (the reads answer) and the control is still absent: the route refuses a 401 caller too |

`?admin`/`?empty`/`?folder`/`?signedout` also drive `nav-frame`'s conventions: `current` IS the
profile's own row, and the library reads answer normally even when signed out, because the point of
the signed-out scenario is that the VIEW renders and offers nothing.

### ⚠ Four traps this frame and its check found (2026-09-13) — read this before trusting a run

1. **A STALE dev server makes the check pass on a BROKEN build.** Vite's watcher does not fire on this
   mount, and an orphaned `vite` still holding port 5199 kept serving the pre-edit `LibraryHomeView`:
   the deliberately-broken build reported **OK: every scenario passed**. Before believing any run,
   confirm the module the server is serving is the one on disk:
   `curl -s http://localhost:5199/src/features/library/LibraryHomeView.tsx | grep "mayScan = "`.
2. **`process kill` on the background wrapper does NOT stop vite.** `nohup` + a subshell leave the
   `node` process alive, so the "restarted" server silently fails to bind (`--strictPort` exits 1)
   while the OLD one keeps serving. Kill the process that owns the port: `ss -ltnp | grep 5199`, then
   `kill -9 <pid>`.
3. **Do not `pkill -f "vite --port 5199"` from a shell whose own command line contains that string** —
   the pattern matches the calling shell and kills it (exit 143 / 137), which looks exactly like a
   successful restart. Use `pgrep -f` and skip your own PID, or kill by port owner.
4. **A readiness gate must not raise.** The first version waited on `/api/auth/profiles` with a bare
   `wait_for_function`, so a build where the wiring was removed (and with it the
   `useCurrentProfile()` call) died on a `TimeoutError` traceback instead of reporting what was wrong.
   `_wait_for` now records a clean FAIL, and readiness additionally asserts the view really rendered —
   otherwise "the control is not offered" is true of an empty page, which is the definition of a check
   that cannot fail.

## `password-frame.html` — Settings → My password (Phase 3)

`python3 tools/check_password_change.py` mounts the REAL `PasswordView` (inside the real
`AuthProvider` and query client) against a stubbed api which — like `household-frame` — is
faithful about the one thing that would make a correct screen look broken: a Jellyfin account with
**no** password accepts anything, and a 401 is about the CURRENT password only.

| Query | What it proves |
|---|---|
| *(default: `has_password=1`)* | the current password is required; a blank one or a mismatch is refused **before any request**; the good case sends exactly `{current_password, new_password}` and says it changed |
| `?has_password=0` | a password-less account can set one with the field blank — the case that must never be blocked |
| `?refuse=wrong` | a 401 reads as "that current password is not correct", and echoes neither value |
| `?refuse=server` | a 502 is NOT reported as a wrong password — the server's own words are shown |
| `?refuse=silent` | a 502 with **no body** still gets our own wording ("your old password still works"), never `POST /… -> 502` — the bug this frame caught |

## `profile-frame.html` — "Who's watching?" (Phase B)

`python3 tools/check_profile_picker.py` mounts the REAL `ProfilesView` (plus the real `AuthProvider`,
`RequireSession` and `Header`) over a stubbed api and drives six scenarios:

| Query | What it asserts |
|---|---|
| `?signedIn=1&profileSelected=0` | the picker IS shown and **app content never appears** (MutationObserver); a lock only where the server needs one — including an administrator with NO password of its own; the disabled row is inert (even to a programmatic click) and says why; no row claims "Watching now"; **zero `/api/admin/*` calls** |
| …then pick `uid-guest` | a password-LESS profile posts `{"user_id":"uid-guest","password":""}` and lands as `Watching as Guest` |
| …then pick `uid-locked` | the prompt appears with **0 requests sent**, a blank attempt and a wrong one both answer the generic message, the right one lands |
| …then pick `uid-owner-nopw` | the administrator's profile asks even with no password set (the server refuses a blank attempt on it) |
| `?signedIn=1&profileSelected=1` | straight into the app, picker NOT shown; the header's **Switch profile** (`/profiles?switch=1`) brings it back with the current profile marked |
| `uid-off` | a disabled profile is not selectable and clicking it makes no call |

⚠ The stub must mirror the SERVER's refusals: a blank attempt on the administrator's profile is
401, a disabled profile is 403, and a password-less profile accepts an empty one. A kinder stub makes
a correct picker look broken.

The stub's own `me()` must keep reporting `profile_selected` honestly — that flag IS the picker's
trigger, so a stub that always said `true` would prove nothing about this screen.

## The brand lockup (2026-09-13) — `nav-frame.html`, checked by `tools/check_brand_lockup.py`

His report: *"RKM Cinema text on top left is not perfectly aligned with the icon"*. It was a real
offset, and a **font-dependent** one: a line box carries its font's ascent/descent and uppercase type has
no descenders, so a box-centred two-line stack leans by `(ascent − capHeight − descent) / 2` — about
1.2px LOW in Segoe UI (what his Windows box renders, since the app ships no webfont) and ~0.3px high in
DejaVu Sans (what this headless sandbox falls back to). The fix is `text-box-trim: trim-both` +
`text-box-edge: cap alphabetic` on the text block, which trims the box to the CAP ink so
`items-center` centres the letters in **any** font.

`python3 tools/check_brand_lockup.py` uses THIS frame (it mounts the real `Sidebar`) and asserts, at
1440px where the brand text is visible:

| Assertion | What it means |
|---|---|
| A | the play glyph is centred inside its rounded square (within 0.75px) |
| B | the two-line text's cap ink is centred on the mark (within 1px — the analytic method's own uncertainty) |
| **C** | ⚠ **the trim must MOVE the geometry** (≥ 0.2px): the same measurement with `text-box-trim: none` forced, across four installed font stacks |
| D | the trim is really applied (computed style, and the block IS shorter trimmed than untrimmed) |

⚠ **C is the assertion that matters.** "Is it centred?" alone passes in a favourable font with the fix
absent, which is the classic check-that-cannot-fail. Falsified: deleting the two utility classes turns
the run into 6 failures / exit 1 (*"the trim moves it 0.00px — the CSS is missing or has no effect"*).

⚠ And `document.fonts.check('16px Inter')` returns **true even when Inter is not installed** (it only
reports that there is nothing to *load*), so it cannot tell you which font is rendering — the canvas
metrics can (`ascent+descent = 1.200em, cap = 0.733em` is DejaVu Sans, not Inter).

## `cta-frame.html` — the card CTA and the search action pair (2026-09-13)

His report, two defects on two high-visibility surfaces: the poster's **"▶ Episodes"** pill rendered the
glyph ABOVE the label, and the search row's **Resume**/**Details** pair rendered at two different
heights. `python3 tools/check_cta_alignment.py` mounts the REAL `MediaCard` (a series card and a movie
card) and the REAL `GlobalSearch` over a stubbed api and measures RECTS — because neither cause is
visible in the source:

* the pill was `grid place-items-center` with **two** children, so grid laid the glyph into row 1 and
  the label into row 2 — and ⚠ the pill's height is FIXED (`h-9`), with the two stacked rows still
  fitting inside it, so **nothing overflowed** to give the mistake away (box right, insides wrong);
* the pair were two hand-rolled class strings that had drifted — the primary `h-8` with no vertical
  padding, the secondary `py-1.5` with no height; their difference is the font's line-height, i.e.
  machine-dependent, which is why a class-string assertion is the wrong instrument.

`?scene=card` mounts only the cards, `?scene=search` only the search widget (its dropdown overlays
everything below it, so the check visits them separately). The search stub answers `/api/search/global`
the way the SERVER does — an episode row mid-play (the state machine's "Resume") and a movie row
("Watch Now") — since those labels come from the backend's own state and an invented one would prove
nothing.

| Assertion | What it means |
|---|---|
| A | the pill's glyph and label boxes **overlap** by ≥ half the shorter one's height (a stack overlaps ~0px) |
| B | the label sits AFTER the glyph, with a 3–12px gap (a centred stack puts it UNDER, so the gap goes negative) |
| C | both are centred on the pill's own axis (1.5px — the analytic ink method's uncertainty) |
| D | the movie CTA (a single glyph in a circle) is UNCHANGED — the flex rewrite must not touch it |
| E | per row: the pair has equal height, vertical padding, border-radius and font-size |
| F | per row: the pair is centred on each other and on the row, neither pokes outside… and **clicking either one still activates the row** (a restyle that leaves them inert would be worse than the misalignment) |
| G | the glyph in the primary button is inline and centred, as in A–C (Resume is the report's reference case) |
| H | the SAME size token reaches every row: both rows' primaries agree, as do their secondaries |

⚠ **Falsified before trusting it** — this repo has twice shipped a check that could not fail, so
`--expect-broken` runs the SAME assertions against the unfixed source and requires them to fail:
**11 problems** before the fix (glyph −11.25px / label +10.25px off the pill's axis, gap −37.59px;
32.00px vs 30.50px with padding 0/0 vs 6/6), none after. It is the same argument as `C` in the brand
lockup: the direction matters more than the absolute.

`Button.test.ts` is the companion, not a substitute: it pins that no `components/ui/Button` variant
grows its own box class (falsified by injecting `py-1.5` into one variant). It cannot see what the
browser does — that is what this frame is for.

## `search-frame.html` — the external ("not in your library") section (2026-09-13)

His third report: searching **"sholay"** returned his one library row and **no external section**, so
the real *Sholay* (1975) looked like it did not exist. The backend half of that cause — a gate that
skipped the external search whenever an owned title merely CONTAINED the query — is pinned in
`backend/tests/test_global_search.py`. This frame pins the half no backend test can reach:

> ⚠ the UI kept its OWN copy of the gate: `showDiscovery` required `!data.strong_match`, so fixing the
> server alone would still have shown him nothing. Two copies of one rule is the same drift that
> produced bug 2's two hand-rolled button strings — and the reason this is a browser check is that what
> must hold is the SERVER's answer versus what the SCREEN does with it.

`python3 tools/check_search_fallback.py` mounts the REAL `GlobalSearch` and drives the real
`/api/search/global` response shape for his query — `strong_match: true` **and** the external rows,
which is exactly the combination the old UI threw away.

| Query | What it proves |
|---|---|
| `?strong=1` (default) | the library row AND the "Discover · not in your library" group render together; the owned row is FIRST and keeps its own Resume action; each external row offers Add-to-watchlist/Download, is marked not-owned, and never offers an OWNED action; clicking one opens that title's metadata modal (the Suggest-card contract) |
| `?tmdbkey=0` | capability off: no group, no rows, and the footer says "TMDB discovery off — library only" — a silently smaller answer reads as broken |

Two things this frame learned/decided:

* ⚠ **Readiness waits for the OWNED row, not for the whole expected set.** Waiting on all three rows
  makes the run die at the gate with *"the frame did not render"* instead of failing the assertion
  that says WHY the rows are missing — which is the defect under test. Falsified: restoring the old
  UI gate turns it into 4 failures that name it (*"the UI showed groups `['In your library']`"*),
  and the click step is guarded so a missing row reports a FAIL rather than a Playwright traceback.
* His report suggested external rows should carry "no Resume/Details buttons". **Details stays, on
  purpose**: on an unowned row it opens that title's metadata modal (the same destination as clicking
  the row), not the owned item's page. The distinction that matters is the PRIMARY action, which is
  what the check asserts — an unowned row must never offer something that resumes or opens what he
  does not have.

## `item-frame.html` — the item detail as a modal (Bug 5, 2026-09-13)

`python3 tools/check_item_modal.py` mounts the REAL router (`AppShell` + `LibraryLayout` + the real
views) over a stubbed api at **2560×1440** — the viewport where his "detail overlay" report was
measured. ⚠ Read that report's cause carefully before touching this frame: **there was no broken
modal** — clicking a search result or a poster card navigated to `/library/item/:id`, a full PAGE
(`dialogCount=0`, `scrimCount=0`, and `main` at x 540→2260, i.e. the right 67% with the sidebar and a
300px gutter exposed). The route now renders `components/ui/Dialog` instead, which is why the check is
about PRESENTATION of a route, not about a component's internals.

| Scenario | What it asserts |
|---|---|
| A–F (search result) | scrim covers the viewport and really dims (alpha ≥ 0.4; measured `rgba(0,0,0,0.65)`); the panel is centred (±2px), rounded, shadowed, internally scrollable; content is inset from the panel's edges; a close X exists; body scroll is LOCKED; the library behind is rendered but `pointer-events: none` |
| D | each of the three dismissals — X, **Esc**, and a backdrop click — closes it AND releases the scroll lock |
| I | a poster CARD reaches the same dialog (his report asked for the other entry points too) |
| G | a COLD DEEP LINK renders the same modal, and closing it lands on the library |
| H | ⚠ with the PLAYER open, one Esc closes the PLAYER and the modal stays behind it |

Three things this frame learned the hard way:

* ⚠ **The dialog must not swallow Escape it does not act on.** `Dialog`'s handler runs in the CAPTURE
  phase and calls `stopPropagation()`, so a modal that merely ignored Escape while the player was open
  consumed the key and NOTHING closed. `Dialog` grew `canEscapeClose`; the modal passes the player's
  state. Scenario H is the assertion that keeps it (it caught this before the commit).
* ⚠ **Scope every measurement to the PANEL.** The backdrop is a real library view with a hero of its
  own, so a `main …` query for "the panel's inner inset" measured the wrong element and reported 0px.
* Readiness waits on the library view, never on the dialog: waiting for the dialog turns "there is no
  modal" into "the frame did not render", which is the defect under test. Falsified by restoring the
  old page route: **8 failures**, all reading *"no dialog on screen — the detail is not being presented
  as a modal at all"* — and every click on a dialog-only control is guarded so the run reports those
  failures instead of a Playwright timeout.



