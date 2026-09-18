# SPIKE — can the app serve its own shell? (A, B and C)

⭐ **This doc is the RECORD; the code that produced it was throwaway and is gone.** The spike files lived on
`spike/shell-origin` (`apple/ios/R...[truncated]

## Why it exists

His Mac round on 2026-09-19 proved two things at once (`docs/adr/ADR-0012-cold-launch-offline-shell.md`
§"The device round"):

* ✅ **the cold-launch ladder works** — with the Wi-Fi off, the *document* comes back from the device's own
  cache (`didFinish / : title "RKM Cinema"`), which is what the phase was built for;
* ❌ **and the app still does not paint**, because the ~1.1 MB `/assets/index-*.js` is not something WebKit
  will STORE — it refuses a response larger than roughly 5% of its disk cache, so no amount of freshness
  helps.

⇒ The shell has to be **app-owned**: the app keeps the document and its assets and serves them to the page.
That decision turns on two questions no reading settles, so they get measured (the E1 tradition).

## Run it — Mac, on the DEVICE

```
cd ~/dev/rkm-cinema
git fetch origin
git checkout spike/shell-origin
./apple/scripts/mac-round.sh ios
```

then in Xcode: **Product → Scheme → Edit Scheme → Run → Arguments → Arguments Passed On Launch**, add

```
-RKMShellSpike YES
```

and press **⌘R** with the iPhone or iPad selected. ⚠ A device, not the simulator: the spike asks the api
who you are, so it needs the real session cookie and the tailnet.

You will see the spike's own page instead of the app (a line of text and nothing else — that is correct),
and every answer lands in the log as `SPIKE …`. The debug overlay reads the same lines, so a screenshot of
the overlay is evidence too.

## What each answer means

| Question | The line to look at | What it decides |
|---|---|---|
| **A** — does `loadHTMLString(_:baseURL:)` with the server's URL give the page the server's ORIGIN? | `SPIKE A+B t=…: {"origin":"…","me":200,…}` | ⭐ **`me: 200` means yes** → the app can hand the page its own copy of the document and everything the page relies on keeps working: the session cookie is sent, `/api/*` resolves same-origin, and A1's persisted query cache (keyed by origin) is still there. ⚠ An opaque origin, or a network error instead of a status, means the fallback design. |
| **B** — does a MODULE SCRIPT load from a `WKURLSchemeHandler`? | the `moduleNow` field | **`"ok @ rkm-spike-asset://spike/probe.js"` means yes.** The module uses `import.meta`, which exists *only* in a module — so this cannot be faked by a classic script. ⚠ E1 measured custom schemes out for **media**; this answers it for the app's own code. |
| **C** — does a DOCUMENT load from one, and where do its relative URLs go? | `SPIKE C t=…: {"origin":"rkm-spike-asset://spike",…}` | This is the fallback shape. ⚠ A CORS error inside it is a **result, not a problem**: it proves the request left the page and named a real origin. |

⭐ **And one line carries all of it about 16 seconds in:** `SPIKE SUMMARY · A+B {…} · C {…}`. The debug
overlay shows only the newest eight lines, so that summary is what a screenshot needs — it is the last
line the spike writes.

Then:

```
python3 tools/check_spike_shell.py <the log file>
```

⚠ On a **device** the file log is not on the Mac's disk, so the tool needs the path — get it with Xcode →
Window → Devices and Simulators → your device → **Download Container…**, then

```
<the downloaded>.xcappdata/AppData/Library/Application Support/RKMCinema/Logs/rkm-ios.log
```

(`python3 tools/check_spike_shell.py --selftest` proves the tool's own rules can fail.)

## Result — measured 2026-09-19, on the iPhone

The full summary line, verbatim from Xcode's console (⚠ the debug overlay clips it; the console does not):

```
SPIKE SUMMARY · A+B {"href":"http://rkm-hp.tail8d5e8.ts.net:8124/","origin":"http://rkm-hp.tail8d5e8.ts.net:8124",
"secure":false,"module":"ok @ rkm-spike-asset://spike/probe.js","status":200,"me":200,"cookieChars":0,
"moduleNow":"ok @ rkm-spike-asset://spike/probe.js"}
 · C {"href":"rkm-spike-asset://spike/index.html","origin":"rkm-spike-asset://spike","secure":true,"relative":200}
```

| | Answer |
|---|---|
| **A** | ⭐ **YES.** `origin` is the server's exactly, `/api/status` → 200 and **`/api/auth/me` → 200** — a signed-out caller would have been refused, so the **session cookie travelled**. (`cookieChars: 0` is not a contradiction: the cookie is HttpOnly.) ⇒ the app can hand the page its own copy of the document with the server as the base URL, and **nothing about `/api`, the cookie, or A1's origin-keyed query cache has to move.** |
| **B** | ⭐ **YES.** `moduleNow` is `ok @ rkm-spike-asset://spike/probe.js`, and the module's own `import.meta.url` is what proved WebKit treated it as a **module**. ⇒ the app's own code CAN be served from the app's container. |
| **C** | Loads: `origin rkm-spike-asset://spike`, `secure: true`, and a relative fetch answered 200 (by the handler — the log shows `asked for /api/status` → `serving /api/status`). The fallback shape works — **we do not need it.** |
| **Storage** | ⭐⭐ **`"ls":"ok","lsKeys":4,"lsSeesQueryCache":true`** — a document the app hands to WebKit with the server as its base URL shares the **same `localStorage`**, and it can SEE the app's own snapshot (`rkm.query-cache…`). ⚠ This is the fact that decides whether the offline shell comes back with the library rows or with an empty app: A1's persisted query cache is keyed by origin, and this says the origin is genuinely the same one. |

**⇒ The fix is the cheap shape**: the app keeps the document + the assets it names, and serves the
document itself (`loadHTMLString(html, baseURL: address.url)`) with the asset URLs rewritten to a custom
scheme. Same origin, same cookies, same storage partition, no CORS, no api change.

⚠ **One second-order question was then asked of the same spike** (`localStorage` on a document loaded this
way): A1's persisted rows live in `localStorage`, which is keyed by origin, so the same store is *likely*
— but likely is how the previous design was chosen. The probe now writes one throwaway key and reports
`ls`, `lsKeys` and `lsSeesQueryCache`.

## What it changes in the app

Nothing, unless the launch argument is set. When it is set: a URL scheme handler is registered on the web
view's configuration, the page is replaced by the spike's own two documents, and the answers are read back
out of the page with `evaluateJavaScript` and logged. The ladder from the phase is still in this build, so
the same round can also re-run the Wi-Fi-off test.

## Limits, stated plainly

* It answers A, B and C and **nothing else** — it does not download a shell, does not keep a cache, and
  does not touch the ladder.
* ⚠ `ShellSchemeHandler` answers any unknown path with its document, on purpose (so that a *relative*
  request from the custom-scheme page is visible in the log). A real implementation must not.
* ⚠ It is unverified until it runs: the Swift is typechecked on Linux
  (`bash apple/scripts/check-apple-typecheck.sh`, which now covers both files against the stub scaffold),
  and that proves shapes, not behaviour.
