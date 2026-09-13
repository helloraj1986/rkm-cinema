# Two-machine workflow — authoring on Windows, testing on the Mac

**Revised 2026-09-13** after the user's clarification: *"i plan to use mac only for testing... development will
be strictly here."* That single constraint **changes the recommendation**: there is no reason to hand a project
file to Xcode's GUI, so the project itself becomes something I author as text. See §2.

```
┌─────────────────────────────┐        ┌──────────────────────────┐
│  Windows PC (RKM-HP)        │        │  MacBook Pro             │
│  Hermes + its Docker sandbox│        │  Xcode + Apple SDKs      │
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
| Does | **writes all the code**, reviews, commits, pushes | pulls, generates, builds, runs, signs, screenshots, streams logs |
| Edits | everything, including `project.yml` | **nothing** (testing only) |
| Command | `bash .git/push_branch.sh feat/apple-clients` | `./apple/scripts/mac-round.sh ios\|tvos` |
| Gate | `swift test` on shared/pure-Swift code | Xcode build + run on device; `log stream` |

---

## 1. One-time setup on the Mac

```bash
# Clone (NOT inside iCloud Drive — Xcode and iCloud fight over derived data).
git clone https://github.com/helloraj1986/rkm-cinema.git ~/dev/rkm-cinema
cd ~/dev/rkm-cinema
git checkout feat/apple-clients

# The only extra tool. Generates the Xcode projects from text I write.
brew install xcodegen
```

**Xcode:** sign in with the Apple ID, and set the Team once under **Signing & Capabilities** after the first
generate. A free personal team builds for 7 days at a time; the paid program (~AUD $149/yr) gives a year and
enables TestFlight.

## 2. The project files are generated from `project.yml` — he never creates them

**Because development is strictly on Windows, the `.xcodeproj` should be build output, not something a human
created in a GUI.** I write `apple/ios/project.yml` and `apple/tvos/project.yml`; `xcodegen generate` turns each
into an `.xcodeproj`.

Why this beat the earlier plan (he creates the project once in Xcode, then I add files):

| | XcodeGen (chosen) | Hand-made project |
|---|---|---|
| Who can add a source file | **me** — edit `project.yml`, done | depends on Xcode version behaviour (synchronized groups) |
| Adding a file while he is on the Mac | never his job | needs Xcode, or `project.pbxproj` surgery |
| Reviewable in a diff | yes — `project.yml` is text | `.xcodeproj` is a large generated blob |
| Extra tool | `brew install xcodegen` once | none |
| Risk | XcodeGen's development pace has slowed (stable, community-maintained) — acceptable, its input format barely changes | `.xcodeproj` corruption from hand-editing |

⚠ **The `.xcodeproj` files are generated, so they are git-ignored and never edited by hand.** If a project
setting is wrong, the fix is in `project.yml` and one regenerate — not in Xcode's UI, where the change would be
lost on the next generate. This is the one habit that makes the whole arrangement work.

## 3. The loop, per round

**I run (Windows):**

```bash
cd /workspace/projects/rkm-cinema
git fetch origin                          # never trust origin/* without this
git pull --ff-only                        # pick up anything he pushed back
#   ... write the Swift / project.yml ...
git add -A && git commit -m "..."
bash .git/push_branch.sh feat/apple-clients
```

**He runs (Mac) — ONE command:**

```bash
cd ~/dev/rkm-cinema && ./apple/scripts/mac-round.sh ios      # or: tvos
```

That script pulls, regenerates the project, builds, and drops a plain-text build log into `apple/logs/`.
⚠ **It has not been run yet** — no Xcode on the Windows side, so it is written-but-unverified; expect one round
of fixing its flags on the first real use.

Then it is Xcode for run/install/screenshot, plus `log stream` per `LOGGING.md` §7.

## 4. The rules that keep the loop honest

1. **One writer at a time.** I write code; he tests. He must not edit sources in Xcode — a fix that only exists
   on the Mac is a fix that gets overwritten by the next pull.
2. **Pull before starting, push before handing back** — including any `project.yml` change.
3. **I fetch before trusting a ref.** A token-URL push does not update local `origin/*`.
4. **Nothing is generated in the GUI.** Project settings live in `project.yml`; `.xcodeproj` is build output.
5. **Testing evidence comes back as text I can read**: the build log, the `log stream` tail, and screenshots
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
