# Apple clients (iOS / iPadOS / tvOS) — plan

> **Status:** 📋 **PLAN ONLY — not executed.** No app code written. Written 2026-09-13, revised
> 2026-09-13 after the "server address on first launch" requirement (§2) — which **deleted** several
> items an earlier revision listed and **replaced the iOS approach entirely**.
> **Branch:** `feat/apple-clients` · **folders:** §5 · **phases:** §7.
> **Goal:** run rkm-cinema on the household's Apple devices with the *minimum* new code, without forking
> the backend and without a second implementation of any business rule.

---

## 1. The one hard constraint

**tvOS has no browser.** Apple removed WebKit entirely from Apple TV (`UIWebView`/`WKWebView` are
unavailable on the platform — not deprecated, absent) and the App Store guidelines prohibit embedding
one. Verified 2026-09-13.

| Target | Can we render the existing React UI? |
|---|---|
| iPhone / iPad | **Yes** — iOS ships full WebKit. A WKWebView can load the real UI. |
| Apple TV | **No.** No web view exists. tvOS must be **native**. |

Two tracks with different costs. The cheap track lands first.

---

## 2. The server-address design (decided: both clients)

**Requirement (user, 2026-09-13):** both apps open on a **server address** field. Enter the address,
the app loads the UI from there, and sign-in is the ordinary username/password the browser already
uses.

This is the **Jellyfin / Infuse / Plex model**, and it is the right call:

- The tailnet host is **not baked into the build**, so the app is portable — LAN
  (`http://192.168.x.x:8124`), Tailscale (`https://rkm-hp.tail8d5e8.ts.net/`), or a future domain.
- It makes the app **shareable** — a family member installs it, types the same address, and gets the
  household picker.
- It keeps one UI. The iPad app is a shell around the *live* UI, so every future web change appears on
  the device with **no app rebuild and no store release**.

### 2.1 The consequence that matters: it deletes the CORS work

Once the WebView's top frame is the server's origin, **every `/api` call is same-origin** — exactly as
in Safari. Therefore:

| Item from the first revision | Status now |
|---|---|
| Pin the CORS origin list + `allow_credentials` (`api/main.py:64`) | **DELETED** — same-origin, CORS never engages |
| `VITE_API_BASE` in `frontend/src/lib/api/client.ts:732` | **DELETED** — the relative `"/api"` is *correct* once the origin is the server |
| Make the session cookie's `Secure` flag config-driven (`api/routes/auth.py:133`) | **DOWNGRADED to optional hygiene** — `secure=False` works over both http and https, which is exactly what a user-entered address needs |

**Net result: the iOS app requires ZERO changes to this repo.** No frontend change, no backend change,
no CORS change. It loads the UI the nginx container already serves.

### 2.2 The one thing it does cost: App Transport Security

Because the address is user-entered, it can be plain `http://` to an arbitrary host — which iOS blocks
by default. The app must declare `NSAppTransportSecurity` (prefer `NSAllowsLocalNetworking`; use
`NSAllowsArbitraryLoads` only if a raw LAN IP must work). ⚠ Apple asks reviewers to justify
`NSAllowsArbitraryLoads` — irrelevant for a household app, relevant only if it is ever submitted to
the App Store.

### 2.3 ⚠ The network is still the client's problem

"Type any address" does **not** remove the connectivity prerequisite. For use away from home, Tailscale
must be running **on the device** — the app itself cannot route to `100.x` tailnet addresses. On the
LAN it just works. Worth knowing before expecting it to work from a hotel.

---

## 3. Track A — iOS / iPadOS (1–2 days, **zero repo changes**)

**Approach: a thin native WKWebView shell with a setup screen.** NOT Capacitor.

### 3.1 Why Capacitor was dropped

The first revision recommended Capacitor. The server-address requirement kills it. Capacitor's own
iOS navigation policy (`ios/Capacitor/Capacitor/WebViewDelegationHandler.swift`, read 2026-09-13):

```swift
// next, check if this is covered by the allowedNavigation configuration
if let host = navURL.host, bridge.config.shouldAllowNavigation(to: host) {
    decisionHandler(.allow); return
}
// otherwise, is this a new window or a main frame navigation but to an outside source
let toplevelNavigation = (navigationAction.targetFrame == nil || ...isMainFrame == true)
let isApplicationNavigation = navURL.absoluteString.starts(with: bridge.config.serverURL.absoluteString)
                           || navURL.absoluteString.starts(with: bridge.config.localURL.absoluteString)
if !isApplicationNavigation, toplevelNavigation {
    if UIApplication.shared.applicationState == .active {
        UIApplication.shared.open(navURL, options: [:], completionHandler: nil)   // Safari
    }
    decisionHandler(.cancel); return
}
```

A top-level navigation to a host outside the app is **cancelled and handed to Safari** unless that host
is in `server.allowNavigation` — a **build-time** list. "User types any address at runtime" is exactly
what Capacitor refuses to do by default; making it work means a custom `shouldOverrideLoad` plugin
patching the bridge. That is more code than simply not using Capacitor.

There is a second, independent reason: navigating off `capacitor://localhost` detaches Capacitor's
plugin bridge. Nothing here needs a plugin (HLS is native Safari; the player is a plain `<video>`), so
the bridge buys nothing and costs a build pipeline.

### 3.2 What the app actually is

```
┌─ Setup view (SwiftUI) ──────────────┐      ┌─ Web view ────────────────────────┐
│  Server address                     │      │  WKWebView → https://rkm-hp...:   │
│  [ https://rkm-hp.tail8d5e8.ts.net ]│ ───► │    the real React UI, live        │
│  [ Connect ]   (persisted)          │      │    same-origin /api, normal login │
│  "Can't reach server" + Change      │ ◄─── │                                   │
└─────────────────────────────────────┘      └───────────────────────────────────┘
```

- `UserDefaults` holds the address; launch goes straight to the web view when one is stored.
- `WKWebViewConfiguration.allowsInlineMediaPlayback = true` — mandatory. The player is a custom
  `<video>` with `playsInline` + `requestFullscreen`; without this iOS hijacks it into the native
  fullscreen player and the custom control bar (seek bar, quality, audio/subs pickers) never renders.
- Handle navigation failure: a "can't reach this server" state with a Change-server affordance — a
  stale address must not leave a blank screen with no way out.

### 3.3 Repo changes required

**None.** The iOS project is new code in `apple/ios/` (§5); it consumes the existing deployed UI.
`frontend/` and `backend/` are untouched.

⚠ One honest caveat: a remote-URL shell is precisely what App Store guideline 4.2 (Minimum
Functionality) targets, so a store submission would likely be rejected. For a household app (free
provisioning, TestFlight, or direct install) this is irrelevant.

---

## 4. Track B — tvOS (native, the real work)

**Approach: a lean native SwiftUI client, read + play only.** The server-address screen is not an
add-on here — tvOS has no other way to know where the server is, so it is screen #0 by construction.

### 4.1 Screen budget

0. **Server address** — text field + Connect, persisted
1. **Sign in** → `POST /api/auth/login`
2. **Who's watching** → `GET /api/auth/profiles`, `POST /api/auth/profile`
3. **Home** — Continue Watching + Recently Added → `GET /api/library/*`
4. **Browse** — folders → per-folder items
5. **Item detail**
6. **Player** — `AVPlayer` + `/api/jellyfin/hls/{id}/master.m3u8`, resume via existing progress routes

**Explicitly out of scope on tvOS:** Request/download + quality profiles, Household admin, subtitle
*vendor* search and download, global search. TV is a *viewing* surface for the library already built.

### 4.2 Entering a URL on a TV is a solved problem (mostly)

Verified via Apple's own guidance: while a text field is focused on Apple TV, a nearby iPhone/iPad
signed into the same Apple Account can be used as the keyboard (Continuity). Bluetooth keyboards pair,
and Siri dictation works ("spell out complex terms"). So a typed address is tolerable — but:

⚠ **Pre-fill the field** with the tailnet address so the common case is one button press. Do not make
a Siri Remote the primary text input.

### 4.3 What we get for free

- **The contract is frozen and versioned** — `docs/api/openapi.v1.json` (ADR-0001, additive-only).
  The frontend already regenerates TS types from it (`npm run generate:types`). The tvOS client
  generates **Swift** types from the same file (`swift-openapi-generator`) — one source of truth, no
  handwritten model drift.
- **No media URL and no credential ever reaches the client.** Playback rides the same-origin
  `/api/jellyfin/hls/{id}/master.m3u8` proxy, which rewrites every upstream URI and strips the Jellyfin
  `api_key`.
- **Apple hardware plays *more* than Chrome.** The HLS ladder in `api/routes/jellyfin_hls.py` exists
  because **Chrome MSE cannot decode `ec-3`/`ac3`/DTS/TrueHD**, forcing `mode=transcode_audio` for
  those titles. Apple silicon decodes HEVC **and** EAC3 in hardware and `AVPlayer` speaks native HLS,
  so a tvOS client can ask for `mode=remux` far more often — *less* transcoder load, not more.

### 4.4 The one backend change that matters: auth for non-browser clients

**Auth is cookie-only today.** `api/session.py::session_context_from_request()` reads
`request.cookies.get(SESSION_COOKIE)` — there is no `Authorization` path anywhere in the tree
(verified 2026-09-13). URLSession shares a cookie store, so ordinary REST calls authenticate fine.
**But `AVPlayer`'s HLS segment requests are the risky part** — do not bet playback on cookie
propagation.

Do not fight it. Extend the seam the architecture already declares (§11 — *the credential comes from
`api/session.py` only*):

| # | Where | Change |
|---|---|---|
| B1 | `POST /api/auth/login` response | Add `session_token` (additive field) — the opaque session id, returned once. |
| B2 | `api/session.py::session_context_from_request` | Accept `Authorization: Bearer <session_id>` as an alternative to the cookie. **One function** — the single documented identity seam, so no route can bypass it. |
| B3 | `api/routes/jellyfin_hls.py` | The proxy **already rewrites every URI** and already strips `api_key` (`_strip_api_keys`). Inject the session token into each rewritten URI the same way. `AVPlayer` then needs **zero** cookie plumbing. |

⚠ **Log hygiene:** a token in a query string can reach access logs. The code already solves this class
of problem (that is what `_strip_api_keys` is for) and the network is a private tailnet — but the token
must be treated as a credential and never logged. Fallback if that is unacceptable: an
`AVAssetResourceLoaderDelegate` injecting the `Cookie` header; more code, more edge cases.

### 4.5 What actually costs the time on tvOS

Not the networking — that is a weekend. It is the **focus engine**:

- No pointer, no hover. `AccountMenu` (hover menu), `PopupMenu`, `Dialog`, the pointer-capture seek bar
  (`Player.tsx`'s custom `div` slider) and every `onClick` need a focusable equivalent for a d-pad.
- The CSS viewport assumptions (fixed overlays, `inset-0`, 16:9 backdrops) are meaningless at 1080p/4K
  from three metres — the TV UI needs its own type scale and spacing.
- The custom seek bar becomes `AVPlayerViewController`'s transport, or `AVPlayer` + a focus scrubber.

Budget **2–4 weeks of evenings**, and expect the first two days to be toolchain (Xcode tvOS target,
signing, provisioning).

---

## 5. Repository layout — two apps, two folders, nothing shared that should not be

All Apple code lives under **`apple/`** (a sibling of `backend/`, `frontend/`, `docs/`). Each app owns
its own folder; the shared surface is deliberately tiny.

```
apple/
├── README.md                     the tree·the rules·build order·what each app may contain
├── WORKFLOW.md                   ⚠ the two-machine loop (author on Windows, TEST on the Mac)
├── LOGGING.md                    the dev-phase logging + diagnostics spec (HUD, correlation ids)
├── Shared/                       local Swift package: RKMServerKit
│   └── Sources/RKMServerKit/
│       ├── ServerAddress.swift   parse + normalise a typed address (add scheme, strip trailing /)
│       └── ServerStore.swift     persist it (UserDefaults)
├── ios/                          RKMCinema — the WKWebView shell (~100 lines of Swift)
│   ├── README.md                 spec, non-negotiables, acceptance
│   ├── project.yml               ← the PROJECT SOURCE (xcodegen ⇒ .xcodeproj, git-ignored)
│   └── RKMCinema/
│       ├── RKMCinemaApp.swift    @main — Setup or Shell, decided by the stored address
│       ├── App/AppRootView.swift routing
│       ├── Server/               ServerSetupView · UnreachableServerView
│       ├── Shell/                WebShellView (WKWebView) · WebShellModel (load/nav failure)
│       ├── Config/Info.plist     NSAppTransportSecurity
│       └── Assets.xcassets
├── tvos/                         RKMCinemaTV — the native client
│   ├── README.md                 spec, screen budget, exclusions, acceptance
│   ├── project.yml               ← the PROJECT SOURCE (xcodegen ⇒ .xcodeproj, git-ignored)
│   └── RKMCinemaTV/
│       ├── RKMCinemaTVApp.swift  @main
│       ├── Server/               screen #0 — PRE-FILLED address field
│       ├── Auth/                 LoginView · ProfilesView · SessionStore
│       ├── Library/              HomeView · BrowseView · ItemDetailView · MediaCard
│       ├── Player/               AVPlayer + HLS · resume · progress reporting
│       ├── Core/
│       │   ├── APIClient.swift   transport: base URL from the stored address + bearer token
│       │   └── GeneratedAPI/     swift-openapi-generator output — generated, then COMMITTED
│       └── Assets.xcassets
└── scripts/
    ├── generate-api.sh           regen the Swift types from docs/api/openapi.v1.json
    └── mac-round.sh              ⚠ the Mac's ONE command per round (pull · generate · build)
```

### 5.1 The three rules this layout encodes

1. **`ios/` and `tvos/` are different shapes and must not be made to match.** The shell has *no* API
   client, models, auth flow or playback code — the web UI owns all of that. tvOS owns all of it. A
   reader who assumes symmetry will get both wrong.
2. **`Shared/` holds only what BOTH apps need.** Today that is exactly one thing: the server address
   (parse, normalise, persist). ⚠ If `Shared/` starts growing API models or networking, one client is
   being forced to look like the other — split it out instead.
3. **Generated code is committed, not ignored.** `GeneratedAPI/` mirrors how `frontend/` commits its
   generated TS types from the same contract: regenerated by a script, never hand-edited, reviewable in
   a diff. `.gitignore` explicitly does **not** ignore it.

**Xcode project structure — REVISED 2026-09-13, after he confirmed development is strictly on Windows and
the Mac is TESTING ONLY:** the projects are **generated from `project.yml` by XcodeGen**, and the `.xcodeproj`
is **git-ignored**. Nothing should depend on a human creating or maintaining a project in Xcode's GUI when the
Mac never authors anything. ⚠ The habit this requires: a wrong project setting is fixed in `project.yml` + one
regenerate — **never in Xcode's UI**, where the change is lost on the next generate. See `apple/WORKFLOW.md` §2
for why this replaced the earlier "he creates the project once" plan. `.gitignore` excludes `xcuserdata/`,
`DerivedData/`, `.build/`, `*.xcodeproj` and `apple/logs/`.

**Bundle identifiers** (to confirm before the first build):
`com.helloraj1986.rkmcinema.ios` · `com.helloraj1986.rkmcinema.tvos`.

---

## 6. Considered and rejected (recorded so it is not re-litigated)

| Option | Verdict |
|---|---|
| **Capacitor for iOS with a runtime server address** | **Rejected.** Its navigation policy cancels a top-level load to an unknown host and opens Safari instead (§3.1, verified against the source). Build-time `allowNavigation` cannot satisfy a runtime address. |
| **Capacitor for tvOS** | **Impossible.** No WKWebView on the platform; guidelines prohibit embedding one. |
| **Electron / Tauri for tvOS** | Same wall — both wrap a web view. Tauri's iOS/tvOS story is WKWebView. |
| **"One web app everywhere" (the Plex-style model)** | Structurally unavailable on Apple TV. That is why Plex, Jellyfin and Infuse all ship *native* tvOS apps. |
| **react-native-tvos** (fork of core RN, actively released — 0.85.x) | **Viable, right answer only under one condition.** It shares the *logic* layer with the web app, not the views: no DOM means Tailwind, react-router and `hls.js` do not carry over and every screen is rewritten anyway. Its real advantage is **Apple TV *and* Android TV from one codebase**. |
| **Install Swiftfin / Infuse on the Apple TV, pointed at the bundled Jellyfin :8098** | **Genuinely the cheapest option; costs nothing today.** Only the wrong answer if the point is *this app's* UX on the big screen. |

**Decision rule:**
- Apple TV **and** Android TV → **react-native-tvos** from the start; do not write Swift.
- Apple TV only → **lean SwiftUI** (recommended).

---

## 7. Phases, with gates

Sandbox-side verification only — **the Apple tracks need Xcode on the MacBook Pro**, which this Linux
sandbox cannot host (no `swift`, no `xcodebuild`; verified 2026-09-13). The agent writes, reviews and
diffs this code; **building and running it is his step.**

| Phase | Work | Gate |
|---|---|---|
| **0. iOS shell** | `project.yml` + `apple/Shared/` (address **+ the log redactor**) + `apple/ios/`: setup screen, WKWebView, ATS, `allowsInlineMediaPlayback`, unreachable-server state, **the debug HUD + structured/file logging per `apple/LOGGING.md`**. | `swift test` green in the sandbox (address + redactor). On the iPad: install → enter the address → sign in → play a title and see the **custom** transport → sign out to the app's own state; a wrong address offers Change server. ⚠ **Plus `LOGGING.md` §9**: a HUD correlation id from a screenshot must resolve to matching log lines, and `grep -iE "password|token|api_key|rkm_session"` over a real run's log must return **nothing**. |
| **1. tvOS skeleton** | `apple/tvos/`: `project.yml`, server-address screen (pre-filled), sign-in, Who's watching — focusable — **plus the debug HUD, which on tvOS is the only diagnostic surface that exists**. | Runs on the Apple TV simulator; sign-in + profile switch work on a real Apple TV; the HUD shows requests with correlation ids. |
| **2. Non-browser auth** | B1–B3 + tests. **Only blocks the tvOS player (Phase 4)** — not Phases 0/1. | `cd backend && python -m pytest tests/ -q` green; a `curl` proof: a bearer-only request to `/api/status`, and an HLS master + segment fetched with **no cookie**. |
| **3. tvOS browse + detail** | Home / Browse / Item detail on the focus engine. | Posters, rows, navigation on hardware. |
| **4. tvOS player** | `AVPlayer` + HLS; resume; progress reporting (`POST /api/jellyfin/progress`); remote transport controls; **playback logging — `AVPlayerItem.status` transitions, `accessLog()` (bitrate/stalls/dropped) and `errorLog()` (the real CoreMedia error), per `LOGGING.md` §3**. | A full film plays, resumes where it left off, and the position appears in the web app's Continue Watching. |
| **5. Polish** | Subtitles (AVPlayer rendition or overlay), artwork caching, app icons, optional top shelf. | Watchable end to end. |

**Order note:** Phase 0 is deliberately first — smallest piece of work, **no backend change at all**,
and it proves the "shell around the live UI" thesis before any Swift UI is written for TV.

---

## 8. Costs

| Item | Cost |
|---|---|
| Apple Developer Program | **~AUD $149/year** — needed to run on a real Apple TV past the 7-day free-provisioning window, and for TestFlight. |
| Xcode, Swift, SwiftUI, AVPlayer, `swift-openapi-generator` | $0 (on the MacBook Pro he already has). |
| Server | $0 — same containers, and Apple clients hit the transcoder *lighter* than Chrome. |
| His time | iOS: 1–2 days. tvOS: 2–4 weeks of evenings. |

---

## 9. Risks, ranked

1. **HLS auth to `AVPlayer`** — the #1 risk, and the reason B2/B3 exist. Mitigated by not depending on
   cookie propagation at all.
2. **The focus engine rewrite** on tvOS — underestimated by everyone who has not shipped a TV app; it
   is the bulk of Track B and is *unavoidable*. There is no shared-view shortcut.
3. **ATS with a user-entered address** — a user-typed `http://` host is blocked by default; the
   declaration must be in place from the first build or the app appears broken (§2.2).
4. **A stale/typo'd server address** with no way back — the iOS shell must always offer Change-server
   (§3.2), or a wrong address bricks the app until reinstall.
5. **Signing / provisioning** — Xcode tvOS signing is its own afternoon; a paid account removes most
   of the friction.

---

## 10. Recommendation

1. **Build Phase 0 (the iOS shell) first.** ~1–2 days, **zero changes to `frontend/` or `backend/`**,
   and it puts the entire existing app on the iPad. It also validates the server-address design before
   any TV code exists.
2. **Then decide on tvOS on the evidence of Phase 0.** If the shell on the iPad satisfies the
   household, the TV app is a nice-to-have. If it is a need, build the lean SwiftUI client against the
   frozen contract, with the server-address screen pre-filled.
3. **Treat Phase 2 (bearer auth) as scoped to the tvOS player only** — it is the one backend change in
   the whole plan, and nothing else waits on it.

**Do not** rewrite the UI for TV, and **do not** reach for Capacitor — the requirement rules it out.
Start by proving the cheapest thing works.
