# RKM Cinema — Mobile-First UI Brief for Hermes

> **Read `docs/ARCHITECTURE.md` §2, §11, §12 and §17 before writing a single line.** This document
> assumes them and does not repeat them. Where this brief and `ARCHITECTURE.md` disagree,
> `ARCHITECTURE.md` wins and you raise the conflict instead of resolving it yourself.

**Audience:** Hermes (the implementing agent).
**Deliverable order:** a written plan first → human approval → implementation, phase by phase, on a new
branch. Do not start Phase M1 until the plan has been approved.

---

## 0. Your operating procedure

1. **Read the ground truth.** `docs/ARCHITECTURE.md`, `docs/PROGRESS.md` (current state only —
   it is ~5,100 lines; skim the head), `frontend/src/` in full, `frontend/harness/*.html`,
   `tools/check_*.py`, `nginx/default.conf`, and `docs/adr/ADR-0009` (the bridge).
2. **Write the plan** at `docs/plans/MOBILE_FIRST_UI_PLAN.md` (contents specified in §12). Include an
   inventory of every existing view and the mobile decision for each. **Stop and ask for approval.**
3. **Cut the branch** `feat/mobile-first-ui` off the current mainline. Every phase is a commit series on
   that branch; every phase ends green and deployable on its own.
4. **Implement one phase at a time.** At the end of each phase: run the gates (§10), update
   `docs/PROGRESS.md`, and report what shipped, what you deferred, and what you learned that changes the
   remaining phases. Then stop for review before the next phase.
5. **The three open decisions are settled — see §2a.** Do not reopen them. If you find a *new* decision
   that is a product call rather than an engineering one, raise it instead of deciding it (§14).

---

## 1. The brief in one paragraph

RKM Cinema is a private household cinema — one family, a few profiles, a library of films and series
they already own, on a phone that is usually held one-handed on a sofa at night. The web layout is
mature and finished; it is not the subject of this work and must come out of it byte-identical in
behaviour. Your job is that **the same React app, viewed on a phone (in a browser or inside the iOS
shell), presents a layout designed for a phone from the ground up** — thumb-reachable navigation,
poster-led browsing, sheets instead of dialogs, a player that behaves like a native player, and the
offline/downloads feature as a first-class citizen rather than a desktop panel squeezed into 390px.

---

## 2. Non-negotiables (inherited — breaking one of these fails the phase)

| Rule | Why | Where it comes from |
|---|---|---|
| **There is ONE UI.** You are not building a second app, a second bundle, a second route tree, or an `m.` variant | A second UI is a second thing to keep in sync, and the whole architecture is built to avoid it | §2, §12 |
| **There is ONE implementation of every business rule** | Mobile components must not re-derive status, watch links, guard decisions, or subtitle row keys | §4, §12 |
| **There is ONE HTTP client:** `frontend/src/lib/api/client.ts` | It holds the 401 / `X-RKM-Auth-Problem` rule. A `fetch()` anywhere else silently loses the profile-stale behaviour | §12 |
| **Zero changes under `apple/`.** The bridge contract is frozen at `v1` for this work | A bridge change costs a Mac build round and a page+app pair release | §17.5, §17.3 |
| **Zero changes under `backend/`** unless a phase is explicitly approved for it. If approved: additive-only, plus a `ROUTE_LEVELS` line and a pytest | ADR-0001 additive-only; the route-protection inventory fails on an undeclared route | §5, §14 |
| **No bridge → no offline affordance at all.** Never a disabled button, never a "download unavailable" message | `bridgeAvailable()` already encodes this; an older app viewing a newer page is normal | §17.1 |
| **The identity purge stays intact.** `AuthProvider` purges the React Query cache on every identity change | One person's rows must never flash for the next | §12 |
| **`/login` and `/profiles` render outside the app shell** — your mobile shell must not swallow them | They must paint when every other route is refusing | §12 |
| **No service worker. No PWA install flow. No Workbox.** | `navigator.serviceWorker` is absent in this WebView (measured, E2) | §17.6 |
| **Do not touch `Config/Info.plist`, ATS, or nginx cache headers** | ATS is `NSAllowsArbitraryLoads` only; adding a sibling key breaks plain http and loopback outright | §17.6 |

---

## 2a. Decisions already made — build to these

Three questions were open when this brief was drafted. All three are now decided, and each was decided
the same way: **the option with the fewest code paths and the smallest diff wins.** Record them in the
ADR as settled, with the rejected alternatives and this rationale.

| Decision | Settled answer | Why this one |
|---|---|---|
| **Does a tablet get the mobile layout?** | **Yes.** Two modes only — `mobile` (< 1024px, phone *and* tablet) and `desktop` (≥ 1024px). The tablet is the same shell with a wider poster grid and a larger type step, driven by CSS, not by a third branch | A third "tablet" mode means a third set of components, a third set of harness checks and a third thing to regress forever. The iPad in the shell is held, not moused, so the thumb-zone shell is the right one anyway. Column count and type scale are a media query inside the mobile shell — no extra TS, no extra branch |
| **Do the desktop views move into `layouts/desktop/`?** | **No.** They stay exactly where they are. `layouts/desktop/` is a thin index that re-exports them | A physical move is a large diff with zero behaviour change, it breaks every existing import path and every reviewer's mental map, and it puts the mature web layout at risk for a filing preference. Re-export costs one file and is reversible |
| **What does "my downloads" mean on a shared iPad?** | **Nothing changes.** The file stays the household's (ADR-0007 D6). The Downloads screen states it in one line of copy: *"On this device — shared by everyone in the household."* | This is the zero-code answer to a real ambiguity. Per-profile downloads would mean profile-stamped native storage, a bridge field, a Mac round and a v2 contract — a large, irreversible piece of work to solve a labelling problem. A sentence solves it today, and leaves the door open if he later wants the real thing |

**Consequences for the rest of this document:** §4's `compact` tier disappears — it is a media query
inside the mobile shell, not a mode. §3's file tree is the one you build. §8's downloads screen gains one
line of copy and nothing else.

---

## 3. The central decision: one app, two layout shells

This is the architectural shape of the work. Propose it in the plan; do not deviate without approval.

```
frontend/src/
├── lib/            api client · query hooks · pure rules        ← SHARED, unchanged
├── features/       auth · library · player · offline · subs     ← SHARED logic, unchanged
│                   (existing desktop views stay exactly where they are)
├── layouts/
│   ├── LayoutMode.tsx        the ONE switch: mobile | desktop   ← NEW
│   ├── desktop/              re-exports the existing views      ← NEW, thin
│   └── mobile/               new phone-first presentation       ← NEW, all your work
└── routes/         each route renders <Mobile/> or <Desktop/>   ← edited, minimally
```

**The rule that makes this safe:** a file under `layouts/mobile/` may contain **layout, markup, styling,
interaction and local UI state — and nothing else**. No `fetch`. No status derivation. No date/size
formatting invented locally. No copy of a guard decision. It consumes the same hooks the desktop view
consumes.

**When a mobile view needs data the desktop view computed inline:** extract that computation into a
shared hook or pure function first, refactor the desktop view to use the extraction, prove the extraction
is behaviour-preserving with the existing gates, commit that refactor **separately** — and only then
build the mobile view on top. Never fork the logic. A logic fork is the one failure mode this whole
architecture exists to prevent.

**Settled (§2a):** existing desktop views are **not moved**. `layouts/desktop/index.ts` re-exports them
from where they live today. That file exists so routes read symmetrically (`desktop.TitleDetail` /
`mobile.TitleDetail`) and so a future move, if it is ever wanted, is a one-file change.

---

## 4. The layout switch

**Two modes. Not three.**

```ts
// One evaluation, at the root, reactive to resize/orientation. No user-agent sniffing.
type LayoutMode = 'mobile' | 'desktop'
mobile  : matchMedia('(max-width: 1023px)')   // phone AND tablet — one shell
desktop : >= 1024px                            // existing layout, untouched
```

Inside the mobile shell, the phone/tablet difference is **CSS only** — poster grid columns, type step,
sheet max-width, optional two-pane detail at ≥ 768px:

```css
/* one shell, breakpoints inside it — no second component tree */
.m-grid        { --cols: 3; }
@media (min-width: 600px) { .m-grid { --cols: 4; } }
@media (min-width: 834px) { .m-grid { --cols: 5; } }
```

⚠ **No component may branch on "is this a tablet".** If a screen genuinely cannot be expressed as one
markup tree across 320–1023px, that is a finding to report (§14), not a third mode to add.

Rules:

- **Viewport decides layout. The native shell never decides layout.** `bridgeAvailable()` gates
  *capabilities* (downloads, play-offline), not presentation. A phone browser on the tailnet gets the
  same mobile layout minus the offline affordances.
- **The switch must not remount the data layer.** Crossing the breakpoint (rotating an iPad) swaps
  presentation only; the React Query cache, the session and the player state survive. Prove this in the
  harness — rotate mid-session and assert no refetch storm and no sign-out.
- **One provider, one hook, one import site.** `useLayoutMode()` is read by routes and by a small number
  of shared shells. A component that reads it to change three paddings is a component that should have
  been two components.
- **`prefers-reduced-motion` and `(hover: hover)` are read in CSS, not in JS.**

**Settled (§2a):** the iPad in the shell gets the **mobile** layout — thumb nav, sheets, wider grid. It
is held, not moused, and one shell is one thing to build, check and maintain.

---

## 5. iOS WKWebView field guide — the traps that will cost you a round

The shell loads the live page (§17.1), so every one of these is a web fix, deployed with
`.\rkm-cinema.ps1 apply`, with no app rebuild. That is the good news. These are the ones that bite:

| Trap | The fix |
|---|---|
| `100vh` is wrong in WKWebView and changes as chrome moves | `100dvh` with a `-webkit-fill-available` fallback; never lock a scroll container to `vh` |
| Notch, home indicator, rounded corners | `viewport-fit=cover` + `env(safe-area-inset-*)` on the bottom nav, the player chrome and every sheet. Bottom nav padding is `env(safe-area-inset-bottom)`, not a magic 34px |
| An input under 16px makes iOS zoom the page on focus, permanently | Every `input`/`select`/`textarea` at `font-size: 16px` minimum. This includes search |
| The keyboard covers fixed footers | Use `window.visualViewport` (`resize` + `offsetTop`) for anything pinned while an input is focused |
| Grey flash on every tap | `-webkit-tap-highlight-color: transparent` **plus** a real `:active` state — removing the highlight without replacing it makes the app feel dead |
| 300ms delay / double-tap zoom on controls | `touch-action: manipulation` on interactive elements |
| A modal scrolls the page behind it | `overscroll-behavior: contain` on sheets; a proper body scroll-lock (position-fixed + restore scrollTop) for full-screen sheets |
| `<video>` goes native-fullscreen on iPhone and you lose your controls | `playsinline` **and** `webkit-playsinline` on the element; decide deliberately where you hand over to native fullscreen |
| Hover-revealed actions are invisible on a phone | Every action reachable by tap. `@media (hover: hover)` for the desktop-only refinements |
| Rubber-band scroll reveals the page background behind a dark UI | Set the background on `html`, not only on a wrapper |
| Multiple `<video>` elements preloading kill a cellular connection and the battery | One media element at a time; `preload="none"` outside the player |
| Long-press on a poster fires the iOS callout menu | `-webkit-touch-callout: none` + `user-select: none` on poster art, but never on text the user might want to copy |

**Performance floor on a phone:** posters come through `/api/jellyfin/poster` (nginx caches artwork 7
days). Use `loading="lazy"`, `decoding="async"`, explicit `width`/`height` or `aspect-ratio` to stop
layout shift, and `content-visibility: auto` on long lists. Virtualise any list that can exceed ~200
rows. If you find yourself wanting a server-side thumbnail size parameter, that is a **backend phase** —
propose it, do not smuggle it in.

---

## 6. Design direction

Read `ARCHITECTURE.md` and then read the actual stylesheet. **Derive the palette, type and radii from
what `frontend/src/` already uses** — the mobile layout is the same product, not a rebrand. Your plan
must contain a token table (4–6 named colours with hex, the type scale with roles, the spacing scale, the
radius scale) showing what you inherited and the *few* tokens you are adding, each with a reason.

Direction, for a dark room and one hand:

- **The poster is the interface.** Art carries the identity; chrome stays quiet. Let the artwork be the
  only saturated thing on screen.
- **Thumb zone is law.** Primary navigation and the primary action of every screen live in the bottom
  third. Nothing important in the top corners.
- **Sheets, not dialogs.** Request-a-title, quality profile, subtitles, profile switch, filters — all
  bottom sheets with a drag handle and a swipe-to-dismiss. A centred modal on a phone is a desktop habit.
- **State is a sentence, not a spinner.** The status vocabulary already exists (requested → downloading →
  downloaded → available). Reuse its exact words, including **"Preparing on the server…"** — that label
  was written because a zero-byte row was honest and the old label was not (§17.4).
- **Motion answers a tap.** Sheet open, row expand, download confirm. No scroll-triggered entrances, no
  hover transitions on cards, no page-load choreography.
- **Spend the boldness once.** Pick one memorable moment — the Continue Watching hero, or the player's
  scrub interaction — and keep everything else disciplined.
- **Copy:** sentence case, active voice, plain verbs. An empty library says what to do next. An error
  says what happened and what fixes it. The action keeps its name from button to toast.

Avoid the generated-page tells: tracked-out all-caps eyebrow labels, identical rounded cards with the
same soft grey shadow, meta strings joined with middle dots, one word of a headline in an accent colour,
a `→` glued to every link. If a choice would look the same for a banking app, it is not a choice.

**Quality floor, unannounced:** visible keyboard focus, `prefers-reduced-motion` respected, 44×44pt
minimum touch targets, contrast that survives a phone at 20% brightness, and every screen usable at the
largest Dynamic Type setting the WebView reports.

---

## 7. Feature-by-feature mobile mapping

Every one of these must be *app-friendly*, not merely reachable. Your plan expands this table with a
screen-level description and an ASCII wireframe for each row.

| Feature | Backing routes | Mobile treatment |
|---|---|---|
| Sign in | `POST /api/auth/login` | Full-screen, single field per row, 16px inputs, keyboard-aware submit. Outside the app shell |
| Who's watching | `GET /api/auth/profiles`, `POST /api/auth/profile` | Full-screen avatar grid, 2–3 across, large tap targets. Outside the app shell. This is the first screen of the evening — make it good |
| Home / Continue watching | `GET /api/library/*` | Poster-led. Continue Watching first, resume progress on the art, then recently added by folder |
| Browse a folder | `GET /api/library*` | Snap-scrolling rails or a 3-across grid; sticky section headers; virtualised |
| Search | `GET /api/search`, `/api/search/global` | Dedicated screen, immediate focus, debounced, owned-vs-discover clearly separated, recent searches |
| Title detail | `GET /api/status`, TMDB art, trailer | Backdrop hero → title → primary action (Play / Request / Downloading) pinned in the thumb zone → metadata → episodes |
| Request a title | `POST /api/download` (**admin**), `GET /api/quality` | Bottom sheet. Handle the "pick one" ambiguity list as a list, never a silent guess. Handle 404/502/503 with the honest sentence |
| Episodes | `GET /api/library*` | Season selector as a sheet or segmented control; episode rows with watched state and duration |
| Player | `/api/jellyfin/stream\|hls`, `POST …/progress` | Landscape-first, `playsinline`, tap-to-reveal chrome with auto-hide, large scrubber with a thumb-sized target, skip ±10s, lock-controls, brightness/volume left alone (iOS owns them). ⚠ `progress` answers **204 — a success with no body**; never parse it as JSON |
| Subtitles | `GET·POST /api/jellyfin/subtitle-*` | Sheet from the player. Reuse `activeSubtitleRowKey()` — do not re-derive which row gets the tick. A vendor failure degrades the sheet, never the player |
| Downloads / offline | bridge `list·download·cancel·delete·play` + `GET /api/offline/bundle/{id}` | A real screen in the bottom nav *when the bridge exists*. Rows with state, bytes/total, and the "Preparing on the server…" label at zero bytes. Swipe-to-delete. Play from device without touching `playback-info` |
| Account & password | `POST /api/auth/profile/password` | Sheet or a settings sub-screen |
| Household (admin) | `GET /api/admin/*` | Mobile-usable, not mobile-beautiful. Admin-only, refused while another profile is selected — surface that refusal as a sentence |
| Health / degraded | `GET /api/health` | A quiet banner, never a blocking screen |
| Auth failure states | `X-RKM-Auth-Problem` | `session` → login. `profile-token` → keep the session, drop the rows, go to Who's watching with the server's sentence. Both must look deliberate on a phone |

---

## 8. Offline and the native shell

- The affordance appears **only** when `bridgeAvailable()` is true. No bridge, no downloads tab, no
  download button, nothing that hints at a missing feature.
- **Two owners, two answers** (§17.4): the server says what a download would cost
  (`GET /api/offline/bundle/{id}`), the app says what is already on the device (bridge `list`). A screen
  that needs both asks both. Never infer one from the other.
- The bridge refuses by version with a sentence ("update the app"). Render that sentence; never guess
  past a refusal, never retry a version refusal.
- Progress events are already throttled by a pure planner on the native side. Do not add a second
  throttle, and do not animate a percentage between events — a rewind is a real state change.
- The loopback URL is a capability: never log it, never persist it, never put it in a cache key. The port
  changes every launch.
- **Shared downloads — settled (§2a).** The file is the household's, not the profile's (ADR-0007 D6), and
  that does **not** change here. The Downloads screen carries one line of copy under its heading: *"On
  this device — shared by everyone in the household."* No profile stamping, no bridge field, no native
  change, no Mac round. If per-profile downloads are ever wanted, that is a bridge `v2` phase of its own.

---

## 9. What you must *not* regress

The web layout is the acceptance risk of this entire project. Treat it as a contract.

1. **Every existing `tools/check_*.py` passes unchanged, at a desktop viewport.** Not adapted. Not
   re-baselined. If one needs a change, that is a finding to report, not a fix to make.
2. **No edits to existing view files except behaviour-preserving extraction** (§3), each in its own
   commit, each with the gates green before and after.
3. **No global CSS change that is not scoped.** A mobile-first reset that leaks into the desktop tree is
   the classic way this goes wrong. Scope by the layout mode or by a mobile root class; do not rewrite
   base element styles the desktop tree depends on.
4. **Desktop screenshots before and after each phase.** Attach them to the phase report.

---

## 10. Gates — every phase ends with all of these green

```bash
cd frontend && npm run typecheck && npx vitest run && npm run build
cd backend  && python -m pytest tests/ -q        # must still pass; you changed nothing here
npx vite --port 5199                             # then the harness checks:
python tools/check_*.py                          # existing ones, desktop viewport, unchanged
python tools/check_mobile_*.py                   # yours, new, 390×844
```

New browser checks you own, following the existing `frontend/harness/*.html` + `tools/check_*.py`
pattern (a frame mounting real views over a stubbed api, driven headless):

| Check | Proves |
|---|---|
| `check_mobile_shell.py` | Bottom nav, safe-area padding, route switching, no horizontal overflow — asserted at **320, 390 and 1023px** (one shell, three widths) |
| `check_mobile_layout_switch.py` | Crossing 1024px swaps presentation without a refetch, a remount or a sign-out. 390 ↔ 1023 changes **no** component tree, only CSS |
| `check_mobile_player.py` | Chrome shows/hides, scrubber seeks, `playsinline` set, a 204 progress reply is treated as success |
| `check_mobile_offline.py` | No bridge → no affordance. Bridge present → rows, zero-byte "Preparing on the server…", cancel, delete |
| `check_mobile_auth.py` | Login and picker render full-screen; `profile-token` 401 lands on the picker with the server's sentence |

⚠ **A fake more permissive than the real route is a gate that cannot fail** (§17.6). Your stubs must
answer exactly what the api answers — 204 with no body where the api answers 204.

**Deploy for a real phone check:** `.\rkm-cinema.ps1 apply` rebuilds `web`; the phone sees it on next
load with no app rebuild (§17.5). Confirm with `.\rkm-cinema.ps1 status`.

---

## 11. Branch, commits, docs

- **Branch:** `feat/mobile-first-ui`, cut fresh from mainline. One phase = one reviewable commit series.
- **Commits:** `mobile(M3): title detail — hero, pinned action, episodes sheet`. A refactor-only commit
  says so in the first word and touches no behaviour.
- **Never mix** an extraction refactor and a new mobile view in one commit.
- **Docs, following the repo's ADR + plan + PROGRESS convention:**
  - `docs/plans/MOBILE_FIRST_UI_PLAN.md` — the plan (§12), kept current as phases land.
  - `docs/adr/ADR-00NN-mobile-layout-shells.md` — the §3 decision, its alternatives (media-query-only CSS;
    a second bundle; a native client) and why they lost, **plus the three §2a decisions** recorded as
    settled with their rejected alternatives. Use the next free ADR number.
  - `docs/PROGRESS.md` — a short entry per phase, in the existing style.
  - `docs/ARCHITECTURE.md` §12 — **one paragraph** added at the end of the phase run describing the two
    layout shells. Do not restructure that file.

---

## 12. Deliverable #1 — the plan document

Write it, then stop. It must contain:

1. **Inventory.** Every route and view in `frontend/src/`, and for each: mobile treatment, which phase,
   whether an extraction is needed, and the risk to the desktop view.
2. **The layout-shell design** (§3) as you intend to build it, with the actual file tree and the exact
   signature of `useLayoutMode()`.
3. **The token table** (§6): inherited tokens, new tokens, each new one justified.
4. **Wireframes.** ASCII is fine, one per screen in §7, with the thumb zone marked.
5. **The extraction list:** every piece of logic currently living inside a desktop view that a mobile view
   will need, and the shape of the shared hook it becomes.
6. **The phase plan** (§13), with a done-when per phase written as something a person can check on a
   phone in under a minute.
7. **New open questions only.** The three original ones are settled in §2a — restate them as decisions,
   not as questions. List anything *new* you found, with your recommendation and what it costs to change
   later.
8. **The regression argument:** how a reviewer will be convinced the web layout did not move.

---

## 13. Phases

Each ends green, deployable, and reviewed before the next starts. Ordering is deliberate: the shell and
the switch come first because everything after them is cheap; the player and offline come late because
they are where a phone is most different from a desktop and you want the foundation settled.

| Phase | Scope | Done when |
|---|---|---|
| **M0 — Foundation** | Two-mode layout provider + switch (§4), `layouts/desktop/index.ts` re-export, viewport meta (`viewport-fit=cover`), safe-area tokens, dvh handling, tap/touch base styles, scoped mobile root, grid/type column tokens, token additions. No visible feature work | The existing app renders unchanged at ≥ 1024px, a debug readout reports the current mode, and the grid tokens already reflow correctly at 320/390/834/1023 |
| **M1 — Shell & navigation** | Bottom tab bar in the thumb zone, screen transitions, the sheet primitive (drag handle, swipe dismiss, scroll-lock, safe-area), toast/banner primitives, skeleton primitives matching `guardDecision`'s skeleton state | You can move between every existing route on a phone using only your thumb, and every route renders *something* correct |
| **M2 — Identity screens** | Login, Who's watching, account menu as a sheet, the two 401 answers | Sign in, pick a profile, switch profile and sign out on a phone with no pinch, no zoom-on-focus, no clipped home indicator |
| **M3 — Library & search** | Home, Continue Watching, folder browse, grids/rails, search screen, empty and degraded states | Browsing 500+ titles is smooth on a real phone; no horizontal overflow at 320px; the same screens fill an iPad at 834px with more columns and no new components |
| **M4 — Title detail & request** | Backdrop hero, pinned primary action, metadata, episodes, trailer, request sheet with quality profiles and the ambiguity list | A title can be found and requested end to end on a phone, including the "pick one" case and each honest error |
| **M5 — Player** | Full-screen player, landscape, tap chrome, scrubber, skip, resume, progress reporting | A film plays, scrubs, resumes and reports position on a phone. The 204 is handled |
| **M6 — Subtitles** | Subtitle sheet from the player, search, select, disable, quota display, vendor-failure degradation | With the vendor dead, the sheet still lists and applies the item's own tracks |
| **M7 — Offline & downloads** | Downloads screen, bridge-gated affordances, download/cancel/delete, play-from-device, the two-owners rule | On a build with the bridge: download, airplane mode, play. On a browser: no trace of the feature |
| **M8 — Admin & settings** | Household, account, password, settings on a phone | An administrator can run the household from a phone without rotating it |
| **M9 — Polish & proof** | Performance pass, a11y pass, reduced motion, largest type size, the desktop regression report, docs | The gates are green, the desktop screenshots match M0's, and `PROGRESS.md` + the ADR are written |

---

## 14. When to stop and ask

Stop and ask rather than deciding, if:

- a mobile view seems to need data no existing hook provides (it may be a backend phase, or it may be a
  hook you should extract — the difference matters);
- an extraction cannot be made behaviour-preserving;
- a fix appears to require touching `apple/`, the bridge, `Info.plist`, nginx headers, or `.env`;
- an existing `tools/check_*.py` fails and the honest fix is to change the check;
- a screen seems to need a third layout mode, or a component wants to branch on "is this a tablet" —
  report it; the answer is almost always a media query you have not found yet;
- a phase's scope grows past what a person can review in one sitting — split it and say so;
- you find a bug in the existing app. Report it. Do not fix it inside a mobile phase, where it will be
  invisible in the diff.

**One line:** the phone gets a layout designed for a phone, built inside the one app, with one copy of
every rule, and the web comes out of it untouched.
