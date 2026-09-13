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

⚠ **The Swift sources here have never been compiled.** There is no Xcode on the Windows side, so this
half of Phase 0 is **written but unverified** until the Mac builds it (`../WORKFLOW.md` §5). What *was*
checked in the sandbox is listed in `docs/PROGRESS.md`: the shared package's tests, the Info.plist's
structure and ATS keys, bracket balance, and that the injected JavaScript is complete and balanced.

**Not yet done, and not part of Phase 0:** the Xcode project itself (his one-time GUI step), and the
tablet acceptance run.

## Non-negotiables (each one is a bug if missed)

| Requirement | Where it lives | Why |
|---|---|---|
| `WKWebViewConfiguration.allowsInlineMediaPlayback = true` | `WebShellView.makeUIView` | The player is a custom `<video>` with `playsInline` + `requestFullscreen`. Without this, iOS hijacks it into the native fullscreen player and the custom transport — seek bar, quality, audio/subtitle pickers — **never renders**. |
| `NSAppTransportSecurity` declaration | `Info.plist` (a real file — the dictionary cannot be expressed as an `INFOPLIST_KEY_*` setting) | The address is user-entered and may be plain `http://` to an arbitrary host, which iOS blocks by default. ⚠ **Both** `NSAllowsArbitraryLoads` and `NSAllowsLocalNetworking` are set: the documented LAN address is a raw private IP, which is the case `NSAllowsLocalNetworking` alone has never reliably covered. The launch banner logs the resolved values, so a mis-pointed `INFOPLIST_FILE` is visible in the first ten lines. |
| Always-reachable **Change server** | `UnreachableServerView`, and the debug overlay's ⚙ | A stale or typo'd address must not leave a blank screen with no way out, short of reinstalling. |
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
