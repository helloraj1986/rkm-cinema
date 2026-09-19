# `tvos/` — RKMCinemaTV (Apple TV)

A **native SwiftUI client**. tvOS has no WebKit at all (Apple removed it; the guidelines prohibit
embedding one), so there is no shell shortcut here — the UI is written for the TV. Full reasoning:
[`../../docs/APPLE_CLIENTS_PLAN.md`](../../docs/APPLE_CLIENTS_PLAN.md) §4.

**Status: Phase A ACCEPTED on his Apple TV simulator (2026-09-19)** — screens 0–2 (address → sign in →
who's watching), merged to `dev`. **Phase B is under way on `feat/tvos-library`**: **B1 (the item models +
gate), B2 (Home), B3 (Browse) and B4 (item detail) are BUILT**, and only B5 — the Mac round — remains.
⚠ **None of Phase B's SwiftUI has ever been compiled** — that round is the first time. §1's one-time Xcode
step is DONE: the project, `INFOPLIST_FILE`, the shared scheme and the local package are all committed.

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

⚠ **No bundle-id step, deliberately.** `mac-round.sh` reads `PRODUCT_BUNDLE_IDENTIFIER` out of the
project's build settings and launches that, so Xcode's own default (`com.helloraj1986.RKMCinemaTV`) is
fine. It used to hardcode `com.helloraj1986.rkmcinema.tvos`, which would have built and installed and then
refused to launch — a failure that reads like a build fault, and a GUI step nobody should have to get right.

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

⚠⚠ **READING A SCREENSHOT FROM THIS ROUND — three things that have already cost time (2026-09-19):**

1. **The debug HUD covers the top-left of the app.** It is a **980pt-wide** panel at `padding(28)` with
   `black.opacity(0.88)`, so on Home it hides the header's left side and **the first rail's heading**.
   A heading missing under the panel is COVERAGE, not absence — and a screenshot taken with
   `-RKMDebugHUD YES` is *for the log lines*, not for judging layout. Run the round without the flag for a
   clean screen.
2. **The HUD reads newest-first**: the newest line is at the TOP. So what you need is at the top of the
   panel, not the bottom.
3. ⚠⚠ **A launch that has not finished painting shows the PREVIOUS run's snapshot.** Two consequences: the
   cards on a very early screenshot are not this launch's, and the log lines will stop at the session read —
   `/api/library/*` and `poster` lines appear only once Home actually loads. **Wait until the rails are
   drawn before screenshotting**, or the frame answers nothing (it happened on his first B2 round).
   Falsified if: a screenshot taken well after the rails appear still shows no `poster` lines — then the
   HUD is not live or the lines are not emitted, and that is a defect, not a timing artefact.

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
| 3 | Home | `GET /api/library/continue-watching` · `/recently-watched` | **B ✅ built (B2)** |
| 4 | Browse | `GET /api/library/folders` → `/items` | **B ✅ built (B3)** |
| 5 | Item detail (read-only) | `GET /api/jellyfin/detail?id=` · `/api/library/series/{id}/episodes` | **B ✅ built (B4)** |
| 6 | Player | `GET /api/jellyfin/hls/{id}/master.m3u8` · `POST /api/jellyfin/progress` | C |

⚠ **Screen #5 has NO Play control, deliberately.** The player is Phase C and the api has no route this app
may play from, so a Play button would be a promise the app cannot keep (`docs/ARCHITECTURE.md` §11 — never
OFFER what the server will refuse). It says where playback comes from and shows the verb it **will** offer
(`Resume S1E4`), computed by the same rule Phase C's button will read.

**Deliberately out of scope:** request/download + quality profiles, Household admin, subtitle *vendor*
search and download, global search.

### Phase A's acceptance, exactly

On the simulator, with `-RKMDebugHUD YES`:

1. **Screen #0 opens with the field already filled** — `http://rkm-hp.tail8d5e8.ts.net:8124`. Press
   Connect once. *(A simulator uses the Mac's network. If the Mac is not on the tailnet, the field is
   editable — clear it and type the LAN address the web app uses on the home network, then Connect.)*
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
  `AppLog`, `SessionStore`, `ServerDefaults`, `DetailStore` and `DetailView`'s dependencies typecheck
  (nineteen portable files); the models and every endpoint literal are checked against the frozen contract,
  with the item and detail shapes checked against the frontend's own TypeScript interfaces where the contract
  is silent; **the URLs, the models and every screen's rules are EXECUTED** (297 checks); and every framework
  import is present. See §6.

⚠ **Say "it builds on the Mac", never "it works"** — and a screenshot with the HUD is the report that
makes the next fix possible.

---

## 6. Gates (all runnable here, all run before every hand-back)

```bash
python3 apple/scripts/check-tvos-models.py            # models + endpoints vs the frozen contract
python3 apple/scripts/check-tvos-models.py --falsify  # 14 mutations, each must go red
python3 apple/scripts/check-tvos-core.py              # RUNS the URLs, the models + every screen's rules
python3 apple/scripts/check-tvos-core.py --falsify    # 45 rules reverted, each must go red
TMPDIR=/root/tmp bash apple/scripts/check-apple-typecheck.sh   # compiles the 19 portable files
python3 apple/scripts/check-imports.py apple/tvos/RKMCinemaTV  # missing imports — INCLUDING the views
python3 apple/scripts/check-imports.py --selftest     # 6 snippets, incl. the RKMServerKit rule's edges
bash apple/scripts/test-mac-round.sh                  # the round script, stubbed, 10 cases
```

⚠⚠ **`check-imports.py` IS THE ONLY GATE THAT SEES THE SWIFTUI VIEWS, and it earned that role on
2026-09-19** — Phase B2's first Mac round died on `Home/HomeView.swift: cannot find 'RKMLog' in scope`. The
view files are not in `check-apple-typecheck.sh`'s list (no SwiftUI exists on Linux to compile them
against), and this checker's rule table listed only **Apple's** frameworks, so the app's own
`RKMServerKit` was in neither. Two gates, one blind spot each, one failed round. The module is now a rule
like any other, and `--selftest` pins both of its edges: it must fire on a real use without the import, and
must stay silent on the app's own `RKM`-prefixed types (`RKMCinemaTVApp`) and on a symbol that only appears
in a comment.

⚠ **A SwiftUI stub is deliberately NOT built.** The three things a view can get wrong are: a missing import
(now caught above), a typo in a type or member name, and a wrong API shape. A partial stub would catch only
some of the second kind and would generate cascading false errors for the third — and a gate that cries
wolf is worse than a gate that is honestly absent. The views stay Mac-round business, which is exactly what
`TVStubs.swift` says.

⚠ **`check-tvos-core.py` is not a duplicate of the typecheck — it EXECUTES.** `swiftc -parse` and even a
clean compile prove nothing about behaviour, so the seven pure sources (`LibraryModels`, `PosterURL`,
`HomeRails`, `BrowseRules`, `DetailModels`, `DetailRules`, `RequestURL`) are compiled **and run** against
fixtures shaped like the real payloads (**297 checks across B1, B2, B3 and B4**). That is what makes the
silent failures visible here instead of on the TV: a poster URL that 404s, a request whose query became part
of the path, a payload that cannot decode, and a screen whose states are wrong — all of which look like
nothing at all on a screen.

⚠ **Two of these have already caught real defects, and one of them is the argument for the pair:**

- `check-apple-typecheck.sh` caught **five Mac build errors** (`withBusy` called but never written) on
  its first run.
- `check-imports.py` caught a **missing `import Combine`** in `SessionStore.swift` that the typecheck
  *passed* — because `typecheck-stubs/TVStubs.swift` declares `ObservableObject` in the same module, so
  the missing real import is invisible there. Exactly the iOS-first-build failure mode
  (`apple/WORKFLOW.md` §7b), caught for free.

**And all four gates that matter have been falsified**, not just observed green:
`check-tvos-models.py --falsify` reverts each rule and requires the matching check to fail (14/14 red,
including the two Phase B rules R6/R7, the interpolated-endpoint case and three mutations on B4's detail
models, all against the frontend's own interfaces); `check-tvos-core.py
--falsify` does the same for the 45 rules the running harness pins (45/45 red — and it earned its keep on
its first B2 run by finding a TAUTOLOGY in the harness itself); `test-mac-round.sh` asserts on the
stubs' call log, and goes red against the previous revision of
`mac-round.sh` on two separate faults: the truncating device-name extraction fails 2 of its 10 cases, and
the hardcoded bundle id fails case J.

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
