# ADR-0008: the device's half of offline downloads is a background session, an explicit Cookie header, and a `.part` file it never trusts

- **Status:** Accepted (phase B2 built; the Mac round is outstanding — see *What is NOT verified*)
- **Date:** 2026-09-16
- **Phase:** `feat/offline-downloads` (`NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4.4/§6, phase **B2**)
- **Depends on:** ADR-0007 (B1 — the server contract this consumes), `apple/SPIKE_E1_E2.md` (B0 — the
  measurement that made loopback playback a fact, and therefore made "hold a real file" the device's job)

## Context

B1 gave the server the ability to **hand a film over**: `prepare` packages one title, `HEAD` reports its
size, `GET` serves it byte-ranged, `DELETE` drops the copy. Nothing consumed it. B2 is the consuming
half on **iOS** — one client, two devices (the iPhone and the iPad run the same WKWebView shell) — and its
gate is a sentence about behaviour, not about code:

> *Downloads complete with the app backgrounded, resume after a forced failure, and appear in the manifest
> after a relaunch.*

Three constraints shape everything below, and two of them changed the world after B1 was written:

1. **⚠⚠ `RKM_AUTH_REQUIRED` is now `true`.** B1's own step-5 probe was answered
   `401 {"detail":"Sign in to use this app"}`, so **all six `/api/offline/*` routes are session-scoped**.
   A native `URLSession` has **no cookie jar of its own**, which turns §4.4's "cookie mirroring" from a
   nicety into a hard prerequisite.
2. **The two legs are different networks, deliberately** (B0's measurement): the download rides the
   **tailnet** (`rkm-hp…:8124`, ≈3.8 MB/s → ~9 minutes for a 2 GB film, worse if DERP-relayed), while
   playback is **loopback**. So the transfer must survive a network that stalls, and it must be resumable
   — the thing B1's `Range`/`206` support exists for.
3. **The Mac is the only place this can be *run*.** `apple/WORKFLOW.md` §5 is blunt: everything UI, and
   every Apple SDK API, is Mac-only, and a build that has not run is not verified. That is why the
   decisions below are pushed into pure Foundation code wherever they could be.

## Decision

### D1 — A **background** `URLSession`, one task per item, with a stable identifier

`URLSessionConfiguration.background(withIdentifier:)`, `sessionSendsLaunchEvents = true` (the system may
relaunch the app to hand over a finished transfer), `isDiscretionary = false` (a film the user asked for
starts now, not when iOS decides the phone is idle and charging — the opposite of Apple's own sample, and
deliberate), and `timeoutIntervalForResource = 6 h` (a tailnet stall that recovers, not a target).

⚠ **The identifier is derived from the bundle id and must never change**: the system matches a relaunch to
a session by that string, so a build that renames it orphans every in-flight download.

⚠ **This is the first thing in this app that needs an `AppDelegate`.** A SwiftUI `@main` app has none, and
iOS delivers background-session events to the **application delegate** only —
`application(_:handleEventsForBackgroundURLSession:completionHandler:)` and
`urlSessionDidFinishEvents(forBackgroundURLSession:)` are the two halves, and *both* are required: the
first hands the app a completion handler, the second must call it or the system keeps the session's
background budget reserved and treats the app as busy. Implemented as `@UIApplicationDelegateAdaptor`.
⚠ Apple's own guide for background downloads specifies exactly this flow (create the config → provide a
delegate → store the handler → call it in `urlSessionDidFinishEvents`), and **no `UIBackgroundModes`
entry is part of it** — see *What is NOT verified* for the honest caveat.

### D2 — Cookies are attached **explicitly**, and the session is told not to touch them

`CookieMirror` (`WKHTTPCookieStoreObserver`) mirrors the web view's jar; `CookieHeader` decides which
cookies may go on which request; the download request carries a literal `Cookie:` header. The session is
built with `httpShouldSetCookies = false`, `httpCookieAcceptPolicy = .never`, `httpCookieStorage = nil`.

Two rejected alternatives, and the reason each was rejected:

* **`httpCookieStorage = HTTPCookieStorage.shared` + copy WebKit's cookies into it** (§4.4 option 1 as
  written). Rejected because a background session's own cookie handling is documented to use the shared
  store *inconsistently* — the known bug is cookies lost on redirects (Apple r.16,852,027), and the
  workaround the community converged on is exactly this ADR's decision: set the header yourself. A silent
  cookie loss is a **mystery `401`** at the moment the user committed to a 2 GB download, which is the
  worst possible failure to debug.
* **A device bearer token** (§4.4 option 2, `APPLE_CLIENTS_PLAN.md` phase 2). Cleaner — it removes the
  session-expiry edge entirely — but it is a backend change and a bigger dependency for this feature.
  ⚠ Still the recommended destination; this ADR does not close that door, it just does not make B2 wait
  for it.

⚠ **The observer is the part that earns its complexity**: it fires when the *page* signs in, so the native
side learns about a new session with **no page change at all**. Polling the jar was the alternative and it
can miss the one moment that matters.

⚠ **Cookie values never become loggable strings.** `CookieSnapshot` conforms to `CustomStringConvertible`
with a names-only `description`, so the first stray `RKMLog.verbose("cookies: \(cookies)")` cannot leak
`rkm_session` into a file that is pasted into chat (`LOGGING.md` §6/§9 make that grep an acceptance gate).
That conformance is pinned by a check *and* by a falsification — it is the kind of safety that has to be a
property of the type, not of every call site.

### D3 — Resume with an explicit `Range`, then **verify the splice**

The device keeps its own `.part` file and asks for `bytes=<offset>-` on a resume. The arithmetic and the
rules live in `OfflinePlan.swift` (Foundation-only, Linux-tested, 30 falsifications), because a wrong
resume produces a film that **plays** and is wrong for the rest of its length — the nastiest failure
available here. The rules, each of which exists because of a specific way this corrupts a file:

| Rule | Why |
|---|---|
| Completion requires **size AND ETag**; a size-only match is recorded as the weaker claim | a re-packaged rendition can land on exactly the same size |
| A **changed ETag restarts** rather than resumes | appending a new file's tail to an old file's head is a film with a bad seam |
| A partial with **no recorded ETag restarts** | it cannot be proven to belong to the file now on offer; nine minutes of re-transfer is cheaper than a wrong edit |
| A local file **bigger** than the server's is a restart | it is not this file |
| A `206` whose `Content-Range` **start** ≠ the requested offset is **refused**, not written | the splice would put wrong bytes at the seam |
| A `206` whose `Content-Range` **total** ≠ the size `HEAD` reported is **refused** | the artefact changed underneath the download |
| A `200` to a **ranged** request **replaces** the partial (and says how many bytes it discarded) | the server ignored the `Range`; appending would produce a file of exactly the wrong length |
| A **zero-byte** server artefact is refused before anything else | "0 bytes local, 0 bytes remote" would otherwise read as *complete* — an empty file that plays as nothing |

⚠ The fragment is appended with `FileHandle` in 1 MB blocks, never `Data(contentsOf:)`: the household's
library has a 1,882,377,499-byte film (measured in B1's live gate), and loading that on a phone is how a
background download becomes a memory kill.

⚠ **Everything in `didFinishDownloadingTo` is synchronous, deliberately.** The temp file is deleted the
moment that method returns, so the splice, the size check and the publish happen inside it — no `Task`, no
`async`, no `DispatchQueue.async`. Getting that wrong yields a download that reports success and a film
that is not there.

### D4 — The manifest is an index; the **filesystem is the truth**

`manifest.json` (versioned, atomic write, tolerant decoding, refuses a *newer* version rather than
half-reading it) records what each download **is**. `OfflineStore.reconcileFromDisk` re-derives what each
download **has** on every launch: `bytes` from the two files that can hold them, `ready` only from a
published file whose size matches the server's, and `failed` when the index claims a file that is not
there. ⚠ One destructive branch, and it is deliberate: a published file whose size disagrees with the
server's is not a film, it is a corrupt copy that would play badly, so it is discarded **and said so** —
the version is on the server and can be re-fetched; a lie in the index cannot be repaired.

⚠ Progress is **not** persisted. It lives in memory and is re-derived from the `.part` size, because the
one thing that cannot be re-derived is a *state* — so only states are written often.

### D5 — Failure is classified once, and only three things are retried

`OfflineHTTPVerdict` / `OfflineFailure` (pure, checked on Linux) map a status to a decision, and the retry
policy is deterministic (`3s, 15s, 60s`, 4 attempts max, no jitter — jitter protects a shared server from
a herd, and this is one device talking to one household server; an untestable schedule is the worse trade).
⚠ **`404` and `410` are not retried** — retrying them is a loop that never ends. ⚠ **`401` is not retried**
— the fix is a human signing in, and the row says so; a retry loop would fill the log while the actual fix
waits. ⚠ **`416` IS retried, but from zero**, because the offset is what was stale.

### D6 — Item ids are **validated, not rewritten** (a deliberate deviation from the server's own rule)

The server *rewrites* an unsafe id (`safe_id`: strip to `[A-Za-z0-9_-]`, truncate, append a hash when that
changed anything). The device **refuses** an id outside that character set. A rewrite is an *alias*, and an
alias is the one thing that can put two different titles in one directory; refusing is the stronger rule
when the raw id is already known to the server. A real Jellyfin id is 32 hex characters, so this has never
fired — and if it ever does, the sentence names the id and the fix is on the server side, not a silent
local alias.

### D7 — The phase is testable **before B4 exists**: a dev-only trigger, and a Linux gate for the rules

⚠ B2 is the downloader; the page affordances are **B4** and the loopback server is **B3**. Without
something to press, the phase's own gate could not be tested on the Mac and B2 would be handed over
unverified. So:

* a **DEBUG-only panel in the debug HUD** (`Debug/OfflineDebugPanel.swift`): it lists real library titles
  (via `/api/library/items`), starts a download through **the same API the page will call in B4**, and
  shows state/percent/ETA/errors with Cancel / Resume / Retry / Delete. It is deleted when B4 lands and is
  explicitly not the beginning of a native UI;
* **launch arguments** for a scriptable Mac round: `-RKMOfflineItem <id>` and `-RKMOfflinePick YES`;
* **`apple/scripts/check-offline-core.py`** — compiles the three Foundation-only sources with `swiftc` on
  Linux, runs 194 checks, and with `--falsify` **reverts every rule one at a time** and requires the
  matching check to go red. This is the only part of B2 that can be *executed* without the Mac, so it is
  where the correctness burden was deliberately placed. `apple/scripts/check-imports.py` also grew rules
  for the new WebKit/UIKit members (and grew a documented **exception** for `isHTTPOnly`, which is ours as
  well as WebKit's and would otherwise force a WebKit import into a Foundation-only file).

## Consequences

* **What this buys, stated as the gate:** the transfer is a background session (completes while the app is
  suspended), the resume path is `Range`-based and verified against the server's ETag, and the manifest
  survives because it is re-derived from disk.
* **The one new shared-package change:** `LogCategory.offline`. Categories exist so one area can be
  filtered (`--predicate 'category == "offline"'`), and downloads are their own area. The 66 shared tests
  pass.
* **⚠ The honest limits, all of them:**
  1. **Nothing here has run on the Mac.** It is written, import-checked, syntax-checked, and its rules are
     executed and falsified on Linux — but the URLs, the delegate callbacks, the background session and
     the SwiftUI panel are **unverified until the Mac round**, and `WORKFLOW.md` §5 says exactly that.
  2. **A packaging wait (`remux`/`transcode`) needs the app awake.** The transfer does not — a background
     session lives in a system process — but the *polling* for a packaging job happens in our process, and
     an assertion buys only the standard grace period. A long packaging job plus a backgrounded app is a
     wait that resumes when the app is opened again. Stated, not papered over.
  3. **A packaged rendition has still never been measured end to end** (B1's own open item): every live
     check so far used a *borrowed*, direct artefact. B2's first real download of an MKV is the moment
     that changes, and the log is designed to show it (`mode`, `needs_transcode`, the artefact's size and
     ETag, and each fragment's status/`Content-Range`).
  4. **No eviction, cap, pin or "delete after watching"** — that is B5. No artwork/subtitle capture yet
     (§4.6 puts both at download time; B4 owns the page side that decides what to ask for).
  5. **`UIBackgroundModes` is not set**, following Apple's own guide for background downloads, which does
     not ask for it. If the Mac round shows the system does not relaunch the app for a finished transfer,
     adding `fetch` to `UIBackgroundModes` in `Config/Info.plist` is the first thing to try — a one-line,
     already-owned file.
  6. **Wi-Fi-only is a preference, not a guarantee** (`allowsCellularAccess`), and it defaults to off.
