# Player Layout Plan — fit, orientation & fullscreen (`feat/player-layout`)

Status: **IN PROGRESS** (branch `feat/player-layout` from `main` @ `3ce786c`).
Scope: the in-app player's *geometry only* — how the shell, video stage, transport
dock and fullscreen behave at every viewport and orientation. No `/api` change, no
backend change, no streaming/engine change (that surface is finished: see
`HLS_PLAYER_PLAN.md` complete + `PLAYER_TAIL_PLAN.md`).

Target files:
- `frontend/src/features/playback/Player.tsx` (1371 lines — the whole player)
- `frontend/src/features/playback/lib.ts` + `lib.test.ts` (pure helpers)
- `frontend/src/styles/index.css` (the player shell CSS + tokens)
- `frontend/index.html` (`viewport-fit=cover`)
- `frontend/harness/*` + `tools/measure_player_layout.py` (verification, committed)

---

## 1. The user's report, and what the measurements say

Reported (2026-09-11, used on a phone browser AND a laptop browser):

1. the player does not fill the available screen — there is a border around it
   that looks blank/transparent;
2. on a phone browser the player's controls do not fit the screen;
3. on a laptop the controls drop below the bottom screen margin.

None of this had ever been measured, so it was first reproduced in a real browser.
`tools/measure_player_layout.py` drives the real `<Player>` (API-stubbed by
`frontend/harness/player-frame.html`, media remapped to a genuine 960×540 MP4) in
Chromium at 10 device sizes and asserts the invariants "fits the screen" means.

**Baseline — 3 of 10 viewports PASS:**

| Viewport | Result | Measured problem |
|---|---|---|
| Phone SE 320×568 | **FAIL** | 14 elements outside the viewport (time readout right edge 367.6 > 320, Settings button 417.6) |
| Android small 360×640 | **FAIL** | 13 elements outside (Settings button right 417.6 > 360) |
| iPhone 12 portrait 390×844 | **FAIL** | 11 elements outside (PiP button right 467.6 > 390 → **78 px of controls off-screen**) |
| Android landscape 915×412 | **FAIL** | transport dock bottom **584.7** vs viewport 412 → **173 px below the fold** |
| iPhone 12 landscape 844×390 | **FAIL** | dock bottom **544.8** vs 390; video bottom 544.8 |
| iPad portrait 820×1180 | PASS | — (video 788×443 inside the padded stage) |
| Laptop 1366×768 | PASS | — (video only 960×540 with a 203 px band either side) |
| Laptop short window 1280×600 | **FAIL** | dock bottom **628** vs 600; stage bottom 644 |
| Narrow short window 1024×500 | **FAIL** | dock bottom **628** vs 500 → **128 px below the fold** |
| Desktop 1920×1080 | PASS | — (video 960×540 = 1/4 of the screen area) |

Raw reports: `/tmp/baseline.json` shape is reproducible any time with
`python3 tools/measure_player_layout.py --out report.json`.

### 1.1 Root causes (each one measured, not inferred)

**A. The shell is exact, the column inside it is not.** `root` measures exactly
`0,0 → vw,vh` at every size and `100dvh == innerHeight`, so `fixed inset-0` is fine.
The overflow comes from the stage: `<div className="relative flex flex-1 items-center
justify-center">` is a flex item whose `min-height` defaults to `auto`, i.e. it
**cannot shrink below the video's intrinsic height** (540 px for the fixture). The
column therefore overflows the fixed shell instead of shrinking the video: at
1280×600 the stage ends at y=644 and the transport bar — positioned
`absolute bottom-0` inside that stage — lands at **628**, i.e. 28 px (to 128 px at
500 px height) below the visible screen. **This is complaint 3, and it gets worse the
shorter the window / the taller the video** (the user's own files are 1080p).

**B. The transport row cannot wrap and has no compact tier.** It is one
non-wrapping `flex` row of: play · prev-episode · next-episode · mute · volume slider
(`w-16`) · mode chip · time · settings · PiP · fullscreen, each button a fixed 40 px
`h-10 w-10`. On a 390 px phone that is ~468 px of controls → **complaint 2**, and it
is the reason the *time readout* gets pushed off-screen first (it is `ml-auto`).

**C. The video is sized to its intrinsic pixels inside a padded box, so the leftover
space shows the blurred poster.** `p-4` on the column + `max-h-full max-w-full` on
the video + `rounded-lg` = the video is 960×540 in a 1366×768 window with 16 px of
padding and a 203 px band either side, filled with the `opacity-40 blur-md` poster
backdrop and a `bg-black/55` scrim. **That is the "border that looks blank/
transparent" — complaint 1.** The space is not empty, it is a blurred backdrop, so it
reads as a translucent frame around the picture. The video never scales up to the
space it is given (`max-*` only ever caps; nothing makes it fill).

---

## 2. The layout contract (what "production" means here)

The player is a full-viewport *surface*, and the whole surface is one of three bands
that always add up to the viewport — never more:

```
┌──────────────────────────────────────────┐  ← shell: fixed, exactly the visible viewport
│ backdrop (blurred keyart) + scrim        │     (100dvh, not 100vh — mobile URL bars)
│ ┌──────────────────────────────────────┐ │
│ │ top chrome  (close · title · S/E)    │ │  shrink-0, safe-area-inset-top
│ └──────────────────────────────────────┘ │
│ ┌──────────────────────────────────────┐ │
│ │ STAGE  flex-1  min-h-0               │ │  ← min-h-0 is the whole point:
│ │   <video>  h-full w-full             │ │    the ONLY band allowed to shrink
│ │            object-contain            │ │    video fills this box exactly, so any
│ │   spinner · play · error · subtitles │ │    letterbox is the video's own black
│ │   · up-next · settings panel         │ │
│ └──────────────────────────────────────┘ │
│ ┌──────────────────────────────────────┐ │
│ │ DOCK  shrink-0                       │ │  seek bar + transport row
│ │  seek bar                            │ │  safe-area-inset-bottom,
│ │  transport row (tiered by width)     │ │  height published as --rkm-dock-h
│ └──────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

Rules the implementation must hold (each one is asserted by the measuring tool):

1. **Shell = viewport.** `position: fixed; inset: 0; height: 100dvh` (with a `100vh`
   fallback), `overflow: hidden`, `overscroll-behavior: none`. `100dvh` — not
   `100vh` — because on Chrome Android/iOS Safari the *layout* viewport is the
   URL-bar-hidden height: `inset-0` alone can put the dock under the browser's
   toolbar, which is the second half of complaint 3.
2. **Only the stage flexes, and it must be allowed to shrink.** `min-h-0` on the
   stage (and `min-h-0`/`shrink-0` stated explicitly on every band). No band may
   rely on `flex-1` while keeping an `auto` min-height.
3. **The video fills the stage.** `h-full w-full object-contain bg-black` — the
   element *is* the stage box; letterboxing happens inside it in black. Nothing in
   the shell is ever left showing a poster scrim "around" the picture → complaint 1
   is structural, not a paint tweak. `rounded-lg` goes away (visible black corner
   notches when the video fills; Plex/YouTube do not round a fullscreen video).
4. **The dock is anchored to the visible bottom.** `pb-[max(10px,env(safe-area-inset-bottom))]`,
   horizontal insets from `env(safe-area-inset-left/right)` for landscape notches.
5. **The dock's own height is published** as `--rkm-dock-h` (ResizeObserver) so the
   subtitle overlay, the Up-Next card, the centre play button and the settings panel
   can clear it instead of guessing `bottom-24`/`bottom-28`.
6. **Chrome auto-hide keeps working while docked in flow, not overlaid on the
   picture.** Hiding is `opacity` + `pointer-events`, so the geometry never moves
   mid-playback (no reflow, no video resize stutter) — and a hidden dock must not
   leave a transparent gap where it was: the dock band keeps its reserved height and
   the stage keeps its box.

### 2.1 Orientation matrix (what each shape must produce)

| Shape | Stage | Dock | Top chrome |
|---|---|---|---|
| Phone portrait 320–430 × 568–932 | video letterboxes top/bottom, black | single row, compact tier: play · ±10 s · prev/next-ep · time · settings · fullscreen (no volume slider, no PiP chip, no mode chip — the OS owns volume on a phone) | title truncates, S/E chip stays |
| Phone landscape 640–930 × 320–430 | video uses the full width; the top/bottom bands are the expensive space, so the dock gets the compact tier and the header collapses to a single icon row (no S/E line, no "n of m") | compact | minimal |
| Tablet 768–1024 × 1024–1366 | as portrait, room for the full row | full | full |
| Laptop/desktop ≥ 1024 × ≥ 500 | video fills the stage (up to ~2.4× today's rendered size) | full tier: play · prev/next ep · mute + slider · mode chip · time · settings · PiP · fullscreen | full |
| Short window (any width × < 460) | stage shrinks (never overflows) | full tier still, one row | full |

Numbers are established by the measured matrix in §1 + the tier rules in Phase 2;
"compact/full" is a CSS tier (a `sm:`/`landscape:` boundary), not a JS branch, so it
cannot desync from the layout.

### 2.2 Fullscreen alignment

- Fullscreen targets the **shell** (`rootRef`), so the dock/header/subtitles come
  along and the same band arithmetic applies inside the fullscreen element.
- `:fullscreen` gets `height: 100dvh` too (the fullscreen viewport has no URL bar,
  and on a notched device it *does* include the safe areas).
- **iPhone has no `Element.requestFullscreen`** (only iPad/desktop do). Today the
  fullscreen button is a silent no-op there. The plan adds a tested resolver —
  `fullscreenPlan({ hasElementFullscreen, isAppleMobile, isPip })` →
  `"element" | "video" | "none"` — falling back to `video.webkitEnterFullscreen()`
  (the native iOS player) and hiding the button when neither exists.
- Entering/leaving fullscreen re-measures the dock (`--rkm-dock-h`) and, on the HLS
  path, does nothing to the engine — fullscreen changes no source, so playback must
  not restart or stutter.
- `document.fullscreenchange` and `orientationchange`/`resize` both just re-run the
  measurement; no state depends on the old numbers.

### 2.3 Everything else that counts as a "quirk" here

- **Body scroll lock** while the player is open (the `Dialog` component already does
  exactly this): without it, iOS rubber-band scrolling drags the page behind the
  fixed layer and a phone user sees the player visually detached/misaligned.
- **`viewport-fit=cover`** in `index.html` — the app already prints
  `env(safe-area-inset-*)` (MobileNav) but the insets are always 0 without it, so the
  existing "safe-area aware" code is currently dead. Enabling it is what makes §2.4's
  insets real, and it is what makes the player use the whole screen on a notched
  iPhone rather than a letterboxed browser viewport.
- **No page-level scrollbars/scroll chains**: `overflow: hidden` on the shell,
  `touch-none` stays on the seek bar (already), `overscroll-behavior: none` so a
  drag at the end of a swipe cannot bounce the shell.
- **Double-tap-to-zoom / tap delay**: the controls are real buttons ≥36 px with
  `touch-action: manipulation` on the dock so a fast double-tap on play/pause is two
  taps, not a zoom.
- **The 40 px fixed button size** becomes a tiered size (40 px at `sm`, 36 px below)
  so a narrow phone fits without hiding anything essential.

---

## 3. Phases (one commit each, gates green after every phase)

Gate per phase (from `frontend/`): `npx vitest run <file>` → `npx tsc --noEmit` →
`npm run build`, plus `python3 tools/measure_player_layout.py` (must end `10/10
viewports PASS`; it is the only thing that can prove the fit).

### Phase 0 — plan + measurement harness *(done in this commit)*
`docs/PLAYER_LAYOUT_PLAN.md`, `frontend/harness/player-frame.html`,
`frontend/harness/player-frame.tsx`, `frontend/harness/README.md`,
`tools/measure_player_layout.py`. No app code touched. Produces the baseline table
in §1 and the muscle to verify every later phase.

### Phase 1 — shell + stage geometry (complaints 1 and 3)
1. `index.css`: add the `.rkm-player` shell (fixed / inset-0 / `100dvh` fallback chain
   / `overflow-hidden` / `overscroll-behavior: none` / `--rkm-dock-h: 96px` default)
   and a `.rkm-player:fullscreen` rule.
2. `Player.tsx`: restructure the shell into three explicit bands — top chrome
   (`shrink-0`), stage (`min-h-0 flex-1`), dock (`shrink-0`) — and delete the
   `p-4` letterboxing wrapper.
3. Video becomes `h-full w-full object-contain bg-black`, `rounded-lg` removed; the
   backdrop/scrim stay in the shell behind the chrome only.
4. Assert: shell == viewport, stage never exceeds it, video box == stage box, and the
   remaining bands' heights sum to the viewport at all 10 sizes.

### Phase 2 — transport dock (complaint 2)
1. Dock reflow: seek bar on its own line (≥20 px tall, `touch-none`), the transport
   row below it with `flex-wrap` allowed as a last resort, `gap-1.5`, tiered button
   size, `min-w-0` on the row.
2. Tiers: volume slider, mode chip and the PiP button are `sm:`-and-up; the compact
   tier keeps play · prev/next episode · mute · time · settings · fullscreen.
   Add ±10 s skip buttons to the transport (currently keyboard-only) — the single
   most useful phone control that is missing today.
3. `--rkm-dock-h` ResizeObserver; subtitle overlay, Up-Next card, centre play button
   and settings panel anchor off it (no more `bottom-24`/`bottom-28` guesses).
4. Assert: 0 elements outside the viewport at every size, dock row narrower than the
   viewport at 320 px, and the play/pause + fullscreen buttons still ≥36 px.

### Phase 3 — fullscreen, orientation, mobile guards
1. `lib.ts`: `fullscreenPlan(...)` (+ tests) and `playerChromeFor({vw, vh, isMobile})`
   (+ tests) driving the landscape header collapse (§2.1).
2. `Player.tsx`: fullscreen via the plan (element → video fallback → hide button),
   `fullscreenchange` re-measure, `orientationchange`/`resize` re-measure, body
   scroll lock while open.
3. `index.html`: `viewport-fit=cover`; safe-area insets on the top chrome + dock.
4. Assert: `--fullscreen` run of the harness tool (element fullscreen really entered
   via a synthetic click) still reports shell == screen, dock inside, no overflow.

### Phase 4 — close-out
Re-run every gate, capture the after/table + screenshots, write the
`docs(status): …` PROGRESS.md record, hand the user the web-only redeploy +
eyeball (phone portrait, phone landscape, laptop window) and merge after OK.

---

## 4. Acceptance

Sandbox (agent): all four gates green after every phase, `10/10 viewports PASS`,
before/after screenshots delivered in chat, `docs/PROGRESS.md` updated.

RKM-HP (user, web-only — no api/backend change):
`docker compose -p rkm-bundled up -d --build web`, then on the phone (portrait +
landscape) and on the laptop: the picture fills the frame with no translucent
border, every control is visible without scrolling, nothing sits under the browser
toolbar, and the fullscreen button fills the screen on both.

Merge `feat/player-layout` → `main` (fast-forward) only after that eyeball, then
fast-forward `experiment/bundled-docker-stack` and push all three.
