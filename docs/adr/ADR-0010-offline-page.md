# ADR-0010: the offline PAGE — a capability the page must not assume, and a queue that must never rewind

- **Status:** Accepted · ✅ **phase B4 built** (2026-09-16 — the browser gate
  `python3 tools/check_offline_page.py` passes 6 scenarios / 0 problems against the real components, and
  three of its rules were falsified and went red) · ⚠ the limits below stand — see *What is NOT verified*
- **Date:** 2026-09-16
- **Phase:** `feat/offline-downloads` (`NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4.6, phase **B4**)
- **Depends on:** ADR-0007 (B1 — the server packages and serves), ADR-0008 (B2 — the device holds the
  file), ADR-0009 (B3 — the device serves it back over loopback, with a versioned bridge)

## Context

B2 gave the device a film and B3 gave the page a way to reach it. B4 is the half the household actually
touches: **the download button, the Downloads screen, a player that prefers the file to the stream, and a
queue that carries a position back to the server.**

⚠ It is the first phase in this workstream whose deliverable is almost entirely the WEB app — which has
two consequences that shape everything below. It ships with `apply` (no Mac build, no native change), and
it is the phase where the feature stops being reachable only through a DEBUG probe.

Three facts about where this code runs decide the design:

1. **`window.__rkmOffline` exists only inside the iOS shell.** It is injected at document-start by
   `OfflineBridge.swift`; in a desktop browser there is no bridge at all. So "is offline available here"
   is a question the page asks of a global, and the honest answer is often NO.
2. **Native is the authority on the device, and only native.** Whether a film is on the phone is not
   derivable from the server's staging record — those are two machines, and a screen that conflated them
   would offer to play a file that is not there (or hide one that is).
3. **The page can be left at any moment, and it is left most often mid-film.** A position reached with no
   server has to survive a suspension, a relaunch and a profile switch — which makes it PERSISTED state,
   and therefore identity-bearing state.

## Decision

### D1 — The rules are pure and falsified; the boundary is PARSED; the server's contract is TYPED

`frontend/src/features/offline/lib.ts`, `spool.ts` are pure, and `lib.test.ts` + `spool.test.ts`
(**62 checks**) execute them on Linux. Everything that decides something lives there: payload validation,
the event fold, the percentage rule, the action each state offers, the spool's watermark, the resume
decision, the envelope rules.

⚠ **Two boundaries, two disciplines — and they are not the same thing:**

* the **bridge** is untyped (`postMessage`'s `any`), so every payload is parsed and anything unreadable is
  **dropped whole**. A half-read row is worse than a missing one: `bytes: NaN` renders "NaN GB", a missing
  state renders a row with no controls, and an empty string in the wrong field is a lie with no error.
  ⚠ `Number(null)` is `0`, so a missing byte count must not become a confident "0 B" — 0 B is a real
  answer we need to be able to tell apart from silence.
* the **API** is typed (`lib/api/client.ts` + the frozen `openapi.v1.json`), so `GET /api/offline/bundle/{id}`
  arrives as `OfflineBundleShape` with no parser at all — the repo already trusts this contract everywhere
  else, and adding a second authority on the same bytes is how two of them start disagreeing.

### D2 — ⚠ The feature is INVISIBLE where it cannot work, and that is a rule about the DOM

Without a bridge there is **no Downloads entry in the navigation and no Download button on the detail
page** (§4.5: never render a control that cannot work). And the page does not even ask the server what a
download would cost — a request whose answer could only decorate a button that must not exist.

⚠ The nav asks the GLOBAL directly (`bridge.ts::bridgeAvailable()`), not the offline session's store. That
is a measured decision, not a stylistic one: subscribing the nav to the session dragged the api client,
the spool and zustand into the module graph of every screen, and that was enough to push
`tools/check_nav_access.py` over its ten-second wait on a loaded dev server.

### D3 — ⚠ What the DEVICE holds and what the SERVER has are two facts, and the page keeps them apart

* A row's state, size, mode and error come from `list` and from events — never from the server.
* The server is asked (once, cached) what a download WOULD cost: the rendition, an estimate, whether it
  needs a re-encode. That is what the button under it says, and it says "about" because it is an estimate.
* ⚠ **"No longer on the server" is only claimed when the server ANSWERED.** A 404 is an ordinary answer
  (the title left the library, or the staging file was swept by the TTL) and the copy still plays; a
  network failure says nothing at all, and drawing the same sentence for both would be a lie about the
  first fact in order to explain the second.

### D4 — One decision per surface, and the contract's vocabulary is what the buttons say

`actionsFor(row)` returns exactly the controls a state can act on, and both surfaces render them:

| State | Offered |
|---|---|
| not on the device | Download (+ the rendition and size) |
| `downloading` | Cancel · Delete |
| `paused` | Resume · Delete |
| `failed` | Retry · Delete |
| `ready` | Play offline · Delete |

⚠ **Delete is offered in every state, deliberately**: bytes on a phone with no way to remove them is a
worse outcome than any of the failures the other buttons address.

⚠ **There is no `pause` and no `resume` in the contract** (ADR-0009 D6), and the page does not pretend
otherwise: `cancel` stops a transfer and leaves the `.part` resumable, so the row it produces reads
"paused — resumable" and **Resume re-sends `download`**. The app decides whether that means "carry on from
the byte it stopped at" or "the file is already whole", because it is the side that can see the filesystem.

⚠ **The detail page deliberately has NO "Play offline" button.** Its own Play button goes through the
player, which prefers the local file — a second play affordance would be a second path to the same film,
and the one that forgot to prefer the copy on the phone is the one that would get pressed.

### D5 — ⚠ The player asks the DEVICE first, and then does not ask the server at all

`playLocal(itemId)` is the first question the player asks. With a local file it sets
`<video src="http://127.0.0.1:<port>/offline/<handle>.mp4">` and makes **zero**
`/api/jellyfin/playback-info` calls — the call that is pointless online and impossible offline.

* ⚠ **The engine key is EMPTY until the device has answered.** Starting the server stream and switching to
  the local file when the answer arrives would be a request made on the strength of an assumption, and the
  assumption is exactly what is being checked. (A blank player for one frame against a stream request to
  the server: the first is invisible, the second is the bug.)
* ⚠ **The resume point comes from THIS DEVICE.** Offline, the server's resume position is the fact that
  stopped updating — so the spool's own watermark is folded in (`resumeSecondsFrom`, `max`), and a position
  near the end is read as "finished" rather than as a place to start.
* **The chrome says where the film is coming from** ("On this device"), because the difference between a
  film that plays with the Wi-Fi off and one that does not is worth one chip on the screen.

### D6 — ⚠⚠ The spool keeps the FURTHEST position, never the latest — and a live post cancels a queued one

The failure this file exists to prevent, stated once: **a replay that rewinds someone.** He watches to
1:04:00 on a plane; the queue holds it; he reconnects and keeps watching online, and the server hears
1:20:00 from the live player — and then the stale 1:04:00 arrives from the queue. Every other rule in this
phase recovers from a mistake; that one just loses twenty minutes of his evening.

Three rules, each of which is a way that could happen:

1. **Within a title the spool keeps the maximum position, not the newest report.** Every time a film is
   REOPENED the player reports `start` at the resume point — or at 0:00 after a deliberate restart — and
   with last-write-wins that report would overwrite the watermark. ⚠ **The price, stated plainly: a
   deliberate rewind while offline is not replayed.** The film resumes where it was furthest watched, and
   the live (online) path is untouched.
2. **A successful live post supersedes everything at or below it** (`confirmSpoolPosted`) — the other half
   of "newest wins", and the half that only exists because the queue and the player use different paths.
3. **The replayed entry is dropped by its own `recorded_at`**, so a newer position recorded while the
   request was in flight survives the flush. Drop-by-item would silently throw those minutes away.

⚠ **The replay stops at the first failure and keeps the rest, in order** — the queue is a timeline, and a
report that cannot reach the server means the next one cannot either.

### D7 — The queue is IDENTITY-BEARING state, and "we cannot tell" is not "it is somebody else's"

The queue is on disk, so it outlives a sign-out, a profile switch and a relaunch. Every write is stamped
with the profile id and the server origin; a queue written for **another person or another server** is
DROPPED on read (another server's item ids name different films). Same rule, same reason, as the query
cache (A1): a stale snapshot outliving a sign-out is an identity leak, not a stale render.

⚠⚠ **And an UNKNOWN owner neither reads NOR destroys.** A page that loads with no network cannot ask
`/api/auth/me` who is watching — and that is exactly the launch where the positions on disk matter most.
Deleting the envelope then would destroy the one thing the queue exists to carry. An identity purge
belongs to "we know this is a different person", never to "we cannot tell".

⚠ A built-in consequence, recorded rather than hidden: a cold launch with the server unreachable runs the
session with **no owner**, so positions reached in that launch are held in memory and cannot be written.
They are lost if the page is reloaded before the server answers. Fixing that means remembering the last
profile id on disk (which the query cache already does) — a deliberate follow-up, not a silent one.

### D8 — ⚠ A background replay is not allowed to bounce the page to the sign-in screen

`reportProgressQueued` (a second client method, `skipAuthRedirect`) exists for exactly this: a 401 on a
flush means the session expired while the queue waited, and nobody is watching the screen at the time.
Signing the page out for that would be an action taken on nobody's behalf; the entries stay on disk,
stamped with their owner, for the next time that person is watching.

### D9 — ⚠ "We could not reach the server" is not "you are signed out" — the one change outside the feature

`AuthStatus` grew a fourth state (`unreachable`), and `guardDecision` answers **`app`** for it (and NOT the
picker: asking "who's watching?" needs the same unreachable server). The reason this belongs to B4 rather
than to an auth phase: until it existed, **the feature was unreachable at the one moment it exists for** —
a phone with the Wi-Fi off showed a sign-in form it could not submit, with the downloads behind it.

⚠ Failing open to the SHELL is honest here because this app enforces nothing client-side: every route is
session-scoped on the server, so a shell that renders without a verified session can display nothing it is
not entitled to — it shows its own empty and offline states, and the server still refuses every route it
would refuse anyway. ⚠ And the disk cache is NOT adopted in that state (nobody is known to be watching),
so no cached rows appear either.

### D10 — The gate is a BROWSER harness against a fake bridge, and the rules were falsified one at a time

`tools/check_offline_page.py` drives `frontend/harness/offline-frame.html` — the real `DownloadButton`,
`DownloadsView` and `Player` over a scriptable `window.__rkmOffline`, and `?bridge=0` reproduces a desktop
browser exactly. Six scenarios, and the ones worth naming:

1. no bridge → no nav entry, no button, and not even a request;
2. nothing downloaded → the button names the rendition and the estimate BEFORE the tap, and claims no
   resolution the server never sent;
3. pressing it → one `{v:1,c:"download",…}` reaches the bridge, the row follows the events (75% ring,
   decimal units matching the app's own HUD), a finished film offers Delete and no Download;
4. the Downloads screen lists device rows (ready + resumable), and **Play sets the video source to the
   loopback URL with zero playback-info calls**;
5. **a position reached with no server is queued, replayed exactly once on reconnect, carrying a real
   position and the runtime** — and the screen says it is waiting rather than being silently behind;
6. the server unreachable → the shell, not a sign-in form.

⚠ **Falsified three times, each restoring afterwards:** making the bridge claim to exist everywhere
(4 checks red), making the player use the server for a film it holds (3 checks red — and the frame even
reached the HLS escalation ladder), and reporting through the server while playing locally (5 checks red,
including a replayed `start` at position 0 — the rewind this ADR is about).

## Consequences

* **What this buys, as the gate:** a film he chose is downloadable from the page it is described on, is
  visible and manageable on a Downloads screen that reads the DEVICE, plays with the Wi-Fi off without the
  page touching the API, and the position he reaches lands in Continue Watching when the network returns.
* **What ships how:** the whole phase is web — `apply` (`docker compose -p rkm-bundled up -d --build web`)
  is the entire deploy, and no Mac build is needed. ⚠ It is visible ONLY inside the app (there is no bridge
  in a browser), which is the same statement as §4.5's.
* **The honest limits, all of them:**
  1. ⚠ **Artwork and subtitles offline are DEFERRED.** §4.6 has both captured into the item's directory at
     download time, which needs the downloader to fetch them (native) and the loopback server to serve them
     (a second route). This phase plays the film; a downloaded film therefore has no poster and no subtitle
     track. Deferred deliberately: it is native work with no page-side decision in it, and the plan's own
     gate for B4 does not mention them.
  2. ⚠ **`downloaded-at` on the Downloads screen is DEFERRED.** The device's own `downloadedAt` is in the
     app's manifest but NOT in the bridge's item payload (ADR-0009 D6's shape), and adding it would need a
     Mac build for a cosmetic line. The screen shows what the device really reports; it does NOT substitute
     the server's staging timestamp, which is a different fact about a different machine.
  3. ⚠ **Cap, eviction, keep/pin and the delete-after-watch option are B5's** (§4.6 lists "keep" in the
     screen; §6 gives lifecycle to B5). Nothing here silently evicts anything, and the screen shows what is
     held without pretending to manage it.
  4. ⚠ **The DEBUG probes are NOT deleted in this phase.** B3's record says B4 is what lets
     `Debug/OfflineServerProbe.swift` and `Debug/OfflineDebugPanel.swift` go — and it does, in the sense
     that the feature is now reachable by hand. They stay for one more round because the two native gates
     (`check_offline_server.py`, `check_offline_download.py`) read the log lines only those probes write:
     deleting them in the same commit that first exercises the page would leave the native half with no way
     to be re-measured. Deletion is a one-commit follow-up.
  5. ⚠ **Playback on the DEVICE is not exercised here.** The harness proves the page sets the loopback URL
     and never asks the server; that a real `<video>` seeks against the app's own server is B0's
     measurement, and it needs his phone.
