# `tvos/` — RKMCinemaTV (Apple TV)

A **native SwiftUI client**. tvOS has no WebKit at all (Apple removed it; the guidelines prohibit
embedding one), so there is no shell shortcut here — the UI is written for the TV. Full reasoning:
[`../../docs/APPLE_CLIENTS_PLAN.md`](../../docs/APPLE_CLIENTS_PLAN.md) §4.

**Status: Phase A built — screens 0–2 (address → sign in → who's watching), on branch `feat/tvos-client`,
not yet built on the Mac.** The Xcode project does not exist yet; §1 is the one-time step that creates it.

**Scope rule: TV is a *viewing* surface.** Read + play only. The acquisition and administration half of
rkm-cinema stays on web/iOS, where a keyboard and forms make sense.

---

## 1. The one-time Xcode step (his, ~5 minutes) — nothing else needs the GUI, ever

⚠ **Order matters.** `apple/tvos/RKMCinemaTV/` already holds the real sources (like `apple/ios/` did in
Phase 0), so the project is created in a **scratch folder** and only the `.xcodeproj` is moved in. If
Xcode wrote its own template `RKMCinemaTVApp.swift` over ours, that would be a silent overwrite of a
committed file.

```bash
# 1. On the Mac. Fresh Xcode refuses command-line builds until the licence is accepted.
sudo xcodebuild -license accept
cd ~/dev/rkm-cinema && git fetch && git checkout feat/tvos-client && git pull --ff-only
```

**2. In Xcode: File → New → Project → tvOS → App.** Product Name **`RKMCinemaTV`**, Interface
**SwiftUI**, Language **Swift**, ⚠ **untick "Create Git repository"** (the repo exists). Save it to
**`~/Desktop/rkm-scratch`** — *not* into `apple/tvos/`.

```bash
# 3. Move only the project across; throw the template away.
cd ~/dev/rkm-cinema
mv ~/Desktop/rkm-scratch/RKMCinemaTV.xcodeproj apple/tvos/
rm -rf ~/Desktop/rkm-scratch
git status     # ⚠ expect ONLY the new .xcodeproj. If a source file shows as modified, Xcode
               #   overwrote it — restore it:  git checkout -- apple/tvos/RKMCinemaTV/
```

This works because Xcode 16's source reference is the **synchronized folder `RKMCinemaTV/`**, stored
relative to the project — so the project lands beside the folder of that name and picks up every source
file inside it. **A file's presence in that folder IS its target membership**, which is why the agent can
add files for the rest of the project's life without touching the project file.

**4. Open `apple/tvos/RKMCinemaTV.xcodeproj`** and confirm the navigator lists `App/`, `Auth/`, `Core/`,
`Debug/`, `Server/`, `Assets.xcassets` — that is the check that the synchronized group found the real
sources.

**5. Four settings, then commit:**

| Where | Setting | Value | Why |
|---|---|---|---|
| Build Settings | `INFOPLIST_FILE` | `Config/Info.plist` | ⚠ ATS is a nested dictionary and `INFOPLIST_KEY_*` cannot express it |
| Build Settings | `GENERATE_INFOPLIST_FILE` | `NO` | otherwise Xcode generates a second plist |
| Build Settings | `TVOS_DEPLOYMENT_TARGET` | `17.0` | ⚠ Xcode pins the SDK version (26.x) by default. 17.0 installs on anything newer, and the code uses nothing newer |
| Signing & Capabilities | Team | your Apple ID | only needed for a *device* build; **the simulator needs no signing** |

⚠ **The plist must stay in `Config/`, never inside `RKMCinemaTV/`.** A file inside the target's
synchronized folder is auto-added as a *resource*, so a custom `Info.plist` there is at once copied into
the app and processed as the Info.plist → `error: Multiple commands produce …Info.plist`. Learned on the
iOS target's first build.

⚠ **Then share the scheme:** Product → Scheme → Manage Schemes → tick **Shared**. `mac-round.sh` builds
with `-scheme RKMCinemaTV`, and a scheme living only in `xcuserdata` is not in the clone.

**6. File → Add Package Dependencies → Add Local… → `apple/Shared`** (once). That links
**`RKMServerKit`** — see §3.

**7. Commit and push** (`git add -A && git commit -m "chore(tvos): the Xcode project" && git push`).

---

## 2. The round command (one command, every time after that)

```bash
cd ~/dev/rkm-cinema && ./apple/scripts/mac-round.sh tvos --sim -RKMDebugHUD YES
```

It pulls, builds, installs and launches on an Apple TV simulator, logging to `apple/logs/`. Paste the
short summary back (the errors, then the tail).

⚠ **Two things about the simulator, both fixed in the script on 2026-09-19 and both worth knowing:**
the script uses the Apple TV that is **already booted** if there is one, and there is **no committed
default device name** for tvOS because every Apple TV's name contains brackets (`Apple TV 4K (3rd
generation)`) — so it takes the first available and prints which one it chose. If you want a specific
one, boot it first and the script will use it.

After the first green round, Xcode's ⌘R works too, and is better for stepping through a focus bug.

---

## 3. What was REUSED from the iOS app, and what could not be

Measured against the actual files, not assumed. This is the answer to *"reuse as much as possible"* —
and the honest part is the middle column.

| | Files | LOC | Verdict |
|---|---|---|---|
| **Shared package** | `apple/Shared/Sources/RKMServerKit/*` (8 files) | 1,545 | ✅ **Linked as-is.** Its `Package.swift` already declares `.tvOS(.v16)`. Gives screen #0 (`ServerAddress` parse/normalise + `ServerStore` persistence) and the whole logging stack (`RKMLog`, `RollingFileLog`, `LogRingBuffer`, `LogRedactor`, `CorrelationID`) |
| **One iOS file, copied** | `apple/ios/RKMCinema/Server/ServerProbe.swift` | 57 | ✅ **Identical logic, new home.** `Foundation` + `RKMServerKit`, no UIKit, no WebKit — and its reachable/unreachable rule is a rule, not a platform behaviour, so a second copy would only be a second place to get it wrong |
| **iOS views, as shapes** | `Server/ServerSetupView`, `Server/UnreachableServerView`, `Debug/DebugHUD`, `App/AppLog`, `App/AppModel`, `App/AppRootView` | ~1,000 | ⚠ **Rewritten, not ported.** Every one needed the focus engine (no pointer, no hover), the TV type scale (readable from three metres), and the removal of iOS-only API. `ProfilesView` and `LoginView` are new |
| **`Sheet/` — the whole WKWebView shell** | 10 files | ~1,700 | ❌ **Dead.** tvOS has no WebKit at all. Not deprecated — absent |
| **`Offline/` + `Spike/`** | 14 files | ~6,600 | ❌ **Dead, and out of scope.** The download + loopback-server stack exists to serve the SPA into a WebView with no network. TV is read+play |
| **New on tvOS** | `Core/APIClient`, `Core/Models/AuthModels`, `Auth/SessionStore` | ~700 | ⚠ **Genuinely new.** ⚠ The iOS shell has **no API client by design** — the page makes its own same-origin `/api` calls — so the REST layer was never a port, it is the first one |

**The design rule that keeps this honest** (`apple/README.md`): nothing goes in `Shared/` unless *both*
apps need it. So the REST client, the auth models and the session live in the tvOS target, not in
`RKMServerKit` — the iOS shell would never use them, and putting them there would be one client being
bent to look like the other.

---

## 4. Screens (the whole app — resist adding to this list)

| # | Screen | Endpoints | Phase |
|---|---|---|---|
| 0 | Server address (PRE-FILLED) | — (persisted locally) | **A ✅ built** |
| 1 | Sign in | `POST /api/auth/login` | **A ✅ built** |
| 2 | Who's watching | `GET /api/auth/profiles` · `POST /api/auth/profile` · `GET /api/auth/me` | **A ✅ built** |
| 3 | Home | `GET /api/library/continue-watching` · `/recently-watched` | B |
| 4 | Browse | `GET /api/library/folders` → `/items` | B |
| 5 | Item detail | `GET /api/jellyfin/detail` · `/api/status` | B |
| 6 | Player | `GET /api/jellyfin/hls/{id}/master.m3u8` · `POST /api/jellyfin/progress` | C |

**Deliberately out of scope:** request/download + quality profiles, Household admin, subtitle *vendor*
search and download, global search.

### Phase A's acceptance, exactly

On the simulator, with `-RKMDebugHUD YES`:

1. **Screen #0 opens with the field already filled** — `http://rkm-hp.tail8d5e8.ts.net:8124`. Press
   Connect once. *(If the simulator cannot reach the tailnet, type the LAN address instead —
   `http://192.168.x.x:8124`. Simulators use the Mac's network, so the Mac must be on the tailnet or the
   LAN.)*
2. **A wrong address is refused with a reason**, and `Can't reach this server` offers `Try again` and
   `Change server` — both reachable with the d-pad.
3. **Sign-in screen**: the household username/password signs in.
4. **Who's watching** lists the profiles with a lock on the protected one and the admin marked. Selecting
   a password-less profile goes straight through; the admin asks for a password.
5. **The session screen** shows the server, the signed-in user, the profile, and `Profile selected: yes`.
6. **A screenshot with the HUD visible** — the correlation ids on it are what makes the log readable.

⚠ There is **no library screen in this phase, and that is deliberate** — the screen after the picker says
so in as many words. Phase B replaces it.

---

## 5. What is NOT verified (read this before believing anything above)

Everything UI. Specifically:

- **The SwiftUI views have never been compiled or run.** No Mac here. They use only APIs that exist on
  tvOS 15+ and avoid every iOS-only modifier (`keyboardType`, `textContentType`, `submitLabel`,
  `textInputAutocapitalization`, `autocorrectionDisabled`, `textSelection`) — that avoidance is a
  deliberate design choice, not an accident, and it is why the code looks plainer than its iOS twin.
  ⚠ **The focus engine is the single biggest unknown.** How the grid lands, whether the password overlay
  keeps its focus, whether the remote's Back behaves — none of it can be known from here.
- **What IS verified, on Linux, before any Mac round:** `APIClient`, `AuthModels`, `ServerProbe`,
  `AppLog`, `SessionStore` and `ServerDefaults` typecheck; the models and every endpoint literal are
  checked against the frozen contract; every framework import is present. See §6.

⚠ **Say "it builds on the Mac", never "it works"** — and a screenshot with the HUD is the report that
makes the next fix possible.

---

## 6. Gates (all runnable here, all run before every hand-back)

```bash
python3 apple/scripts/check-tvos-models.py            # models + endpoints vs the frozen contract
python3 apple/scripts/check-tvos-models.py --falsify  # 6 mutations, each must go red
TMPDIR=/root/tmp bash apple/scripts/check-apple-typecheck.sh   # compiles the 6 portable files
python3 apple/scripts/check-imports.py apple/tvos/RKMCinemaTV  # missing framework imports
bash apple/scripts/test-mac-round.sh                  # the round script, stubbed, 9 cases
```

⚠ **Two of these have already caught real defects, and one of them is the argument for the pair:**

- `check-apple-typecheck.sh` caught **five Mac build errors** (`withBusy` called but never written) on
  its first run.
- `check-imports.py` caught a **missing `import Combine`** in `SessionStore.swift` that the typecheck
  *passed* — because `typecheck-stubs/TVStubs.swift` declares `ObservableObject` in the same module, so
  the missing real import is invisible there. Exactly the iOS-first-build failure mode
  (`apple/WORKFLOW.md` §7b), caught for free.

**And both gates that matter have been falsified**, not just observed green:
`check-tvos-models.py --falsify` reverts each rule and requires the matching check to fail (6/6 red);
`test-mac-round.sh` asserts on the stubs' call log, and goes red against the previous revision of
`mac-round.sh` — the truncating device-name extraction fails 2 of its 9 cases.

---

## 7. The two things that will actually cost the time (unchanged from the plan)

1. **The focus engine.** There is no pointer and no hover on tvOS. The web app's `AccountMenu` (hover
   menu), `PopupMenu`, `Dialog`, and the pointer-capture seek bar in `Player.tsx` all need focusable
   equivalents for a d-pad. Design for focus from the first view; retrofitting it is the expensive path.
   *(Phase A does this much: the profile grid is a focus grid, the password card carries its own Cancel,
   and `Change server` is on every screen.)*
2. **Distance.** CSS viewport assumptions (fixed overlays, `inset-0`, 16:9 backdrops) are meaningless at
   1080p/4K from three metres. The TV UI has its own type scale — 54pt titles, 22–30pt body — not the
   web's.

**Budget: 2–4 weeks of evenings**, of which the toolchain and signing are the first two days.

## 8. What comes next

- **Phase B** — Home (Continue Watching / Recently Added), Browse (folders → items), item detail,
  posters. New contract models for `GET /api/library/*` and `GET /api/jellyfin/detail`, checked by the
  same gate.
- **Phase C** — `AVPlayer` + HLS, resume and progress reporting, **and the only backend change this app
  needs**: B1–B3 (`session_token` from login, accepted in `api/session.py::session_context_from_request`,
  injected into each rewritten HLS URI). Auth is cookie-only today — verified
  `backend/api/session.py:236`. ⚠ **Do not bet playback on cookie propagation to segment requests.**
- **Phase D** — focus/distance polish at 1080p from three metres.
