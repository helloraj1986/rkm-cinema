# Logging & diagnostics — dev phase

**Goal (user, 2026-09-13):** *"extensive logs for both during dev phase so that we will exactly know what is
going on once the dev starts."*

Development happens on Windows; only testing happens on the Mac. That split is the whole design constraint:
**a log the Mac cannot see, or a log that vanishes when the app stops, is a log we do not have.** So both apps
log for two consumers at once — the Mac (live, while he tests) and **me** (afterwards, so I can diagnose without
guessing).

---

## 1. The three-layer strategy

| Layer | What | For whom |
|---|---|---|
| **1. Structured `os.Logger`** | subsystem + per-area categories, so `log stream` can filter to exactly one area | live, on the Mac |
| **2. Rolling file log** | capped file in Application Support, dual-written | afterwards — export survives the app stopping |
| **3. On-screen debug HUD** | last events + correlation id + state, toggleable | **screenshots** — makes the screenshot self-describing |

⚠ **Layer 2 exists because of this fact:** `os_log` **`.debug`-level messages are not persisted** — they are only
visible to a live `log stream`. `.info` is memory-buffered and only flushed to disk on collection. If the only
sink is `os_log`, then every log from a test run he was not streaming is **gone**. The file log is the answer.

## 2. The trick that makes screenshots + logs work together

**Every request gets a correlation id, and the HUD displays it.**

```
[7f3a2c] net  GET /api/library/continue-watching → 200 in 84ms (1.2 KB)
[7f3a2c] ui   home rows rendered: 2 (cw=8, recent=12)
```

He screenshots the TV; the HUD carries `7f3a2c`; I grep the log for that id and land on the exact request,
status, body size and surrounding events. **Without the id, a screenshot and a 5000-line log cannot be joined
up** — this is the single highest-value item in this document.

## 3. What to log

### Both apps

| Area | Events |
|---|---|
| `app` | launch, build/version, server address in use (**redacted host only is fine, keep it**), config flags |
| `nav` | screen transitions, focus moves (`tvos`), dismissed/back |
| `net` | **every request**: id, method, path, status, duration, response bytes; failures with the full `NSError` domain/code |
| `auth` | sign-in attempt/outcome, profile list size, profile switch, credential-refused (`401` + `X-RKM-Auth-Problem` marker), sign-out |
| `library` | per-screen fetch result counts, artwork load failures, empty-vs-error distinction (⚠ "no library" and "200 with zero rows" must be distinguishable — a silent empty list is exactly the bug that cost days in the web app) |
| `playback` | see below — this is the expensive one |

### `playback` (tvOS — the highest-risk area)

Log, on every transition: `AVPlayerItem.status`, why it stalled, and then dump the two logs Apple gives you —
they are the whole diagnosis for an HLS problem:

```
playback item status → .readyToPlay   (hls url: /api/jellyfin/hls/<id>/master.m3u8?mode=…)
playback errorLog:    error 0: coremedia err -12865 at t=0.0s
playback accessLog:   bitrate 4.2Mbps · segments 118 · dropped 3 · stalls 1 · stallMs 4200
```

`AVPlayerItem.accessLog()` (bitrate, dropped frames, stalls) and `errorLog()` (the real CoreMedia error) are
**the** reason we can debug playback without seeing the screen. Also log the chosen `mode` (`remux` /
`transcode_audio` / `transcode`) — the ladder is where the browser bugs lived.

### `ios` shell — extra, because the WebView is otherwise opaque

| Item | Why |
|---|---|
| **`webView.isInspectable = true`** (iOS 16.4+) | ⚠ **The single best debugging lever on the whole iOS app.** He attaches **Safari → Develop → [his iPad] → the page** from the Mac and gets the real DOM, console, network tab and JS errors. A screenshot cannot compete with this. |
| WKUserScript console capture | Hooks `console.log/warn/error` + `window.onerror` + `window.onunhandledrejection`, posts each to native, native logs it with the page's path. Without it, every JS error inside the shell is invisible. |
| Navigation delegate events | `decidePolicyFor`, `didStartProvisionalNavigation`, `didFinish`, `didFailProvisionalNavigation`, `didFail` — with the `NSError` code. This is how "blank screen" is diagnosed instead of guessed. |
| Cookie presence | **count and names only, never values.** Proves whether the session cookie landed. |
| Address changes | old → new base URL, plus the normalised form. |

## 4. The HUD (both apps)

Toggleable overlay. ⚠⚠ **iOS: it starts HIDDEN, in Debug and Release alike** (his instruction,
2026-09-19 — a Debug build used to open with it ON, which put the panel over the centre of the screen and
made a centred screen's own content, a session-check skeleton included, read as "a blank app").

**To show it, in the order that needs least setup:**

1. **three taps — or one press-and-hold — in the top-left corner of the display.** ⚠ The gesture is
   installed on the window and works whether or not the corner mark is drawn (the mark appears only while
   the overlay is up, so nothing sits in the corner on a normal launch);
2. on a simulator, `Device ▸ Shake` (⌃⌘Z) — and **shake** works on a device too;
3. launch with `-RKMDebugHUD YES` (Product ▸ Scheme ▸ Edit Scheme ▸ Run ▸ Arguments). ⚠ That is the argument
   domain: it applies to that launch only. **In a Debug build it is the ONLY way a launch can start with
   the overlay up** — a Debug build ignores the stored setting on purpose, because remembering a previous
   session is how the overlay became effectively permanent. A Release build still reads the stored setting.
   **tvOS: play-pause ×3.**

⚠⚠ **The tap target cost TWO rounds, and both reasons are worth keeping** (2026-09-14).

**(1) It was 59pt below the corner it is aimed at.** The original was a 52pt `Color.clear` square in an
`.overlay(alignment: .topLeading)`, which aligns to the **modified view's** bounds — and the root view
is inset by the safe area — so it sat **y ≈ 59pt, below the status bar, inside the page's own header**,
while a thumb aims at the top of the *display*. His screenshot measured it: the page's title and back
chevron begin at the same height as the overlay's first line, with an empty strip above both.

**(2) Then the fix moved the wrong thing.** The next version drew its marker correctly in the corner
and *still* could not be tapped — because an offset moves what is **drawn** without promising to move
where the app **listens**. So the mark was in the corner and the hit area was still 59pt lower.

**The design that survives:** the gesture recognisers live on the **`UIWindow`** (installed in
`didMoveToWindow`), limited by `shouldReceive` to a **110pt corner** — so no safe-area value, no
subscription to SwiftUI's overlay layout, and no z-order question can affect it. `cancelsTouchesInView = false`
plus simultaneous recognition keeps every page interaction intact, inside the corner as well as outside.
It also **logs each received gesture before toggling**, so "the overlay did not appear" and "the touch
never arrived" — opposite problems that look identical — are told apart from the file log.

```
── RKMCinema debug ─────────────
base   https://rkm-hp.tail8d5e8.ts.net
auth   profile "Rajeev" · session ok · token hid
net    7f3a2c GET /api/status → 200 · 84ms
last   ⚠ playback error -12865 (mode=remux)
[7f3a2c] net GET /api/library/continue-watching → 200
[7f3a2c] ui  home rows rendered: 2 (cw=8, recent=12)
```

⚠ **On tvOS the HUD is not a nicety — it is the only diagnostic surface.** There is no Safari Web Inspector,
no console, no easy file access on a TV. Nothing else can show him (or me) what the app thinks.

## 5. Levels, and the switch

- `ErrorLog.level`: `verbose` (dev default) · `info` · `error` · `off`.
- Driven by a single value (UserDefaults / build setting), so production can be quiet without a code change.
- Verbose stays on for the whole dev phase — the user asked for exactly that.

## 6. ⚠ What must NEVER be logged

The apps hold a **session cookie** and the server holds Jellyfin/OpenSubtitles/TMDB keys. A log is a file that
gets pushed to git and pasted into chats.

- ❌ passwords, session ids/tokens, the `rkm_session` cookie value, Jellyfin `api_key`, any `?token=` value.
- ❌ full `Authorization` headers. Log `Authorization: <redacted>` or just its presence.
- ✅ Redact centrally, in the one place headers/URLs are built — not at each call site, where it will be forgotten.
- A redaction bug in a log is a credential leak, so **the redactor gets its own unit tests** (Phase 0).

## 7. How the logs get back to me (no backend change needed)

**Primary — live, from the Mac while he tests:**

⚠⚠ **THERE IS NO `log stream --device` ON macOS. Measured 2026-09-19 on his Mac (Xcode 26.6): the command
fails with `log: unrecognized option '--device'`, and neither `--device` nor `--device-udid` appears in
`log stream --help`. `log stream` streams THIS MACHINE only — it has never been able to reach a phone.**
The earlier note here claiming it was verified on the iPad was wrong, and it cost him a round; the two
routes that do work are below, and the first one is verified.

```bash
# THE SIMULATOR is the one case where a Mac streams directly. One area only, or drop both filters.
log stream --subsystem com.helloraj1986.rkmcinema --level debug \
  --predicate 'category == "playback"' | tee ~/dev/rkm-cinema/apple/logs/sim-$(date +%Y%m%d-%H%M%S).log
```

**On a PHYSICAL device, in order of convenience:**

1. **Xcode's console** — the Debug area (**⌘⇧Y** if hidden) while the app runs from **⌘R**, with the filter
   field at the bottom-right of the console pane. ✅ **Verified 2026-09-19**: the whole `SPIKE SUMMARY`
   line was read back this way. ⚠ It clips nothing (unlike the overlay, which truncates every line).
2. **Console.app** → sidebar → **Devices** → the device → **Start**, same filter.

⚠⚠ **ON A PHYSICAL DEVICE THE *FILE* LOG IS NOT ON THE MAC'S DISK — the simulator's
`get_app_container` trick does not apply.** Three ways to get at it, in order of convenience:

1. **The overlay** (why §4 exists): a screenshot carries the correlation id and the last error.
2. **Xcode's console or Console.app** — same lines, no file needed.
3. **The file itself**, when a whole run has to be read offline: Xcode → **Window → Devices and
   Simulators** → the device → **Installed Apps** → `RKMCinema` → **⚙ → Download Container…** → then, in
   Terminal (adjust the path to wherever it landed):

```bash
C=~/Downloads/RKMCinema.xcappdata
LOG="$(find "$C" -name 'rkm-ios.log')"
echo "--- file: $LOG"
tail -40 "$LOG"
echo "=== redaction gate (must print NOTHING below) ==="
grep -iE "password|token|api_key|rkm_session" "$LOG"
```

Then he pastes the tail in chat. ⚠ `apple/logs/` is **git-ignored** — logs travel by pasting, not by
committing; if a whole file ever needs to reach me, un-ignore that one file explicitly with
`git add -f apple/logs/<file>`. **Deferred decision:** if that round-trip proves clunky, the alternative is a
dev-only `POST /api/debug/log` sink (off unless an env flag is set, size-capped, no secrets) so I could fetch
logs myself. **Not proposing it yet** — we do not know the volume, and the plan's rule is that the only backend
change is bearer auth. Say the word if you want me pulling them instead of being handed them.

## 8. Screenshots — how to make them worth something

He volunteered screenshots; they are genuinely useful, but only if they carry state:

1. **Turn the HUD on first.** A screenshot with the correlation id + last error in it beats three without.
2. **iOS:** prefer the **Safari Web Inspector** over a screenshot for anything DOM/JS/network. Screenshot for
   layout and "looks wrong".
3. **tvOS:** screenshots are the primary surface — there is no inspector. Photograph the whole panel including
   the HUD, not a crop of the poster row.
4. For a failure, the useful pair is **HUD-visible screenshot + the log tail for that id**.

## 9. Acceptance for this phase

1. A round of testing produces **one file** that contains every request, its status, its duration, and the
   correlation ids shown in the HUD.
2. Given only a HUD correlation id from a screenshot, the matching log lines can be found — **demonstrated, not
   assumed**, before Phase 0 is called done.
3. `grep -iE "password|token|api_key|rkm_session" apple/logs/*.log` returns **nothing** on a real run.
   ⚠ **Phase B3 kept this gate absolute instead of widening it.** The loopback server's log line names the
   path **by shape** (`/offline/<handle>.mp4`) and the bridge's page-side probe report carries the *shape* of
   an event (`{e, itemId, state, percent, hasUrl}`) rather than its payload — so the word in this grep is
   never a thing the code needs to log, and **the wording gave way, not the grep**: a security grep with
   exceptions is a security grep that gets weakened. (The domain word for that value is still *token* in the
   code and in every doc; only the strings that reach a log say *handle*.)
4. The redactor's unit tests pass in the sandbox (`swift test`, no Mac needed — see `WORKFLOW.md` §5).
5. ⚠ **NO LOGGED IDENTIFIER CONTAINS ONE OF THE WORDS ABOVE — INCLUDING AN ID MADE OF THEM.** The safety
   sweep rewrites those words in *any* message, so a probe case named `get-unknown-token` reaches the log as
   `offline probe case cred PASS`: the id is gone, and with two such cases in one suite the gate cannot say
   which one failed (measured 2026-09-16, from `check_offline_server.py --grep`). ⚠ `apple/scripts/check-offline-core.py`
   now pins the rule — no probe case id may contain a §9 word — because the next case name will be written by
   someone who has not read this line.
6. ⚠ **A loopback URL never reaches the log.** With B3's server running, a real log must contain exactly ONE
   line with `127.0.0.1` — the listener announcement (`offline server listening on 127.0.0.1:<port>
   (loopback only)`) — and no `http://127.0.0.1:<port>/offline/<32 hex>` anywhere. The port alone is not a
   capability; the full URL is, for as long as the process lives.
