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

**What IS open, and is the decision this phase carries**, is the *carrier*: the record says "accept
`Authorization: Bearer`" (B2) **and** "inject the session token into each rewritten URI" (B3) — two different
carriers for the same credential, and **a header does not carry a segment request from `AVPlayer`**. §2 lays out
the three ways to close that gap and recommends one.

**What it costs.** This is the **only phase of this client that touches `backend/`** — every earlier phase
changed `apple/` and `docs/` only, and B0 deliberately kept `backend/` untouched for exactly that reason. So
this phase is the one that can break the working web app, and the deployment question becomes real again (§6).

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

**Recommendation: (b).** It keeps the architecture's stated invariant (*the credential comes from
`api/session.py` only*) literally true — there is still exactly one function that turns a request into a
session — while not turning a playback fix into a new way to authenticate to every route in the app. (a) is
rejected because it changes the meaning of `session_context_from_request` for `admin_users.py` and
`routes/media.py` as a side effect of a player; (c) is rejected as more identity machinery than a two-client
private-tailnet app needs, and as the option most likely to grow failure modes nobody has a round for.

⚠ **Log hygiene is part of the decision, not a footnote.** A token in a URI reaches access logs. The codebase
already solves this class (`_strip_api_keys`, `jellyfin_hls.py:100`; `RKMLog.request` redacts a URL at its one
call site), but the rule for C1 is explicit: **the session id is a credential, is never logged, and every
place a URL is written must go through the existing redactor.** If a later round finds an unredacted URL, that
is a defect, not a polish item.

---

## §3 — Phases

### C1 — the auth carrier, backend only *(backend phase; the risky one)*

| # | Where | Change |
|---|---|---|
| B1 | `POST /api/auth/login` | Add `session_token: str = ""` to `LoginResponse` (`backend/api/models.py:101`) — the **opaque session id**, additive. ⚠ Not the Jellyfin token: `auth.py:12`'s rule stands. |
| B2 | `api/session.py::session_context_from_request` | Accept the same opaque id from an `Authorization: Bearer …` header as an alternative to the cookie — outside any request context the behaviour is unchanged. |
| B3 | `api/routes/jellyfin_hls.py` | Inject the session id into each rewritten URI (master variant, media playlist, segments) the same way `_strip_api_keys` already removes `api_key`. `AVPlayer` then needs **zero** cookie plumbing. |

⚠⚠ **The identity rail is the risk, and it is not a theory.** `ARCHITECTURE.md` §11: a request that resolved a
session and published nothing must **error**, never fall back — that fallback *"once wrote a password to the
wrong account while reporting success"*. A second way to resolve a session is exactly the place that could
reopen it. So:

* the resolution stays in **one** function — `session_context_from_request` — and the query-param path (b) is a
  parameter on it, not a second resolver;
* **`set_resolved_session` must still record the request** on every path that can resolve one, so the rail
  sees a Bearer/query request exactly as it sees a cookie request;
* C1 is not done until a test proves a **Bearer** request that resolves a session and publishes nothing still
  raises `UnpublishedIdentityError` — the same guarantee the cookie path has.

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

---

## §4 — Out of scope on this branch

Subtitles (renditions or overlay) · audio-track and quality pickers · the autoplay-next countdown · the
`AVPlayerViewController` transport vs a focus scrubber decision (that is Phase D polish) · the tvOS app icon ·
`AVAssetResourceLoaderDelegate` (option (c)'s cousin — the recorded fallback, deliberately not built) · any
`frontend/` change: the web player is the **reference**, not a target, and it already works.

---

## §5 — Options rejected, so they are not relitigated

* **Betting on cookie propagation to segment requests.** The recorded decision (`APPLE_CLIENTS_PLAN.md` §4.4),
  and C1-F2 is the measurement that either retires it for good or proves it was over-cautious — either way the
  answer is recorded rather than argued.
* **Widening the seam to every route (option (a)).** A player would then have changed how `admin_users.py`
  authenticates.
* **A playback-token type (option (c)).** More identity machinery than two private-tailnet clients need.
* **`AVAssetResourceLoaderDelegate`.** The recorded fallback; more code and more edge cases than a URI the
  proxy already rewrites. Reach for it only if C1-F2 fails *after* B3 is in.
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

⚠ **Deploy scope changes on this branch.** `backend/` is the api image, so this is the first tvOS phase with a
real deployment step: `docker compose -p rkm-bundled up -d --build api` — and **not** a full `deploy`/bootstrap,
which cancels a running library scan. ⚠ **And it must be deployed BEFORE his Mac round**, or F2 measures the
old api.
