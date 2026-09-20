# tvOS client — Phase C (playback: AVPlayer, resume, progress) — plan

⚠ **Every number in this file came from a command run on 2026-09-19, on branch `feat/tvos-player` cut from
`dev` (`0d75e1f`)** — with **two exceptions, both marked where they appear**: the **`1177` pytest count** (§6) and
the **`check-offline-core.py` / browser-check** totals are **quoted from `docs/ARCHITECTURE.md` §15**, not
re-measured here. §15's own rule applies to them: *"Verify the numbers below on the day … the commands are the
contract, not the totals."* Where a claim could NOT be measured here (no tvOS SDK, no Mac, no
SwiftUI/AVFoundation on Linux) it is marked **[hypothesis]** and given a falsifier, never written as fact.

---

## §0 — What this phase is, and the one decision it carries

Phase C is the recorded next step of the tvOS client (`apple/tvos/README.md` §8, `docs/APPLE_CLIENTS_PLAN.md`
§4.4): **play a film on the Apple TV, resume where it left off, and have that position show up in the web app's
Continue Watching.**

**The auth design is NOT this plan's decision — it is already recorded.** `APPLE_CLIENTS_PLAN.md` §4.4 measured
on 2026-09-13 that *"auth is cookie-only today … there is no `Authorization` path anywhere in the tree"* and
recorded three additive backend changes (B1–B3) plus the reason for them: *"do not bet playback on cookie
propagation"* to HLS **segment** requests. §1 and §2 below re-measure that claim and confirm it still holds.
This plan does not relitigate it.

**What IS open is the *carrier*: how the credential reaches `AVPlayer`.** The record says "accept
`Authorization: Bearer`" (B2) **and** "inject the session token into each rewritten URI" (B3) — two different
carriers for the same credential, and **a header does not carry a segment request from `AVPlayer`**. §2 lays out
the three ways to close that gap.

⚠⚠ **But this plan does NOT build it yet, and that ordering is the plan's most important choice.** Whether
`AVPlayer` carries a credential to a **segment** request is a claim about **Apple's platform** that cannot be
tested anywhere but the Mac. This repo has twice paid for building on exactly that kind of claim — `RailFocus.swift`
was written and **deleted** because tvOS's focus engine already scrolled the rail, and B3's 2-D grid was
"predicted to be the ONE focus case the platform does not solve for you" and was not. The rule it left behind:
*do not pre-build for a platform behaviour you cannot test; ship the platform's behaviour and let the round's
falsifier disprove it* — and pick a failure mode that is **visible** and one line to fix.

So the phase is ordered to **measure, not bet**: the player is built first against the **cookie carrier the app
already has** (zero backend change), and **C4's F2 is the measurement** that either retires the backend change
for good or supplies the evidence that justifies it. **A `401` on a `…/hls/…` request in the log is that
visible failure mode.** §2's recommendation is therefore recorded as the *fallback to build if F2 fails*, not as
work to do up front — and the only cost of being wrong is that F2 is answered by the round that had to happen
anyway to see the player at all.

**What it costs.** ⚠ If F2 fails, this is the **only phase of this client that touches `backend/`** — every
earlier phase changed `apple/` and `docs/` only, and B0 deliberately kept `backend/` untouched for exactly that
reason. If F2 passes, that cost never arrives, and the deployment question in §6 never becomes real.

**And it is the only phase whose risk is concentrated in the identity seam** — the one place
`ARCHITECTURE.md` §11 says a credential comes from, and the place where a silent fallback once wrote a password
to the wrong account while reporting success. §5 lists the one option that would have widened a fix to the
wrong place, so it is not relitigated.

---

## §1 — What already exists (measured)

**Everything the player needs already exists server-side.** Phase C adds no playback endpoint.

| Endpoint | Exists? | What it is | Evidence |
|---|---|---|---|
| `GET /api/jellyfin/stream/{item_id}` | ✅ | Direct progressive video, `Range` forwarded (`206` on a range) — the byte-seekable path. `mode` selects `direct` / `remux` / `transcode_audio` / `transcode`, and `start_time_ticks` restarts a non-direct stream at an offset | `backend/api/routes/jellyfin_stream.py:60` |
| `GET /api/jellyfin/hls/{item_id}/master.m3u8` | ✅ | Same-origin HLS master. Fetches Jellyfin's master with the codec pair for `mode`, then **rewrites every URI**: the embedded `api_key` is stripped and relative URIs are kept relative | `backend/api/routes/jellyfin_hls.py:127`, `_strip_api_keys` at `:100` |
| `GET /api/jellyfin/hls/{item_id}/{rest:path}` | ✅ | Passthrough for the media playlist + segments. Forwarded query carries `MediaSourceId` + codec params; a server-side `api_key` is added and any client `api_key` dropped | `backend/api/routes/jellyfin_hls.py:207` |
| `POST /api/jellyfin/progress` | ✅ | Resume + watched. `event` ∈ `start｜timeupdate｜stopped`; `position_ticks` in Jellyfin 10 ms ticks. A `stopped` within `FINISHED_FRACTION = 0.95` marks the item **watched** instead of storing a resume point at the credits. Answers **204** | `backend/api/routes/jellyfin_stream.py:166`, `:164` |

**All four are session-scoped, and that is the whole problem.** `backend/api/main.py:49` defines
`SESSION_SCOPED = [Depends(require_live_credential)]` and applies it per router — `jellyfin_stream_routes` at
`:93` and `jellyfin_hls_routes` at `:94`. So a request without a resolvable session gets `401`, and
`acting_media_token()` (`backend/api/session.py:281`) answers with **the profile's** credential — which is the
point: *"a missed site would silently show the administrator's library and watch state to a household member"*.

**Measured against the deployed stack** (`scripts/probe_stack.py`, 2026-09-19):

```
  /api/library/folders           -> HTTP 401 b'{"detail":"Sign in to use this app"}'
  /api/library                   -> HTTP 401 b'{"detail":"Sign in to use this app"}'
  /api/library/continue-watching -> HTTP 401 b'{"detail":"Sign in to use this app"}'
  /api/watchlist/entries         -> HTTP 401 b'{"detail":"Sign in to use this app"}'
```

⇒ The app is answering, and it is enforcing the session. Nothing is misconfigured.

**The web player's rules already exist and are the porting target** — `frontend/src/features/playback/`
(`lib.ts` 771 lines, `Player.tsx` 1949 lines). The portable, testable rules Phase C must reuse rather than
reinvent (they are the same rules the web app has been running in production):

`fmtTime` · `isFiniteDuration` · `barTotal` · `clampSeek` · `pickStreamMode` · `streamModeLabel` ·
`playMethodForMode` · `audioCodecNeedsTranscode` · `videoNeedsTranscode` · `QUALITY_OPTIONS` ·
`AUTOPLAY_DELAY_MS` · `nextPlayableEpisode` — the last of which `Core/DetailRules.swift` **already ports**
(B4), so the player reads the same rule the detail screen's `Resume S1E4` verb comes from.

⚠ **`nextPlayableEpisode`'s stable-sort hazard is already documented** in `DetailRules` (the web relies on
JavaScript's stable sort; Swift's `sorted(by:)` does not promise one). Any further port from `lib.ts` inherits
the same class of hazard and gets the same treatment: write it the long way and pin it with a mutation.

---

## §2 — The one decision: how the credential reaches `AVPlayer`

`backend/api/session.py:236` — the single identity seam — reads exactly one thing today:

```python
session_id = str((request.cookies or {}).get(SESSION_COOKIE) or "")
```

`POST /api/auth/login` (`backend/api/routes/auth.py:128`) sets that cookie `HttpOnly`. And the file's own rule
(`auth.py:12`) is *"the Jellyfin token is NEVER in a response body, a log line, or the cookie"* — so the thing
that may be handed to a client is the app's **opaque session id**, never the media-server credential.

Re-measured 2026-09-19: `grep -rn "Authorization\|Bearer\|authorization" backend/api backend/services` returns
**no inbound auth path** — every hit is an *outbound* header (Jellyfin `X-Emby-Authorization`, OpenSubtitles
`:335`, trailers `:92`). The 2026-09-13 measurement holds.

**Ordinary REST calls need nothing.** `Core/APIClient.swift` uses `URLSession.shared`, which shares a cookie
store, so sign-in → Home → Browse → detail already authenticate. That is why Phases A and B needed no backend
change at all.

**`AVPlayer` is different** because the HLS **media playlist and every segment** are separate requests made by
playback machinery, not by our `URLSession`. **[hypothesis]** a header (or cookie) set on the *asset* does not
reliably reach those sub-requests. That is the recorded reason for B1–B3, and it is the one thing this phase
must settle with a measurement rather than an argument (§3, C1).

### The carriers, and the gap in the record

The record's B2 (Bearer header) and B3 (token injected into the rewritten URIs) are **different carriers for
the same credential** — and the one that survives to a segment request is the **URI**, because the HLS proxy
already rewrites every URI and can put anything it likes in one. So B3's carrier needs a resolution path that
B2's header does not provide. Three ways:

| | Approach | Blast radius | Cost / risk |
|---|---|---|---|
| **(a)** | Accept the session id as a **query parameter in the one seam**, i.e. every route | **Widest** — a session id may then appear in *any* URL | One function, but the surface it accepts grows for all ~20 routers |
| **(b)** | Accept the session id as a query parameter **only on the two HLS routes** — still resolved by the ONE function, called with an explicit opt-in | Narrow: two routes | Resolution logic stays in one place; the opt-in is a parameter, not a second copy of the rule |
| **(c)** | Mint a **short-lived playback token** bound to (session, item), accepted only by the HLS routes | Narrowest | A new credential type in the identity model — new code, new lifetime rules, new failure modes |

**Recommendation, if the backend change is needed at all: (b).** ⚠ **And it is built only if C4's F2 fails** — it
is recorded here as the fallback with its reasoning, not as work to do up front (§0). (b) keeps the
architecture's stated invariant (*the credential comes from `api/session.py` only*) literally true — there is
still exactly one function that turns a request into a session — while not turning a playback fix into a new way
to authenticate to every route in the app. (a) is rejected because it changes the meaning of
`session_context_from_request` for `admin_users.py` and `routes/media.py` as a side effect of a player; (c) is
rejected as more identity machinery than a two-client private-tailnet app needs, and as the option most likely
to grow failure modes nobody has a round for.

⚠ **Log hygiene is part of the decision, not a footnote.** A token in a URI reaches access logs. The codebase
already solves this class (`_strip_api_keys`, `jellyfin_hls.py:100`; `RKMLog.request` redacts a URL at its one
call site), but the rule for C1 is explicit: **the session id is a credential, is never logged, and every
place a URL is written must go through the existing redactor.** If a later round finds an unredacted URL, that
is a defect, not a polish item.

---

## §3 — Phases

### C1 — the player against the carrier the app already has *(built — zero backend change)*

**Built: `apple/tvos/RKMCinemaTV/Core/PlaybackAuth.swift`** + a new `the playback credential` section in
`tvos-core-tests/main.swift`, 10 mutations in `check-tvos-core.py`, and the file added to
`check-apple-typecheck.sh`'s list **in the same commit** (a portable file no gate compiles is an unguarded
file). Gates: `check-tvos-core.py` **320 checks, 0 failures** (was 297 — the new section is 23 of them) ·
`check-apple-typecheck.sh` 36 files ✓ · `check-imports.py` 32 files ✓ · `check-tvos-models.py` ✓ ·
`check_md_links.py` ✓.

⚠⚠ **The gate's own falsification pass found a gap in the plan as written, and it is worth keeping.** Four of
C1's rules are predicates of `applies(_:to:)`, and the first draft of the section checked three of them by
calling `domainCovers` / `pathCovers` **directly** — which means deleting the domain predicate from `applies`
would have left every one of those checks GREEN. The section now carries a check that reaches the predicate
*through* the selector (a correctly-named session cookie belonging to `evil.example`), and the mutation
`the host check inside applies` is what pins it. **Same family as B2's tautology**: a check that does not travel
the path the mutation edits is a check that proves nothing about it.

⚠ **A portability finding that would have silently removed the file from the gate:**
`HTTPCookie` lives in **`FoundationNetworking`** on Linux and in **`Foundation`** on Darwin. The first compile
failed with `'HTTPCookie' is unavailable: This type has moved to the FoundationNetworking module`, and the fix
is the conditional import both files now carry (`#if canImport(FoundationNetworking)`). Worth knowing because
the symptom is not an error at all in the case that matters — a file that fails to compile here simply leaves
the runnable set, and a rule that is no longer executed looks exactly like a rule that passes.

`Core/APIClient.swift` already authenticates every REST call through `URLSession.shared`'s cookie store, so
`POST /api/jellyfin/progress` and every JSON route need **nothing new**. The only question is `AVPlayer`, whose
sub-requests are not made by our `URLSession`.

It is built against the **cookie the app already holds**, handed to the asset through `AVURLAsset`'s documented
cookie option. ⚠ **The option key itself is deliberately NOT named in `PlaybackAuth.swift`** — it is
`AVFoundation`, and naming it there would take the file out of the Linux gate. The Mac-only call site passes
it, so a wrong or non-existent key is a **compile error on the Mac** — the visible failure this repo insists on
over a silent one. **[hypothesis, still]**: `AVURLAssetHTTPCookiesKey`, an array of `HTTPCookie` — the exact
symbol is verified by the Mac build, and whether it *works* is C4's F2.

⚠ **This step is deliberately the one that cannot be tested here, and the phase is arranged around that.** The
claim in play — that a cookie does or does not reach a *media playlist and a segment* — is a statement about
Apple's platform, so it is **measured by C4's F2 rather than argued in this file**. The failure mode is
deliberately the visible one: a `401` on a `…/hls/…` URL, named in the log by `RKMLog.request`. **If F2 passes,
this phase never touches `backend/` at all and C5 is not built.**

### C2 — the pure playback rules, RUN here *(portable, gateable)*

`Core/PlaybackRules.swift` — `Foundation` only, added to **both** `check-tvos-core.py`'s runnable set and
`check-apple-typecheck.sh`'s list in the same commit. Ports from `frontend/src/features/playback/lib.ts`:

* the **event decision** — given `(event, positionTicks, runtimeTicks)` answer `start｜timeupdate｜stopped`, and
  answer **`watched` versus `resume`** at the server's own `FINISHED_FRACTION = 0.95`;
* the **resume position** from an item's `playbackPositionTicks` (B4's `DetailModels` already carries it);
* `pickStreamMode` / `streamModeLabel` / `playMethodForMode` — with the Apple-hardware difference **measured,
  not assumed**: `APPLE_CLIENTS_PLAN.md` §4.3 records that Apple silicon decodes HEVC + EAC3 in hardware, so
  **[hypothesis]** a tvOS client can ask for `mode=remux` far more often than Chrome can. The rule that
  expresses this is a *parameter* (which codecs this client decodes), never a hardcoded "Apple = remux".

⚠ **Two traps from Phase B apply unchanged.** A heading/label asserted against the constant the mutation moves
is a **tautology** — pin copy against literal words. And a mutation that does not compile pins nothing, so it
must be read as `ERROR`, never counted as `red`.

### C3 — the player screen *(SwiftUI — Mac-only verification)*

`Core/PlaybackAPI.swift` (the three endpoints above), `Core/PlaybackStore.swift` (the state table), and
`Player/PlayerView.swift` (AVPlayer + transport). Extends `AppModel`'s phase enum with `.player`, and the
detail screen's `Resume S1E4` / `Play` verb — which B4 already renders **from the rule** — becomes actionable.

⚠ **B4 deliberately left no Play control**, because a control the server would refuse is "offering what the
server will refuse" (`ARCHITECTURE.md` §11). C3 is what makes that control honest, so the button lands in this
phase and not before.

⚠ The resume write path is a **write**, so it gets the rule this repo has paid for twice: *a `204` that stores
nothing is not success*. `POST /api/jellyfin/progress` answers `204` — C3 must **re-read the position it claims
to have written** (`GET /api/jellyfin/detail`) rather than trusting the status code.

### C4 — his round, on the MacBook Pro

Screen round, **without** `-RKMDebugHUD YES`; log round for the resume write, with it. Falsifiers written
**before** the round, in §3's table below — never after.

| # | Falsifier | What disproves it |
|---|---|---|
| F1 | A film plays for ≥60 s on the simulator | a black screen, or a stall with no progress |
| F2 | **[the phase's real question]** the media playlist **and segments** authenticate | a `401` in the log on any `…/hls/…` request — this is what settles §2's carrier |
| F3 | `stopped` at ~50% then reopen → **resumes at that position** | the position reads back as 0 |
| F4 | finishing a film marks it **watched** | it stays in Continue Watching |

⚠ **What C4 CANNOT prove, said before the round rather than after:** nothing about real Apple TV hardware (the
simulator is not an Apple TV), and **a failed build proves nothing about the player** — a `BUILD FAILED` means
F1–F4 were never attempted, so it is a build round, not a player round.

### C5 — the backend carrier *(ONLY if F2 fails; the phase's fallback)*

⚠ **Not built, not scheduled.** It exists here so the reasoning is not relitigated if F2 comes back red — and
so the decision is made on a measurement rather than on a bet in either direction.

| # | Where | Change |
|---|---|---|
| B1 | `POST /api/auth/login` | Add `session_token: str = ""` to `LoginResponse` (`backend/api/models.py:101`) — the **opaque session id**, additive. ⚠ Not the Jellyfin token: `auth.py:12`'s rule stands. |
| B2 | `api/session.py::session_context_from_request` | Accept the same opaque id as an alternative to the cookie — via the HLS-routes-only opt-in of option (b) (§2). ⚠ Note `SessionStore` keeps only the **sha256** of the id (`services/auth.py`), so the id is a bearer credential by construction and this widens where it may travel. |
| B3 | `api/routes/jellyfin_hls.py` | Inject the session id into each rewritten URI (master variant, media playlist, segments) the same way `_strip_api_keys` already removes `api_key`. `AVPlayer` then needs **zero** cookie plumbing. |

⚠⚠ **The identity rail is the risk, and it is not a theory.** `ARCHITECTURE.md` §11: a request that resolved a
session and published nothing must **error**, never fall back — that fallback *"once wrote a password to the
wrong account while reporting success"*. A second way to resolve a session is exactly the place that could
reopen it. So:

* the resolution stays in **one** function — `session_context_from_request` — and the query-param path (b) is a
  parameter on it, not a second resolver;
* **`set_resolved_session` must still record the request** on every path that can resolve one, so the rail sees
  a query-token request exactly as it sees a cookie request;
* C5 is not done until a test proves a request that resolves a session via the new carrier and publishes
  nothing still raises `UnpublishedIdentityError` — the same guarantee the cookie path has.

---

## §4 — Out of scope on this branch

Subtitles (renditions or overlay) · audio-track and quality pickers · the autoplay-next countdown · the
`AVPlayerViewController` transport vs a focus scrubber decision (that is Phase D polish) · the tvOS app icon ·
`AVAssetResourceLoaderDelegate` (option (c)'s cousin — the recorded fallback, deliberately not built) · any
`frontend/` change: the web player is the **reference**, not a target, and it already works.

---

## §5 — Options rejected, so they are not relitigated

* **Betting on cookie propagation to segment requests** — ⚠ **not "rejected": MEASURED.** It is C1 (build against
  it) with C4-F2 as the test. The record (`APPLE_CLIENTS_PLAN.md` §4.4) cautions against it; this plan refuses to
  bet *either way*, because a bet against it is the same class of untestable platform claim as a bet for it.
* **Widening the seam to every route (option (a)).** A player would then have changed how `admin_users.py`
  authenticates.
* **A playback-token type (option (c)).** More identity machinery than two private-tailnet clients need.
* **`AVAssetResourceLoaderDelegate`.** The recorded fallback; more code and more edge cases than a URI the
  proxy already rewrites. Reach for it only if C4-F2 fails *after* C5's B3 is in.
* **Porting `Player.tsx`.** 1949 lines of DOM, `hls.js` and pointer-capture. The rules port (C2); the view does
  not exist on a TV, where the transport is the platform's.

---

## §6 — Gates for this branch

| Gate | Why it is on this branch |
|---|---|
| `cd backend && python -m pytest tests/ --capture=no -q` | **C1 is a backend change** — the full suite (⚠ count **quoted** from `ARCHITECTURE.md` §15: 1177; re-measure when C1 lands), plus the new rail tests |
| `cd backend && ruff check api application config core domain infrastructure jobs services` | as above |
| `python3 apple/scripts/check-tvos-models.py` | any new model key must match the frozen contract |
| `python3 apple/scripts/check-tvos-core.py` (+ `--falsify`, backgrounded: ~10 min) | C2's rules must **run**, not merely compile |
| `bash apple/scripts/check-apple-typecheck.sh` | the portable files — ⚠ it caught a real Mac build error on B4 |
| `python3 apple/scripts/check-imports.py apple/tvos/RKMCinemaTV --selftest` | the ONLY gate that can see the SwiftUI views |
| `python3 tools/check_md_links.py` | this file | 
| `cd frontend && npx vitest run` · `npm run typecheck` | ⚠ expected **unchanged** — if either moves, `frontend/` was touched against §4 |

⚠ **Deploy scope is CONDITIONAL on this branch, and that is the ordering's whole point.** If C4-F2 passes,
**nothing is deployed** — the api and web images are untouched, exactly as on Phases A and B. Only if F2 fails
(C5) does `backend/` change, and then it is the api image: `docker compose -p rkm-bundled up -d --build api` —
and **not** a full `deploy`/bootstrap, which cancels a running library scan. ⚠ **If C5 is ever built, it must be
deployed BEFORE the round that reads F2**, or the round measures the old api.

---

## §7 — THE THIRD DESIGN INPUT, MEASURED (2026-09-20)

He asked for the player with a fourth file in his hand: `tvos_ux/3. MediaPlayerUx/rkm-cinema-tvos-player.html`
(781 lines — a browser mock of the whole player: video surface, top bar, scrubber, transport row, info panel and
a five-category settings drawer). ⚠ **It is a SOURCE, not a measurement** — the rule this repo paid for on set 1
and again on set 2 — so every claim in it was checked against this repo before it was built, and where the
measurement contradicts the file, the file loses.

### 7.1 Its palette is not the brand — THIRD TIME, same file-family failure

| Its token | Its value | What the app actually uses | Verdict |
|---|---|---|---|
| `--gold` | `#c9a227` | `--accent` **`#ffc400`** (`frontend/src/styles/index.css`) | ⚠ **wrong — the brand accent, for the third design input in a row** (set 1's spec said `#F2B93A`, set 2's said `#E8B33D`) |
| `--gold-bright` | `#e8c468` | `--accent-hover` `#ffd43b` | ⚠ wrong |
| `--ink` | `#f5f2ea` | `textPrimary` `#f5f2ea` | ✅ **exact** |
| `--ink-dim` | `#a39d92` | `textSecondary` `#a7a7a2` | warm grey the app does not have → the app's own |
| `--ink-faint` | `#6b665e` | `textMuted` `#70747e` / tvOS `#81858f` | ⚠ ditto, and the tvOS override still applies |
| `--bg` | `#08080a` | `background` `#08080a` | ✅ exact |
| `--glass`, `--glass-strong` | `rgba(16,16,18,.66)` / `rgba(12,12,14,.86)` | `TVTokens.Colour.topBarTint` `rgba(14,14,16,.86)` | tvOS-only tints → `TVTokens.Player`, with reasons |

⇒ **Same rule as set 1: the brand gold comes from the CSS, never from a spec's table.** A player built on
`#c9a227` would be a gold no other screen in the app shares.

### 7.2 Its unit: there is no `--u`, and the canvas is the anchor

The file mixes `%`, `rem` and absolute `px` — because a browser mock has a viewport. What it DOES fix is its own
frame: `.tv { width:100%; height:100%; max-width:1600px; aspect-ratio:16/9 }`, i.e. a **1600 × 900 design canvas**.
tvOS renders in a fixed 1920 × 1080 point space, so:

> **`PlayerPx` = 1920 / 1600 = `1.2` pt per CSS px**, and its PERCENTAGES are relative to that same frame, so
> **`p%` of the canvas ≡ `u * p`** (1920 pt = 100u). Every metric in `TVTokens.Player` is `px * <the number>`
> or `u * <the percentage>`.

⚠⚠ **Checked against the one value three files now have to agree on — the screen margin:** its `.topbar`
pads by `4.2%`, and 4.2 % of 1920 is **80.64 pt = `Metric.safeMargin` (4.2u)** — the same margin set 1 fixed at
`4.2u` and set 2's `1.26 pt/px` was derived from. Three files, one margin, and this is the number to change if a
round shows the player too large or too small — **not one metric at a time**.

### 7.3 What the api can actually honour (measured today, 2026-09-20)

| His control | What exists server-side | Verdict |
|---|---|---|
| **Playback speed** (0.5–2×) | nothing needed — `AVPlayer.rate`, client-side | ✅ **built** (his five values = the web's `PLAYBACK_RATES`) |
| **Picture Fit/Fill** | nothing needed — `videoGravity`, client-side | ✅ **built** (his two captions are used verbatim) |
| **Quality** Original/1080p/720p/480p | `max_bitrate` on the stream route AND the HLS master; the web's ladder is 8 / 5 / 2.5 Mbps | ✅ **built** — ⚠ but with the **web's real bitrates**: his captions say *"4.2 Mbps"* for 1080p, an invented number |
| **Audio Track** (his four fixed rows) | `audio_stream_index` on the HLS master (**`> 0` only**, and Jellyfin IGNORES it under `Static=true`) | ✅ **built from `playback-info`'s real tracks**, and choosing one **forces a non-direct mode** |
| **Subtitles** Off/English/Hindi + *Search OpenSubtitles…* | `GET /api/jellyfin/playback-info` (local text tracks + `preferred_subtitle`), `GET /api/jellyfin/subtitle` (WebVTT), `GET /api/jellyfin/subtitle-search`, `POST /api/jellyfin/subtitle-select`, `POST /api/jellyfin/subtitle-disable` | ✅ **built from the server's own lists** — ⚠ *"Search OpenSubtitles…"* is drawn **only when `enabled` is true** (no key configured ⇒ the api's search half is off by design) |
| **chapters** — the scrubber's ticks + the *"Chapter"* flag above the tooltip | **NOTHING.** `grep -rn "Chapters\|chapter" backend/api backend/services` → no chapter data anywhere in the api | ❌ **NOT built.** The ticks and the flag are drawn from a hardcoded array in his file; on the wire there is nothing to draw them from, and an invented chapter marker is a lie a viewer can check |
| **the scrub tooltip's 150 × 84 thumbnail** | **NOTHING.** No trickplay/thumbnail endpoint exists | ❌ **NOT built** — the tooltip shows the seek TIME, which is real |
| the keyboard hint (`↑↓←→ Navigate …`) | — | ❌ not built: a web artefact (a Siri Remote has no `Space` or `Esc`) |
| the 16:9 "TV frame" — `border-radius:14px`, its box-shadow, `.grain`, the painted `.scene` gradient | — | ❌ not built: on a television **the device IS the screen**, and the painted "video still" is the prototype's stand-in for a film this app actually has |

⚠⚠ **The two ❌ rows are the phase's honest cost**: his file draws a scrubber with chapter ticks and a
thumbnail preview, and the app will ship the scrubber without them. That is recorded here rather than quietly
approximated, and the fix is a backend phase (chapters + trickplay are both Jellyfin capabilities the api does not
proxy yet) — **not** a cosmetic one.

### 7.4 The things his JavaScript does that tvOS already does

⚠ **Not ported, third file in a row:** its focus engine (`moveRow`/`moveItem`, `paint()`, `scrollIntoView`) is the
same class of hand-rolled nearest-neighbour maths `RailFocus.swift` and B3's grid already paid for twice.
**What IS taken from it is the DECISION it encodes** — *"default focus: play/pause"* (`let r = 2, i = 2`), which is
a design choice, not an algorithm, and lives in `PlaybackRules.defaultFocusIsPlayPause`. The chrome's idle timer is
the other: his 4000 ms vs the web's `CHROME_HIDE_MS = 2800` — **the prototype wins for this screen** (`PlaybackRules.chromeHideSeconds`), and the divergence is written down so it is not "fixed" later.

---

## §8 — The transcription table (`TVTokens.Player`)

Every number below is `px * <his number>` or `u * <his percentage>` — no hand-converted values.

| His rule | Its number | tvOS |
|---|---|---|
| `.topbar` / `.bottombar` padding | `4.2%` | `u * 4.2` = **80.64** (= `Metric.safeMargin`) |
| `.ctl-btn` | `58px` | `69.6` |
| `.ctl-btn.primary` | `74px` | `88.8` |
| `.ctl-btn svg` / `.primary svg` | `22 / 26px` | `26.4 / 31.2` |
| `.backbtn` | `44px` | `52.8` |
| `.track` height, focused | `5 / 8px` | `6 / 9.6` |
| `.playhead` | `16px` | `19.2` (**= 1u**) |
| `.center-pulse` / its icon | `108 / 42px` | `129.6 / 50.4` |
| `.film-title` | `2.5rem` = `40px` | `48` |
| `.meta-row` / `.badge` / `.clock` | `.92/.72/.95rem` = `14.72/11.52/15.2px` | `17.66 / 13.82 / 18.24` |
| `.scrub-times` | `.86rem` = `13.76px` | `16.51` |
| `.settings-panel` width | `min(58%, 760px)` | `min(0.58 * 100u, 760 * 1.2)` = **1113.6** (cap wins) |
| `.settings-nav` width | `230px` | `276` |
| `.settings-nav-item` / `.seg-btn` font | `1rem / .92rem` | `19.2 / 17.66` |
| `.settings-section-title` | `1.6rem` = `25.6px` | `30.72` |
| `.info-panel` top / padding | `32%`, `0 4.2% 5.2%` | `u * 32`, `u * 4.2 / u * 5.2` |
| `--focus-scale` | `1.14` | `1.14` (the app's own focus lift) |
| `.scrim-top` / `.scrim-bottom` | `34% / 48%` | `u * 34 / u * 48` — ⚠ **kept**: they are what makes white text legible over a bright frame |

---

## §9 — Phases, as built (2026-09-20)

| Phase | What | State |
|---|---|---|
| **C1** | `Core/PlaybackAuth.swift` — the cookie carrier | **BUILT** (`6919626`), merged with `dev` this session |
| **C2** | `Core/PlaybackRules.swift` (**the decisions**), `Core/PlaybackURLs.swift` (**the URLs `AVPlayer` fetches itself**), `Core/Models/PlaybackModels.swift` (**the wire shapes**), `Core/PlaybackAPI.swift`, `Core/PlaybackStore.swift` | **BUILT** — all five in the sandbox's compiler; the first four are also **RUN** by `check-tvos-core.py` |
| **C3** | `Player/PlayerView.swift` + `Player/PlayerControls.swift` + `Player/PlayerSettingsPanel.swift`, the `TVTokens.Player` table, `AppModel`'s `.player` phase, and the detail screen's `Play` / `Resume` control | **BUILT** — ⚠ **SwiftUI: compiled ONLY on his Mac** |
| **C4** | his round — F1–F4 (§3) plus the screen falsifiers below | **NEXT** |
| **C5** | the backend carrier — ⚠ **still NOT built**, still conditional on F2 | unchanged |

### 9.1 The screen's own falsifiers (written before the round, again)

| # | Falsifier | What disproves it |
|---|---|---|
| **F5** | the film **plays** — a moving picture, ≥60 s | a black screen, or a stall with no clock movement |
| **F6** | **default focus is Play/Pause**, and every control is reachable with the remote | focus lands on the back button, or a control cannot be reached |
| **F7** | the chrome **hides after ~4 s** of playback and never hides while paused | it never hides, or it hides on a paused film |
| **F8** | the settings drawer opens, its **five categories** switch panes, and its Audio/Subtitles lists are **the server's own tracks** | a fixed list, a pane that never changes, or an empty list |
| **F9** | a subtitle draws **on the frame** when one is chosen | nothing appears (then: is the choice applied server-side? does the VTT load?) |
| **F10** | **leaving the player saves the position** — reopen and it resumes, and the position shows up in the web app's Continue Watching | it restarts at 0 (**then** read the `player: progress` log line and the `Saved/verified` toast) |

⚠ **What this round CANNOT prove:** nothing about real Apple TV hardware (the simulator is not an Apple TV), and a
`BUILD FAILED` proves nothing about any of F5–F10.
