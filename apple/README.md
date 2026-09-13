# Apple clients — iOS/iPadOS and tvOS

Two separate apps, two separate folders, one shared idea: **the apps are clients of the server, not a
second implementation of it.** The full plan is [`../docs/APPLE_CLIENTS_PLAN.md`](../docs/APPLE_CLIENTS_PLAN.md).

```
apple/
├── README.md          ← you are here: the tree, the rules, the build order
├── WORKFLOW.md        ← ⚠ the two-machine loop: author on Windows, TEST on the Mac
├── LOGGING.md         ← the dev-phase logging/diagnostics spec (HUD · correlation ids · redaction)
├── Shared/            ← local Swift package: code BOTH apps genuinely need (deliberately tiny)
│   └── Sources/RKMServerKit/     the server ADDRESS (parse · normalise · persist)
│                                 + the log REDACTOR and the rolling file log (LOGGING.md)
├── ios/               ← RKMCinema: a WKWebView shell around the LIVE web UI
├── tvos/              ← RKMCinemaTV: a native SwiftUI client (tvOS has no browser)
└── scripts/           ← generate-api.sh: regen the Swift API types from the frozen contract
```

⚠ **Read [`WORKFLOW.md`](WORKFLOW.md) before touching either folder** — the two-machine loop
(all development here, **the Mac is testing only**, GitHub as the only bridge) and the one-time
Xcode step in §2 — he creates each project once, and after that the agent adds sources freely.

⚠ **Read [`LOGGING.md`](LOGGING.md) before writing any app code** — extensive logging is a Phase 0
requirement, not a later addition: the Mac can only report what the apps can tell it, so a missing log
line is an undiagnosable bug. Both apps ship a **debug HUD**, and every request carries a **correlation
id** that the HUD displays — that is what makes a screenshot and a log join up.

## The two apps are NOT the same shape — do not make them match

| | `ios/` | `tvos/` |
|---|---|---|
| Renders | the **real React UI**, loaded live from the server | its **own** SwiftUI views |
| Why | iOS ships WebKit — the existing UI *is* the app | **tvOS has no WebKit at all**, so a native UI is the only option |
| Screens | 2 (server address → web shell) | 7 (address, sign-in, profiles, home, browse, detail, player) |
| API client | **none** — the web UI makes its own `/api` calls, same-origin | yes — generated from `docs/api/openapi.v1.json` |
| New code | thin — the shell itself is small; the dev-phase logging and debug overlay are the bulk | thousands |
| Cost | 1–2 days | 2–4 weeks of evenings |

**Consequence worth remembering:** because `ios/` loads the *live* UI, every future change to
`frontend/` appears on the iPad with **no app rebuild and no store release**. `tvos/` does not get that
— it is a real client that must be updated as the contract grows (additively, per ADR-0001).

## Why there is a `Shared/` package at all — and what may go in it

Both apps must do exactly one thing the same way: **take a server address a human typed and turn it
into a usable base URL, then remember it.** That is the whole package.

⚠ **The rule for this folder: nothing goes in `Shared/` unless BOTH apps need it.** The iOS shell
needs no API client — it has no models, no auth flow, no playback code. If `Shared/` starts growing
API models or networking, that is a design smell: one client is being made to look like the other.
Split it out instead.

## The server address (both apps, screen #0)

The user types an address on first launch; the app stores it and loads from there. This is the
Jellyfin/Infuse/Plex model and it means **the tailnet host is never baked into a build**:

- LAN: `http://192.168.x.x:8124`
- Tailscale: `https://rkm-hp.tail8d5e8.ts.net/`

⚠ **Normalisation is not optional** — accept a bare host, add `https://` when no scheme is given, strip
trailing slashes. A rejected address must say *why*.

⚠ **A wrong address must never brick the app.** Both apps need an always-reachable "can't reach this
server → Change server" path, or a typo leaves a blank screen until reinstall.

⚠ **The network is the client's problem.** Away from home the Tailscale app must be running *on the
device*; these apps cannot route to `100.x` tailnet addresses themselves.

## Requirements on the server (what the apps depend on)

- The existing deployed stack, unchanged. The iOS app needs **zero** server-side work.
- Same-origin access works because the address *is* the origin: the web UI's relative `/api` calls and
  the session cookie behave exactly as in Safari. **No CORS change is needed.**
- ⚠ The session cookie is set with `secure=False` (`backend/api/routes/auth.py:133`). That is
  deliberate and **correct for this design** — it must work over both `http://` LAN and `https://`
  tailnet addresses. Do not "fix" it to `True` without removing plain-HTTP support.
- The tvOS **player** additionally needs the bearer-token work (plan §4.4, B1–B3). Nothing else does.

## Build order

1. **`ios/`** — smallest work, no backend change, and it proves the "shell around the live UI" thesis
   before any TV code exists.
2. **`tvos/`** skeleton → browse → player.

## ⚠ Toolchain

These folders cannot be built in the Linux sandbox (`swift` and `xcodebuild` are absent — verified
2026-09-13). They build **on the MacBook Pro**. The agent writes, reviews and diffs; he compiles and
runs. Suggested bundle identifiers, to confirm before the first build:
`com.helloraj1986.rkmcinema.ios` / `com.helloraj1986.rkmcinema.tvos`.
