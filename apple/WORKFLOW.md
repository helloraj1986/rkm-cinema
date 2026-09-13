# Two-machine workflow — authoring on Windows, testing on the Mac

**Revised 2026-09-13** for: *"i plan to use mac only for testing... development will be strictly here"* and
*"will it work if i simply installed xcode app?"* → **Yes. Xcode alone is enough to build, run, sign and
debug.** No Homebrew, no XcodeGen, no extra tooling required to test. See §2 for the one thing Xcode cannot do
for me, and the check that decides whether that matters.

```
┌─────────────────────────────┐        ┌──────────────────────────┐
│  Windows PC (RKM-HP)        │        │  MacBook Pro             │
│  Hermes + its Docker sandbox│        │  Xcode                   │
│  /workspace/projects/       │        │  ~/dev/rkm-cinema        │
│    rkm-cinema               │        │                          │
│  = HIS WINDOWS CHECKOUT     │        │  TESTING ONLY            │
│  ALL DEVELOPMENT HAPPENS    │        │  build · run · screenshot│
│  HERE                       │        │  · stream logs           │
└──────────┬──────────────────┘        └────────────┬─────────────┘
           │  push (token script, sandbox-side)     │  pull · run one script
           ▼                                        ▲
      ┌──────────────────────────────────────────────┐
      │  GitHub — helloraj1986/rkm-cinema (private)  │
      │  branch feat/apple-clients                   │
      └──────────────────────────────────────────────┘
```

⚠ **The sandbox IS his Windows checkout** (`/workspace/projects/rkm-cinema` ==
`D:\hermes_agent\hermes-workspace\projects\rkm-cinema`). Agent commits land in his Windows tree directly — there
is no second Windows copy. **GitHub is the only bridge to the Mac.**

| | Windows (Hermes) | MacBook Pro |
|---|---|---|
| Does | **writes all the code**, commits, pushes | pulls, creates the projects **once**, builds, runs, signs, screenshots, streams logs |
| Edits | every source file | **only**: the two projects (once) · signing · one Info.plist setting |
| Command | `bash .git/push_branch.sh feat/apple-clients` | `./apple/scripts/mac-round.sh ios\|tvos` |

---

## 1. One-time setup on the Mac

```bash
# Just Xcode, from the App Store, then accept the licence — a fresh Xcode refuses
# command-line builds until you do, with a confusing "agree to the license" failure.
sudo xcodebuild -license accept
xcodebuild -version          # confirm the toolchain responds

# Clone (NOT inside iCloud Drive — Xcode and iCloud fight over derived data).
git clone https://github.com/helloraj1986/rkm-cinema.git ~/dev/rkm-cinema
cd ~/dev/rkm-cinema
git checkout feat/apple-clients
```

**Signing:** sign in with the Apple ID, and set the Team once under **Signing & Capabilities** after the first
build attempt. A free personal team builds for 7 days at a time; the paid program (~AUD $149/yr) gives a year and
enables TestFlight.

## 2. The Xcode projects: he creates each one ONCE, then never again

**Xcode alone cannot be skipped for this one step** — only Xcode writes a valid `.xcodeproj`, and hand-writing
one is how projects get corrupted. So: **he creates both projects once (a ~5-minute GUI job), commits them, and
I write every source file after that.**

### Order matters — the projects come first, and Phase 0 arrived around it

Xcode's new-project template writes `RKMCinemaApp.swift` and `Assets.xcassets` into the source folder, so
writing my sources first would normally collide with those files. The order is therefore:

1. **He** creates both projects (below).
2. **I** write every real source file into them.

⚠ **Phase 0 ran in the other order, deliberately.** His project did not exist yet and he asked for the
sources anyway, so `apple/ios/RKMCinema/` is already populated. That changes only step 1 — it becomes the
**collision-free variant** below (build the project scratch, move only the `.xcodeproj` in). Nothing else
about the arrangement changes, and `apple/Shared/` was never affected by any of it: it needs no Xcode,
which is why it was written and `swift test`ed first.

### Creating each project

⚠ **This is the Phase 0 variant, because `apple/ios/RKMCinema/` already holds the real sources.**

1. In Xcode: **File → New → Project** → `iOS` → **App**. Product Name `RKMCinema`, Interface **SwiftUI**,
   Language **Swift**, ⚠ **untick "Create Git repository"** (the repo already exists). **Save it somewhere
   scratch** — e.g. `~/Desktop/rkm-scratch` — and **not** into `apple/ios/`: Xcode would otherwise write its
   own template `RKMCinemaApp.swift` and `Assets.xcassets` over ours.
2. Move only the project across and throw the template away:

   ```bash
   cd ~/dev/rkm-cinema
   mv ~/Desktop/rkm-scratch/RKMCinema.xcodeproj apple/ios/
   rm -rf ~/Desktop/rkm-scratch
   git status      # ⚠ expect ONLY the new .xcodeproj. If a source file shows as modified, Xcode
                   #    overwrote it — restore it:  git checkout -- apple/ios/RKMCinema/
   ```

   This works because Xcode 16's source reference is the **synchronized folder `RKMCinema/`**, stored
   relative to the project. So the project simply lands beside a folder of that name and picks up every
   source file inside it. Nothing else needs moving.
3. Open `apple/ios/RKMCinema.xcodeproj` and confirm the navigator lists `App/`, `Server/`, `Shell/`,
   `Debug/` and `Info.plist` — that is the check that the synchronized group found the real sources.
4. Work the settings in the table below, then commit and push. The same steps with `RKMCinemaTV` into
   `apple/tvos/` when Phase 1 starts.

⚠ **Then share the scheme** (Product → Scheme → Manage Schemes → tick **Shared**). `mac-round.sh` builds with
`-scheme RKMCinema`, and a scheme that lives only in `xcuserdata` is not in the clone — a fresh checkout would
fail with "scheme not found", for a reason that looks nothing like the cause.

### ⚠ The check that decides whether the loop stays smooth

```bash
grep -c PBXFileSystemSynchronizedRootGroup apple/ios/RKMCinema.xcodeproj/project.pbxproj
```

| Result | What it means |
|---|---|
| **≥ 1** | Xcode 16+ created a **synchronized** folder group: a file's *presence in the folder* is its target membership. **I add Swift files freely, forever, with no project edits.** Expected with any current Xcode. |
| **0** | Classic groups — every new file must be registered in `project.pbxproj`. Then either he adds files in Xcode's GUI, or we move to XcodeGen (§2.1). **We do not hand-edit `project.pbxproj`.** |

This is why every source lives under its target's own folder: synchronized groups only auto-include files
*inside* that folder.

### The complete list of things he ever has to touch (one-time)

| Once | Why | If skipped |
|---|---|---|
| **Signing & Capabilities → Team** | device builds need a team | the build fails on device |
| **`INFOPLIST_FILE` → `RKMCinema/Info.plist`** (I supply the file; he points the setting at it) | the ATS declaration is a nested dictionary, which `INFOPLIST_KEY_*` build settings **cannot express** — a real Info.plist is required | a user-typed `http://` address is blocked and the app looks broken |
| **File → Add Package Dependencies → Add Local… → `apple/Shared`** (once per project) | links `RKMServerKit` into the target | compile error on the import |

That is the whole list. ⚠ Everything else stays mine, and if project-level changes ever become routine, §2.1 is
the answer.

### 2.1 Fallback: XcodeGen — only if project-file changes become routine

`brew install xcodegen`; I then own `apple/{ios,tvos}/project.yml` and the `.xcodeproj` becomes generated build
output (flip the `.gitignore` line and delete the committed projects). Honest notes: XcodeGen is **not** bundled
with Xcode, and its development pace has slowed — though its input format barely changes.
**Not needed to start.** The reason it is no longer the default: synchronized folder groups already solve the
only problem that mattered — adding a file without touching the project.

## 3. The loop, per round

**I run (Windows):**

```bash
cd /workspace/projects/rkm-cinema
git fetch origin                          # never trust origin/* without this
git pull --ff-only                        # pick up anything he pushed back
#   ... write the Swift ...
git add -A && git commit -m "..."
bash .git/push_branch.sh feat/apple-clients
```

**He runs (Mac) — ONE command:**

```bash
cd ~/dev/rkm-cinema && ./apple/scripts/mac-round.sh ios      # or: tvos
```

It pulls, builds, and drops a plain-text build log into `apple/logs/`, printing a **short** summary (the errors,
then the tail) — a full `xcodebuild` log is thousands of lines. Add `--sim` to install and launch on a simulator.
(If we ever move to XcodeGen it also regenerates the project first — the script handles both.)

⚠ **It has not been run yet** — no Xcode on the Windows side, so it is written-but-unverified; expect one round
of fixing its flags on first real use.

Then: Xcode for run/install/screenshot, plus `log stream` per `LOGGING.md` §7.

## 4. The rules that keep the loop honest

1. **One writer at a time.** I write code; he tests. He must not edit sources in Xcode — a fix that exists only
   on the Mac is a fix that the next pull overwrites.
2. **Pull before starting, push before handing back.**
3. **I fetch before trusting a ref.** A token-URL push does not update local `origin/*`.
4. **The project file is his, once** (the GUI steps in §2) — then it is nobody's: with synchronized groups it
   never needs editing again. If a project change *does* become routine, that is the signal for §2.1.
5. **Testing evidence comes back as text I can read**: the build summary, the `log stream` tail, and screenshots
   with the **debug HUD visible** (`LOGGING.md` §3, §8). "It doesn't work" is not actionable; a HUD screenshot
   plus the log tail for that correlation id is.
6. **Line endings are LF everywhere, pinned** in `.gitattributes`. Do not add `*.ps1 eol=crlf` — the existing
   PowerShell scripts run correctly as LF.

## 5. What I can and cannot verify without a Mac

| Verifiable in the sandbox | Mac-only |
|---|---|
| **Pure Swift** — the shared package (address parse/normalise/persist) and the **log redactor** have no UIKit, so they compile and unit-test on Linux. ⚠ The sandbox is **Debian 13, glibc 2.41**; swift.org ships **Ubuntu 24.04** builds (glibc floor 2.39, reachable — verified 2026-09-13). I will **install the toolchain and actually run `swift test`**, and say plainly if it does not work rather than claiming a green run. | **Everything UI**: SwiftUI, `WKWebView`, `AVPlayer`, focus engine, ATS behaviour, signing, and any Apple SDK API. **A build that has not run on the Mac is not verified** — I will never describe it as working. |
| `backend/` (pytest) · `frontend/` (tsc · vitest · build) — the existing loop. | Screenshots and live behaviour — his side of the loop, and the only real evidence for UI claims. |

## 6. The handoff artefact

Each phase ends with a block at the top of `docs/PROGRESS.md`: what was built, branch + commit, gates actually
run, **what is unverified**, and the exact next action. With two machines and one of them out of my reach, this
is load-bearing rather than a nicety — it is how the next Windows session knows what the Mac already proved.
