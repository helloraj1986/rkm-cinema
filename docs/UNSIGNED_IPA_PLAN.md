# Unsigned IPA — a Mac build step that needs no Apple ID, and a Windows install step

> **Status:** PLAN — nothing built. Written 2026-09-25 against `apple/ios` @ `feat/tvos-player` (`694c51b`).
> **Author's machine:** this sandbox (Linux, no Xcode). Every claim below about Xcode behaviour is from
> `apple-platform-clients` §7/§7g and this repo's own history, **not** from a run — see §7 for exactly
> what is and is not verified, and §8 for the one question that blocks Phase 1.

**Goal:** one command on the Mac produces a **device-architecture, UNSIGNED** `RKMCinema.ipa` — no Apple ID,
no team, no provisioning profile — and that file is then signed and installed *from Windows* with
Sideloadly. The Mac is needed only when the Swift code changes; renewal happens on RKM-HP.

**Why this is worth doing:** today, getting the app onto the iPad is `⌘R` from Xcode on the Mac with the
cable attached. That is fine for development and bad for everything else — the laptop must be open, awake
and cabled, and a lapsed profile means going back to it. This splits **build** (Mac, rare, scripted) from
**install/renew** (Windows, one click, any time).

---

## 0. Say this first: what an "unsigned IPA" actually is

⚠ **An unsigned IPA cannot be installed on any device.** iOS validates code signatures at install; there is
no configuration, no profile and no jailbreak-free trick that installs unsigned code. So the file is **not an
installable artifact** — it is an **input to a signer**.

That reframes the whole exercise honestly:

| | Signed IPA (the usual thing) | **Unsigned IPA (this plan)** |
|---|---|---|
| Apple ID needed to *build* | yes — team + profile on the Mac | **no** |
| Apple ID needed to *install* | yes, already baked in at build | yes — consumed by the signer on Windows |
| 7-day clock on a free account | 7 days | **the same 7 days** |
| How it renews | rebuild on the Mac | **re-sign on Windows** — no Mac, no cable |
| Sideloader slots used (free = 3) | — | **0** with Sideloadly |

⚠ **Do not sell this as `install it whenever I want`.** Per `apple-platform-clients` §7g(b), the provisioning
profile travels inside the app and a free-account signature is 7 days whatever form the file takes. The
expensive and genuinely new thing here is **which machine you need when it expires** — Windows, not the Mac.

**And the second honest caveat:** this app is a `WKWebView` shell (`apple/ios/README.md`). The IPA stores no
content. What you gain is an **icon on the home screen that is not Safari**, without Xcode in the loop. If
the Safari/PWA route already satisfies you, this is an evening for aesthetics.

---

## 1. What I found looking through the repo

Read-only audit, 2026-09-25. Everything here is a fact about the committed tree, not a guess.

| Check | Command | Result | Why it matters |
|---|---|---|---|
| Restricted entitlements | `grep -rn "com.apple.developer" apple/` | **nothing found; no `.entitlements` file anywhere** | ✅ **The decisive one.** Push, App Groups, iCloud and HealthKit are unavailable to a free account, so a re-sign of an app that uses them fails. This app has none — it is a plain WebView shell, so it re-signs cleanly. |
| Bundle id | `grep PRODUCT_BUNDLE_IDENTIFIER` | `com.helloraj1986.rkmcinema.ios` | Fixed identity — see §3.4. Read it from the project, never hardcode it (`apple-platform-clients` §7e rule 11). |
| Team | `grep DEVELOPMENT_TEAM` | `J65A2F5SQM`, `CODE_SIGN_STYLE = Automatic` | A team is already committed. Irrelevant to an unsigned build — which is the point. |
| Deployment floor | `grep IPHONEOS_DEPLOYMENT_TARGET` | `16.4`, set in **both** the PROJECT and TARGET sections | Already correct (the template's 26.5 trap was fixed). 16.4 installs on any iPad on 16.4+; a low floor is a one-way bet. |
| Synchronized groups | `grep -c PBXFileSystemSynchronizedRootGroup` | `3` | ✅ A file's *presence in the folder* is its target membership. Adding sources needs no project edit. |
| Shared scheme | `find …xcodeproj -type f` | `xcshareddata/xcschemes/RKMCinema.xcscheme` **on disk** | ✅ `xcodebuild -scheme RKMCinema` can resolve. (A scheme shown as "Shared" in the GUI but absent from disk is the classic CLI miss — §7f.3.) |
| Local package linked | `grep packageProductDependencies` | `RKMServerKit` present | ✅ The `Missing package product` failure would be Xcode's per-machine SwiftPM state, not the repo — see the pre-flight in §4. |
| `Info.plist` location | build setting vs tree | `INFOPLIST_FILE[sdk=*] = Config/Info.plist`, **outside** `RKMCinema/` | ✅ The `Multiple commands produce` trap is already avoided. |
| `DEVELOPMENT_ASSET_PATHS` | `grep` in pbxproj | not set | Fine — `Preview Content/` exists but nothing requires it. |
| Debug-only code | `grep -rn "#if DEBUG" apple/ios` | `DebugHUD`, `OfflineDebugPanel`, `OfflineServerProbe`, `OfflineBridge`, `WebShellModel`, `AppLog` | ⚠ **This decides the configuration** — §3.1. |
| Existing IPA tooling | `grep -rn -iE "\.ipa\|exportArchive\|xcarchive\|sideload"` | **nothing** | Nothing to build on; `ExportOptions.plist` does not exist. |
| Round script | `apple/scripts/mac-round.sh` | builds only — no archive, no export, no packaging. ⚠ **Updated 2026-09-25**: it gained an `ipa` verb that `exec`s `build-ipa.sh`, so the Mac keeps ONE command (`mac-round.sh ios\|tvos\|ipa`) and the recipe stays in one file. The verb is placed *before* its own `git pull`, so it is a forwarder, not a round (§4.9). |
| gitignore | `.gitignore` | already covers `build/`, `dist/`, `*.log` | But the IPA still goes **outside** the repo — §4.7. |

**The three findings that shape the plan:** no entitlements (so a re-sign is safe), a free account is
therefore the likely ceiling (so the signer must be free-account-aware), and `#if DEBUG` gates the entire
diagnostic surface (so *which configuration you export is a real decision, not a default*).

---

## 2. The mechanism, in one paragraph

`xcodebuild` with `CODE_SIGNING_ALLOWED=NO` compiles for a **device** destination and skips the signing
phase entirely, leaving an unsigned `.app` in `…/Build/Products/Debug-iphoneos/`. Zip that into
`Payload/<Name>.app` and you have an IPA. This uses no Apple ID, no team and no `-allowProvisioningUpdates`,
and it cannot fail on a missing profile because it never asks for one. Sideloadly then takes the IPA, creates
a certificate and profile from **your** Apple ID via Apple's own services, re-signs, and installs.

⚠ **Two silent ways this goes wrong, both of which produce a file that looks fine:**
1. **A simulator build.** `-destination 'generic/platform=iOS Simulator'` also yields an arm64 binary, but
   its `LC_BUILD_VERSION` platform is *iOS Simulator* (7), not *iOS* (2). The IPA packs, signs and then
   refuses to install — with nothing in the error naming the real cause. §4.5 asserts the platform number.
2. **A stale signed `.app` in a reused `DerivedData`.** Copy the wrong one and the "unsigned" IPA carries a
   signature. §4.4 reads the product path from `-showBuildSettings` and §4.6 would catch it.

---

## 3. Decisions, with the reason each one is not the other option

### 3.1 Configuration: **Debug**, not Release — for now
`#if DEBUG` in this repo is not incidental: it wraps `OfflineDebugPanel`, `OfflineServerProbe`, the
`DebugHUD` block and `AppLog.debugBuild` (the launch banner that prints the resolved ATS values). A
**Release** IPA publishes a build with **no on-device diagnostics at all** — and a sideloaded app is
*exactly* where you cannot attach Safari or read Xcode's console. That is a bad trade for an app whose whole
performance question is whether a WebView paints.

✅ **Decision: the first IPA is `Debug-iphoneos`.** A Release IPA is a follow-up once the install path is
proven — and it is a one-word change (`-configuration Release`), so nothing is foreclosed.

⚠ Note the state it launches in: since 2026-09-19 a Debug build **ignores the stored HUD setting and starts
clean** (`AppLog.hudStartsVisible`). Routes in are `-RKMDebugHUD YES`, the window-level corner gesture, or a
shake. So a Debug IPA is safe to hand to the household — nothing opens over the UI.

### 3.2 Unsigned, not signed
The signed route (`-exportArchive` with `method=debugging`, `apple-platform-clients`
`references/ipa-and-device-install.md` §2) works on a free team — but it needs `-allowProvisioningUpdates`
and produces **the same 7-day install**. Signing on the Mac therefore buys nothing that signing on Windows
does not, and it re-couples renewal to the laptop. Unsigned is the smaller, more portable artifact.

✅ **Confirmed 2026-09-25: the team is a FREE personal team.** So this is not merely the tidy choice, it is
the *only* useful one: the paid-only routes (Ad Hoc up to a year, TestFlight 90 days) are unavailable, and the
7-day clock applies to every form the file takes. Signing on the Mac would add a team dependency, a
`-allowProvisioningUpdates` requirement and a profile that expires in a week, to produce a file with the same
expiry as the unsigned one. Unsigned + re-sign on Windows is the design.

### 3.3 Sign on Windows with Sideloadly
| Option | Why not |
|---|---|
| **Sideloadly** ✅ | Runs on **Windows** (RKM-HP), uses **none** of the free account's 3 app slots, and its daemon auto-refreshes apps near expiry whenever the device is next seen. |
| AltStore | Needs AltServer running on the same Wi-Fi; occupies 1 of 3 slots with itself. |
| SideStore | Setup requires a computer anyway; occupies a slot. |
| `xcrun devicectl` | Needs a paired device and a **Mac** — defeats the purpose. |
| OTA `itms-services` | Requires **Ad Hoc**, i.e. a paid account. |
| TrollStore-style permanent install | Version-gated on an unpatched CoreTrust bug; not an option on a current iOS. |

⚠⚠ **Sideloadly asks for your Apple ID password.** Use a **dedicated Apple ID** for sideloading, not the
primary one, and never a "free signing service" that wants the credential *and* the IPA.

### 3.4 Keep the bundle id fixed at `com.helloraj1986.rkmcinema.ios`
Changing it per build creates a **new App ID** (free accounts get 10 per 7 days) and a **new app container** —
so the stored server address is lost and the app opens on the setup screen. One identity, always.

### 3.5 tvOS is out of scope, deliberately
A **portless Apple TV can only be sideloaded from macOS**, so the Windows step does not exist for it. The
tvOS route stays `xcodebuild` + `xcrun devicectl` over Wi-Fi (`references/ipa-and-device-install.md` §4),
which needs a Mac anyway. **This plan is iOS/iPadOS only.**

---

## 4. What gets built: `apple/scripts/build-ipa.sh`

One new script, one command, no arguments required.

```bash
./apple/scripts/build-ipa.sh          # → ~/dev/rkm-cinema-dist/RKMCinema-unsigned.ipa
```

Each numbered step exists because of a specific way this has already gone wrong in this project.

**4.1 Pre-flight `xcode-select`** — reuse `mac-round.sh`'s existing check verbatim (it is already right):
`xcode-select -p` must end in `/Xcode*.app/Contents/Developer`, else fail with the `sudo xcode-select -s …`
fix. Otherwise the build dies on "requires Xcode, but active developer directory is a command line tools
instance" — which reads like a code error.

**4.2 Pre-flight the local package** — `xcodebuild -resolvePackageDependencies -project apple/ios/RKMCinema.xcodeproj`.
This is the falsifier from `apple-platform-clients` §7g(a): if it resolves, a later `Missing package product
'RKMServerKit'` is Xcode's gitignored per-machine SwiftPM state and the fix is *Reset Package Caches*; if it
fails, it is a real problem. Running it up front is what stops an IPA round being burned on a diagnosis.

**4.3 Build, unsigned, to a dedicated DerivedData**

```bash
xcodebuild -project apple/ios/RKMCinema.xcodeproj \
           -scheme RKMCinema \
           -configuration Debug \
           -destination 'generic/platform=iOS' \
           -derivedDataPath /tmp/rkm-ipa-build \
           CODE_SIGNING_ALLOWED=NO \
           CODE_SIGNING_REQUIRED=NO \
           CODE_SIGN_IDENTITY="" \
           CODE_SIGN_ENTITLEMENTS="" \
           build
```

⚠ The dedicated `-derivedDataPath` is not tidiness — it stops §2's second failure (a signed `.app` from an
earlier Xcode run sitting in the shared DerivedData).

**4.4 Locate the product by asking Xcode, never by globbing**

```bash
SETTINGS="$(xcodebuild … -showBuildSettings)"
BUILT_PRODUCTS_DIR=…   # parsed from $SETTINGS
FULL_PRODUCT_NAME=…    # parsed from $SETTINGS
APP="$BUILT_PRODUCTS_DIR/$FULL_PRODUCT_NAME"
```

`mac-round.sh` paid for this lesson already (§7e rule 3): the old code filtered a DerivedData path for
`*iOS*`, but the product directory is `Debug-iphonesimulator` — no `"iOS"` in it, so the lookup matched
nothing and install+launch silently never happened. Print the `.app`'s date too, so a stale pick is visible.

**4.5 Assert it is a DEVICE binary, not a simulator binary** — the check §2 says nothing else covers:

```bash
PLATFORM="$(otool -l "$APP/$EXECUTABLE" | awk '/LC_BUILD_VERSION/{f=1} f&&/platform/{print $2; exit}')"
# 2 = iOS device   ✅     7 = iOS Simulator   ✗ fail loudly
```

⚠ Also confirm `file "$APP/$EXECUTABLE"` reports `arm64` (not `x86_64`), and that the arm64 slice is not an
`arm64e`-only simulator oddity.

**4.6 Assert it is genuinely unsigned** — the claim the whole plan rests on, so it gets a gate, not a comment:

```bash
codesign -dv "$APP" 2>&1 | grep -q "not signed at all"   # else fail
```

⚠⚠ **AS BUILT, THIS ASSERTION IS WIDER, AND THE NARROW VERSION WAS A BUG.** On Apple Silicon the *linker*
ad-hoc signs arm64 binaries automatically, so a build that made no signing decision at all can still come
back with a signature — and **ad-hoc signing also creates `_CodeSignature/`**, which makes that directory
useless as a test too. The gate therefore rejects a **signing identity** (`Authority=` / `TeamIdentifier=`)
rather than the absence of any signature, and treats `not signed at all` and `Signature=adhoc` as both
acceptable (an ad-hoc signature carries no identity and Sideloadly replaces it regardless).

⚠ Note which way that errs: a wrong guess lets an ad-hoc app through — harmless, it is re-signed anyway —
instead of blocking a perfectly good build with a confusing message. The ad-hoc branch is **reasoned from
the platform, not observed on a Mac**; the harness pins all three outcomes so the *script's* behaviour is
tested even though the *platform's* is not.

**4.7 Package and hand over**

```bash
DIST="$HOME/dev/rkm-cinema-dist/RKMCinema-unsigned.ipa"
rm -rf "$DIST"; mkdir -p "$(dirname "$DIST")" /tmp/rkm-ipa/Payload
cp -R "$APP" /tmp/rkm-ipa/Payload/
( cd /tmp/rkm-ipa && zip -qry "$DIST" Payload )
unzip -l "$DIST" | grep -c mobileprovision   # must be 0
shasum -a 256 "$DIST"
```

⚠ **The IPA goes outside the repo** — `~/dev/rkm-cinema-dist/`, not `apple/`. It is a build artifact, and
the workspace policy has no place for binaries. (`.gitignore` covers `build/`/`dist/` anyway; this keeps it
unambiguous.)

**4.8 Print a short summary** — the IPA path, its size, its sha256, the bundle id, the deployment floor, the
configuration, and the platform/unsigned assertions. One paste-able block; errors first if it failed. Same
shape as `mac-round.sh`'s §4, for the same reason: the full `xcodebuild` log goes to `apple/logs/`, and what
comes back to chat is the summary.

⚠ `set -euo pipefail` + a `grep` that matches nothing **ends the script silently** — every `grep` in a
pipeline gets `|| true` and an explicit branch, exactly as `mac-round.sh` documents (§7e rule 5).

**4.9 The verb, and which machine gets it** — decided 2026-09-25, his choice from three options.

`mac-round.sh` gains a third verb, and it is a **forwarder**:

```bash
./apple/scripts/mac-round.sh ipa              # Debug  → ~/dev/rkm-cinema-dist/RKMCinema-unsigned.ipa
./apple/scripts/mac-round.sh ipa --release
```

- ⚠ **Placed before its own `git pull`, and it `exec`s** — so no `git fetch`/`pull`, no project generation,
  no build, no simulator, no device selection, and nothing of the round can run after the hand-off. A change
  to the recipe is still a change in **one file** (`build-ipa.sh`).
- ⚠ **It is NOT a verb in `rkm-cinema.ps1`, and that is not an oversight.** `rkm-cinema.ps1` is PowerShell 5.1
  on **Windows**, and `xcodebuild` exists only on **macOS** — the Windows CLI cannot build an IPA at all.
  `apple/WORKFLOW.md` states the boundary the repo already lives by: *"GitHub is the only bridge to the
  Mac"*, the Mac being testing-only. So the three candidate shapes were:

  | Option | Verdict |
  |---|---|
  | Mac-side verb on `mac-round.sh` | ✅ **chosen** — zero new infrastructure; the Mac already has exactly one command, and this adds to it rather than inventing a second |
  | `.\rkm-cinema.ps1 apple ipa` over **SSH** to the Mac, pulling the IPA back | ✗ for now — it is the best UX (one command, and the IPA lands next to Sideloadly), but it makes SSH a **second bridge** where GitHub is the only one. Worth revisiting if walking to the Mac becomes the annoyance |
  | An `apple` verb group in both CLIs, Windows refusing with the Mac command | ✗ — two surfaces to keep in sync for discoverability alone |

- ⚠ A verb on the Windows CLI that *silently* did nothing would be worse than no verb: it either does the job
  or it says plainly that the job belongs on the Mac. Recorded so it is not "fixed" later by adding a
  no-op that looks like a feature.
- ⚠ **tvOS is not in this verb.** A portless Apple TV can only be sideloaded from macOS, so its route stays
  `xcodebuild` + `xcrun devicectl` over Wi-Fi (§3.5) — an IPA step there would be packaging work with nowhere
  to go.

---

## 5. Phases

| Phase | What | Who runs it | Done when |
|---|---|---|---|
| **1a** | Write `apple/scripts/build-ipa.sh` | me (sandbox) | ✅ **DONE 2026-09-25** — `bash -n` clean, 8 numbered steps, every guard commented with the failure it prevents |
| **1b** | Write `apple/scripts/test-build-ipa.sh` — the stub harness | me (sandbox) | ✅ **DONE — 14 cases, 14 green, run for real** (§6.1) |
| **1c** | Prove the packaging + verification half against a synthetic `.app` | me (sandbox) | ✅ **DONE** — the `ditto` stub makes a genuine zip, so step 7's structure assertions ran against a real archive. Packer settled as **`ditto`** (§6.2) |
| **1d** | **Falsify** the harness — break each guard, require the matching case to go red | me (sandbox) | ✅ **DONE** — 3 guards disabled in 3 copies, each turning **exactly** its own case red (§6.1) |
| **1e** | **The verb** — `mac-round.sh ipa`, a forwarder, and its falsification | me (sandbox) | ✅ **DONE** — 2 more cases (M/N), and falsified twice: a forwarder that stops `exec`ing, and one placed *after* the round's `git pull` (§4.9, §6.1) |
| **2** | Run the script once on the Mac | **him** — one command | an `.ipa` exists; sha256 + summary pasted back |
| **3** | Sideload from RKM-HP | **him** | the app opens on the iPad from the IPA, not from Xcode |
| **4** | Docs: `apple/WORKFLOW.md` §3 + the command table, `apple/README.md`'s script list, and the record in `docs/PROGRESS.md` | me | ✅ **DONE (except PROGRESS.md, which is written once Phase 3 passes)** — the next session does not rediscover this |

⚠ **Phases 1a–1e are finished and were executed here.** Phase 2 needs Xcode; Phase 3 needs Windows and the
iPad. Neither is done and neither will be described as done. What that means concretely: **the script has
never run against a real `xcodebuild`.** Everything Xcode-side is argued from the project's own history and
the `apple-platform-clients` skill — the harness proves the *script's* logic, the *archive's* structure and
the *hand-off*, and proves nothing about Xcode's behaviour.

---

## 6. Verification — and what can honestly be checked from here

### 6.1 The stub harness (how a Mac-only script is tested on Linux)
`apple/scripts/test-mac-round.sh` already established the pattern and it is the reason that script works at
all: stub `xcrun`/`xcodebuild`/`git` on `PATH`, feed realistic fixtures, and **assert on the stubs' call
log** rather than on the script's stdout. `references/round-script-stub-testing.md` carries the traps
(PATH shadowing, `set -e` + `pipefail`, fixtures easier than reality).

The new harness needs these cases, each of which is a bug this plan exists to prevent:

| # | Fixture | Expects | Result |
|---|---|---|---|
| **A** | happy path | exit 0, IPA produced, call log shows `-destination generic/platform=iOS`, `CODE_SIGNING_ALLOWED=NO`, the dedicated DerivedData, and **no** `-allowProvisioningUpdates` | ✅ |
| **B** | `-showBuildSettings` returns a **simulator** products dir | fails loudly, **no IPA written** | ✅ |
| **C** | a **real signing identity** in `codesign` output | fails, no IPA | ✅ |
| **D** | `xcode-select -p` → Command Line Tools | fails with the `xcode-select -s` fix, **before any build** | ✅ |
| **E** | `-resolvePackageDependencies` fails | fails there, naming the package | ✅ |
| **F** | `xcodebuild` exits 1 | prints the `error:` lines, announces the failure, no IPA | ✅ |
| **G** | `otool` reports `platform 7` while the products dir looks like a device build | fails, naming the simulator binary — ⚠ this is the case that proves the platform check is not redundant with the directory check | ✅ |
| **H** | project directory absent | fails naming `WORKFLOW.md`, no build attempted | ✅ |
| **I** | `otool` gives **no output** | fails — ⚠ an unreadable live check is a failure, not an assumed pass | ✅ |
| **J** | `file` reports `x86_64` | fails on architecture | ✅ |
| **K** | `codesign` reports **`Signature=adhoc`** | **exit 0** — ⚠ the false-positive guard: an Apple-Silicon ad-hoc signature must not block a good build | ✅ |
| **L** | `codesign` output the script does not recognise | fails — refuses to guess on the property the artefact is named after | ✅ |
| **M** | `mac-round.sh ipa` (the forwarder) | exit 0, IPA produced, the call log shows `CODE_SIGNING_ALLOWED=NO` **and no `git` at all** — i.e. the hand-off happened *before* the round's pull | ✅ |
| **N** | `mac-round.sh ipa --release` | exit 0, and `-configuration Release` survived the forward | ✅ |

**Run 2026-09-25: `14 passed, 0 failed`, exit 0.**

⚠ **Falsified, and the first attempt at falsifying was itself wrong — which is the point.** Disabling all
three guards at once turned only **A** and **G** red: breaking the `platform 2` accept-case made B and C die
at step 5c *before they could reach their own guard*, so two disabled checks looked like working ones. A
cascade is not a detection. Redone one guard at a time, on three fresh copies of the final script:

| Disabled guard | Cases that went red |
|---|---|
| products-dir simulator check | **B** — and only B |
| real-identity rejection | **C** — and only C |
| `LC_BUILD_VERSION platform 7` | **G** — and only G |
| the forwarder's `exec` (it prints and returns) | **M, N** |
| the forwarder's *placement* (a `git fetch` inserted above it) | **M, N** |

Each guard now has a case that fails without it — which is what makes the other green results mean something.
⚠ M and N both go red for either forwarder fault, deliberately: they are the two faces of one hand-off
(does it reach `build-ipa.sh`, and do the arguments survive), and neither is meaningful alone.

⚠ **Also found: a temp directory that cannot `exec` makes every stub fail.** This sandbox's `/tmp` is a tmpfs
mounted `noexec`, so all stubs died with `Permission denied` (rc 126) — which reads as a broken harness
rather than a filesystem property. The harness now probes for an exec-capable temp dir and falls back to
`.rkm-ipa-harness/` beside it (gitignored), printing the substitution.

### 6.2 The half that was verified for real, in this sandbox
The packaging and structure checks are **not** Xcode-dependent, so they were run for real rather than stubbed:
the `ditto` stub produces a **genuine zip** with python's `zipfile`, and step 7's assertions then run against
a real archive with the real `unzip` — `Payload/RKMCinema.app/` present, **0** `mobileprovision` entries,
**0** `_CodeSignature` entries, and a real sha256 through the real `shasum`. `grep`, `stat`, `unzip` and
`shasum` are deliberately **not** stubbed, which is what makes those four assertions evidence.

✅ **Packer settled: `ditto`.** `ditto -c -k --sequesterRsrc --keepParent` is macOS-native, preserves
symlinks and extended attributes (plain `zip` does not, and it matters for a `.app` bundle), and ships with
macOS so there is nothing to install. `zip` remains a fallback solely so the harness's code path is
exercised on Linux, where **neither `ditto` nor `zip` exists** — noted here because the container has `unzip`
and `file` but not `zip`, which is the kind of asymmetry that makes "it worked here" a false claim.

⚠ What this does **not** prove: that Xcode produces the app, that `ditto`'s archive is byte-identical to what
Sideloadly expects, or that Sideloadly signs and installs it. Those are Phases 2 and 3.

### 6.3 What only the device can prove
That Sideloadly accepts an unsigned IPA with no `LC_CODE_SIGNATURE` and installs a launchable app. This is
the standard flow and it is well attested — **but it is not proved by anything in this repo or this sandbox**,
so it is Phase 3's acceptance criterion, stated as an open risk in §7.

---

## 7. Risks and open questions

| | Risk | Mitigation |
|---|---|---|
| R1 | ~~Free vs paid Apple ID for team `J65A2F5SQM`~~ | ✅ **ANSWERED 2026-09-25 — free personal team.** §3.2 confirmed; this plan is the right design, not a fallback. |
| R2 | Sideloadly + unsigned-IPA acceptance is not verifiable from here | Phase 3; fallback is the **signed** export route (`method=debugging`, `-allowProvisioningUpdates`), which is a different script and a tested path in the skill |
| R3 | iPad on iOS 16+ needs **Developer Mode** enabled (Settings → Privacy & Security) and the developer profile trusted | ✅ **Developer Mode already on** (iPadOS 26.x, 2026-09-25). Remaining human step: trust the developer profile at Settings → General → VPN & Device Management on first install. Note an expired profile blocks *launch* while the icon stays — the symptom users report as "the app is broken" |
| R4 | ~~`codesign`/`zip` availability and flags differ Mac vs Linux~~ | ✅ **Resolved** — `ditto` chosen (macOS-native), and the codesign assertion rewritten to reject a *signing identity* rather than the literal string (§4.6), because Apple Silicon linker-signs ad-hoc. §6.2 |
| R5 | A Debug IPA is larger and slower than Release | Accepted deliberately (§3.1); `-configuration Release` is a one-word follow-up |
| R6 | Free-account limits: 3 apps per device, 10 App IDs per 7 days | §3.4 fixed bundle id keeps App IDs to one |
| R7 | Sideloadly wants the Apple ID password | Dedicated Apple ID; never put it anywhere near an agent or a "signing service" |

---

## 8. Open questions — the ones that change the plan, not just the logistics

**Q1 — ✅ ANSWERED 2026-09-25: free personal team.** Unsigned + Sideloadly is confirmed as the design (§3.2).
The paid-account alternative (Ad Hoc up to a year, TestFlight 90 days, no sideloader, no Apple ID password on
RKM-HP) is off the table unless you buy the membership — worth knowing it is the clean answer at ~AUD $149/yr
if the 7-day renewal ever becomes annoying enough to pay to be rid of.

**Q2 — ✅ ANSWERED 2026-09-25: iPadOS 26.x, Developer Mode already on.** No prerequisite work needed. The one
remaining human step, on the first install: trust the developer profile at Settings → General → VPN & Device
Management.

**Q3 — open, but I have made the call and you can overrule it:** Debug IPA (full diagnostics, bigger) or
Release (stripped, faster)? **The plan assumes Debug**, per §3.1 — the diagnostics are the only way to see
inside a sideloaded app. Say the word and it becomes `-configuration Release`, a one-word change.

---

## 9. Files

| Action | Path |
|---|---|
| Create | `apple/scripts/build-ipa.sh` — the one command |
| Create | `apple/scripts/test-build-ipa.sh` — the Linux stub harness (§6.1) |
| Create | `docs/UNSIGNED_IPA_PLAN.md` — this document |
| Modify | `apple/WORKFLOW.md` — one paragraph: the IPA step sits beside the round script |
| Modify | `apple/ios/README.md` — how to get it onto the iPad without Xcode |
| Modify | `docs/PROGRESS.md` — the record, once Phase 3 passes |
| **No change** | **any `.swift` file, `project.pbxproj`, `Info.plist`, or anything server-side** |

⚠ **Zero server changes.** The shell reads a runtime address; nothing about how it is packaged touches
`backend/` or the stack.
