# ADR-0012: the cold-launch offline shell — ask the device before declaring the server unreachable

- **Status:** Accepted · ✅ **built 2026-09-19** — the pure ladder is executed and falsified on Linux
  (`apple/scripts/check-offline-core.py --falsify`, 8 rules reverted); the WebKit half is written and
  typecheck-clean.
- ⚠⚠ **AND THE DEVICE ROUND ON 2026-09-19 SAYS THE MECHANISM IS NOT SUFFICIENT — read §"The device round"
  before relying on D3.** The ladder works exactly as designed (a cold launch with no network DOES load the
  document from the device), but the app still does not paint, because the shell's ~1.1 MB script does not
  come back with it. ⚠ D3's claim that the HTTP cache is the shell store is **contradicted by that
  measurement**.
- ⭐ **The replacement shape was then measured, not chosen** — `apple/SPIKE_SHELL_ORIGIN.md` (his iPhone,
  2026-09-19) answers all three questions, and the last of them decides whether the offline shell carries
  the library or an empty app: the app can hand the page its own copy of the document **and keep the
  server's origin, its cookies, its `/api/*` and its `localStorage`**. See **D7/D8** below. ⚠ **This branch
  is still NOT merged**, and the ladder in it is unchanged: only what the `cached` step LOADS changes.
- **Date:** 2026-09-19
- **Phase:** `feat/offline-cold-launch` (plan: `docs/OFFLINE_SHELL_PLAN.md`, re-scoped — see the note at
  the end of this file)
- **Depends on:** A0 (`nginx/default.conf`) and A1 (`frontend/src/lib/query/persist.ts`) — the two pieces
  that make a cold launch *possible* at all. Before them there was nothing to boot from.
- **Depended on by:** nothing. It is the last gap in "it works offline" (§17.4), not a foundation.

## Context

Two different things were conflated under *"offline doesn't work"*, and only one of them was true:

| Works today (§17.4) | Did not work before this ADR |
|---|---|
| A **downloaded title plays** with no network — native filesystem, the loopback server, real `Range` support (ADR-0008, ADR-0009). The offline video path never calls `/api/jellyfin/playback-info`. | **A cold launch with no network never asked the DEVICE whether it already had the app.** It asked the network once, was refused, and went to *"Can't reach this server"*. |

⚠ **The premise "there is no service worker and no bundled UI, so there is nowhere to load from" was only
half the story, and the missing half was measurable.** E2 answered the service-worker question on
2026-09-14 — `navigator.serviceWorker` is **absent in this WKWebView on a secure origin as well as on the
app's own HTTP origin**, so a service worker is not an option this app declined; it does not exist here.
But A0 had already made the shell **storable**: `/` is served `Cache-Control: no-cache` (revalidated on
every load, but *stored* — it used to be `no-store`, which forbids keeping the document at all, and is why
an offline launch was impossible by construction) and Vite's content-hashed `/assets/*` are `immutable`
for a year. **So the bytes were already on the device, and nothing ever asked for them.**

The honest statement of the gap is therefore not a missing cache. It is a missing *question*.

## Decision

**A three-step launch ladder, and the live app is always asked first:**

| Step | What it loads | Why |
|---|---|---|
| `fresh` | the live URL, `URLRequest.CachePolicy.useProtocolCachePolicy` | Every launch starts here, so a working network always wins and there is nothing to "unstick". |
| `cached` | the same URL, `.returnCacheDataElseLoad` | Reached only when `fresh` failed for a **transport** reason (DNS, refused, no network, TLS). This policy answers from the device's own copy and touches the network only if there is none. |
| `unreachable` | **nothing** | Both attempts failed → `UnreachableServerView`, with its always-reachable *Change server*. This is a screen, not an attempt. |

The ladder is **pure Foundation** (`apple/ios/RKMCinema/Shell/ShellLaunchPlan.swift`) and the WebKit half
(`WebShellModel`) merely carries out the answer — the same split as `OfflineServerCore.plan` (ADR-0009),
and for the same reason: with the Wi-Fi off the app has exactly **one** shot at the cached copy, so *when
is it spent, and what happens after* is a rule that must be **run**, not reviewed.

## The alternatives, and why each lost

| Alternative | Why it lost |
|---|---|
| **The plan's `WKURLSchemeHandler` + a `ShellCache/` directory (§2 phases A and B)** | It is a **second cache of bytes WebKit already caches**, carrying its own sync step, its own eviction cap, its own atomicity discipline and its own staleness rules — for one document and two hashed assets. And its risk was already measured: E1 found custom schemes fail for this app's media (`mediaError=code=4`, *with* the bytes served), so a scheme handler would have to be justified anew for documents. ⚠ The decisive point is that `immutable` hashed assets + a revalidating document **IS** sync-on-successful-load: there is no diffing to write, and no drift for a store-shipped bundle to accumulate. |
| **Always load the cached copy first** (the plan's §1 option (b)) | The cached copy would become the default and the live app the exception, so a stale shell could outlive a deploy — and the plan's own falsification test (*"restore the network and confirm it goes back to loading live"*) would be the shape of a permanent bug. Worse, `.returnCacheDataElseLoad` **skips revalidation**, so the served `index.html` could name a hashed bundle the last deploy deleted: `/assets/` answers **`=404`** for exactly that case, deliberately (an SPA fallback there would be reported as a *syntax error* and send the next session looking at the bundle). |
| **A synced shell downloaded on every successful live load** (plan §2 phase B) | The sync step is what WebKit does for free once the headers allow storing. Building it also reintroduces the "app older than the page" problem the bridge already tolerates — except now for the WHOLE UI rather than one contract. |
| **Re-probing on foreground and reloading when the network returns** | ⚠ A reload while a downloaded film is playing kills the playback — the whole point of the feature. The ladder is therefore **per launch** (D4), and the recovery route is the one that already exists: *Try again*, or the next launch. |
| **Bundling the web app inside the app** | It breaks the property this design rests on: **every `apply` reaches the phone with no app rebuild** (§17.1). A bundled copy is a second UI to ship and a store release for a CSS fix. |

## The decisions inside the decision

**D1 — the order is `fresh → cached → unreachable`, and it is not configurable.** A setting would have to
be persisted, and a persisted "prefer local" is how an app ends up serving a superseded UI for a month.
The failure is the only thing that ever moves the ladder.

**D2 — `cacheFirst` for the `cached` step ONLY.** Spelled on the step (`ShellBootStep.asksCacheFirst`) and
mapped to a `URLRequest.CachePolicy` at **one** call site, so the rule cannot be re-derived somewhere else
by accident. See the table above for why the policy is wrong at `fresh`.

**D3 — no scheme handler, no `ShellCache/`, no second serving path.** ADR-0009 established *one* mechanism
for "how the app serves local bytes to the page" (loopback HTTP); this ADR establishes that there is *one*
mechanism for "how the app gets its own UI offline" (the WebView's HTTP cache). Neither is a second path.

> ⚠⚠ **D3 IS CONTRADICTED BY THE DEVICE ROUND (2026-09-19) — it stands here as the decision that was taken,
> and it must not be relied on.** Measured: the document IS served from the device, and the ~1.1 MB
> `/assets/index-*.js` is NOT — so the app never boots. WebKit refuses to cache a response larger than
> roughly **5% of its disk cache** (Apple's own documented rule for `URLCache`, whose iOS default disk
> capacity has been measured as low as **9 MB**), which fits a 1.6 KB document surviving and this bundle
> not, and it does not improve with freshness (his retest immediately after an online visit was blank too).
>
> **⇒ A scheme handler (or an equivalent app-owned store) IS required, as `OFFLINE_SHELL_PLAN.md` §2
> phase A originally said.** The HTTP cache is a shell store for a SMALL document, not for the app.
> ⭐ **And the shape of it was then MEASURED rather than chosen** — `apple/SPIKE_SHELL_ORIGIN.md`, run on
> his iPhone 2026-09-19: `loadHTMLString(_:baseURL:)` with the server's URL **does** give the page the
> server's origin (`/api/auth/me` → 200, so the session cookie travelled), a **module script does load
> from a `WKURLSchemeHandler`**, and — the fact that decides whether the offline shell carries the library
> or an empty app — **a document handed over this way shares the app's own `localStorage`**
> (`lsKeys: 4`, `lsSeesQueryCache: true`). See **D7**.

**D4 — per launch, reset by `load()`; and `reload()` now goes through `load()`.** It previously called
`webView.reload()`, which **re-sends the last request** — so a reload of a cached-booted page would re-read
the cache even with the network back. `load()` is the ONE entry point and it always starts at `fresh`,
which is what makes "no permanent stickiness" a property of the code rather than a promise.

**D5 — a benign cancellation does NOT spend the cached attempt.** WebKit cancels navigations for its own
benign reasons (`WebKitErrorDomain` 102, `NSURLErrorCancelled`), and those say nothing about the network.
This rule already existed as an early return; it now lives in the ladder, where it is falsifiable.

**D6 — the page is NOT told which step served it, and the bridge stays `v1`.** The page already computes
its own offline state from its own failed `/api/*` calls and B4's auth guard (`guardDecision` reads
*unreachable* as *offline*, not as *signed out*). Telling it would be a seam-2 contract change requiring
both sides to move — for a fact it does not need.

**D7 — the shell is APP-OWNED: the app keeps the document and its assets, and hands the document to the
page itself.** ⭐ This is the design D3 said was unnecessary and the device then showed is necessary, and
it is cheap because of three measured facts (`apple/SPIKE_SHELL_ORIGIN.md`):

1. the app fetches the document (and the assets it names) into `Application Support/ShellCache/` — the
   same durable directory decision as the offline downloads, and for the same reason (`Caches/` is
   purgeable by iOS, which is exactly what loses a WebView cache entry);
2. on the offline step it loads **that** document with `loadHTMLString(html, baseURL: address.url)` —
   ⭐ measured to keep the SERVER's origin, so the session cookie, same-origin `/api/*` **and A1's
   origin-keyed `localStorage` snapshot** all keep working. **That is why the origin does not move and no
   CORS, cookie or api work is needed.**
3. the document's asset URLs are rewritten to a custom scheme (`rkm-asset://…`) served by a
   `WKURLSchemeHandler` from that directory — measured to carry **module scripts**, which is the one thing
   E1's media result did not tell us.

**D8 — the store is refreshed on every successful LIVE load, and the offline step never invents content.**
A live load is already the moment the app knows the deployed shell; the document is small (1.6 KB) and the
assets are content-hashed, so a refresh is a diff, not a transfer. ⚠ The stored set is only ever used as a
**pair** — a document and the assets it names, fetched together — so a half-updated store cannot paint an
app whose script does not match its document, which is the failure `/assets/ =404` exists to make loud.
⚠ And when the store has nothing (a device that has never been online), the offline step falls back to the
plain cache-first URL load this ADR originally shipped — **degrade, never crash**.

## What this deliberately does NOT change

- **Seam 1 and seam 2** — untouched. No new route, no `openapi.v1.json` change, no bridge version bump.
- **`frontend/`** — nothing. Not one line: the shell it already serves is the thing being cached.
- **`backend/`, `nginx/default.conf`, `Config/Info.plist`** — nothing. A0's headers are what this relies on,
  and this change is downstream of them rather than alongside them.
- **The identity model (§11)** — the cached shell is the SAME app: it asks the same api for the same
  session, and offline it degrades exactly as B4 made it (the rows come from the persisted query cache,
  owned by whoever is watching).

## ⚠ What is verified, and what is not

**Verified here (Linux, executed):**
- The ladder's eight rules, each reverted one at a time and watched go red —
  `python3 apple/scripts/check-offline-core.py --falsify`.
- Types and call shapes of `ShellLaunchPlan.swift` against the stub scaffold —
  `bash apple/scripts/check-apple-typecheck.sh`.
- The missing-framework audit — `python3 apple/scripts/check-imports.py`.

**⚠ NOT verified — and this is the phase's one real unknown, so it is the Mac round's whole purpose:**
**does WKWebView serve a top-level DOCUMENT from its own cache when the origin is unreachable?**
`returnCacheDataElseLoad` is the API for exactly this and the document is storable (A0), but nothing in
this sandbox can run WebKit, and E1's lesson is that WebKit's behaviour here is *measured*, not inferred.
The falsification test is the plan's own, and it is run with the Wi-Fi actually off:

1. Launch the app on the regular network and browse something → the shell and its assets are now cached.
2. Turn Wi-Fi off. Force-quit the app. Relaunch.
3. **Expected:** the app paints, *not* "Can't reach this server". The log shows
   `shell boot: step fresh …` → `navigation failed … step cached` → `the server did not answer — trying the
   copy of the app this device holds` → `load #2 … step cached · cache-first`.
4. Turn Wi-Fi back on and relaunch → the log shows `load #1 … step fresh · revalidating` and the live UI.
   **No stickiness.**

⚠ If step 3 does NOT paint, the honest conclusion is that the WebView refuses a cached document for an
unreachable origin, and the answer becomes the scheme handler the plan proposed — which is why this ADR
records that option as *not chosen yet*, rather than as wrong.

### ⚠ The device round (2026-09-19) — and the prediction above was half right

**He ran it. The answer to the question this section asked is YES — the document DOES come back from the
device — and the app still does not paint.** The log chain proves the ladder engaged: `the server did not
answer — trying the copy…` → `load #2` → `didFinish / : title "RKM Cinema"` → `web page ready`, with the HUD
reading `web / · loaded`. What the same screenshot shows about the PAGE:

| Evidence | Reading |
|---|---|
| HUD `net —` (the "newest request" field) | ⚠ **The page made ZERO requests** — no `/api/auth/me`, no `/api/config` ⇒ React never booted. |
| `last` still shows the *navigation* failure; no `jserror` line | Nothing threw. ⚠ A `<script src>` that fails to load logs **nothing at all** — this is that signature. |
| The overlay covers 380×586pt of a 402×874pt screen; outside it the page is a flat `#08090b` (the app's own `--bg`) with **zero** bright pixels | No header, no bottom nav, no "Checking your session…" skeleton, no text. |

⇒ **The document is served from the device and its ~1.1 MB script is not.** ⚠ A retest *immediately after a
successful online visit* was blank too, so this is not cache ageing: the response is not being STORED.
Apple documents the rule for `URLCache` ("the response must be no larger than about **5% of the disk cache
size**"), and the iOS default disk capacity has been measured at **9 MB** — which fits a 1.6 KB document
surviving and this bundle not.

⚠ **So this ADR's own conclusion was wrong, and `OFFLINE_SHELL_PLAN.md` §2 phase A was right**: the shell
must be app-owned. The next step is a **spike** (in the E1 tradition — cheapest possible build, one Mac
round) to answer the two questions that decide its shape:

1. does `loadHTMLString(_:baseURL:)` with the **server's** URL give the page the server's ORIGIN — i.e. do
   the session cookie, same-origin `/api/*` and A1's persisted query cache (which is keyed by origin) all
   keep working?
2. does a **module script** load from a `WKURLSchemeHandler`? (E1 measured custom schemes out for **media**;
   scripts are a different risk profile, and CORS is required for module scripts.)

**✅ That round ran on 2026-09-19 and answered BOTH — plus a third question the answer raised — and it is
recorded verbatim in `apple/SPIKE_SHELL_ORIGIN.md` §Result: YES, YES, and `lsSeesQueryCache: true`.**
The design it settles is **D7/D8**.

⚠ `WebShellModel.swift` **cannot be typechecked in this sandbox** (SwiftUI/WebKit are not stubbable in the
committed scaffold), so the file that carries the ladder out is compile-checked for the first time on his
Mac. That is stated rather than glossed, and it is the reason the pure half is so thoroughly run here.
**Measured, not assumed** — adding it to `check-apple-typecheck.sh` as an experiment reports **8 errors,
none of them about this change**: the committed `WKWebView` stub deliberately has no `load`, `title` or
`configuration`, `UnreachableInfo` lives in `App/AppModel.swift` (outside the checked set), and the DEBUG
probe is `#if DEBUG`. ⚠ Making it checkable therefore means growing the stub scaffold — a separate change
with its own risk, because **a stub kinder than the real API is a gate that cannot fail** (`ARCHITECTURE.md`
§17.6).

## ⚠ Note on the plan this implements

`docs/OFFLINE_SHELL_PLAN.md` was written 2026-09-19 against the architecture *as documented*, and re-reading
it against the repo the same day found that **most of it already exists**:

- **Phase C** (persisted query cache) shipped 2026-09-14 as A1 — `frontend/src/lib/query/persist.ts`,
  gated by `tools/check_query_cache.py`.
- **Phase D's first tier** (posters visible offline) is already the artwork policy: `max-age=604800,
  stale-while-revalidate=604800` with an ETag, so a poster wall browsed within the week paints from the
  device with no network.
- **§5a** (audit "does it transcode compatible MKV?") is **done and was already worse than the plan
  guessed** — `choose_mode()` keys on codec/bit-depth/audio and then the container **family**, after the
  live B1 gate found 13 of 13 real MP4s being fully re-copied (ADR-0007 D3).
- **Phases A, B and E** are what this ADR replaces (A, B) or fulfils differently (E).

Still genuinely open, and NOT part of this phase: the poster + subtitle capture into a downloaded title's
bundle (ADR-0010 limit 1), and §5b's packaging/transfer pipeline — which would break ADR-0008 D4's
atomic-publish invariant and therefore needs its own decision and a measurement before any code.
