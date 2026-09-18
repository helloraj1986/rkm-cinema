# ADR-0012: the cold-launch offline shell — ask the device before declaring the server unreachable

- **Status:** Accepted · ✅ **built 2026-09-19** — the pure ladder is executed and falsified on Linux
  (`apple/scripts/check-offline-core.py --falsify`, 8 rules reverted); the WebKit half is written and
  typecheck-clean and ⚠ **unverified until his Mac round**, because a WebKit build cannot be run here.
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
