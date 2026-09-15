# SPIKE — E1 (loopback media) + E2 (service worker / storage)

⚠⚠ **THROWAWAY. NOT TO BE MERGED.** This branch (`spike/offline-loopback`) exists to answer two
questions **on a device**, because every choice in the offline-downloads design
(`docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4) rests on them and neither can be settled by reading:

| # | Experiment | Decides |
|---|---|---|
| **E1** | Does media play in a `<video>` **inside a WKWebView** from a **loopback HTTP server**, *with seeking* — and does the same file work through a `WKURLSchemeHandler`? | **Everything.** If loopback HTTP works, the design in §4.4–4.6 stands. If neither works, offline playback has to be handed to **AVPlayer natively** (a SwiftUI player outside the web UI) — a different, larger piece of work, and the plan's ranked risk #1. |
| **E2** | Is a service worker available at all (`sw=`) and what does storage look like (`quota=`, `persistent=`) | Whether a service worker is worth planning for. If `sw=false`, A0's cache headers **are** the offline-shell story and nothing more is designed. |

## What it does

* Downloads `harness-sample.mp4` **from the app's own server** into
  `Application Support/Spike/` (backup-excluded, not `Caches/`) — no binary is committed to the repo,
  and the file is already served on his stack (measured 2026-09-14: `GET /harness-sample.mp4` → `200`,
  1,128,375 B).
* Starts `LoopbackServer` — a minimal HTTP/1.1 file server on **127.0.0.1**, OS-assigned port,
  **loopback interface only**, with real `Range` → **206** support.
* Loads its **own probe page from that same loopback origin** into a **second `WKWebView`** carrying
  the app's real configuration (`allowsInlineMediaPlayback`, `isElementFullscreenEnabled`, the real
  instrumentation + bridge), then:
  1. plays `probe.mp4` **over loopback HTTP**, reports metadata, **seeks to the halfway point**, and
     plays;
  2. asks the **same file** for `rkm-offline://probe.mp4` — the `WKURLSchemeHandler` the plan
     *expects* to fail — and reports the same four facts;
  3. logs `[rkm-caps] …` for E2.

⚠ The spike deliberately uses **one logging route** (`console.log` → the shell's existing
instrumentation → `rkm-ios.log`). There is no second bridge event, so the answer is one grep.

## How to run it (Mac — his step; the sandbox has no Xcode and no iOS SDK)

```bash
cd ~/dev/rkm-cinema
git pull --ff-only
git checkout spike/offline-loopback

# 1. build + run with the spike open at launch (simulator needs no signing)
./apple/scripts/mac-round.sh ios --sim -RKMOfflineSpike YES
```

⚠ `mac-round.sh` takes the extra arguments and passes them to the launch; if its flags have drifted,
the equivalent by hand is:

```bash
xcodebuild -project apple/ios/RKMCinema.xcodeproj -scheme RKMCinema \
           -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build
xcrun simctl launch booted com.helloraj1986.rkmcinema.ios -RKMOfflineSpike YES
```

⚠ **Two preconditions, and the app tells you if either is missing** (the spike screen shows the
reason instead of failing silently):

1. **A stored server address.** The probe file comes from his own server, so connect once in the app
   (or it may already be stored) — the spike reads the same `ServerStore` the app uses.
2. **The file is reachable at `http://<his-server>/harness-sample.mp4`.** It is today. If a clean
   web rebuild ever drops it (it lives in `frontend/public/`, which is git-ignored), copy any small
   `.mp4` to that path on the server, or drop one into `frontend/public/` and rebuild.

## Reading the answer — ONE command, and it gives the verdict

```bash
python3 tools/check_spike_e1_e2.py
```

⚠ **No argument needed — it finds the log itself** (the booted simulator's app container, or any
simulator on the Mac). ⚠ The docs used to say `… "$LOG"`, and `$LOG` was never defined anywhere: the
empty variable expanded to nothing, `Path("")` became `.`, and the tool died with
`IsADirectoryError: '.'`. **A placeholder in a command is a command that does not run** — so the path
is now optional, the tool prints where it read from, and if you do pass one it must be a real file:

```bash
python3 tools/check_spike_e1_e2.py "/path/to/rkm-ios.log"          # simulator, by hand
# on a DEVICE the file is not on the Mac: Xcode → Devices and Simulators → Download Container…,
# then …/<name>.xcappdata/AppData/Library/Application Support/RKMCinema/Logs/rkm-ios.log
```

It prints the evidence, then **PASS or FAIL**, and on a FAIL it says which piece is missing and what
that means for the plan. It exists because the gate is a *specific set of lines*, not a feeling:
`[spike]` lines are the **page's** account, `loopback request:`/`serving 206` lines are the
**server's** — and two of them must agree, because `seek -> ok` with a `200` on the wire means the
whole file was re-read, not a seek. The page cannot tell those apart. The server can.

⚠ Falsified before it was trusted: a passing log, a whole-file-`200` log, a never-reached-the-server
log, a codec-error log and a *spike-never-launched* log — the last four all FAIL, with the right
reason named. That suite also caught two bugs in the tool itself (a pattern that missed the real
`loopback: serving 206 …` line shape, and a glob that read **zero lines** from a log handed in under
another name), and the empty-path case that started all of this.

⚠⚠ **AND IT NOW JUDGES ONE RUN, NOT THE WHOLE FILE — the log is APPEND-ONLY ACROSS RUNS** (`rkm-ios.log`
plus its archives), and this tool used to take the **first** match in all of it. That is fine for a first
round and wrong for every round after it: once a run had passed, its `seek -> ok` and `RESULT play=ok`
sat in the file **forever**, so a later round that FAILED still reported **PASS** — a gate that cannot
fail again after its first success, which is not a gate. ⚠ And the mirror fault: the first round's
`mediaError=code=4` would be printed as the **new** round's evidence. It now judges **the newest
`offline spike: starting` run** (matched by *timestamp*, so archive order cannot matter), prints which
run it read and how many earlier lines it ignored, and falls back to the whole file — saying so — only
when there is no marker at all. Re-run the falsification with
`python3 tools/check_spike_e1_e2.py --selftest`: **11 cases**, including both of those bugs, and ⚠
**the old tool exits 0 on the stale-pass case where this one exits 1 — checked by running both against
the same two-run log.**

The raw greps, if you would rather read it yourself:

```bash
grep -E "\[spike\]"         "$LOG"   # the probe's own report, every step in order
grep "loopback request"     "$LOG"   # what the SERVER saw — a 206 here proves seeking used a range
grep "\[rkm-caps\]"         "$LOG"   # E2 — ⚠ note this rides the app's OWN page, so it needs the app
                                     #      loaded, not just the spike sheet
```

where `$LOG` is the app's log file (`apple/LOGGING.md` §7 — on a device, Xcode → Devices and
Simulators → **Download Container…**; on the simulator, `simctl get_app_container`).

**What each outcome means:**

| `[spike]` line | Reading |
|---|---|
| `[loopback] metadata ok …` and `seek to … -> ok` | ✅ **loopback HTTP works, with seeking.** The offline design in §4 stands as written. |
| `[loopback] RESULT … mediaError=code=N` | ⚠ Loopback failed. Read `LoopbackServer`'s own `loopback request:` lines: if **no request arrived at all**, WebKit refused the connection (ATS/origin) — if a `206` was served and the element still errored, the codec/container is the problem, not the transport. |
| `[scheme] RESULT loadedmetadata=ok` | ⚠ **The plan's assumption is WRONG** in the good direction: `WKURLSchemeHandler` can carry media, and the design gets simpler (no port, no server). Rewrite §4.1/§4.4. |
| `[scheme] RESULT loadedmetadata=TIMEOUT` / error | The expected result — the plan's §4.1 stands, and the loopback server is the design. |
| `[rkm-caps] sw=false` | A service worker is unavailable ⇒ A0's headers are the offline-shell story; plan no SW work. |

⚠⚠ **IF E1 FAILS ON THE SIMULATOR, CONFIRM THAT ON THE DEVICE BEFORE THE PLAN CHANGES — a PASS, by
contrast, may be taken at face value.** The Simulator's media pipeline is the Mac's, wired up differently
from a device's, and the two directions do not cost the same: a **pass** says the transport works and a real
device is not *less* capable than a Simulator (and the file itself is H.264 High 3.1 + AAC, measured above —
both play it), while a **fail** sends the whole of Workstream B to a **native `AVPlayer`**, i.e. a different
and larger piece of work. A negative that expensive does not get to rest on a Simulator: re-run the same
build on his **iPad** before §4.4–4.6 are rewritten. ⚠ `mac-round.sh --sim` only ever launches a Simulator,
so a device run is launched from **Xcode** with `-RKMOfflineSpike YES` set as a scheme argument (Product →
Scheme → Edit Scheme → Run → *Arguments Passed On Launch*), and the log then comes out of the device with
`Download Container…` (`apple/LOGGING.md` §7) — `tools/check_spike_e1_e2.py <that path>` reads it by hand.

## What is and is not verified

* ⚠⚠ **THE FIRST REAL RUN FAILED, AND IT WAS A BUG IN THE SPIKE, NOT IN WEBKIT — `probe.mp4` vs
  `harness-sample.mp4`.** The file was downloaded under the name it has on HIS server and the server
  looked for the name the PAGE asks for, in the same directory. So `/probe.mp4` 404'd, **not one byte of
  media reached WebKit**, and both transports reported `mediaError=code=4` (src not supported).
  ⚠ **Both failures had the same mundane cause** — so that round said **nothing** about
  `WKURLSchemeHandler` either; "the scheme handler failed as expected" was meaningless.
  The tell was in the log and easy to read past: the request line was there
  (`loopback request: GET /probe.mp4 · Range: bytes=0-1`) with **no matching `serving` line** — a served
  response always logs one. Fixed by storing the file under the name the page asks for
  (`OfflineSpike.servedName`), and the checker now **prints the server's own trace** and reports
  **INCONCLUSIVE (exit 3)** rather than FAIL when no bytes were sent.
* ✅ **THE PROBE FILE WAS MEASURED FROM THIS SIDE (2026-09-15), so a codec refusal cannot be misread as a
  transport fault.** `harness-sample.mp4` fetched from his own stack (`http://…:8124/harness-sample.mp4` →
  `200`, `video/mp4`, **1,128,375 B** — the same size the app logged) and its boxes parsed: **H.264 High
  profile, level 3.1 (`avc1`), AAC audio (`mp4a`/`esds`), `moov` at the front (faststart), 5.05 s.** Both the
  Simulator and a device play exactly that, so if E1 comes back `mediaError=code=4` **with** `serving 206`
  in the trace, the finding is about the **transport**, not the file.
* ✅ **E2 IS ANSWERED (2026-09-14) — and the answer is the strong one, because the probe ran on TWO
  origins.** The capability line rides `WebInstrumentation`, so the **loopback** page the spike serves got
  one as well as the app's own page:
  `[rkm-caps] sw=false fullscreen=true origin=http://rkm-hp.tail8d5e8.ts.net:8124 persist=none` and
  `[rkm-caps] sw=false fullscreen=true origin=http://127.0.0.1:57949 persist=probe`.
  ⚠ **`persist=` is the tell that the two origins differ in kind, not merely in address:**
  `navigator.storage.persisted` **exists** on `127.0.0.1` — a *potentially trustworthy* origin, so the
  storage API is exposed there — and is **absent** on the plain-HTTP tailnet origin. So `sw=false` is **not**
  an artefact of serving the app over HTTP: **on a secure origin this WKWebView still exposes no
  `navigator.serviceWorker`.** ⇒ E2's decision holds — **A0's cache headers ARE the offline-shell story, and
  no service-worker work is planned.** ⚠ It also corrects a loose first reading of that log: `navigator.storage`
  is not "absent in WKWebView", it is absent **on an insecure origin** — a distinction that matters for the
  storage design later (`storage.estimate()` reported `quota=103 GB usage=0`, and `persisted()` → `false`, on
  the secure loopback origin only).
* ⚠⚠ **THE FIRST MAC BUILD FAILED — one error, and it was exactly the kind `-parse` cannot see.**
  `OfflineSpike.swift` used `Result<URL, String>`, and **`Result`'s failure type must conform to
  `Error`** — which `String` does not. His build reported it verbatim (*"type 'String' does not conform
  to protocol 'Error'"*), and **`swiftc -parse` had passed on every file beforehand**, which is the
  lesson this repo already had written down: *a check that only proves syntax proves nothing about
  types.* Fixed with a real failure type (`SpikeFailure: LocalizedError`, so the sentence survives into
  `localizedDescription`), and the fix was **reproduced and typechecked on Linux** — the failing shape
  rejected, the new shape accepted — before he was asked to build again.
* ✅ **Verified here:** `swiftc -parse` on every changed file, `apple/scripts/check-imports.py`
  (no missing framework imports), both injected scripts pass `node --check`, the probe page's HTML/Swift
  raw string is well-formed, and **`LoopbackServer.parseRange` was lifted verbatim and RUN on Linux**
  against 12 real `Range` headers (suffix ranges, clamping, reversed, garbage) — 12/12, falsified by
  removing the clamp (the clamped-end case fails, exit 1). The Foundation-only pieces
  (`SpikeFailure`, `OfflineSpike.directory()`) were **typechecked by a real compiler** too.
* ✅ **`mac-round.sh`'s new argument pass-through was RUN, end to end, against stubbed Mac tooling**
  (`git`/`xcode-select`/`xcodebuild`/`xcrun`/`open`): with extras it launches
  `…-RKMOfflineSpike YES`, with none it launches bare, and a Mac without the committed default
  simulator falls back to the first available iPhone instead of skipping the run. Without that
  fallback "the build succeeded but nothing launched" reads exactly like "the spike is broken".
* ⚠ **NOT verified: everything that needs a Mac.** No Xcode here: not one line of this has been
  compiled, the `NWListener` has never started, and no media has played. `swiftc -parse` proves
  *syntax only* — this repo has already shipped an "obviously fine" file that failed on an ambiguous
  `.zero`, which `-parse` cannot see.
* ⚠ **Not merged, and it should not be.** `LoopbackServer` has no auth, no manifest, no token and no
  staging TTL — `B1`–`B3` of the plan replace it. `SpikeSchemeHandler` serves without `Range` on
  purpose (a fake range would turn a seeking failure into a silent whole-file re-read).
