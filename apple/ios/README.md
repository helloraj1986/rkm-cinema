# `ios/` — RKMCinema (iPhone / iPad)

A **WKWebView shell**, not a native client. It shows a server-address screen, then loads the real React
UI from that address. Full reasoning: [`../../docs/APPLE_CLIENTS_PLAN.md`](../../docs/APPLE_CLIENTS_PLAN.md) §3.

**Not Capacitor.** Capacitor cancels a top-level navigation to an unknown host and hands it to Safari
unless the host is in `server.allowNavigation` — a *build-time* list, which cannot satisfy a
user-entered runtime address. A plain `WKWebView` does this natively with less code. Do not re-propose
it; §6 of the plan records the source-level evidence.

## Layout — as built (Phase 0)

```
ios/
├── README.md
├── RKMCinema.xcodeproj/              ← created ONCE in Xcode, then COMMITTED (WORKFLOW.md §2)
│   └── xcshareddata/xcschemes/RKMCinema.xcscheme  ← ⚠ SHARED, or the CLI build can't find it
├── Config/
│   └── Info.plist                    ← ⚠ what `INFOPLIST_FILE` points at — and it must sit
│                                       OUTSIDE RKMCinema/ (see the note below)
└── RKMCinema/                        ← the target's source folder (Xcode's synchronized group)
    ├── RKMCinemaApp.swift            @main — bootstrap the log FIRST, then Setup or Shell
    ├── App/
    │   ├── AppLog.swift              launch banner · file-log setup · flush on background
    │   ├── AppModel.swift            routing · connect/probe · reachability recovery · HUD state
    │   └── AppRootView.swift         no address → Setup · address → Shell
    ├── Server/
    │   ├── ServerSetupView.swift     address field, live normalisation, Connect
    │   ├── UnreachableServerView.swift  "can't reach this server" + Try again / Change server
    │   └── ServerProbe.swift         GET /api/status before the shell commits to an address
    ├── Shell/
    │   ├── WebShellView.swift        UIViewRepresentable + navigation & UI delegates
    │   ├── WebShellModel.swift       load state · main-frame failure → unreachable · cookies
    │   ├── WebBridge.swift           native half of the console/network bridge
    │   ├── WebInstrumentation.swift  the JS injected at document start
    │   └── WebsiteData.swift         clear cookies + cached page data
    ├── Debug/
    │   ├── DebugHUD.swift            the overlay: state, last lines, correlation ids, actions
    │   └── HUDToggle.swift           triple-tap hotspot (shake too, on iPhone)
    ├── Assets.xcassets               AppIcon (generated placeholder) · AccentColor
    └── Preview Content/              ⚠ required by Xcode's DEVELOPMENT_ASSET_PATHS setting
```

⚠ **Two lessons the first real build paid for** (recorded so the tvOS app does not repeat them):

1. **A custom `Info.plist` must live OUTSIDE the target's synchronized folder.** Inside it, the file is
   automatically a target member — so Xcode both *copied it into the app as a resource* and *processed it
   as the Info.plist*, failing with `error: Multiple commands produce …RKMCinema.app/Info.plist`. It sits
   in `Config/` now, referenced only by the `INFOPLIST_FILE` build setting.
2. **Xcode's template set `IPHONEOS_DEPLOYMENT_TARGET = 26.5`** — its own SDK version — so the app would
   refuse to install on any iPad not already on iPadOS 26.5. ⚠ **Open, deliberately not bundled with the
   build fix**: see `docs/PROGRESS.md`.

`Server/` deliberately holds almost nothing: address parsing, normalisation and persistence live in the
shared package (`../Shared/Sources/RKMServerKit/`), because the tvOS app needs the identical rules.

## Status — what is verified and what is not

**✅ It builds, it runs, and the diagnostics are earning their keep** (2026-09-14, on the Mac;
`docs/PROGRESS.md` is the authoritative step-by-step account).

| | |
|---|---|
| Compiles and runs on an iPhone 17 Pro simulator (iOS 26.5) | ✅ |
| Enter the address → **the live React UI loads** in the `WKWebView` | ✅ |
| Sign in; the session cookie lands and survives (HUD: `cookies 1 cookie (session)`) | ✅ |
| **The custom transport renders and plays** — `allowsInlineMediaPlayback` doing its job, iOS *not* hijacking the player | ✅ |
| A wrong address → the unreachable state with **Change server / Forget** | ✅ — the `-1022` round; the full `NSURLErrorDomain` code on screen made it diagnosable from a screenshot alone |
| **`LOGGING.md` §9 — all three items** | ✅ **demonstrated 2026-09-14** — the exact lines are quoted in the Acceptance section below |
| **Install on the iPad** | ⏳ the deployment target is now **16.4** (was `26.5`, Xcode's own template value — too high for any iPad not on iPadOS 26.5). Needs one rebuild, and his iPad's version to confirm the floor is low enough |
| The overlay's corner gesture (3 taps / press-and-hold) | ⏳ unverified since its third rewrite. ⚠ Nothing depends on it: a Debug build opens with the overlay already **on** |

⚠ **What the sandbox can and cannot prove** is in `../WORKFLOW.md` §5 — with one addition earned on
2026-09-14: a Swift failure that is a *language or overload* question **can** be reproduced here without
an SDK, by mimicking the shape and running `swiftc -typecheck` (that is how `convert(.zero, to:)` was
caught). ⚠ `swiftc -parse` proves *nothing* about it — it passed that file.

## Non-negotiables (each one is a bug if missed)

| Requirement | Where it lives | Why |
|---|---|---|
| `WKWebViewConfiguration.allowsInlineMediaPlayback = true` | `WebShellView.makeUIView` | The player is a custom `<video>` with `playsInline` + `requestFullscreen`. Without this, iOS hijacks it into the native fullscreen player and the custom transport — seek bar, quality, audio/subtitle pickers — **never renders**. |
| `NSAppTransportSecurity` declaration | `Info.plist` (a real file — the dictionary cannot be expressed as an `INFOPLIST_KEY_*` setting) | The address is user-entered and may be plain `http://` to an arbitrary host, which iOS blocks by default. ⚠ **`NSAllowsArbitraryLoads` is the ONLY key — never add `NSAllowsLocalNetworking` beside it.** On iOS 10+ the presence of a more specific key makes ATS *ignore* `NSAllowsArbitraryLoads`, so setting both blocked plain `http://` to every non-local host: his first real connect failed with `NSURLErrorDomain -1022` on `http://rkm-hp.tail8d5e8.ts.net:8124`, while the same http:// to a LAN IP still worked. The launch banner logs the resolved values, so a mis-pointed `INFOPLIST_FILE` is visible in the first ten lines. |
| Always-reachable **Change server** | `UnreachableServerView`, and the debug overlay's ⚙ | A stale or typo'd address must not leave a blank screen with no way out, short of reinstalling. |
| **The page owns the safe-area insets** | `frontend/index.html` (`viewport-fit=cover`) · `AppRootView` (`.ignoresSafeArea()`) · `frontend/src/app/layout/Header.tsx` (`pt-[env(safe-area-inset-top)]`, `min-h-16`) · `Info.plist` (`UIUserInterfaceStyle = Dark`) | ⚠⚠ **Four edits in two languages, all four required, and none of them visible in a desktop browser.** The web view fills the display; the page pads *itself* against the notch and home indicator; and the app forces dark so the status-bar glyphs stay legible over the page's `#08090b`. Drop any one and the app still builds, still runs, and looks fine in a browser — the failure is visual and device-only, which is exactly why `frontend/src/app/shell-contract.test.ts` pins all four. ⚠ A browser reports `env(safe-area-inset-*) = 0px` whatever you do, so this contract cannot be eyeballed in the sandbox. |
| Handle main-frame navigation failure | `WebShellModel.didFail` | `didFailProvisionalNavigation` / `didFail` must surface as the unreachable state, not a white screen. ⚠ Benign cancellations (`NSURLErrorCancelled`, `WebKitErrorDomain` 102) are filtered out first, or an ordinary cancelled sub-load would throw the app into the error screen. |

## Two things added beyond the letter of the spec, both because the named behaviour needs them

- `webView.isInspectable = true` (iOS 16.4+) — **required by `../LOGGING.md` §3**, and the single best
  debugging lever on the app: Safari → Develop → [his iPad] gives the real DOM, console, network tab
  and JS errors.
- `configuration.preferences.isElementFullscreenEnabled = true` — the other half of the inline-playback
  requirement: it lets the *page's* own `requestFullscreen` work instead of being ignored, so the page
  keeps its own transport UI.
- `WebInstrumentation` (the injected JS) exists because **the shell makes no API calls of its own** —
  the page does. Without instrumenting `fetch`/XHR there is no "log every request" on iOS at all, and
  no correlation id in the HUD. It never clones a response body (that would buffer whole HLS segments).
- `WKUIDelegate.createWebViewWith` — `target="_blank"` appears in `DiscoverView` and
  `WatchlistDetail`; without this delegate method WKWebView silently does nothing with those links.

## The debug overlay's toggle — measured, because it was wrong once

⚠⚠ **The overlay opens ON in a Debug build** (`AppLog.hudStartsVisible`, and `-RKMDebugHUD YES` works
in any build via `UserDefaults`'s argument domain). That is the primary route to it: dev happens on
Windows, testing on the Mac, so an overlay that has to be *found* is missing exactly when it is
needed. Hiding it is still a session-scoped choice — the overlay's ⚙, or the corner gesture below.

**To toggle it in the shell: three taps in the top-left corner of the screen — or one press-and-hold
there.** On a simulator, `Device ▸ Shake` (⌃⌘Z) also works.

⚠ **The previous 52pt triple-tap square never fired once, and the cause was geometry, not the
gesture.** `.overlay(alignment: .topLeading)` aligns to the **modified view's** bounds; the root view
is inset by the safe area; so on an iPhone the square sat at **y ≈ 59pt — *below* the status bar,
inside the page's own header** — while every tap aimed at the corner of the *display*, which is above
it. He reported it as *"nothing comes up"*, which is exactly what a correctly-built control in the
wrong place looks like. Two independent measurements in his own screenshot agree: the page's title and
back chevron start at the same height as the overlay's first line, and the strip above both is
**white** — the window background, not page content, since the cinema UI is dark there.

⚠⚠ **AND THEN THE FIX MOVED THE WRONG THING — a second round, and the more instructive one.** The next
version drew its bug glyph correctly in the corner and *still* could not be tapped: he clicked the
glyph itself and nothing happened. **An offset moves what is *drawn* without promising to move where the
app *listens*** — the mark was in the corner, the hit area was still 59pt lower. The general lesson is
the one to keep: **a control whose hit area depends on SwiftUI's layout of an overlay over a `WKWebView`
is a control with two unknowns multiplying.** So the working design removes both:

- ⚠ **The gesture recognisers are installed on the `UIWindow`** (in `didMoveToWindow`), not on a view in
  the overlay. Every touch passes through the window, whatever is on top of it, whatever the safe area
  is, whatever SwiftUI does with an overlay — nothing is left to be wrong.
- ⚠ **`shouldReceive` accepts a touch only inside a 110pt corner**, and `cancelsTouchesInView = false`
  with simultaneous recognition, so the page keeps every interaction — inside that corner as well as
  outside it. A triple-tap there does not steal a page gesture; it just also toggles the overlay.
- ⚠ **One live instance at a time** (a `static weak var`): if SwiftUI ever rebuilds the view, the old
  one takes its recognisers off the window first — otherwise two sets would toggle once each per
  gesture, i.e. on and straight back off, and the overlay would look broken while being correct.
- It still **logs every received gesture before toggling** — which is what makes "the overlay did not
  appear" falsifiable from the log:

```bash
grep -E "toggle:|debug overlay" "$LOG"
```

- `toggle: 3-tap in the corner` **and** `debug overlay on/off` → the gesture arrived and the toggle
  worked; a missing overlay is then a rendering problem.
- `toggle:` **absent** → the gesture never reached the window recogniser at all.

## What NOT to add here

- **No bundled web assets.** The UI is served by the `web` container; bundling it would create a second,
  stale copy of `frontend/`.
- **No Capacitor plugins, no JS bridge, no `capacitor.config`.** Nothing here needs one (HLS is native
  Safari), and leaving the local origin detaches the bridge anyway. ⚠ The injected script is for
  **logging only** — it does not carry app functionality, and nothing should be added to it that the
  app depends on.
- **No API client, no models, no auth code.** The web UI owns all of that. The one `URLSession` call in
  `ServerProbe` is a reachability check, not an API client. If this folder starts growing an API layer,
  the design has drifted.

## Acceptance (Phase 0 gate)

Install on the iPad → enter the address → the UI loads → sign in with the ordinary household
username/password → play a title (transport controls visible, not the iOS player) → sign out → back to
the app's own state, not a dead end. Then: enter a deliberately wrong address and confirm the
unreachable state offers Change server.

Plus `../LOGGING.md` §9: a round of testing produces **one file** holding every request with its status,
duration and correlation id; a HUD correlation id from a screenshot resolves to matching lines in that
file (**demonstrated, not assumed**); and `grep -iE "password|token|api_key|rkm_session"` over a real
run's log returns **nothing**.

### ✅ All three §9 items demonstrated, 2026-09-14 — the raw output

Run against the app's own file log after a real session on the simulator (pasted verbatim, not
summarised):

```
=== 1. the join:                      (26a253 was read off a HUD screenshot)
[2026-09-14 09:03:47.514] I [26a253] net      GET /api/library/continue-watching -> 200 in 446ms (532 B)

=== 2. redaction (must print NOTHING):   ← printed nothing

=== 3. requests in the file (excerpt)
[2026-09-14 09:03:47.363] I [a73fa7] net      GET /api/library/items -> 200 in 299ms (60.1 KB)
[2026-09-14 09:03:47.445] I [5f67ad] net      GET /api/library/recently-watched -> 200 in 380ms (28 B)
[2026-09-14 09:03:47.461] I [e87827] net      GET /api/jellyfin/detail?id=c2e55d3adc… -> 200 in 395ms (3.2 KB)
[2026-09-14 09:03:47.489] I [b05ebe] net      GET /api/library -> 200 in 423ms (3.6 KB)
[2026-09-14 09:03:48.802] I [664704] net      GET /api/jellyfin/similar?id=c2e55d3adc…&limit=10 -> 200 in 1.33s (2.3 KB)
```

**What each proves.** (1) A correlation id visible *in a photograph* resolves to the matching line in
the file — the property this whole design exists for, and the one that turns "it didn't work" into a
`grep`. (2) The redactor: no credential, token or cookie value reached a file that gets pasted into
chat. (3) One file holds every request the page made, with status, duration and size.

⚠ **The gap this closes:** until this run the JavaScript bridge was silently dead — a weak proxy let it
deallocate — so the HUD showed an empty request list *while a film played*. These lines are the first
proof the shell has an account of what the page fetched, which is what made §9 items 1 and 2 unprovable
before.
