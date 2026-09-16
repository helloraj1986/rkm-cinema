# ADR-0009: the device's loopback server is a token, a byte range, and a decision made in pure code

- **Status:** Accepted (phase B3 built; the Mac round is outstanding — see *What is NOT verified*)
- **Context superseded in part:** ADR-0008's own Mac round **PASSED** on 2026-09-16, so the file this server
  serves is a file the device has actually produced — not one taken on trust
- **Date:** 2026-09-16
- **Phase:** `feat/offline-downloads` (`NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4.4/§4.5/§6, phase **B3**)
- **Depends on:** ADR-0008 (B2 — the device has the file), `apple/SPIKE_E1_E2.md` (B0 — the measurement
  that says media DOES play from `127.0.0.1` inside this WKWebView, with seeking, proved by a `206` on the
  wire rather than by the page's own report)

## Context

B2 gave the device a film. It is a file in `Application Support/Offline/<item>/media.mp4`, and the page
that has to play it lives at `http://<server>` — a different origin, with no access to the app's filesystem.
B0 already answered the only question that could have changed the design: a `<video>` inside the shell **does**
play from a loopback HTTP server, and **seeks** (the server answered `206 Partial Content bytes 0-1/1128375`
and then a real range). B3 is the half that makes that reproducible:

> *the loopback server passes a Range test suite; the page round-trips a command and a progress event.*

⚠ Three things about this phase decide everything below:

1. **It cannot be run here.** `apple/WORKFLOW.md` §5: this sandbox has no Xcode, and B3 is 100% Apple APIs
   (`NWListener`) plus a `WKWebView`. A phase like that, written blind, is how B2 delivered a build that
   failed on one `Int64?` — the same class of mistake, one layer up.
2. **The arithmetic is where the danger is.** A wrong byte range does not fail loudly; it produces a film
   that plays and is wrong from that point on. That is the same failure mode B2's resume work was shaped
   around, and the reason both phases push their rules into code that can be *executed*.
3. **A loopback server is a server.** It reads the user's device and writes to a page. It must not be
   reachable off the device, must not be able to serve the wrong title, and must not be tricked into
   reading outside one directory.

## Decision

### D1 — The split is pure-vs-socket, and the *pure* half is where every decision lives

`OfflineHTTP.swift`, `OfflineBridgeContract.swift` and `OfflineProbeCases.swift` are **Foundation-only**
sources, compiled and RUN on Linux by `apple/scripts/check-offline-core.py` (445 checks; every rule reverted
one at a time by `--falsify`). They decide:

* what a request head means (method, target, headers, duplicates, folding, size limits);
* whether a path is one we serve at all, and which handle it names;
* **what a `Range` asks for**, resolved against the real size, and therefore the status, the
  `Content-Range`, the offset and the length;
* the entire response head, header by header, including the refusal to write a value containing CRLF;
* which commands the bridge accepts, what every refusal is called, and what the page is told and when.

`OfflineServer.swift` is what is left: an `NWListener`, a byte accumulator and a `FileHandle`. It decides
nothing — it asks `OfflineServerCore.plan(requestData:tokens:resolve:)` and carries out the answer. ⚠ **The
socket calls the same entry point the Linux harness calls**, so the two cannot drift: the Mac round tests
the code the Linux gate executed, not a second implementation of it.

### D2 — Bound to loopback by the listener's own endpoint, and on an ephemeral port

`NWParameters.requiredLocalEndpoint = .hostPort(host: .ipv4(.loopback), port: .any)`.

* ⚠ **Loopback-only is a property of the socket, not a check in a handler.** "We look at the peer address"
  is a second thing that can be wrong, and a film server reachable from the tailnet would be a way to read
  the household's media through a phone.
* ⚠ **Ephemeral, not fixed.** A fixed port can be occupied by something else on the device — and the page is
  told the real port over the bridge, so there is nothing to gain by fixing it.

### D3 — A **token**, never a path: there is no client-supplied filename anywhere

The route is `/offline/<32 lowercase hex>.<ext>` and nothing else. The file is found by looking the token up
in `OfflineTokenBook`, which was populated from the store, so **there is no path for a traversal to traverse
to** — but the shape is still validated strictly, because a token-shaped hole is only safe while it stays
token-shaped:

* ⚠ **Percent-encoding is REFUSED, never decoded.** Decoding can only ever produce a path we never minted,
  and a decoder is the classic way `%2e%2e%2f` becomes `../`. `%` is not a hex character, so it fails
  validation on its own terms.
* ⚠ **Uppercase hex is refused**, so a token has exactly ONE spelling and an equality test cannot be wrong
  by accident.
* ⚠ **`entry(for:)` never falls back.** There is no "or the first one" — that is how the wrong film gets
  served under the right title (the identity rule of ADR-0008 D6, one layer up).
* ⚠ **One live token per title.** A re-download that lands a different rendition drops the previous token,
  so a URL that points at a file that is gone cannot still resolve.
* ⚠ **`forgetAll()` on an address change or a sign-out.** A token minted against a previous server names a
  film from another library, under this one's title.

### D4 — The Range rules, each of which exists because of a way this corrupts a film

| Rule | Why |
|---|---|
| `bytes=a-` with `a >= size` is **416**, never a clamp | there is nothing at that offset; answering with the last byte puts the wrong frame on screen with no error anywhere |
| A last-byte-pos past the end **IS** clamped (`bytes=a-999999` → `a..size-1`) | the start names a real byte, so there is a correct answer — and refusing would break the players that ask for more than exists |
| `bytes=-N` means the **last** N bytes, `-0` is unsatisfiable, `-N > size` is the whole file | the suffix form is the one that reads backwards in the spec, and the one an off-by-one turns into the first N bytes |
| **Multiple ranges → the whole file (200)**, never `multipart/byteranges` | a contiguous film is what a player wants, and multipart is a second format to get wrong for no gain |
| An unreadable/other-unit `Range` → the whole file | both answers are defensible; a player that receives a `200` plays, while a `416` leaves it stuck on an error nobody can act on |
| A duplicated `Range` header is **refused (400)** | two conflicting ranges means there is no single correct answer to give |
| A `206` states `Content-Range: bytes a-b/size`; a `416` states `bytes */size` | RFC 7233 requires both, and the 416's is the only thing that tells a player how big the file really is — which is how it recovers |
| A zero-byte artefact is **404** | "0 bytes local, 0 bytes remote" would otherwise read as complete: an empty file that plays as nothing |

### D5 — A HEAD tells the truth about the body it will not send

`HEAD` is served, not special-cased away, and the plan — not the sender — decides that it has no body while
`Content-Length` still reports the real length (of the **range**, when one was asked for). ⚠ A lying HEAD is
the single most common way a media player mis-seeks, and the case is in the suite (`head-with-range`).

### D6 — The bridge is versioned, and **every** command is answered

Page→native: `{v:1, c:"list"|"download"|"cancel"|"delete"|"play"|"ping", …}` over a
`WKScriptMessageHandlerWithReply`; native→page: `window.__rkmOffline.emit({v:1, e:"state"|"progress"|
"ready"|"removed", …})`.

* ⚠ **A refusal is a reply.** A `postMessage` the page can never settle is a button that does nothing and an
  error nowhere, so an unknown command, an unreadable body, a missing item id, an unknown rendition, or a
  version this build does not speak are all answered with a **code** (what the page switches on) and a
  **sentence** (what a human can act on).
* ⚠ **The version is required and exact.** A page newer than the app is refused with "update the app" rather
  than guessed at, which is the only honest answer when the payload shape may have changed.
* ⚠ **A download is accepted, never "done".** A 2 GB transfer cannot be a return value; the result arrives
  as an event.
* ⚠ **The handler is registered with `addScriptMessageHandler(_:contentWorld:name:)`**, not `add(_:name:)`.
  Only the reply-capable form makes `postMessage` return a Promise — with the plain form every command would
  silently be a promise that never settles. (The injected script also *checks*: a reply that is not a
  thenable is a rejection with a sentence, never a hang.)

### D7 — The URL is a capability, so it goes to the page and nowhere else

* ⚠ **Never in the manifest** (ADR-0008's manifest holds no token) — the port changes every launch, so a
  cached URL is a stale URL.
* ⚠ **Never in the log.** The server's log line prints the path **by shape** (`/offline/<handle>.mp4`), and
  the page's probe report carries the *shape* of an event (`{e, itemId, state, percent, hasUrl}`) rather
  than the payload. `LOGGING.md` §9's acceptance grep is `password|token|api_key|rkm_session` over a real
  log, and ⚠ **the log deliberately says "handle", not the domain word "token"** — a security grep that has
  acquired exceptions is a security grep that gets weakened, so the wording gave way instead.
* ⚠ **No `UIBackgroundModes` and no ATS change**: `Info.plist` already carries `NSAllowsArbitraryLoads`,
  which covers `http://127.0.0.1`. ⚠ **The B0 warning stays load-bearing:** adding
  `NSAllowsLocalNetworking` *disables* `NSAllowsArbitraryLoads` on iOS 10+, which would break the loopback
  server outright.

### D8 — What the page is told, and how often: a pure event planner

`OfflineEventPlanner` (pure, falsified) decides whether a change is worth waking the page for:

* ⚠ **`previous == nil` → a state event.** The page is never assumed to know anything; every title is
  announced at least once per process, which is also why the page's first paint is right instead of "wait
  for something to change".
* ⚠ **State changes are never throttled; progress always is.** They are different promises: a missed state
  change is a UI that lies, while an unthrottled progress stream is ~10 `evaluateJavaScript` calls a second
  for a number that moved by a tenth of a percent. Progress is emitted at whole-percent steps.
* ⚠ **A rewind is a state change, not progress** (a restart must be visible, never a silent backwards bar),
  and it **resets the throttle** — otherwise a restart at 3% would re-announce itself on every tick until it
  climbed back past the old percentage.
* ⚠ **An unknown total is never a percentage.** `percent` is `nil` when `totalBytes == 0`, and the planner
  has no other guard: one place decides, so one check pins it.
* ⚠ **The URL appearing is its own event** (`ready`) — that is the moment a film becomes playable with the
  network off. The URL **disappearing** is a state change, because the page must stop offering it.
* ⚠ **The page is told what it still holds.** A row the downloader has forgotten (a delete) is announced,
  and its token dropped; `vanished` is sorted so the order is deterministic.
* ⚠ **A loaded page knows NOTHING, and the bridge acts on that.** `snapshots` records what the page has been
  told, so a navigation (a reload, a sign-in redirect, a new address) would leave every real change judged
  "already sent" and the offline UI empty until something *changed* — which, for a finished download, is
  never. `OfflineBridge.pageDidLoad()` (called from `WebShellModel.didFinish`) clears what was told and
  re-announces every title: the same rule the pure planner starts from, because a new page IS `previous ==
  nil`.

### D9 — The phase is testable **before B4 exists**, and its gate is a shared table

The suite's cases are DATA (`OfflineProbeCases.cases(size:)` — 16 cases, derived from the real size), used by
both worlds:

* **Linux**: `check-offline-core.py` drives each case through `plan(requestData:)` — status,
  `Content-Length`, `Content-Range`, the planned body length, and a **round trip** of the response head back
  through the client-side parser (`OfflineProbeWire.parseHead`) to prove the sender's bytes and the reader's
  expectations are one document;
* **the Mac**: `Debug/OfflineServerProbe.swift` (`-RKMOfflineServerProbe YES`) sends **the same composed
  heads** over a real socket to a real listener, and adds the two things only a live run can show — that the
  bytes are the file's bytes **at the offset asked for** (a shifted range returns the right count and the
  wrong film), and that `URLSession` — the stack WebKit itself sits on — agrees.
* ⚠ The probe runs against a **1 MiB synthetic artefact it creates itself** (deterministic bytes, inside the
  offline root). Fetching a 2 GB film to prove a Range works would be a terrible test. The one thing the
  synthetic file cannot prove — that the URL the **bridge** mints for a real download works — is a separate
  **HEAD-only** check (`real-film-head`), which reads the length without the body.
* ⚠ **The native→page direction needs a witness outside the native code**, so the page reports every event it
  receives back through the EXISTING instrumentation channel (`WebBridge`). It is the only thing that can
  distinguish "the page got it" from "we called `evaluateJavaScript` and nothing threw". The bridge probe
  (`-RKMOfflineBridgeProbe YES`) re-announces the REAL rows through the production path — nothing is
  fabricated — and asks `ping` + `list` so the reply direction is exercised in the same action.

## Consequences

* **What this buys, stated as the gate:** a film the device holds is addressable from the page by a token
  that dies with the process, served byte-exact over loopback with real `Range` support, from a server that
  cannot be reached off the device and cannot name another title — and the page learns about every download
  without polling.
* **The honest limits, all of them:**
  1. ⚠ **Nothing here has run on the Mac.** It is import-checked, typechecked per file against a stub
     scaffold (`apple/scripts/check-apple-typecheck.sh` — which caught a duplicated `#if DEBUG` that would
     have failed the build outright, and a `Result<Data, String>` whose failure type does not conform to
     `Error`), and its rules are executed and falsified on Linux. The socket, the delegate callbacks and the
     `WKWebView` wiring are unverified until the round.
  2. ⚠ **The probe is a DEBUG-only artefact and is expected to be deleted** when B4's page affordances make
     the feature reachable by hand. It is not the beginning of a native UI.
  3. ⚠ **Two bugs were found by re-reading the wiring after the typecheck passed**, and neither is visible to
     a compiler: a second `start()` while the first was still coming up would have built a **second listener
     on a second port** (the page holding a URL nobody reads), and nothing re-announced the download state to
     a page that had just loaded (the JS-side queue covers events that arrive before a *listener*, not a page
     that did not exist yet). Both are fixed above; both are the class of thing only the Mac round can
     confirm.
  3. **Playback itself is not exercised here.** B3 serves bytes and proves them; whether the `<video>`
     element seeks against *this* server is B0's measurement plus B4's player path.
  4. **No artwork or subtitle serving.** Those are files in the item directory and will need their own routes
     (or the same one, extended) — §4.6 puts their capture at download time, and B4 owns the page side.
  5. **No keep-alive.** `Connection: close` on every response: a `<video>` reopens what it needs, and
     one-request-per-connection is the version with fewer ways to be wrong.
