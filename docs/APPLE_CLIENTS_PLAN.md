# Apple clients (iOS / iPadOS / tvOS) — plan

> **Status:** 📋 **PLAN ONLY — not executed.** No code changed. Written 2026-09-13.
> **Goal:** get rkm-cinema running on the household's Apple devices with the *minimum* new code,
> without forking the backend and without a second implementation of any business rule.

---

## 1. The one hard constraint

**tvOS has no browser.** Apple removed WebKit entirely from Apple TV (`UIWebView`/`WKWebView` are
unavailable on the platform — not deprecated, absent) and the App Store guidelines prohibit embedding
one. Verified 2026-09-13.

Consequences:

| Target | Can we wrap the existing React app? |
|---|---|
| iPhone / iPad | **Yes** — iOS ships a full WebKit (WKWebView). Wrapping is cheap. |
| Apple TV | **No.** No web view exists. TV needs a **native** UI. |

So this is not one decision, it is two tracks with different costs. Everything below is arranged so
the cheap track lands first and pays for the expensive one.

---

## 2. What we get for free (why the TV app is smaller than it looks)

The backend is already the right shape for a native second client:

- **The contract is frozen and versioned** — `docs/api/openapi.v1.json` (ADR-0001, additive-only).
  The frontend already regenerates its types from it (`npm run generate:types`, openapi-typescript).
  A tvOS client generates **Swift** types from that same file (`swift-openapi-generator`) — one
  source of truth, no handwritten model drift.
- **No media URL and no credential ever reaches the client.** Playback goes through the same-origin
  `/api/jellyfin/hls/{id}/master.m3u8` proxy, which rewrites every upstream URI and strips the Jellyfin
  `api_key`. A native client gets the same protection the browser has.
- **The player is easier on Apple hardware than in Chrome.** The HLS ladder in
  `api/routes/jellyfin_hls.py` exists because **Chrome MSE cannot decode `ec-3`/`ac3`/DTS/TrueHD**, so
  those titles need `mode=transcode_audio`. Apple silicon (A15/M-series/Apple TV 4K) decodes HEVC
  **and** EAC3 in hardware, and `AVPlayer` speaks native HLS. A tvOS client can therefore ask for
  `mode=remux` far more often than the web player can — *less* server CPU, not more.
- **The logic is already extracted from the views.** Every feature has a pure, unit-tested `lib.ts`
  (auth guard, playback, library, search, subtitles). That is the layer worth sharing; the views are
  not shareable in any framework (see §5).

---

## 3. Track A — iOS / iPadOS (1–2 days, near-zero new UI)

**Approach: Capacitor shell over the existing React build.** Capacitor packages the built SPA into a
WKWebView app; the React code, Tailwind, react-router and the whole UI are reused unchanged. This is
the only approach that costs effectively no UI work, because on iOS the rendering engine *is* Safari.

### Code changes required (all small, all additive)

| # | Where | Change | Why |
|---|---|---|---|
| A1 | `frontend/src/lib/api/client.ts:732` | `export const BASE = (import.meta.env.VITE_API_BASE ?? "/api") as string;` | `BASE` is currently relative (`"/api"`). In a Capacitor WKWebView the page origin is `capacitor://localhost`, which has nothing to resolve `/api` against. One line. |
| A2 | `backend/api/main.py:64` | CORS is `allow_origins=["*"]` **with no `allow_credentials`** — a credentialed cross-origin request from `capacitor://localhost` is therefore refused. Pin the origin list and add `allow_credentials=True`. | ⚠ A wildcard origin is *invalid* with credentials (browsers reject it), so this must be an explicit list, not `["*"]`. Keep the existing behaviour for non-credentialed callers. |
| A3 | iOS project | `NSAppTransportSecurity` exception for the tailnet host — **or better, remove the need for it** by enabling Tailscale HTTPS (§4 Phase 0). | iOS blocks plain `http://` by default (ATS). |
| A4 | Capacitor config | `allowInlineMediaPlayback: true` — the player is a custom `<video>` with `playsInline` + `requestFullscreen`, not a native iOS player. | Without it, iOS forces the native fullscreen player and the custom control bar never renders. |
| A5 | nginx / cookie | Nothing structural. If Phase 0 lands HTTPS, flip the session cookie to `secure=True` via config (`api/routes/auth.py:133` currently hardcodes `secure=False`). | The comment there says "tailnet is plain http — Secure would break login". HTTPS makes `Secure` correct. |

**Deliberately NOT in this track:** no rewrite, no new components, no new endpoints. If A1–A4 is done
and the app signs in, the iOS track is finished.

---

## 4. Track B — tvOS (native, the real work)

**Approach: a lean native SwiftUI client, read + play only.** Not a port — a *smaller* app. The
acquisition/admin half of rkm-cinema stays on web/iOS where a keyboard and forms make sense.

### Screen budget (the whole app)

1. **Sign in** → `POST /api/auth/login`
2. **Who's watching** → `GET /api/auth/profiles`, `POST /api/auth/profile`
3. **Home** — Continue Watching + Recently Added → `GET /api/library/*`
4. **Browse** — folders → per-folder items → `GET /api/library/*`
5. **Item detail** → `GET /api/status` / item detail
6. **Player** — `AVPlayer` + `/api/jellyfin/hls/{id}/master.m3u8`, resumes via existing progress routes

**Explicitly out of scope on tvOS:** Request/download + quality profiles, Household admin, subtitle
*vendor* search and download, global search. Six screens is the whole product — TV as a
*viewing* surface for the library the household already built.

### The one backend change that matters, and where the real risk is

**Auth is cookie-only.** `api/session.py::session_context_from_request()` reads
`request.cookies.get(SESSION_COOKIE)` — there is no `Authorization` path anywhere in the tree
(verified). URLSession shares a cookie store, so ordinary REST calls authenticate fine. **But
`AVPlayer`'s HLS requests are the risky part** — cookie propagation to segment requests is not
something to bet the playback path on.

Do not fight this. Extend the seam the architecture already declares (§11 — *the credential comes from
`api/session.py` only*):

| # | Where | Change |
|---|---|---|
| B1 | `POST /api/auth/login` response | Add `session_token` (additive field) — the opaque session id, returned once to a client that asked for it. |
| B2 | `api/session.py::session_context_from_request` | Accept `Authorization: Bearer <session_id>` as an alternative to the cookie. **One function** — the single documented identity seam, so no route can bypass it. |
| B3 | `api/routes/jellyfin_hls.py` | The proxy **already rewrites every URI** and already strips `api_key` (`_strip_api_keys`). Inject the session token into each rewritten URI the same way. `AVPlayer` then needs **zero** cookie plumbing. |

⚠ **Log hygiene:** a token in a query string can reach access logs. The existing code already solves
this exact class of problem (that is what `_strip_api_keys` is for) and the network is a private
tailnet — but the token must be treated as a credential and never logged. If that is unacceptable,
the fallback is an `AVAssetResourceLoaderDelegate` that injects the `Cookie` header on every request;
it is more code and more edge cases.

### What actually costs the time on tvOS

Not the networking — that is a weekend. It is the **focus engine**:

- There is no pointer and no hover. `AccountMenu` (a hover menu), `PopupMenu`, the pointer-capture
  seek bar (`Player.tsx`'s custom `div` slider), `Dialog`, and every `onClick` need a focusable
  equivalent. The Siri Remote gives you a d-pad and a select button, nothing else.
- The existing CSS viewport assumptions (fixed overlays, `inset-0`, 16:9 backdrops) are meaningless at
  1080p/4K from three metres — the TV UI needs its own type scale and spacing.
- The custom seek bar must become a proper transport: `AVPlayerViewController`'s built-in transport,
  or `AVPlayer` + a focus-friendly scrubber.

Budget this as **2–4 weeks of evenings**, not a weekend, and expect the first two days to be toolchain
(Xcode tvOS target, signing, provisioning).

---

## 5. Considered and rejected (recorded so it is not re-litigated)

| Option | Verdict |
|---|---|
| **Capacitor for tvOS** | **Impossible.** No WKWebView on the platform, and the App Store guidelines prohibit embedding one. |
| **Electron / Tauri for tvOS** | Same wall — both are wrappers around a web view. Tauri's iOS/tvOS story is WKWebView too. |
| **The Plex/Emby-style "one web app everywhere" model** | Structurally unavailable on Apple TV. This is why Plex/Jellyfin/Infuse all ship *native* tvOS apps. |
| **react-native-tvos** (fork of core RN, actively released — 0.85.x) | **Viable, and the right answer only under one condition** (below). It shares the *logic* layer with the web app, not the views: RN has no DOM, so Tailwind/react-router/`hls.js` do not carry over and every screen is rewritten anyway. Its real advantage is **Apple TV *and* Android TV from one codebase** — worth it only if a Shield/Chromecast is also in the plan. |
| **Just install Swiftfin / Infuse on the Apple TV, pointed at the bundled Jellyfin :8098** | **Genuinely the cheapest option, and it costs nothing.** If the TV goal is only "watch in the lounge", this already works today. It is only the wrong answer if the point is *this app's* UX — the household profile picker, your library rows, your Continue Watching — on the big screen. |

**Decision rule:**

- Apple TV **and** Android TV → build **react-native-tvos** from the start; do not write Swift.
- Apple TV only → **lean SwiftUI** (recommended). More code than RN in the abstract, but the smallest
  total surface because the iOS track already reuses the web UI in full.

---

## 6. Phases, with gates

Each phase ends green on its own gates before the next starts. Sandbox-side verification only —
**the Apple tracks need Xcode on the MacBook Pro**, which this Linux sandbox cannot host
(no `swift`, no `xcodebuild`; verified 2026-09-13). The agent can write, review and diff this code;
**building and running it is his step.**

| Phase | Work | Gate |
|---|---|---|
| **0. Tailnet HTTPS + CORS seam** | Enable Tailscale HTTPS (`tailscale serve --bg --https 443 http://127.0.0.1:8124`) so the app has a real certificate on `https://rkm-hp.<tailnet>.ts.net/`; pin the CORS origin list; make the session cookie's `Secure` flag config-driven. | `cd backend && python -m pytest tests/ -q` green; `tools/check_deployed.py` MATCH; browser app still signs in over HTTPS. **Unblocks both tracks and improves the current browser app.** |
| **1. iOS via Capacitor** | A1–A4. | `npm run typecheck && npx vitest run && npm run build` green; app signs in and plays on the iPad. |
| **2. Non-browser auth** | B1–B3 + tests (`tests/test_route_protection.py` awareness if a route is touched). | pytest green; a `curl` proof: bearer-only request to `/api/status` and an HLS master fetched with **no cookie**, segments playable. |
| **3. tvOS skeleton** | Xcode tvOS target; Swift API client generated from `docs/api/openapi.v1.json`; sign-in + Who's watching, focusable. | Builds and runs on the Apple TV simulator; sign-in + profile switch work on a real Apple TV. |
| **4. tvOS browse + detail** | Home / Browse / Item detail views on the focus engine. | Posters, rows, navigation on hardware. |
| **5. tvOS player** | `AVPlayer` + HLS; resume; progress reporting (`POST /api/jellyfin/progress`); remote transport controls. | A full film plays, resumes where it left off, and the position shows up in the web app's Continue Watching. |
| **6. Polish** | Subtitles (AVPlayer rendition or overlay), artwork caching, top-shelf behaviour (optional), app icons. | Watchable end to end. |

---

## 7. Costs

| Item | Cost |
|---|---|
| Apple Developer Program | **~AUD $149/year** — needed to run on a real Apple TV beyond the 7-day free-provisioning window and to use TestFlight. |
| Xcode, Swift, SwiftUI, AVPlayer, Capacitor, swift-openapi-generator | $0 (free, on the MacBook Pro he already has). |
| Server | $0 — same containers, no new service. Apple clients are *lighter* on the transcoder than Chrome (HEVC/EAC3 hardware decode). |
| His time | iOS: 1–2 days. tvOS: 2–4 weeks of evenings. |

---

## 8. Risks, ranked

1. **HLS auth to `AVPlayer`** — the #1 risk, and the reason B2/B3 exist. Mitigated by not depending on
   cookie propagation at all.
2. **The focus engine rewrite** on tvOS — underestimated by everyone who has not shipped a TV app.
   It is the bulk of Track B's effort, and it is *unavoidable*; there is no shared-view shortcut.
3. **ATS / HTTPS** — plain-HTTP tailnet access is blocked by default on iOS. Phase 0 removes this
   class of problem permanently (and is worth doing for the browser app regardless).
4. **Signing / provisioning** — Xcode tvOS signing is its own afternoon; a paid account reduces the
   friction to near zero.

---

## 9. Recommendation

1. **Do Phase 0 first** — it is worth doing even if neither track is built, and it unblocks both.
2. **Then Track A (iOS via Capacitor)** — 1–2 days, essentially free, and it puts the existing app in
   his pocket immediately.
3. **Then decide on Track B on the evidence of Track A** — if the wrapped app on the iPad already
   satisfies the household, the TV app is a nice-to-have, not a need. If it is a need, build the lean
   SwiftUI client with the contract regenerated from `openapi.v1.json`, and keep the acquisition and
   admin half of the product on web/iOS where it belongs.

**Do not** start by rewriting the UI for TV. Start by proving the cheapest thing works.
