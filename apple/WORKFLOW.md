# Two-machine workflow — authoring on Windows, building on the Mac

The Apple clients cannot be built where Hermes runs. This is the agreed loop, and the
one thing that decides whether it stays smooth.

```
┌─────────────────────────────┐        ┌──────────────────────────┐
│  Windows PC (RKM-HP)        │        │  MacBook Pro             │
│  Hermes + its Docker sandbox│        │  Xcode + Apple SDKs      │
│  /workspace/projects/       │        │  ~/dev/rkm-cinema        │
│    rkm-cinema               │        │                          │
│  = HIS WINDOWS CHECKOUT     │        │  builds + runs on the    │
│    authoring only           │        │  simulator / real device │
└──────────┬──────────────────┘        └────────────┬─────────────┘
           │  push (token script, sandbox-side)     │  pull / commit / push
           ▼                                        ▲
      ┌──────────────────────────────────────────────┐
      │  GitHub — helloraj1986/rkm-cinema (private)  │
      │  branch feat/apple-clients                   │
      └──────────────────────────────────────────────┘
```

⚠ **The sandbox IS his Windows checkout.** `/workspace/projects/rkm-cinema` is the same
tree as `D:\hermes_agent\hermes-workspace\projects\rkm-cinema`. So a commit the agent
makes appears in his Windows working tree immediately — there is no separate Windows copy
to sync. **GitHub is the bridge to the Mac, and nothing else is.**

| | Windows (Hermes) | MacBook Pro |
|---|---|---|
| Does | writes Swift, reviews, commits, pushes | generates projects, builds, runs, signs, fixes |
| Command | `bash .git/push_branch.sh <branch>` (token, sandbox-side) | plain `git pull` / `git push` |
| Gate | `swift test` on the shared package (see below) | Xcode build + run on device |

---

## 1. One-time setup on the Mac

```bash
# 1. Clone the repo somewhere sane (NOT in iCloud Drive — Xcode and iCloud fight).
git clone https://github.com/helloraj1986/rkm-cinema.git ~/dev/rkm-cinema
cd ~/dev/rkm-cinema
git checkout feat/apple-clients

# 2. Xcode: sign in with the Apple ID and set the Team under
#    Signing & Capabilities. A free personal team builds for 7 days at a time;
#    the paid program (~AUD $149/yr) gives a year and enables TestFlight.

# 3. ONLY IF the check in §2 fails — not needed otherwise.
# brew install xcodegen
```

## 2. Who creates the Xcode projects — he does, once

Only Xcode can produce a valid `.xcodeproj`. So: **he creates both projects once, pushes
them, and the agent writes every Swift file after that.**

In Xcode, for each app:

1. **File → New → Project**, then `iOS` → **App** (name `RKMCinema`), and separately
   `tvOS` → **App** (name `RKMCinemaTV`). Interface **SwiftUI**, Language **Swift**.
2. Save into `apple/ios/` and `apple/tvos/` respectively.
   ⚠ **Untick "Create Git repository"** — the repo already exists.
3. Push.

### ⚠ The one check that decides whether the loop stays smooth

```bash
grep -c PBXFileSystemSynchronizedRootGroup apple/ios/RKMCinema.xcodeproj/project.pbxproj
```

| Result | What it means |
|---|---|
| **≥ 1** | Xcode 16+ created a **synchronized** folder group: a file's *presence in the folder* is what adds it to the target. The agent can add Swift files freely and Xcode picks them up — **no project file edits, ever**. This is what we want. |
| **0** | Classic groups: every new file must be registered in `project.pbxproj`. **Then we stop and switch to XcodeGen** — `brew install xcodegen`, the agent writes `project.yml` + sources, he runs `xcodegen generate`. We do **not** hand-edit `project.pbxproj`; that is how projects get corrupted. |

This check is why the layout keeps all sources under the target's own folder — synchronized
groups only auto-include files *inside* that folder.

### Adding the shared package (after Phase 0)

The agent writes `apple/Shared/Package.swift` in Phase 0. Once it exists:

**File → Add Package Dependencies → Add Local… → `apple/Shared`** in **both** projects.
That is what stops the address rules being copy-pasted into two apps and drifting.

## 3. The loop, per round of work

**On Windows (the agent):**

```bash
cd /workspace/projects/rkm-cinema
git fetch origin                    # do NOT trust origin/* without this
git pull --ff-only                  # pick up whatever the Mac pushed
#   ... write the Swift ...          (never touch project.pbxproj)
git add -A && git commit -m "..."
bash .git/push_branch.sh feat/apple-clients
```

**On the Mac (him):**

```bash
cd ~/dev/rkm-cinema
git pull
xcodegen generate        # ONLY on the XcodeGen path (see §2)
open apple/tvos/RKMCinemaTV.xcodeproj
#   ... build, run on the simulator / Apple TV, fix ...
git add -A && git commit -m "..." && git push
```

Then the agent pulls again on Windows and sees exactly what Xcode produced.

## 4. The rules that keep the loop honest

1. **One writer at a time.** The agent and Xcode must never be editing the same file in
   the same round. Finish a round, push, hand over — then start the next.
2. **Pull before you start, push before you hand back.** Every round, both sides.
3. **The agent never trusts a ref it has not fetched.** A token-URL push does not update
   the local `origin/*` — the fetch is the authoritative check.
4. **`project.pbxproj` is his territory.** The agent edits sources only; if a project-file
   change is ever needed, that is the signal to move to XcodeGen (§2).
5. **Xcode state stays out of git.** `xcuserdata/`, `DerivedData/`, `.build/` are already
   ignored; generated API types are deliberately **not** ignored.
6. **Line endings are LF everywhere and now pinned** (`.gitattributes`, added 2026-09-13).
   Do not add `*.ps1 eol=crlf` — the existing PowerShell scripts run correctly as LF.

## 5. What the agent can and cannot verify without a Mac

| Verifiable in the sandbox | Mac-only |
|---|---|
| The **shared package** — address parsing/normalisation/persistence is pure Swift with no UIKit, so it compiles and unit-tests on Linux. ⚠ The sandbox is **Debian 13 with glibc 2.41**; swift.org ships **Ubuntu 24.04** builds (glibc floor 2.39, toolchain confirmed reachable 2026-09-13), so it should run — **the agent installs it and actually runs `swift test` at Phase 0, and says so plainly if it does not work** rather than claiming a green run. | **Everything UI**: SwiftUI, `WKWebView`, `AVPlayer`, focus engine, ATS behaviour, signing, provisioning, and any Apple SDK API. These are the **Mac gate** — a build that has not run there is not verified. |
| `backend/` (pytest) and `frontend/` (tsc · vitest · build) — the normal existing loop. | |

## 6. The handoff artefact

Each phase ends with a block at the top of `docs/PROGRESS.md`: what was built, the branch
and commit, the gates actually run, what is **unverified**, and the exact next action —
the same convention every other workstream in this repo uses. Cross-machine work makes
this load-bearing rather than a nicety: it is how the next session on the Windows side
knows what the Mac already proved.
