# Phase W — the Title screen, drawn in the box tvOS actually gives it

Plan committed BEFORE the build, per `feature-shipping-cycle.md`. **Every number in this file was measured
against this repo on 2026-09-20**, and the source is named beside it.

His instruction (2026-09-20, new session): *"there is problem with details screen … can we implement the
title view as it is in html file for the tvos screen only, the details view screen is available but its
resolution somehow not working … we should reuse the details screen component wherever we can … rewrite the
code if it is required rather than just patching up the existing details screen"*.

His answers to the three questions this plan needed:

| # | Question | His answer |
|---|---|---|
| 1 | What does the title screen look like now? | **"Still zoomed: only part of the page is visible"** |
| 2 | Where does the scale get corrected? | **Everywhere** — one scale, so Home/Browse/Player/Title all stay proportional (`KNOWN_ISSUES` #13 has been open since round 6) |
| 3 | How far does the action row go? | **Play only** — `Trailer` / `Add to Watchlist` / `More` and the "Because you watched" shelf stay their own phase |

---

## 0. The fault — measured, and it is one fault

**The screens have been laying out inside tvOS's safe area and then indenting by the prototypes' own
margin, so every screen is inset TWICE.**

| Evidence | Number | Source |
|---|---|---|
| What tvOS hands the root view | **1760 × 960 pt at (80, 60)** — the canvas minus its overscan inset | his round-9 log, `KNOWN_ISSUES` #13: `detail-size: screen = 1760x960 pt at x=80 y=60` |
| What tvOS's point space is | **1920 × 1080 pt**, fixed, on every device — a 4K panel renders the same points at `scale = 2.0` | Apple TV 4K tech talk + `UIScreen.nativeBounds` returning 1920×1080 |
| The design's own margin | **4.2u = 80.64 pt** (`TVTokens.Metric.safeMargin`), which is set 2's `64px` | `TVTokens.swift`; `title-view.html` pads `.topbar`/`.actions`/`.synopsis`/`.shelf-track` by `64px` |
| Where the title's glyphs land today | **160.64 pt** from the panel edge (80 safe area + 80.64 margin) | arithmetic |
| Where his file puts them | **80.64 pt** from the page edge | `title-view.html` |
| The hero's height | **712.8 pt of a 960 pt box = 74.3 %** — but the file asks for `66vh` of the *screen*, i.e. 66 % of 1080 = 712.8 | `TVTokens.Title.heroHeight` (pinned to `1080 × fraction` by the harness) |

⇒ The content box the design is drawn against is **1758.7 pt wide**; the app has been drawing it into
**1598.7 pt** — **9.1 % narrower, with 80 pt of dead gutter on each side**, and the hero taking 74 % of the
height instead of 66 %. The action row therefore lands at ≈932 pt of a 960 pt box and is pushed off the
bottom, so the screen opens scrolled with its hero cut — **which is exactly "still zoomed, only part of the
page is visible"**.

⚠ **The previous round's reading of the same log was wrong in one step, and the correction matters.**
That round took `layoutWidth = 1760` and shrank what FITS to match — the cast row's cap of 7. The cap was
right for the box as it then stood, but the box itself was the bug: **the screens are supposed to fill the
canvas**, and tvOS's safe area is there to stop a TV cropping *critical content*, not to be added on top of
a design that already indents by 4.2 %. The fit rule keeps its cap of 7 and now counts 1920 − 2 × 80.64 =
**1758.7 pt** (8 items would be 1821.96 pt and still do not fit).

**⚠ What this is NOT.** It is not a resolution or a pixel-density fault. tvOS gives a 1080p and a 4K Apple
TV the *same* point space; a 4K panel changes the pixel density, not the layout. So the fix is a layout fix
and it holds on every panel — which is his 4K question answered by construction rather than by a special
case.

**The one thing that IS resolution-dependent, and is fixed here anyway:** artwork. `PosterURL.Route.backdrop`
asks for `width=1600` px, which a 4K panel upscales ~2.4× across a full-width hero. The route's ceiling is
4000 (`jellyfin_poster.py`), and the app can read the panel's scale from `@Environment(\.displayScale)`.

---

## 1. The decision

> **The app's screens fill tvOS's 1920 × 1080 point canvas, and each screen applies its prototype's own
> margin ONCE.** The safe area is not applied a second time at the top of the token table, because the
> design already carries its own inset — the same inset the file draws from the page edge.

Consequences, each stated rather than discovered later:

* `TVTokens.Metric.screenWidth` (1920) is now **the box the screens lay out in** and not just the canvas;
  `Metric.layoutWidth` therefore equals it, and `DetailRules.castCapacity` reads 1758.7 pt of content.
* **Every existing metric keeps its value.** `u` stays 19.2 pt and `px` stays 1.26 pt, because they were
  always derived from the canvas — the screens were simply not being given the canvas. **No number in the
  token table changes**, which is why this is one root-level decision and not a rescale: `Title.heroHeight`
  is 712.8 pt before and after, and the harness's pin on it stays true.
* The prototypes' `66vh`, `4.2u` and `64px` all mean what they meant in the file they were read from.
* ⚠ **The trade, stated plainly:** the design's margin is 80.64 pt from the panel edge, and Apple's tvOS
  guidance is 90 pt. A television that crops more than 4.2 % of the frame can therefore clip the very edge
  of the margin. That is the same exposure his HTML has when a browser draws it full screen, and the knob if
  a round ever shows it is **`Metric.safeMargin`, one number** — never a per-metric re-derivation.
* ⚠ **Artwork may bleed; text may not.** The hero is drawn full-bleed (his `.hero` is full-bleed), and every
  word on the screen stays inside the 80.64 pt margin.

## 2. W1 — the box (`App/AppRootView.swift`, `Design/TVTokens.swift`)

| Change | File | Why |
|---|---|---|
| the screen content fills the canvas (`.ignoresSafeArea()` on the routing `ZStack`) | `AppRootView.swift` | one place, so no screen can forget it — and the flip side, no screen can double it |
| `Metric.screenHeight` (= `u * 56.25` = 1080), `Metric.layoutWidth == screenWidth` | `Design/TVTokens.swift` | the hero's `66vh` and every fit rule now read a named box |
| `Title.heroHeight = Metric.screenHeight * Title.heroHeightFraction` | `Design/TVTokens.swift` | the fraction is the source and the box is explicit; the harness pin (`== 1080 × 0.66`) stays true |
| `overscanInsetX/Y` kept, with the note that they are what tvOS insets and **not** a second margin | `Design/TVTokens.swift` | the measurement stays in the tree where the next session will look for it |
| `DetailRules.castCapacity` counts `layoutWidth` (now 1920) | `Core/DetailRules.swift` | 1758.7 pt of content ⇒ **7**, unchanged, and eight still overflow (1821.96 pt) |

## 3. W2 — the Title screen, transcribed (`Detail/DetailView.swift`, rewritten)

His `title-view.html`, top to bottom, with the token it is built from. **The file is rewritten rather than
patched**: the band order, the full-bleed hero and the floating bar are structural, and the existing file's
band list is the thing that is wrong.

| Band | His CSS | Token |
|---|---|---|
| Top bar | `position: fixed`, over the hero | **the app's `TopBar`**, drawn as an overlay over the scroller (it was a band above it) — ⚠ still the only way out, still one tab |
| Hero | full-bleed art, `height: 66vh`, scrim `to top` `void 0% → .65 32% → clear 68%` | `Title.heroHeight`, `.scrim*`, `PosterImageView(route: .backdrop)` at the panel's own pixel width |
| Title block | `padding: 0 64px 40px`, `max-width: 920px`; `h1 64px` w700; meta `19px` + gold `★`; pills `6px 16px` r999 `15px` | `Title.titleSize/metaSize/pill*` |
| Action row | `padding: 36px 64px 0`; `.btn 16px 30px` r14 `19px`, primary gold, focus `scale(1.08)` + `2px` gold-bright ring | **new** `Title.btn*` — ⚠ his `.btn` is NOT the Home's `.hero-cta` (19 px vs 1.1u), so `CtaButtonStyle` gains a metrics preset and the chrome stays one implementation |
| Synopsis | `padding: 40px 64px 8px`, `max-width: 62ch`, `19px`, `line-height: 1.6` | `Title.synopsis*` |
| Cast shelf | `h2 24px`, track `gap: 28px`, item `150px`, avatar `110px`, initials `32px`, name `16px`, role `14px` | `Title.cast*`, one non-scrolling row capped by the fit rule |
| Episodes (series only) | — (not in his file: his title screen is a film) | B4's rows, kept — real data the screen would otherwise have nowhere to put |
| Progress bar | — (not in his file) | kept when the title is genuinely in progress: identical artwork tells a viewer nothing about where they stopped |

⚠ **Reused, not re-drawn:** `TopBar`, `PosterImageView`/`PosterLoader`/`PosterURL`, `CtaButtonStyle`,
`RKMColour`, `LibraryRules.marginFromPrototype`, `ProfileRules.initials`, and the whole `DetailStore` /
`DetailRules` / `DetailSnapshot` layer with its four states. `AppModel.openDetail` stays the ONE entry
point, so Home's hero, Home's rails and the library grid all reach this screen through one component.

⚠ **Still deliberately absent, and unchanged by this phase** (his answer to Q3, and §11's rule — *never
offer what the server will refuse*): `Trailer` (needs `RemoteTrailers` on the detail payload — a wire
change), `Add to Watchlist` and `More` (the acquisition/administration half, kept on web/iOS by
`apple/tvos/README.md`), and the "Because you watched" shelf (`/api/jellyfin/similar` carries a TMDB id and
no Jellyfin item id — it is an acquisition surface, `TVOS_LIBRARY_UI_PLAN.md` §1 row 3).

## 4. W3 — the artwork (`Core/PosterURL.swift`, `Home/PosterCard.swift`)

`PosterURL.width(points:scale:route:)` — **the pixel width a band of `points` needs on a panel of
`scale`**, clamped by the route's own range. The title hero asks for its full 1920 pt at the panel's
scale: **3840 px on a 4K panel** (the route's ceiling is 4000), 1920 px on a 1080p one. `PosterImageView`
gains the `width` parameter and passes it to the loader it already has.

⚠ Applied to the **title screen's hero only** in this phase. ⚠ `Home/HeroBand.swift` has the same 1600 px
softness on a 4K panel and is a one-line follow-up — offered, not smuggled in.

## 5. Gates

| Gate | Change |
|---|---|
| `check-tvos-core.py` | the `heroHeight` mutation is re-pointed at the new line (`screenHeight * fraction`), plus a new mutation for the fit rule reading the box. ⚠ `--falsify` is **not** run: his standing rule is dev + unit tests, then his round |
| `tvos-core-tests/main.swift` | new pins: the box the screens lay out in is the canvas; the hero is `66 %` of it; a full-width hero asks for `1920 × panel scale`, clamped by the route |
| `check-tvos-members.py` | new symbols this screen names (`PosterURL.width`, the `Title.btn*` tokens) |
| `check-apple-typecheck.sh`, `check-imports.py`, `check-tvos-models.py`, `check-design-tokens.py`, `check_md_links.py` | run unchanged — no wire model, no colour, no new route |

## 6. The round (his Mac — SCREEN round, WITHOUT `-RKMDebugHUD`)

```bash
cd ~/dev/rkm-cinema && git checkout feat/tvos-player && git pull --ff-only && ./apple/scripts/mac-round.sh tvos --sim
```

| # | Falsifier | What DISPROVES it |
|---|---|---|
| W-F1 | the whole page is on screen at once — the title's first letter is not cut and the action row is above the bottom edge | anything is clipped, or the page opens scrolled |
| W-F2 | the hero reaches **both screen edges** and the title block sits over its lower part | the artwork stops short of the edge (the 80 pt gutter is back) |
| W-F3 | `Play` is reachable, starts the film, and the arrows reach the top bar from it | the ring starts elsewhere, or nothing plays |
| W-F4 | the bar floats over the hero and `Back` still leaves the screen | the bar is a band above the hero, or Back is missing |
| W-F5 | the cast row is one row of round initials that fits | the row overflows, or scrolls with no way to reach it |
| W-F6 | the backdrop is **sharp** on a 4K panel | it is visibly upscaled/soft |
| W-F7 | the app's own log says the screen is **1920 × 1080 pt at (0, 0)** | it reports 1760 × 960 at (80, 60) — the double inset is still there |

⚠ W-F7 is read from the file log, not the HUD panel (the panel cannot be scrolled):
`find "$(xcrun simctl get_app_container booted com.helloraj1986.RKMCinemaTV data)" -name rkm-tvos.log`
