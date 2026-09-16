# RKM Cinema — Mobile-First UI: the plan

> **Deliverable #1 of `MOBILE_FIRST_UI_BRIEF.md` §0/§12.** Written before a single line of mobile UI had
> been written, then executed phase by phase — ⚠ **M0 and M1 are built; M2–M9 are not.** The phases'
> own records live in `PROGRESS.md` and `adr/ADR-0011-mobile-layout-shells.md`; this document stays the
> plan, with a ✅ on the phases that landed.

- **Status:** ✅ **M0 AND M1 BUILT AND GREEN** (2026-09-16). Approved by him as "m0+m1 together".
  ⚠ **M2–M9 are planned, NOT built.** Commits: `43e7a16` (brief + plan) · `00cbf58` (M0) ·
  `48de90c` (M0 gate) · `eb18703` (M1) · `f0a5a0b` (M1 gate).
  ⚠ Phase records: `PROGRESS.md`'s top block, `adr/ADR-0011-mobile-layout-shells.md`.
- **His answers to §9, recorded:** Q1 — **cut from `dev`** (the repo rule won over brief §11) ·
  Q2 — **`docs/MOBILE_FIRST_UI_PLAN.md`**, not `docs/plans/` (this file's location) · Q3/Q4 — the
  defaults were accepted · Q5 — ⚠ **the desktop baselines were NOT committed**; see the note under §9 Q5.
- **Source brief:** [`MOBILE_FIRST_UI_BRIEF.md`](MOBILE_FIRST_UI_BRIEF.md) (untracked — see §9 Q1)
- **Branch (proposed):** `feat/mobile-first-ui`, cut from **`dev`** — ⚠ **not** "fresh from mainline"
  as brief §11 says; see §9 Q1, which is a real conflict with `ARCHITECTURE.md` §13/§14.
- **Plan location:** ⚠ the brief says `docs/plans/MOBILE_FIRST_UI_PLAN.md`; this file is at
  `docs/MOBILE_FIRST_UI_PLAN.md` — see §9 Q2.
- **Read with:** `ARCHITECTURE.md` §2, §11, §12, §17 · `adr/ADR-0009` (the bridge) · `adr/ADR-0010`
  (the offline page) · `NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4.5/§4.6
- **Baseline measured before writing (2026-09-16, on `dev` @ `5c59b0b`):**
  `npx tsc --noEmit` ✅ clean · `npx vitest run` ✅ **450 tests, 17 files**
- **ADR to write:** `docs/adr/ADR-0011-mobile-layout-shells.md` (0010 is the highest that exists)

---

## 0. The honest one-paragraph summary

There is **one** UI and this work does not add a second one. It adds a **presentation layer**: a
two-mode layout switch (`mobile` < 1024px, `desktop` ≥ 1024px), a phone-first shell inside the mobile
mode, and a per-route chooser that renders the existing desktop view verbatim at ≥ 1024px. The repo is
already in unusually good shape for this: **every business rule that a mobile screen will need already
lives in a pure `lib.ts`** (I inventoried all nine of them — §6), so the extraction surface is small and
the risk of a logic fork is low. The two places where that is *not* yet true are the sign-in submit and
the profile-pick submit, which are still inside their views (§6.2). The hard part is not the shell; it is
**`frontend/src/components/ui/Dialog.tsx` and four poster/card components whose primary actions are
revealed only on `:hover`** — on a phone those actions are simply invisible (§7.3).

---

## 1. Non-negotiables I am holding myself to

Inherited from brief §2, restated as checkable statements so the phases can be held to them:

| # | Rule | How it is enforced in this plan |
|---|---|---|
| 1 | **One UI.** No second bundle, route tree, or `m.` variant | One router; `layouts/mobile/` are React components inside the same bundle |
| 2 | **One implementation of every business rule** | §6: no mobile file may compute a rule; every rule is imported from the owning `lib.ts` |
| 3 | **One HTTP client** (`lib/api/client.ts`) | `layouts/mobile/**` may not import `fetch`, `axios`, or an api module except through a shared hook — asserted by a new vitest |
| 4 | **Zero changes under `apple/`**; bridge frozen at `v1` | Not one file; M7 consumes `bridgeAvailable()` / the existing `offline/lib.ts` |
| 5 | **Zero changes under `backend/`** | No phase in this plan needs one. If one does, §14 applies and I stop |
| 6 | **No bridge → no offline affordance at all** | M7 reuses `bridgeAvailable()`; `check_mobile_offline.py` asserts *no request is even made* |
| 7 | **The identity purge stays intact** | `clearCacheForIdentityChange()` is not touched; `check_mobile_layout_switch.py` asserts crossing 1024px does not sign anyone out |
| 8 | **`/login` and `/profiles` render outside the shell** | Unchanged in `router.tsx`; M2 gives them their own mobile presentation, still outside `AppShell` |
| 9 | **No service worker / PWA / Workbox** | None |
| 10 | **`Info.plist`, ATS, nginx cache headers untouched** | None. `nginx/default.conf` is not in this diff at all |
| 11 | **Existing gates pass unchanged at a desktop viewport** | §8. The one apparent exception is examined and avoided; see §8.2 |
| 12 | **No unscoped global CSS** | Every new rule is scoped to `[data-layout="mobile"]` / `.m-root` (§5.4) |

---

## 2. The decisions I am building to (brief §2a — restated as settled, not reopened)

1. **A tablet gets the mobile layout.** Two modes only. Inside the mobile shell the phone/tablet
   difference is **CSS only** — grid columns, type step, sheet max-width. **No component may branch on
   "is this a tablet".**
2. **The desktop views do not move.** `layouts/desktop/index.ts` is a thin re-export index. Zero
   relocations, so zero import-path churn and zero reviewer-map churn.
3. **"My downloads" means the household's.** No profile stamping, no bridge field, no Mac round. The
   Downloads screen gains one line of copy: *"On this device — shared by everyone in the household."*

**My own two additions to §2a, because the brief leaves them implicit and they change the diff a lot:**

4. **`layouts/mobile/` re-exports `MobileNav.tsx` from where it lives today** (`app/layout/MobileNav.tsx`)
   rather than moving it. ⚠ This is not a filing preference: `frontend/src/app/shell-contract.test.ts`
   reads that exact path and asserts it contains `env(safe-area-inset-bottom)`, and
   `tools/check_nav_access.py` mounts it from `nav-frame.html`. Moving the file would break an existing
   gate — which brief §9.1 forbids and §14 says to report instead of fixing. Evolution in place keeps
   §9.1 **literally** true, and the re-export keeps §3's symmetry (`desktop.MobileNav` doesn't exist;
   `mobile.MobileNav` does).
5. **The 768–1023px CSS boundary flip belongs to M1, not M0.** ⚠ Today the sidebar is `hidden md:flex`
   and the bottom bar is `md:hidden`, i.e. **the boundary is 768px**. M0 is the *provider*, the tokens and
   the base styles; if M0 also flipped the boundary, then between M0 and M1 an iPad in portrait
   (744–1023px) would lose its sidebar and get the bottom bar **while the routes are still the desktop
   views** — a visibly worse app shipped as "foundation". M1 flips the boundary in the same commit
   series that lands the shell, so **every phase is deployable without regressing any viewport.** M0's
   own done-when does not require the flip (it requires the *grid tokens* to reflow, which is a
   media-query inside the token block).

---

## 3. The layout-shell design (brief §12.2)

### 3.1 File tree

```
frontend/src/
├── lib/                     api client · query hooks · pure rules        ← UNCHANGED
├── features/                auth · library · player · offline · subs      ← logic UNCHANGED
│                            (the only edits are the §6 extractions, each its own commit)
├── components/ui/           Dialog · PopupMenu · Button · Card · Badge …
│                            (+ Sheet.tsx in M1 — an ADDITION, nothing edited)
├── layouts/                                                              ← NEW
│   ├── LayoutMode.tsx            the ONE switch: provider + useLayoutMode
│   ├── LayoutMode.test.tsx       the pure rule + the no-remount assertions
│   ├── Screen.tsx                per-route chooser: <Screen desktop={…} mobile={…}/>
│   ├── desktop/
│   │   └── index.ts              re-exports the existing views (thin, no logic)
│   └── mobile/
│       ├── index.ts              re-exports MobileNav (see §2.4) + the new screens
│       ├── MobileShell.tsx       the phone chrome: header · tab bar · sheet host
│       ├── MobileHeader.tsx      condensed top bar (search + avatar)
│       ├── MobileScreen.tsx      the standard screen frame: title · thumb zone · scroll body
│       ├── LoginScreen.tsx       M2   ┐ markup + local UI state only.
│       ├── PickerScreen.tsx      M2   │ The submit rules come from the §6.2 hooks.
│       ├── HomeScreen.tsx        M3   │
│       ├── BrowseScreen.tsx      M3   │
│       ├── SearchScreen.tsx      M3   │
│       ├── DetailScreen.tsx      M4   │
│       ├── RequestSheet.tsx      M4   │
│       ├── EpisodeList.tsx       M4   │
│       ├── PlayerScreen.tsx      M5   │
│       ├── SubtitleSheet.tsx     M6   │
│       ├── DownloadsScreen.tsx   M7   │
│       ├── AccountSheet.tsx      M8   │
│       └── HouseholdScreen.tsx   M8   ┘
└── app/router.tsx           EDIT: each route element wrapped in <Screen …>
```

### 3.2 `useLayoutMode()` — the exact signature

```ts
// frontend/src/layouts/LayoutMode.tsx
import { createContext, useCallback, useContext, useLayoutEffect, useSyncExternalStore, type ReactNode } from "react";

export type LayoutMode = "mobile" | "desktop";

/**
 * The ONE number. `< 1024px` is mobile — the phone AND the tablet (brief §2a).
 * ⚠ Tailwind's `lg` is 1024px, so the CSS and the JS agree by construction; the
 * constant exists so a future edit cannot move one and leave the other.
 */
export const MOBILE_MAX_PX = 1023;
export const MOBILE_MEDIA_QUERY = `(max-width: ${MOBILE_MAX_PX}px)`;

/**
 * The rule, PURE — no React, no matchMedia, testable in node.
 * There is exactly one input because there is exactly one question: does the viewport
 * match? Everything else (orientation, platform, "is this an iPad") is CSS's job.
 */
export function layoutModeFor(matchesMobile: boolean): LayoutMode {
  return matchesMobile ? "mobile" : "desktop";
}

/** Wraps the app ONCE, above the routes and below the query/auth providers. */
export function LayoutModeProvider({ children }: { children: ReactNode }): JSX.Element;

/** The ONE consumer hook. Components never call `matchMedia` themselves. */
export function useLayoutMode(): LayoutMode;

/** Sugar for the small number of legitimate boolean reads (the tab bar, the player). */
export function useIsMobile(): boolean;

/**
 * ⚠ NOT exported on purpose: `useLayoutMode()` from a component that also reads
 * `window.innerWidth` is how two sources of truth are born. One fact, one hook.
 */
```

**Mechanics, stated because each one is a bug avoided:**

- **`useSyncExternalStore`** subscribed to `matchMedia(MOBILE_MEDIA_QUERY)`'s `change` event — reactive
  to resize, to rotation, and to a split-view resize on iPad, in one mechanism. No `resize` listener
  arithmetic, no `window.innerWidth` polling, **no user-agent sniffing**.
- The provider writes **`document.documentElement.dataset.layout = mode`** in a `useLayoutEffect` (so
  `html`/`body`-level rules — the rubber-band background — have something to key off) **and** the mobile
  shell root carries `.m-root`. Two handles, because some rules must reach outside the shell.
- **The provider mounts above `createBrowserRouter`'s element**, so crossing the breakpoint re-renders
  the routed element but does **not** remount `QueryClientProvider` or `AuthProvider`. That is what makes
  "no refetch storm, no sign-out" true rather than hoped for, and M0 pins it with a test (§8.3).

### 3.3 The per-route chooser

```tsx
// frontend/src/layouts/Screen.tsx
export function Screen({ desktop, mobile }: { desktop: ReactNode; mobile: ReactNode }) {
  return <>{useLayoutMode() === "mobile" ? mobile : desktop}</>;
}
```

`router.tsx` changes from `element: <LibraryHomeView />` to
`element: <Screen desktop={<LibraryHomeView />} mobile={<HomeScreen />} />`. ⚠ **Only the chosen subtree
is rendered** — never both. Two live trees would double every `useEffect`, every observer and every
`aria-*` surface, and would make the desktop gates measure a page that also contains a phone.

### 3.4 The rule that makes it safe (brief §3, restated as an import ban)

A file under `layouts/mobile/` may contain **layout, markup, styling, interaction and local UI state.**
It may import: React, react-router, `components/ui/*`, its own siblings, and **named hooks/pure functions
from `features/*/lib.ts` and `features/*/api.ts`**. It may **not** contain:

- a `fetch`, `XMLHttpRequest`, or a direct `api.*` call it did not get from a shared hook;
- a status derivation, a date/size/number formatter, a watch-link builder, a guard decision, or a
  subtitle row key;
- a second copy of any string that the desktop view also renders (the empty state's sentence, the 401's
  sentence, "Preparing on the server…").

**Enforced, not requested:** a new vitest (`layouts/mobile/imports.test.ts`) walks every file under
`layouts/mobile/` and fails on a forbidden import or on a hand-rolled `toLocaleString`/`Math.round(…%)`.
That is the difference between a convention and a rule.

---

## 4. Inventory — every route and view, and its mobile decision (brief §12.1)

`Ext?` = does it need a §6 extraction first. `Risk` = risk to the desktop view.

### 4.1 Routes

| Route | Element today | Mobile treatment | Phase | Ext? | Risk |
|---|---|---|---|---|---|
| `/login` | `LoginView` (outside shell) | `LoginScreen` — full screen, one field per row, keyboard-aware submit | M2 | ✅ `useSignIn` | Low — view untouched |
| `/profiles` | `ProfilesView` (outside shell) | `PickerScreen` — avatar grid 2–3 across, ≥56px targets, full screen | M2 | ✅ `useProfilePick` | Low |
| `/` → `/library/home` | redirect | unchanged | M0 | – | None |
| `/settings` | `ConfigHealthView` | same view; one-column stack (already `sm:grid-cols-2` → 1 col on a phone) | M8 | – | None |
| `/settings/household` | `HouseholdView` (+`HouseholdModals`) | `HouseholdScreen` — mobile-usable, not mobile-beautiful; modals → sheets | M8 | – (rules already in `admin/lib.ts`) | Low |
| `/settings/password` | `PasswordView` | `AccountSheet` sub-screen; rules already pure in `settings/password.ts` | M8 | – | Low |
| `/library` | `LibraryLayout` | `MobileShell` hosts the same `LibraryLayout` (it owns the player + card handlers — **not forked**) | M1/M5 | – | Medium — see §4.3 |
| `/library/home` | `LibraryHomeView` | `HomeScreen` — Continue Watching hero, poster rails, folder rows | M3 | ✅ `useHomeRows` | Low |
| `/library/folder/:id` | `LibraryFolderView` | `BrowseScreen` — snap rails / 3-across grid, sticky headers, toolbar as a sheet | M3 | – (`library/lib.ts` owns filter/sort) | Low |
| `/library/movies`, `/library/shows` | `LibraryKindRedirect` | unchanged (a redirect has no presentation) | – | – | None |
| `/library/item/:itemId` | `ItemDetailPage` → `ItemDetailModal` (`Dialog`) | `DetailScreen` — backdrop hero, primary action pinned in the thumb zone, full-screen not a centred modal | M4 | ✅ episode progress + initials | Medium — `ItemDetail.tsx` is shared by the page and the modal; see §4.3 |
| `/discover` | `DiscoverView` | rails → snap-scroll; the same `buildWatchlistRows` | M3 (rails) | ✅ `continueWatchingItems` | Low |
| `/watchlist` | `WatchlistView` (+`WatchlistDetail`) | `BrowseScreen` family; chips/sorts as a sheet; "Load more" → sentinel scroll | M3 | ✅ `paginate` | Low |
| `/downloads` | `LibraryLayout` + `DownloadsView` | `DownloadsScreen` — bridge-gated; swipe-to-delete; the household line of copy | M7 | – (`offline/lib.ts` owns it) | Low |
| `/suggest` | `SuggestView` (+`SuggestDetailModal`) | filters as a sheet; results grid | M4 | – | Low |
| `/search` | redirect | unchanged | – | – | None |

### 4.2 Shared components, and what happens to each

| Component | Mobile decision | Phase |
|---|---|---|
| `components/ui/Dialog` | **Unchanged.** The mobile shell uses the new `Sheet` instead for bottom sheets. `Dialog` keeps serving the desktop tree, and stays available on mobile for the two places a centred dialog is still right (nothing in this plan). | M1 (adds `Sheet`) |
| `components/ui/PopupMenu` | **Unchanged.** Already portalled to `body` and viewport-clamped (`window.innerWidth` clamp at line 82) — it works on a phone as-is. Mobile **prefers** a sheet for anything with >3 items. | – |
| `components/ui/Button`, `Card`, `Badge`, `Icon`, `SectionHeader` | **Unchanged and reused.** This is deliberate: they are the product's own chrome. | – |
| `MediaCard` | ⚠ **findings 7.3** — the primary action and the ⋯ are `opacity-0 … group-hover:opacity-100`. Mobile needs a variant where they are **always visible** or reachable by a long-press. | M3 |
| `MediaListRow` | Same class of problem (`opacity-0 … group-hover:opacity-100` on the play button), plus a 3-col ↔ 6-col grid switch. Mobile uses a **list**, not this row. | M3 |
| `ContinueWatchingCard`, `ContinueWatchingRow`, `SimilarRow`, `CardRow` | Reused as-is in the mobile rails (they are already rail-shaped and fixed-width). | M3 |
| `WatchCard`, `SuggestCard` | Same hover-reveal finding; mobile variant needed. | M4 |
| `WatchlistDetail`, `SuggestDetailModal`, `HouseholdModals` | Their `Dialog` → `Sheet` on mobile. **Content is reused**; only the container changes. | M4/M8 |

### 4.3 The three genuine risks to the desktop tree

1. **`LibraryLayout` owns the full-screen player** and is mounted by `/library`, `/downloads` and every
   library child. The mobile shell must **host it**, not reimplement it — a second player host is a
   second place the player's `useEffect` graph can drift. M1 accepts a `chrome` prop (or nothing at all)
   so the same component renders in both shells.
2. **`ItemDetail.tsx` is shared** by `ItemDetailPage` (a route) and `ItemDetailModal` (a `Dialog`). Both
   currently render the *desktop* presentation. On mobile, `DetailScreen` renders `ItemDetail`'s content
   inside a full-screen route with its own action bar. ⚠ I will **not** fork `ItemDetail`; the plan is to
   give it the same treatment as §2.4 — a `variant`/`chrome` seam with the default unchanged, or an
   extraction of its action bar into a shared component. Which one is decided in M4 with the gates green
   before and after, as its own commit.
3. **`MediaCard`/`WatchCard`/`SuggestCard` hover actions** are the single most user-visible mobile defect
   in the app today. They are also the most-touched components in the repo. Mobile must get its own card
   (`layouts/mobile/PosterCard.tsx`) that reuses the same `onOpen`/`onPlay` handlers from `LibraryLayout`,
   so the desktop card is not edited at all. ✅ This is the cheapest safe answer and it is what the plan
   does.

---

## 5. The token table (brief §12.3)

### 5.1 Inherited — read out of `styles/index.css` and `tailwind.config.js`, not invented

| Token | Value | Role |
|---|---|---|
| `--bg` / `canvas` | `#08090B` | The page. **Also must be set on `html`** (brief §5, rubber-band) |
| `--surface-1` … `--surface-3` | `#101216` · `#15171C` · `#1B1E24` | Layered surfaces; `surface-3` is the elevated sheet |
| `--card` | `#17191E` | Card face |
| `--border` | `rgba(255,255,255,.08)` | Hairline |
| `--text-primary` / `-secondary` / `-muted` | `#F5F5F7` · `#A7AAB2` · `#70747E` | Type ramp |
| `--accent` / `--accent-hover` | `#FFC400` · `#FFD43B` | The signature yellow. **The only saturated thing on screen** |
| `--success` / `--warning` / `--danger` | `#35D07F` · `#FFB020` · `#FF5B5B` | The existing state vocabulary |
| `--radius-sm/md/lg/xl` | `6 · 10 · 14 · 20px` | Radii |
| `--space-1…8` | `4 8 12 16 24 32 48 64px` | Spacing |
| `--z-*` | sticky 10 · header 20 · dropdown 50 · popover 100 · **drawer 200** · modal 300 · toast 400 · **player 500** | Layer system — mobile reuses it, adds nothing |
| `shadow-card` / `-hover` / `modal` / `glow` | — | Depth |

⚠ **Finding 5.1a — there is no type scale.** Sizes are ad-hoc utilities (`text-[10px]`, `text-[13.5px]`,
`text-[12px]`, `text-[11px]`, `text-4xl`). The desktop tree is *not* retrofitted (that would move the
desktop and violate §9). The mobile shell gets a named scale and uses it; the desktop keeps its
utilities, and a reviewer can prove the separation by the scope selector.

⚠ **Finding 5.1b — the safe-area custom properties live inside `.rkm-player` only** (`index.css` lines
230–233). The mobile shell needs them on `:root`. Adding a `:root` block is **additive and inert** until
something reads it, and `.rkm-player` keeps its own definitions, so this cannot move the player.

### 5.2 Added — every one, with its reason

| New token | Value | Why it must exist |
|---|---|---|
| `--rkm-safe-top/-bottom/-left/-right` **on `:root`** | `env(safe-area-inset-*, 0px)` | Hoisted from `.rkm-player` (§5.1b). One definition, two consumers |
| `--m-nav-h` | `56px` | The thumb-zone bar's content height. The scroll-padding and the last row's bottom inset are computed from it — one number, so a taller bar cannot leave a row underneath it |
| `--m-tap` | `44px` | The brief's quality floor. Used as `min-height`/`min-width` on every interactive element in the mobile shell |
| `--m-gutter` | `16px` | The phone page gutter. `20px` at ≥600px via the same media queries as the grid |
| `--m-grid-cols` | `3` | Poster columns. `4` ≥600px, `5` ≥834px — **the one place phone and tablet differ, in CSS** |
| `--m-rail-w` | `38vw` (min 132px, max 180px) | A snap rail's card width: three-ish cards visible, art still readable |
| `--m-sheet-max` | `92dvh` | A sheet may not exceed the visible viewport. `dvh`, never `vh` |
| `--m-sheet-radius` | `20px` (`--radius-xl`) | A sheet's top corners — a bottom sheet is a surface, not a dialog |
| `--m-text-title` / `-hero` / `-body` / `-label` / `-meta` | `22/1.15` · `34/1.05` · `15/1.5` · `13/1.4` · `11/1.3` | §5.1a: the mobile type ramp, mobile-scoped only |
| `--m-input` | `16px` | ⚠ **Not a design choice.** Anything under 16px makes iOS zoom the page on focus and it never zooms back (brief §5) |

### 5.3 The mobile base styles, and exactly where they are scoped

Every rule below is inside a `[data-layout="mobile"]` (or `.m-root`) scope. **Nothing here touches a base
element selector the desktop tree depends on.** Each maps to one row of the brief's §5 trap table.

| Rule | Scope | Trap it closes |
|---|---|---|
| `html { background: var(--bg) }` | `[data-layout="mobile"]` on `html` | rubber-band scroll revealing a white page behind a dark UI |
| `-webkit-tap-highlight-color: transparent` **+ a real `:active` style** | `.m-root *` | the grey flash — and the dead-feeling app you get if you only remove it |
| `touch-action: manipulation` | `.m-root a, .m-root button, [role="button"]` | 300ms delay / double-tap zoom |
| `input, select, textarea { font-size: 16px }` | `.m-root` | the permanent iOS zoom-on-focus |
| `overscroll-behavior: contain` + a **`position:fixed` scroll-lock with `scrollTop` restore** | `.m-sheet` | a sheet scrolling the page behind it (⚠ `Dialog`'s `overflow:hidden` lock is not sufficient on iOS — that is why `Sheet` owns its own lock) |
| `-webkit-touch-callout: none; user-select: none` | `.m-root .m-art` **only** | long-press callout on poster art — **never on text the user might copy** |
| `prefers-reduced-motion` | already global in `index.css` `@layer base` | ✅ inherited, nothing to add |
| `@media (hover: hover)` | every desktop-only refinement | hover-revealed actions must have a tap path |

### 5.4 The one CSS rule I will not break

No mobile-first reset leaks into the desktop tree. The scope selector is `[data-layout="mobile"]`, set by
the provider, and the desktop mode never emits it. A reviewer verifies this with one grep and one
screenshot pair (§10).

⚠ **And a convention note, because M0 breaks one on purpose.** Today **there is not a single width-based
media query in `index.css`** — the only `@media` block is `prefers-reduced-motion` (line 101), and every
breakpoint in the app is a Tailwind utility class. That works while each component decides its own
paddings. It stops working for the poster grid, because the column count must be **one fact shared by
several components** (the grid, the rail's snap points, the skeleton that must match the real grid's
shape). So `--m-grid-cols` is a CSS custom property reflowed by a media query, and every consumer reads
the property. Tailwind's `sm:`/`md:`/`lg:` are still used everywhere the decision is **local** to one
element — the custom property exists only where a decision is **shared**. That is the whole rule.

---

## 6. The extraction list (brief §12.5)

### 6.1 The good news, measured

**All nine rule modules already exist and are pure**: `library/lib.ts` (44 exports), `playback/lib.ts`
(58), `watchlist/lib.ts` (40), `auth/lib.ts` (9), `admin/lib.ts` (27), `offline/lib.ts` (26),
`search/lib.ts` (7), `profiles/lib.ts` (6), `settings/password.ts` (4), `app/layout/lib.ts` (3).
A mobile screen that wants `resolveState`, `cardPrimaryAction`, `pickStreamMode`, `guardDecision`,
`actionsFor`, `activeSubtitleRowKey`, `rowStatusText`, `libraryTabsThatFit`, `filterLibraryItems` or
`householdSummary` **imports it.** This is why the extraction surface is small, and it is the single
biggest reason this work is safe.

### 6.2 What is genuinely still inline, and becomes a shared hook (each its own commit, before the view
that needs it)

| # | Where it lives today | What it becomes | Needed by | Phase |
|---|---|---|---|---|
| E1 | `LoginView.tsx:38-55` — `onSubmit`: the `busy` re-entry guard, `signIn()`, and ⚠ **lines 47-48, which are a second, weaker copy of `profiles/lib.ts::safeNext`** (`from && from !== "/login" && from !== "/profiles" ? from : "/library/home"` — no guard against `//host`, a backslash, or a scheme, all of which `safeNext` refuses and its tests pin) | `features/auth/useSignIn.ts` — the mutation + the busy guard + **`safeNext` called, not re-implemented** ⚠ Not exploitable today: `from` comes from router state, never a URL an attacker controls. It is still two copies of one rule, and it is the exact drift this architecture exists to prevent | `LoginScreen` | M2 |
| E2 | `ProfilesView.tsx:55-95` — `askFor`/`password`/`busyId`/`error`, the `api.profiles()` query (queryKey `["auth","profiles"]`), `choose()` (the ask-first rule) and `submit()` | `features/profiles/useProfilePick.ts` — the query + both mutations, keeping `isSelectable` / `requiresPassword` / `pickerErrorMessage` where they live | `PickerScreen` | M2 |
| E3 | ⚠ **`(cw?.items ?? []).filter(isContinueWatching)` appears twice** — `LibraryHomeView.tsx:102` **and** `DiscoverView.tsx:54` | `library/lib.ts::continueWatchingItems(items)`; both callers refactored to it | both screens | M3 |
| E4 | `LibraryHomeView.tsx:102-103,211,218` — the slice counts `14` / `16` and the "recently added" filter | `features/library/useHomeRows.ts` (one hook, the counts named) | `HomeScreen` | M3 |
| E5 | `WatchlistView.tsx:32-39` — `shown` + `list.slice(0, shown)` | `watchlist/lib.ts::paginate(list, shown)` + `PAGE` | `BrowseScreen` (infinite scroll) | M3 |
| E6 | ⚠ **`ItemDetail.tsx:48`** — `Math.min(100, Math.round(((ep.playback_position||0)/ep.runtime)*100))` and the copy at `:89` / `:518` | `library/lib.ts::episodeProgress(ep)` returning `{percent, remainingLabel}` | `EpisodeList` | M4 |
| E7 | ⚠ **`ItemDetail.tsx:117-119`** — `.filter(Boolean).slice(0,2).map(p => p[0])` — a **second copy of the initials rule** that `auth/lib.ts::initials()` already owns | delete the copy; call `initials()` | both | M4 |
| E8 | `MediaCard.tsx:81-87` — the episode/series meta line built with `.filter(Boolean).join(" · ")` | `library/lib.ts::cardMetaLine(item)` | `PosterCard` | M3 |

⚠ **E3 and E7 are drift, not duplication for convenience** — two copies of one rule, in the exact shape
this architecture exists to prevent. I am reporting them here rather than fixing them in passing
(brief §14: "you find a bug in the existing app. Report it."). Each is a behaviour-preserving commit with
the gates green before and after.

---

## 7. Design direction, and the wireframes (brief §12.4)

### 7.1 What I inherited, and the one thing I am spending boldness on

The product's identity is already decided: near-black layered surfaces, the yellow accent, Inter, the
seeded `art-N` gradients when there is no poster. The mobile shell is **the same product** — no rebrand,
no new palette, no second font.

**The one memorable moment: the Continue Watching hero.** On a phone it is the first thing the eye lands
on and the action the household actually wants (resume). It gets the poster's own art as a full-bleed
backdrop, the resume bar as part of the art (not a chip floating over it), and a single yellow **Resume**
in the thumb zone. Everything else stays quiet.

**Deliberately avoided** (brief §6): no tracked-out all-caps eyebrows, no identical rounded cards with the
same soft shadow, no middle-dot meta strings (⚠ the repo already joins with ` · ` — the mobile shell uses
`·` only inside the *existing* label strings it imports, never in new copy), no accent-coloured word in a
headline, no `→` on links.

### 7.2 The status vocabulary is imported, not rewritten

`requested → downloading → downloaded → available` come from `watchlist/lib.ts::STATE_LABEL` and
`offline/lib.ts::rowStatusText`. **"Preparing on the server…" is imported from `rowStatusText`** — the
mobile Downloads screen prints the same sentence the desktop one does, because a second copy of that
sentence is how it stops being true.

### 7.3 ⚠ The finding that shapes M3 and M4

**Every primary action on every poster is revealed by hover.** Measured in the source:

| Component | Line | What is invisible on a phone |
|---|---|---|
| `MediaCard.tsx` | 148, 169 | the play button and the ⋯ menu — `opacity-0 … group-hover:opacity-100` |
| `MediaListRow.tsx` | 124 | the play button — `opacity-0 … group-hover:opacity-100` |
| `WatchCard.tsx` | 184 | the whole action stack — `opacity-0 … group-hover:pointer-events-auto group-hover:opacity-100` |
| `SuggestCard.tsx` | 98 | the add-to-watchlist / details pair — same |

There is no `(hover: hover)` guard on any of them. **On a touch device these actions cannot be
discovered at all.** This is not a polish item; it is the app's primary interaction being unreachable,
and it is why the new `PosterCard` (mobile) puts the action in a **fixed position on the art** rather than
behind a hover state.

**Three more couplings that break on a phone for reasons nothing in the source shouts about:**

| Where | Line | What actually happens on a phone |
|---|---|---|
| `LibraryHomeView.tsx` | 281 | the hero's bleed is `-mx-4 sm:-mx-6 lg:-mx-8 xl:-mx-10` — it **cancels `AppShell`'s gutter by hand**. Any change to the shell's padding silently breaks the hero's left and right edges (it does not clip, it just stops being edge-to-edge). The mobile shell must either keep the same gutter token or the hero must stop hand-cancelling |
| `LibraryHomeView.tsx` | 367, 370 | the **Scan Library** button's label is `hidden sm:inline` — below 640px it is a **bare icon with no accessible name of its own** (it relies on `title`). On mobile it keeps its text |
| `LoginView.tsx` | 86 | the username input carries `autoFocus`. On iOS this raises the keyboard on arrival, which with a `min-h-dvh place-items-center` frame can scroll the card under the notch. Mobile does not autofocus; it focuses the field the person actually taps |

### 7.4 Wireframes — one per screen, thumb zone marked

`▓` = the thumb zone (bottom third of the viewport, this is inside the safe area)

```
SIGN IN (M2)                            WHO'S WATCHING (M2)              HOME (M3)
┌───────────────────────────┐          ┌───────────────────────────┐   ┌───────────────────────────┐
│                           │          │  Who's watching?          │   │ ▣ RKM        Rajeev   ⌕   │← header
│         ▶ RKM Cinema      │          │                           │   ├───────────────────────────┤
│                           │          │  ┌────┐  ┌────┐  ┌────┐   │   │ ┌───────────────────────┐ │
│  Username                 │          │  │ RK │  │ AM │  │ GS │   │   │ │  CONTINUE WATCHING    │ │
│  ┌───────────────────────┐│          │  └────┘  └────┘  └────┘   │   │ │  [ full-bleed art ]   │ │
│  │ 16px, one per row     ││          │  Rajeev  Amita  Guest     │   │ │  ▬▬▬▬▬▬▬▬░░░  62%     │ │
│  └───────────────────────┘│          │                           │   │ │  1h 04m left          │ │
│  Password                 │          │  ← 2 across at 320px      │   │ └───────────────────────┘ │
│  ┌───────────────────────┐│          │    3 across at ≥600px     │   │  Recently added           │
│  │ font-size: 16px       ││          │    (CSS only, no branch)  │   │  ┌────┐┌────┐┌────┐┌──   │
│  └───────────────────────┘│          │                           │   │  │    ││    ││    ││     │
│  ┌───────────────────────┐│          ├───────────────────────────┤   │  └────┘└────┘└────┘└──   │
│  │  Sign in     (16px)   ││          │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│   ├───────────────────────────┤
│  └───────────────────────┘│          │▓ (nothing — no nav here)▓ │   │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│  Incorrect username…      │          │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│   │▓ ⌂     ▤     ▤     ⋯     │
└───────────────────────────┘          └───────────────────────────┘   │▓ Home  Movies  TV   More  │
   no shell · no tab bar                 no shell · no tab bar         │▓ + safe-area-inset-bottom │
   (brief §2.8)                          (brief §2.8)                 └───────────────────────────┘

BROWSE A FOLDER (M3)                    SEARCH (M3)                      TITLE DETAIL (M4)
┌───────────────────────────┐          ┌───────────────────────────┐   ┌───────────────────────────┐
│ ← Movies          ⇅ ⋯     │← sticky  │ ←  ⌕ search your library  │   │ ←     [ backdrop hero ]   │
├───────────────────────────┤          ├───────────────────────────┤   │       [ poster ]          │
│ IN YOUR LIBRARY           │← sticky  │ RECENT                    │   ├───────────────────────────┤
│ ┌────┐┌────┐┌────┐        │  section │  sholay ·  the thing      │   │  Sholay  (1975)           │
│ │    ││    ││    │        │  header  ├───────────────────────────┤   │  2h 24m · Action · PG     │
│ └────┘└────┘└────┘        │          │ IN YOUR LIBRARY           │   │  ┌───────────────────────┐│
│  title   title   title    │          │  ▣ Sholay (1975)  Resume  │   │  │  ▶  Resume  1h 04m    ││
│ ┌────┐┌────┐┌────┐        │          │  ▣ Sholay Returns Details │   │  └───────────────────────┘│
│ │    ││    ││    │        │          ├───────────────────────────┤   │  ↓ Download   ⚙ Quality  │
│ └────┘└────┘└────┘        │          │ DISCOVER · not in library │   ├───────────────────────────┤
│  title   title   title    │          │  ▣ Sholay (1975)  + Watch │   │  Director …  Cast …       │
│        … scroll …         │          │  ▣ Sholay (1975)  + Watch │   │  Episodes  ▾ Season 1     │
├───────────────────────────┤          ├───────────────────────────┤   │  E1  ▬▬▬░  42%  22m left  │
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│          │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│   │  E2  not started          │
│▓ ⌂    ▤     ▤     ⋯      │          │▓ ⌂    ▤     ▤     ⋯      │   ├───────────────────────────┤
│▓ Home Movies  TV  More     │          │▓ ...tab bar, furniture   │   │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
└───────────────────────────┘          └───────────────────────────┘   │▓ ▶ Resume   ↓   ⋯         │← PINNED
   the black play pill and the ⋯                                          └───────────────────────────┘
   on a card are ALWAYS visible on
   mobile — never behind hover (§7.3)

REQUEST SHEET (M4)                      PLAYER (M5)                      SUBTITLES SHEET (M6)
┌───────────────────────────┐          ┌───────────────────────────┐   ┌───────────────────────────┐
│        ▬ drag handle      │          │                           │   │        ▬ drag handle      │
│  Request Sholay (1975)    │          │      [ the film ]         │   │  Subtitles                │
│                           │          │                           │   │  English (local)      ✓   │
│  Quality                  │          │   ⏸  ◀10s   ▶10s   ⚙     │   │  English - SUBRIP      ✓  │
│  ◉ 1080p  HD  (2.1 GB)    │          │                           │   │  Hindi                 ↧  │
│  ○ 720p                      │          │  ───●──────────  24:16    │   │  Search OpenSubtitles     │
│  ○ 4K                        │          │  1h 04m / 2h 24m          │   │  (used 82 of 100 today)   │
│  ⚠ 2 titles matched — pick   │          ├───────────────────────────┤   ├───────────────────────────┤
│    ┌───────────────────────┐│          │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│   │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│    │ Sholay (1975)         ││          │▓ ← ⏸  ──●──── 1× ⇱ ⛶ ⚙  │   │▓   (sheet sits on the     │
│    │ Sholay (1985)         ││          │▓  ≥44px targets, auto-hide│   │▓    player's own chrome)  │
│    └───────────────────────┘│          └───────────────────────────┘   └───────────────────────────┘
│  ┌───────────────────────┐  │             landscape-first · playsinline ·     vendor dead ⇒ the
│  │   Request  (16px)     │  │             progress 204 treated as SUCCESS      item's own tracks
│  └───────────────────────┘  │
└───────────────────────────┘

DOWNLOADS (M7)                          ACCOUNT SHEET (M8)               HOUSEHOLD (M8)
┌───────────────────────────┐          ┌───────────────────────────┐   ┌───────────────────────────┐
│  Downloads                │          │        ▬ drag handle      │   │  Household                │
│  On this device — shared  │          │  Rajeev  [ADMIN]          │   │  3 members · 2 active     │
│  by everyone in the       │          │  Administrator            │   ├───────────────────────────┤
│  household.               │          ├───────────────────────────┤   │  ┌───────────────────────┐│
│  1.5 GB of 41 GB free     │          │  Household          ADMIN │   │  │ RK  Rajeev   [YOU]    ││
├───────────────────────────┤          │  Account & password       │   │  │     [ADMIN] 3 libs    ││
│ Sholay                    │          │  Switch profile           │   │  └───────────────────────┘│
│ On this device · 1.5 GB   │          │  Settings                 │   │  ┌───────────────────────┐│
│ [ Play offline ] [Delete] │          ├───────────────────────────┤   │  │ AM  Amita  2 libs  ⋯  ││
├───────────────────────────┤          │  Sign out                 │   │  └───────────────────────┘│
│ Dune                      │          │                           │   │  ┌───────────────────────┐│
│ Preparing on the server…  │          │                           │   │  │ + Add member          ││
│ 12% ▬▬░░░░░░░░  [Cancel]  │          │                           │   │  └───────────────────────┘│
├───────────────────────────┤          ├───────────────────────────┤   ├───────────────────────────┤
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│          │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│   │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│▓ ⌂    ▤     ▤     ⋯      │          │▓  (sheet: drag or swipe    │   │▓ ⌂    ▤     ▤     ⋯      │
│▓ ...with Downloads        │          │▓   down to dismiss)        │   │▓ Mobile-usable, not      │
└───────────────────────────┘          └───────────────────────────┘   │▓ mobile-beautiful        │
   NO NAV ENTRY AND NO BUTTON                                            └───────────────────────────┘
   AT ALL when there is no bridge
```

---

## 8. The gates, per phase (brief §10/§12.8)

### 8.1 Every phase ends with these

```bash
cd frontend && npm run typecheck && npx vitest run && npm run build
cd backend  && python -m pytest tests/ -q
```

Plus the browser gates, against a freshly restarted `npx vite --port 5199 --strictPort`:

```bash
python3 tools/check_nav_access.py
python3 tools/check_login_flow.py
python3 tools/check_profile_picker.py
python3 tools/check_item_modal.py
python3 tools/check_household_ui.py
python3 tools/check_library_scan.py
python3 tools/check_cta_alignment.py
python3 tools/check_brand_lockup.py
python3 tools/check_subtitle_panel.py
python3 tools/check_query_cache.py
python3 tools/check_offline_page.py
python3 tools/check_search_fallback.py
python3 tools/check_password_change.py
python3 tools/check_injected_js.py
python3 tools/measure_player_layout.py
python3 tools/check_md_links.py
```

⚠ **Restart the dev server and prove it is fresh before believing any result** — the watcher does not
fire on this mount and an orphaned `vite` on :5199 has already produced a false PASS twice in this repo's
history (`frontend/harness/README.md`). `--strictPort` plus a module hash, every time.

### 8.2 ⚠ The one existing gate that *would* break, and why it does not

Moving the mobile boundary from 768px to 1024px changes what the app renders in **768–1023px**. I checked
every viewport every existing tool uses:

| Check | Viewports | In the 768–1023 band? |
|---|---|---|
| `check_brand_lockup` | 1440 | no |
| `check_cta_alignment` | 1280 | no |
| `check_household_ui` | 1440 | no |
| `check_item_modal` | 2560×1440 | no |
| `check_library_scan` | 1280 | no |
| `check_login_flow` | 1366×768 (width 1366) | no |
| `check_nav_access` | 1280 · **744×1024** · **390×844** | ⚠ 744 **is** in the band — **and it asserts the MOBILE surface there already**, so it stays mobile and passes |
| `check_offline_page` | 1280 | no |
| `check_password_change` | 1280 | no |
| `check_profile_picker` | 1366×768 | no |
| `check_query_cache` | 1280 | no |
| `check_search_fallback` | 1280 | no |
| `check_subtitle_panel` | 1366×768 · **390×844** phone | ⚠ 390 is below 768 already → stays mobile |
| `measure_player_layout` | 320 · 360 · 390 · **915×412** · **844×390** · **820×1180** · 1366 · 1280 · **1024×500** · 1920 | ⚠ 915, 844, 820 **are** in the band and are flagged `is_mobile=True` in the tool's own table — they stay mobile. 1024×500 is flagged `False` and is exactly the boundary → stays desktop |

⇒ **No existing check changes its verdict.** `measure_player_layout.py`'s own viewport table already
encodes a 1024px boundary (§18), which is independent evidence that this is the right line.

### 8.3 New checks I own (brief §10)

One harness frame (`frontend/harness/mobile-frame.html` + `.tsx`), **a fresh page per scenario** —
because that is the failure mode 8 tools have already hit here ("the frame did not load" at the 8th or
9th scenario; `ARCHITECTURE.md` §18 item 7). `window.__probe()` exposes mode, the shell's rect, the tab
bar's rect and every element poking outside the viewport.

| Tool | Proves | Phase |
|---|---|---|
| `tools/check_mobile_shell.py` | tab bar in the thumb zone, `env(safe-area-inset-bottom)` honoured, route switching by thumb, **no horizontal overflow at 320, 390 and 1023px** | M1 |
| `tools/check_mobile_layout_switch.py` | 390 → 1023 changes **no component tree, only CSS**; 390 → 1280 swaps the shell and causes **no refetch, no remount of the providers, no sign-out**; a rotation mid-session leaves the query cache intact | M0 (the provider half) + M1 |
| `tools/check_mobile_player.py` | chrome shows/hides, the scrubber seeks, `playsinline` is set, **a 204 progress reply is treated as success** | M5 |
| `tools/check_mobile_offline.py` | no bridge → no nav entry, no button, **and not even a bundle request**; bridge present → rows, zero-byte **"Preparing on the server…"**, cancel, delete | M7 |
| `tools/check_mobile_auth.py` | login and picker render full-screen outside the shell; a `profile-token` 401 lands on the picker **with the server's sentence**; 16px inputs (asserted as a computed style, because that one is invisible in every screenshot) | M2 |

⚠ **The stubs must answer exactly what the api answers** — a 204 with a null body where the api answers
204 (`ARCHITECTURE.md` §17.6: the 204 bug shipped through six green scenarios because the fake was
kinder than the route). Each new stub is generated from the same table as the real route's assertions, or
it is not trusted.

### 8.4 Falsification

Each new check is **falsified before it is trusted** — this repo has shipped a check that could not fail
more than once (`check_brand_lockup`'s assertion C, `check_cta_alignment`'s `--expect-broken`). The
pattern: revert the rule, require the named assertion to go RED, restore, re-run green. A new check with
only a green run is not evidence.

### 8.5 The phone round (his, and the only thing that closes a phase)

```
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\rkm-cinema.ps1 apply
```

⚠ `apply` rebuilds `web` from source; the phone sees it on the next load with **no app rebuild**
(`ARCHITECTURE.md` §17.5). Every phase's done-when in §11 is written to be checkable in under a minute
on the phone, in his own words — because rule 3 of the branch strategy requires *both* a green suite
**and** his UI acceptance before `main` moves.

---

## 9. New open questions (brief §12.7) — decisions I am NOT making alone

The brief's three original questions are settled (§2). These are **new**, each found while reading the
ground truth. Every one has a recommendation and a cost-of-changing-later.

**Q1 — Which branch, really? ⚠ Please confirm.**
Brief §11: *"`feat/mobile-first-ui`, cut fresh from mainline."* `PROGRESS.md`'s first block and
`ARCHITECTURE.md` §13/§14: *"Every new branch is cut from `dev`"*, `dev` is what he deploys, and `main`
only ever advances by fast-forwarding to `dev` (`main` is currently an ancestor of `dev`; `dev` is 24
commits ahead and in sync with `origin/dev`).
**Recommendation: cut from `dev`.** Cost of changing later: a rebase. Per brief §0 this is exactly the
class of conflict I raise rather than resolve — but note that following §11 literally would put the
branch on work he cannot deploy, and would violate the invariant that keeps `main` a fast-forward.

**Q2 — Where does the plan live?**
Brief §12 says `docs/plans/MOBILE_FIRST_UI_PLAN.md`. The repo has **24 sibling `docs/*_PLAN.md` files
and no `docs/plans/` directory**; `ARCHITECTURE.md` §3 lists plans directly under `docs/`.
**Recommendation: `docs/MOBILE_FIRST_UI_PLAN.md`** — which is where this file is. Cost of changing
later: `git mv`, one line in the ADR.

**Q3 — How much offline affordance is "no affordance"?**
Brief §8 and §2.6 are explicit that without a bridge there is nothing. In the browser, mobile still shows
a **Continue Watching** row that resumes from the *server's* position — that is online behaviour and
stays.
**Recommendation: keep it.** No question there. The question is narrower: on mobile, should the
**Downloads** entry be inside the `More` sheet on a phone (as it is today) or should the tab bar carry it
directly when the bridge exists? Today `libraryTabsThatFit` measures a bar of Home + libraries + More.
**Recommendation: leave the measurement rule alone** and let Downloads live in `More`. Changing the tab
allocation is a change to `app/layout/lib.ts`'s tested invariant and is not needed for the brief.

**Q4 — the 768–1023px two-pane detail.**
Brief §4 mentions "optional two-pane detail at ≥768px" as a CSS-only possibility.
**Recommendation: do NOT build it.** It is a second markup arrangement for the detail screen, which is
the same cost as the third mode §2a rejected, and the brief's own rule forbids a component branching on
"is this a tablet". Detail is a full-screen route at every mobile width. If he wants it, it is a
media-query inside `DetailScreen` and one extra wireframe — cheap, but it should be *asked for*.

**Q5 — desktop screenshot baselines: may I commit ~5 PNGs?**
Brief §9.4 requires before/after desktop screenshots attached to each phase report. The repo has exactly
**one** committed image (`apple/ios/.../AppIcon-1024.png`) and no screenshot directory.
**Recommendation was: commit them. ⚠ I did not, and here is why.** The screenshots the sandbox can
produce are of the **harness frame** (`frontend/harness/mobile-frame.html` — the real `AppShell` over a
stubbed api), not of the deployed app: there is no Docker in this sandbox (`docker: command not found`)
and the real stack runs on his RKM-HP box. Committing those as "the desktop baseline" would claim
something they are not. They were produced at eight widths
(`--shots` on `check_mobile_layout_switch.py`) and are the phase's evidence; **say the word and I will
either commit them as clearly-labelled harness screenshots or capture the real pages on his stack.**

**Q6 — the brief itself is untracked.**
`MOBILE_FIRST_UI_BRIEF.md` has never been committed (it was deliberately left out of the merge).
**Recommendation: commit it as the first commit of the branch** (`docs: the mobile-first UI brief`), so
the plan's link to it resolves and the ADR can cite it. Cost: one file.

**Q7 — `ROUTE_LEVELS` / `check_injected_js` etc.**
No backend route changes are planned, so no `ROUTE_LEVELS` line is needed. If a phase turns out to need
one, §14 applies and I stop.

---

## 10. The regression argument (brief §12.8) — how a reviewer is convinced the web layout did not move

Four independent pieces of evidence, in increasing strength:

1. **A frozen baseline.** M0 commits desktop screenshots at 1280 / 1440 / 2560 before any change. Every
   later phase attaches the same five shots. A reviewer diffs them; a pixel that moved is visible without
   reading a diff.

2. **Every existing gate, unchanged and unadapted.** Brief §9.1 is a contract, and §8.2 above shows by
   audit that no existing tool or vitest test changes its verdict — the band the boundary crosses is
   asserted by no desktop check, and the three tools that *are* in that band already assert the mobile
   surface. ⚠ **If any of them disagrees with this audit, that is a finding I report, not a check I
   loosen.**

3. **The diff is legible by construction.** `layouts/mobile/**` and `layouts/Screen.tsx` cannot be the
   cause of a desktop change, because the desktop mode never renders them. So the only files that can
   move the desktop tree are:
   - `app/router.tsx` (wrapping elements in `<Screen>` — a no-op at ≥1024px),
   - `index.css` (new rules, all inside `[data-layout="mobile"]` / `.m-root`, plus the additive
     `:root` safe-area hoist),
   - `main.tsx` (mounting one provider),
   - and the **named §6 extraction commits**, each of which is behaviour-preserving and gated before and
     after.

   One command states it:
   ```bash
   git diff --stat <base>...feat/mobile-first-ui -- frontend/src/features frontend/src/components
   ```
   ⇒ must contain **only** the E1–E8 commits' files, each with a `refactor(library): …` /
   `refactor(auth): …` subject. Anything else in that diff is a bug in this plan, not a surprise.

4. **The CSS scope is greppable.** Every new rule sits under `[data-layout="mobile"]` or `.m-root`;
   `grep -c 'data-layout="mobile"' frontend/src/styles/index.css` and a read of each rule's nesting is
   the proof. A mobile-first reset that leaked into the base layer would be visible as an unscoped
   selector, and there is none.

---

## 11. The phase plan (brief §13) — done-when, checkable on the phone in under a minute

Ordering is the brief's, with one change justified in §2.5 (M1 owns the CSS boundary flip).

### ✅ M0 — Foundation · no visible change · **BUILT** (`00cbf58`, `48de90c`)
**As planned, except one deliberate deviation:** `layouts/Screen.tsx` (the per-route chooser) was **not**
written here. It lands with the first route that has a mobile counterpart (M3) rather than sitting unused
for three phases — dead code in a phase whose whole claim is "nothing changed".
**Delivered.** `LayoutMode.tsx` (provider + `useLayoutMode` + the pure `layoutModeFor`), `LayoutDebug.tsx`
(`?layout=debug`, inert without the param), `layouts/desktop/index.ts` and `layouts/mobile/index.ts`
re-export indexes, the token additions (§5.2), the **scoped** mobile base styles (§5.3), the additive
`:root` safe-area hoist, `LayoutMode.test.tsx` (which reads Tailwind's own resolved `lg`),
`importRule.ts` + `imports.test.ts` (28 checks), `tools/check_mobile_layout_switch.py` (9 scenarios,
`--selftest` 23/23), and `router.tsx` re-pointed through `layouts/desktop` (a runtime no-op).
⚠ **The 768px→1024px CSS boundary was NOT flipped here** (§2.5) — M1 owns it, so no phase leaves the
768–1023px band worse than it found it.

**Done when (phone, < 1 min):** open the app — **it looks and behaves exactly as it does today at every
size**; append `?layout=debug` and a corner readout says `mobile` on the phone and `desktop` on the
laptop, and rotating/reshaping the window flips the word with no reload and no visible change to the
page. ✅ **Measured:** `--m-grid-cols` is `''` and `.m-grid` computes `display:block` at 1024, 1280 and
1440px — the mobile rules do not *apply*, which is a stronger claim than "it looks the same".

### ✅ M1 — Shell & navigation · the boundary flips · **BUILT** (`eb18703`, `f0a5a0b`)
**Deviation, reported (§14, ADR-0011): there is NO `MobileHeader`.** It would be a second `Header`, which
means a second `GlobalSearch` and a second `AccountMenu` — two copies of the interaction wiring
`check_nav_access` exists to keep in one place. `Header` already carries the safe-area inset, the 64px
minimum and both controls, so the mobile shell uses it as-is and **the tab bar is the whole of the new
chrome**.
**Delivered.** The boundary flip (`Sidebar` `md:flex`→`lg:flex`, `MobileNav` `md:hidden`→`lg:hidden`,
`AppShell` `md:pb-12`→`lg:pb-12`), `AppShell` choosing its chrome without moving `<Outlet/>`, the 44px
token floor on tabs and sheet rows, `components/ui/Sheet.tsx` + `sheetRules.ts` (11 pure tests), and
`tools/check_mobile_shell.py` (5 scenarios, `--selftest` 26/26). Also: `MobileNav` keeps its **file, its
exports and its rules** (`libraryNavEntries`, `libraryTabsThatFit`) — §2.4 explains why moving it would
have broken two existing gates.

**Done when (phone, < 1 min):** every route reachable with the thumb from the tab bar and the More sheet;
no route renders a broken screen; **iPad portrait (744–1023px) now gets the same bar**; the page never
scrolls sideways. ✅ **Measured** at 320 / 390 / 1023, plus the sheet's lock, scroll, drag and Escape.
⚠ **The routes still render the existing desktop views inside the shell** — that is what this phase's
done-when asks for, and M3 onwards replaces them one at a time.

### M2 — Identity screens
**Scope.** E1 + E2 extractions (separate commits), `LoginScreen`, `PickerScreen`, the account menu as a
sheet, both 401 answers. `/login` and `/profiles` stay outside the shell. ⚠ **No `autoFocus`** on the
username field (§7.3) and every input at 16px (§5.2) — those two are the whole of what "keyboard-aware
submit" means here.
**Done when (phone, < 1 min):** sign in, pick a profile, switch profile, and sign out — with no pinch, no
zoom when a field is focused, and nothing clipped by the home indicator.

### M3 — Library & search
**Scope.** E3 · E4 · E5 · E8 extractions, `HomeScreen` (the Continue Watching hero), `BrowseScreen`,
`SearchScreen`, mobile `PosterCard` (**actions always visible — §7.3**), the toolbar and filters as
sheets, empty and degraded states, virtualisation above ~200 rows. ⚠ Three couplings from §7.3 are in
this phase's scope, not M9's: the hero's hand-cancelled gutter, **Scan Library keeping its text label
below 640px**, and the skeleton grid matching `--m-grid-cols`.
**Done when (phone, < 1 min):** browse a 500+ title folder and it is smooth; **the play button is visible
on every poster without a hover**; nothing overflows at 320px; the iPad at 834px shows more columns with
no new component.

### M4 — Title detail & request
**Scope.** E6 + E7 extractions, `DetailScreen` (backdrop hero, pinned action bar in the thumb zone),
`EpisodeList`, `RequestSheet` with quality profiles and the **ambiguity list as a list**, the honest
404/502/503 sentences, and the `ItemDetail` reuse decision (§4.3.2).
**Done when (phone, < 1 min):** find a title, open it, and request it end to end — including the
"2 titles matched, pick one" case, and each error shown as a sentence rather than a stack.

### M5 — Player
**Scope.** `PlayerScreen`: landscape-first, `playsinline` + `webkit-playsinline`, tap-to-reveal chrome
with auto-hide, a thumb-sized scrubber, ±10s, lock, resume, and progress reporting that treats **204 as
success** (`playback/api.ts` already returns `undefined` on 204 — assert it on the mobile path).
⚠ iOS owns brightness and volume; no custom controls for either.
**Done when (phone, < 1 min):** a film plays, scrubs, resumes, and the position lands in Continue
Watching.

### M6 — Subtitles
**Scope.** `SubtitleSheet` from the player. Reuses `activeSubtitleRowKey()` — **no re-derivation of which
row gets the tick** — plus search, select, disable, quota display, and vendor-failure degradation.
**Done when (phone, < 1 min):** with the vendor dead, the sheet still lists and applies the item's own
tracks, and the tick is on the row that was tapped.

### M7 — Offline & downloads
**Scope.** `DownloadsScreen`: bridge-gated, rows with state/bytes/total, the imported
**"Preparing on the server…"** label at zero bytes, swipe-to-delete, play-from-device with **no
`playback-info` call**, the two-owners rule, and the household line of copy (§2.3).
**Done when:** in the app — download, airplane mode, play. In the browser — **no trace of the feature
exists** (no nav entry, no button, not even a request).

### M8 — Admin & settings
**Scope.** `AccountSheet`, `HouseholdScreen`, the password flow, `ConfigHealthView`'s quiet banner, and
the `profile-token` refusal as a sentence.
**Done when (phone, < 1 min):** an administrator can add a member, change a password and read the health
banner without rotating the phone.

### M9 — Polish & proof
**Scope.** Performance pass (`loading="lazy"`, `decoding="async"`, explicit `aspect-ratio`,
`content-visibility: auto`), a11y pass (visible focus, 44×44 targets, contrast at 20% brightness),
reduced motion, **the largest Dynamic Type setting the WebView reports**, the desktop regression report,
`PROGRESS.md`, `ADR-0011`, and **one paragraph** appended to `ARCHITECTURE.md` §12.

⚠ **EXPLICITLY INCLUDES THE VIRTUALISATION HE ASKED FOR (his report, 2026-09-16: the Movies tab takes an
extra second to populate, 711 titles).** Brief §5 already states the rule — *"Virtualise any list that
can exceed ~200 rows"* — and `LibraryFolderView` currently maps every item to a `MediaCard` with no
windowing. ⚠ **Measure before changing anything:** if a SECOND visit to the same folder is instant it is
the fetch (React Query holds it 30s stale), not the render — and a fetch fix is a backend phase, which
needs §14. See `PROGRESS.md`'s open item for the full measurement plan. The same applies to Search
results and the Watchlist.

**Done when:** every gate green, the M9 desktop screenshots match M0's baseline, and the docs are written.

---

## 12. What I will stop and ask about (brief §14, restated as my own trigger list)

I stop rather than decide if: a mobile view needs data no existing hook provides; an extraction cannot be
made behaviour-preserving; a fix appears to need `apple/`, the bridge, `Info.plist`, nginx headers, or
`.env`; an existing `tools/check_*.py` fails and the honest fix is to change the check; a screen seems to
need a third layout mode or a component wants to branch on "is this a tablet"; a phase's scope grows past
one sitting; or I find a bug in the existing app.

⚠ **Two of those are already live**: E3 and E7 (§6.2) are pre-existing bugs — two copies of one rule
each. They are reported in this plan and will be fixed as named, behaviour-preserving refactors, **not**
inside a mobile phase where they would be invisible in the diff.

---

## 13. In one line

The phone gets a layout designed for a phone, built inside the one app, with one copy of every rule — and
the web comes out of it untouched, proved by a frozen baseline, every existing gate unchanged, and a diff
whose only reachable-desktop content is eight named refactors.
