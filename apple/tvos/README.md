# `tvos/` — RKMCinemaTV (Apple TV)

A **native SwiftUI client**. tvOS has no WebKit at all (Apple removed it; the guidelines prohibit
embedding one), so there is no shell shortcut here — the UI is written for the TV. Full reasoning:
[`../../docs/APPLE_CLIENTS_PLAN.md`](../../docs/APPLE_CLIENTS_PLAN.md) §4.

**Scope rule: TV is a *viewing* surface.** Read + play only. The acquisition and administration half of
rkm-cinema stays on web/iOS, where a keyboard and forms make sense.

## Planned layout

```
tvos/
└── RKMCinemaTV/                        ← created ONCE in Xcode, then owned by the agent's sources
    ├── RKMCinemaTV.xcodeproj       ← COMMITTED (only Xcode writes a valid one) — WORKFLOW.md §2
    ├── README.md                     ← build/run/acceptance notes, filled in as it is built
    ├── RKMCinemaTV/
    │   ├── RKMCinemaTVApp.swift      @main
    │   ├── Server/                   screen #0 — address field (PRE-FILLED), validation, persistence
    │   ├── Auth/                     login (POST /api/auth/login) · who's watching · profile switch
    │   ├── Library/                  home (continue watching / recently added) · browse · item detail
    │   ├── Player/                   AVPlayer + HLS · resume · progress reporting
    │   ├── Core/
    │   │   ├── APIClient.swift       transport: base URL from the stored address + auth headers
    │   │   └── GeneratedAPI/         swift-openapi-generator output (from the frozen contract)
    │   └── Assets.xcassets
```

`GeneratedAPI/` is **generated, then committed** — mirroring how `frontend/` commits its generated TS
types from the same file. Regenerate with `../scripts/generate-api.sh`; never hand-edit it.

## Screens (the whole app — resist adding to this list)

| # | Screen | Endpoints |
|---|---|---|
| 0 | Server address | — (persisted locally) |
| 1 | Sign in | `POST /api/auth/login` |
| 2 | Who's watching | `GET /api/auth/profiles` · `POST /api/auth/profile` |
| 3 | Home | `GET /api/library/*` (continue watching, recently added) |
| 4 | Browse | `GET /api/library/*` (folders → items) |
| 5 | Item detail | `GET /api/status` · item detail |
| 6 | Player | `GET /api/jellyfin/hls/{id}/master.m3u8` · `POST /api/jellyfin/progress` |

**Deliberately out of scope:** request/download + quality profiles, Household admin, subtitle *vendor*
search and download, global search.

## The two things that will actually cost the time

1. **The focus engine.** There is no pointer and no hover on tvOS. The web app's `AccountMenu` (hover
   menu), `PopupMenu`, `Dialog`, and the pointer-capture seek bar in `Player.tsx` all need focusable
   equivalents for a d-pad. Design for focus from the first view; retrofitting it is the expensive path.
2. **Distance.** CSS viewport assumptions (fixed overlays, `inset-0`, 16:9 backdrops) are meaningless
   at 1080p/4K from three metres. The TV UI needs its own type scale and spacing, not the web one.

⚠ **Server-address entry:** the Siri Remote is a poor text input. **Pre-fill** the field so the common
case is one button press. A nearby iPhone/iPad on the same Apple Account becomes a keyboard
automatically when a text field is focused; Bluetooth keyboards and Siri dictation also work.

## What we get for free

- **The frozen contract** — `docs/api/openapi.v1.json` (ADR-0001, additive-only) generates the Swift
  types, so there is one source of truth and no handwritten model drift.
- **No credential or media URL ever reaches the client** — playback rides the same-origin
  `/api/jellyfin/hls/...` proxy, which rewrites every URI and strips Jellyfin's `api_key`.
- **Apple hardware plays MORE than Chrome.** The HLS ladder exists because Chrome MSE cannot decode
  `ec-3`/`ac3`/DTS/TrueHD. Apple silicon decodes HEVC **and** EAC3 in hardware, so this client can ask
  for `mode=remux` far more often — *less* transcoder load, not more.

## The one backend dependency: HLS auth (`AVPlayer`)

Auth is cookie-only today (`api/session.py::session_context_from_request`). URLSession shares a cookie
store so REST calls authenticate fine, but **do not bet playback on cookie propagation to HLS segment
requests**. Plan §4.4 (B1–B3): return a `session_token` from login, accept it as
`Authorization: Bearer` in that ONE function, and inject it into each URI at the HLS proxy's existing
rewrite point. ⚠ The token is a credential and must never be logged.

**This blocks the player only** — screens 0–2 and 5 do not need it.

## Acceptance (per phase)

- Skeleton: runs on the Apple TV simulator; sign-in and profile switch work on real hardware.
- Browse/detail: posters, rows and navigation on hardware.
- Player: a full film plays, resumes where it left off, and the position appears in the web app's
  Continue Watching.
