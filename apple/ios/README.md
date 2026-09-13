# `ios/` — RKMCinema (iPhone / iPad)

A **WKWebView shell**, not a native client. It shows a server-address screen, then loads the real React
UI from that address. ~100 lines of Swift. Full reasoning: [`../../docs/APPLE_CLIENTS_PLAN.md`](../../docs/APPLE_CLIENTS_PLAN.md) §3.

**Not Capacitor.** Capacitor cancels a top-level navigation to an unknown host and hands it to Safari
unless the host is in `server.allowNavigation` — a *build-time* list, which cannot satisfy a
user-entered runtime address. A plain `WKWebView` does this natively with less code. Do not re-propose
it; §6 of the plan records the source-level evidence.

## Planned layout

```
ios/
└── RKMCinema/                        ← Xcode project (created in the first build session)
    ├── RKMCinema.xcodeproj
    ├── README.md                     ← build/run/acceptance notes, filled in as it is built
    ├── RKMCinema/
    │   ├── RKMCinemaApp.swift        @main — picks Setup or Shell from the stored address
    │   ├── App/
    │   │   └── AppRootView.swift     routing: no address → Setup · address → Shell
    │   ├── Server/
    │   │   ├── ServerSetupView.swift      address field, Connect, validation messages
    │   │   └── UnreachableServerView.swift "can't reach this server" + Change server
    │   ├── Shell/
    │   │   ├── WebShellView.swift    UIViewRepresentable wrapping WKWebView
    │   │   └── WebShellModel.swift   load state, nav-failure → Unreachable, clear-website-data
    │   ├── Config/
    │   │   └── Info.plist            NSAppTransportSecurity (see below)
    │   └── Assets.xcassets
```

`Server/` deliberately holds almost nothing: address parsing, normalisation and persistence live in the
shared package (`../Shared/Sources/RKMServerKit/`), because the tvOS app needs the identical rules.

## Non-negotiables (each one is a bug if missed)

| Requirement | Why |
|---|---|
| `WKWebViewConfiguration.allowsInlineMediaPlayback = true` | The player is a custom `<video>` with `playsInline` + `requestFullscreen`. Without this, iOS hijacks it into the native fullscreen player and the custom transport — seek bar, quality, audio/subtitle pickers — **never renders**. |
| `NSAppTransportSecurity` declaration | The address is user-entered and may be plain `http://` to an arbitrary host, which iOS blocks by default. Prefer `NSAllowsLocalNetworking`; `NSAllowsArbitraryLoads` only if a raw LAN IP must work. |
| Always-reachable **Change server** | A stale or typo'd address must not leave a blank screen with no way out, short of reinstalling. |
| Handle main-frame navigation failure | `didFailProvisionalNavigation` / `didFail` must surface as the unreachable state, not a white screen. |

## What NOT to add here

- **No bundled web assets.** The UI is served by the `web` container; bundling it would create a second,
  stale copy of `frontend/`.
- **No Capacitor plugins, no JS bridge, no `capacitor.config`.** Nothing here needs one (HLS is native
  Safari), and leaving the local origin detaches the bridge anyway.
- **No API client, no models, no auth code.** The web UI owns all of that. If this folder starts
  growing an API layer, the design has drifted.

## Acceptance (Phase 0 gate)

Install on the iPad → enter the address → the UI loads → sign in with the ordinary household
username/password → play a title (transport controls visible, not the iOS player) → sign out → back to
the app's own state, not a dead end. Then: enter a deliberately wrong address and confirm the
unreachable state offers Change server.
