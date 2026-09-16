# ADR-0011: the mobile layout — two shells in one app, decided by the viewport

- **Status:** Accepted · ✅ **phases M0 and M1 built** (2026-09-16) — the switch, the tokens, the
  boundary at 1024px, the thumb-zone bar and the sheet primitive. ⚠ M2–M9 are planned, not built; see
  `MOBILE_FIRST_UI_PLAN.md` §11.
- **Date:** 2026-09-16
- **Phase:** `feat/mobile-first-ui` (brief §2a/§3, plan §3/§4)
- **Depends on:** nothing. This is the foundation the rest of the mobile work sits on.
- **Depended on by:** every one of M2–M9.

## Context

The web layout is mature and finished. The app is used by one household, on a phone held one-handed on
a sofa at night, and on a tablet that is also held. The brief's opening rule is that **the web layout is
NOT the subject of this work and must come out of it byte-identical in behaviour** — so whatever is
built has to be additive in a way a reviewer can verify, not merely intend.

There is also one hard constraint from the architecture: **there is ONE UI.** `ARCHITECTURE.md` §2/§17
put it plainly — the iOS app is a shell around the LIVE web UI, so a second UI would be a second thing
to keep in sync across the browser, the phone and (later) tvOS.

## Decision

**Two layout modes, chosen by the viewport, rendering one component tree.**

- `mobile` — below 1024px. **Phone AND tablet.** `MOBILE_MAX_PX = 1023`.
- `desktop` — 1024px and above. The existing layout, untouched.

`layouts/LayoutMode.tsx` holds the switch: a `useSyncExternalStore` subscription to one shared
`MediaQueryList`, a provider mounted once in `main.tsx`, and the one hook (`useLayoutMode()`) that
anything may read. The provider publishes `document.documentElement.dataset.layout`, which is how the
scoped CSS in `styles/index.css` reaches the `html`/`body` rules a shell needs but does not own.

Inside the mobile mode, the phone/tablet difference is **CSS only** — `--m-grid-cols` reflows 3 → 4 → 5 at
600px and 834px, and the type step and gutter follow. **There is no `isTablet` anywhere in the app, and
adding one is the single change that would turn one shell into three things to maintain.**

## The alternatives, and why each lost

| Alternative | Why it lost |
|---|---|
| **Media-query-only CSS** (one markup tree, `md:`/`lg:` doing everything) | It is genuinely smaller — and it was the first thing I tried to make work on paper. It fails on **the DOM, not the styling**: a bottom sheet and a centred dialog are different elements with different dismissals (a gesture vs a backdrop click); the poster action that is `opacity-0 … group-hover:opacity-100` cannot be made reachable by a media query; and a nav that is a fixed bottom bar needs its own scroll padding. The end state is one tree containing both arrangements at once — double the `useEffect`s, double the `aria-*` surface, and a phone rendering the desktop markup hidden by CSS. ⚠ The decisive argument is measurable: `tools/check_mobile_layout_switch.py` asserts a desktop viewport computes `display: block` on `.m-grid` — with one tree there is no such thing as "the mobile rules do not apply". |
| **A second bundle** (`m.` variant, a separate entry point) | Two bundles is two apps. It contradicts "ONE UI" directly, and it doubles everything that is currently singular: the router, the api client, the auth guard, the query cache, the player. The brief rules it out in its first non-negotiable, and the architecture's whole client story (§17) assumes one. |
| **A native client** (SwiftUI/Compose views, api-generated) | This is what **tvOS** will have to be (`ARCHITECTURE.md` §17.1) — there is no WebKit there. For iOS it is a large, permanent second implementation of every screen, with no path back, to solve a problem that is layout. It also forfeits the property that makes this app cheap to ship: **every `apply` reaches the phone with no app rebuild.** |
| **A third `tablet` mode** | A third set of components, a third set of harness checks and a third thing to regress forever, to express a column count and a type step. The brief's §2a settled this before implementation, and M0 confirmed it: the tablet differs from the phone in **two custom properties**. |
| **A physical move into `layouts/desktop/`** | A large diff with zero behaviour change that breaks every existing import path and every reviewer's mental map, and puts the mature web layout at risk for a filing preference. `layouts/desktop/index.ts` is a thin re-export instead — reversible in one file. |

## The three settled decisions, recorded as settled

Each was decided the same way the alternatives above were: **the option with the fewest code paths and
the smallest diff wins.**

1. **Does a tablet get the mobile layout? — Yes.** Two modes only. A held iPad belongs in a thumb-zone
   shell, and the 76px icon rail the app used to show at 768px was a worse answer for a held device than
   the bottom bar. The cost of a third mode is permanent; the cost of this is two media queries.
2. **Do the desktop views move into `layouts/desktop/`? — No.** They stay exactly where they are; the
   index re-exports them so a route reads symmetrically (`desktop.LibraryHomeView` /
   `mobile.HomeScreen`), and a future move is a one-file change rather than a sweep of the router.
3. **What does "my downloads" mean on a shared iPad? — Nothing changes.** The file is the household's
   (ADR-0007 D6). The Downloads screen states it in one line of copy. Per-profile downloads would mean
   profile-stamped native storage, a bridge field, a Mac round and a `v2` contract — a large,
   irreversible piece of work to solve a labelling problem.

## What M0 and M1 actually changed, and what they deliberately did not

**Changed:** `layouts/` (new), `styles/index.css` (the scoped mobile block + the safe-area hoist),
`main.tsx` (one provider), `app/router.tsx` (imports re-pointed through `layouts/desktop` — a no-op at
runtime), `app/layout/AppShell.tsx` (the chrome is chosen, not hidden by CSS), `Sidebar.tsx` and
`MobileNav.tsx` (the boundary moved from `md` to `lg`), and `components/ui/Sheet.tsx` +
`sheetRules.ts` (new).

**Deliberately NOT changed:** `backend/` (nothing), `apple/` (nothing — the bridge stays `v1`),
`nginx/default.conf` (nothing), `Config/Info.plist` (nothing), `components/ui/Dialog.tsx` (it keeps
serving the desktop tree; the sheet is a sibling, not a replacement), `lib/api/client.ts` (untouched —
there is still exactly one HTTP client), and every existing view file.

### Two deviations from the brief, both reported rather than silently resolved

1. **No `MobileHeader`.** The brief's §3 tree and the plan's §3.1 both imply one. It would be a second
   `Header`, which means a second `GlobalSearch` and a second `AccountMenu` — two copies of the
   interaction wiring that `check_nav_access` exists to keep in one place. `Header` already carries the
   safe-area inset, the 64px minimum and both controls, so the mobile shell uses it as-is and the tab
   bar is the whole of the new chrome.
2. **M0 does not flip the boundary; M1 does.** If M0 had moved `md` → `lg` on its own, then between M0
   and M1 the 768–1023px band would have lost its sidebar and gained the bottom bar while still
   rendering the desktop views — a visibly worse app shipped as "foundation". Keeping the boundary flip
   in the commit series that lands the shell means **every phase is deployable without regressing any
   viewport**, which is what the brief's §13 asks of each phase.

### One shell, one component, and why the page never remounts

`AppShell` chooses its chrome from `useLayoutMode()`. It does **not** render
`{mobile ? <MobileShell/> : <DesktopShell/>}`. That alternative moves `<Outlet/>` to a new position, so
React unmounts the routed view on every rotation — the film you were browsing refetches, and a
half-typed form is lost. The conditionals are siblings of the Outlet's ancestors, so the page in the
middle is the same element at every size. ⚠ **Measured:** scenario C of
`tools/check_mobile_layout_switch.py` resizes 1280 → 390 → 834 → 1280 on one page and requires zero
remounts, zero requests and no sign-out.

⚠ And `OfflineWiring` sits **outside** the mode conditional: a rotation must not restart the progress
spool's replay loop, and a window maximised past 1024px must not lose the positions it is holding.

## The rules that keep the mobile shell from forking logic

`layouts/mobile/**` may hold **layout, markup, styling, interaction and local UI state — nothing else.**
`layouts/importRule.ts` is that sentence turned into something a test can fail on: a second HTTP client,
a second formatter, a second clock, a second viewport source and an inline percentage all fail
`imports.test.ts`. It is a pure function of `(file, source)` so the rule can be falsified with fixture
strings, and it treats a comment that NAMES a banned pattern as documentation rather than a violation —
otherwise the rule punishes the reasoning that justifies it.

## ⚠ Two traps this phase cost, recorded because each is invisible in a diff

1. **`window.scrollY` is 0 while a scroll lock is on, and that is CORRECT.** The body is
   `position: fixed`, so the document has nothing left to scroll and the position lives in the body's
   negative `top`. My first assertion read `scrollY` *after* opening and reported a leak on a lock that
   worked; and the first version of the harness click used Playwright's `.click()`, which scrolls its
   target into view — silently resetting the very scroll position under test. Both produced "the
   assertion passes and the feature is broken", which is the worst kind of check.
2. **A `.ts` and a `.tsx` may not share a base name.** The sheet's pure rules were `sheet.ts`; Vite's
   default extension order puts `.ts` before `.tsx`, so `import { Sheet } from "./Sheet"` resolved to
   the RULES file and the render died with *"does not provide an export named 'Sheet'"* — an error that
   reads like a typo, not a file-naming collision. Hence `sheetRules.ts`.

## What is NOT verified, stated plainly

- ⚠ **No device has seen any of it.** The mobile shell was measured in Chromium at 320/390/600/834/
  1023/1024/1280/1440px. `env(safe-area-inset-*)` resolves to **0px** in every sandbox browser, so the
  notched-phone geometry is pinned by `shell-contract.test.ts` reading the source, **not measured**.
  The iOS shell's own appearance is his round to run (`.\rkm-cinema.ps1 apply`, then reload the phone).
- ⚠ **The 44px floor is a guarantee, not a repair.** The tabs already clear 44px on their own content,
  so `min-h-[var(--m-tap,44px)]` protects against a future smaller icon rather than fixing a present
  defect. Falsified anyway (shrink the icon and the check names all four tabs).
- ⚠ **`check_nav_access.py` fails in this sandbox, on an UNTOUCHED `dev` as well as on this branch.**
  Measured 3/3 on both. The cause is `net::ERR_INSUFFICIENT_RESOURCES`: the tool loads nine frames into
  one Chromium instance, and by the eighth the browser can no longer fetch the unbundled dev modules
  (`FAILED lib.ts`, `FAILED Dialog.tsx`). It is the multi-frame problem `ARCHITECTURE.md` §18.7 already
  names, and it is **not attributable to this phase** — which is why it is reported here rather than
  fixed inside a mobile phase (brief §14). The cure is a fresh page per scenario, which both new mobile
  tools already implement.
- ⚠ **M2–M9 do not exist yet.** No phone-shaped `HomeScreen`, no `DetailScreen`, no sheet-based
  `RequestSheet`, no mobile player, no mobile Downloads screen. The routes still render the existing
  desktop views inside the new shell — which is exactly what M1's done-when asks for ("every route
  renders *something* correct") and the reason it ships on its own.
