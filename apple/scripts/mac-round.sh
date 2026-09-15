#!/usr/bin/env bash
# The Mac side of the loop — ONE command per round of testing.
#
#   ./apple/scripts/mac-round.sh ios        # pull · (generate) · build iOS
#   ./apple/scripts/mac-round.sh tvos       # pull · (generate) · build tvOS
#   ./apple/scripts/mac-round.sh ios --sim  # ...then install+launch on a simulator
#
# ⚠ ANY FURTHER ARGUMENTS ARE PASSED TO THE APP AT LAUNCH (simulator only), so a spike or a debug
# switch can be turned on for one round without editing a scheme:
#
#   ./apple/scripts/mac-round.sh ios --sim -RKMOfflineSpike YES
#
# A DEVICE build is launched from Xcode instead, where the same switch is set as a scheme argument
# (Product → Scheme → Edit Scheme → Run → Arguments → *Arguments Passed On Launch*).
#
# Works with BOTH project arrangements (apple/WORKFLOW.md §2):
#   - hand-made project committed in the repo (the default) → no generation step
#   - XcodeGen                                            → generation runs if project.yml exists
#
# ⚠ WRITTEN BUT NOT RUN — there is no Xcode on the Windows side, so nothing here is
# verified. Expect to correct a flag on first use. It is deliberately plain: it prints
# a SHORT summary (the errors, then the tail) because the full xcodebuild log is huge and
# is saved to apple/logs/ instead. Paste the summary back.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

TARGET="${1:-}"
WANT_SIM="${2:-}"

# ⚠ Shift by hand rather than `shift 2`: with fewer than two arguments that FAILS under `set -e`, and
# an empty array expansion (`"${EXTRA[@]}"`) is an error in bash 3.2 — which is what /bin/bash is on
# macOS. So the count is carried explicitly and the expansion is always guarded.
EXTRA=()
if [ $# -gt 2 ]; then
  shift 2
  EXTRA=("$@")
fi

case "$TARGET" in
  ios)  PROJ="apple/ios/RKMCinema.xcodeproj";    SCHEME="RKMCinema";    PLATFORM="iOS";     SIM_DEVICE="iPhone 16";  PRODUCT_SUFFIX="iphonesimulator" ; BUNDLE_SUFFIX="ios" ;;
  tvos) PROJ="apple/tvos/RKMCinemaTV.xcodeproj"; SCHEME="RKMCinemaTV";  PLATFORM="tvOS";    SIM_DEVICE="Apple TV";   PRODUCT_SUFFIX="appletvsimulator" ; BUNDLE_SUFFIX="tvos" ;;
  *) echo "usage: $0 ios|tvos [--sim] [app arguments…]" >&2; exit 2 ;;
esac

SPEC_DIR="$(dirname "$PROJ")"
say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- 1. pull
say "1. pulling"
git fetch origin
git pull --ff-only
echo "HEAD: $(git log --oneline -1)"

# ---------------------------------------------------------------- 2. generate (only if XcodeGen is in use)
say "2. project"
if [ -f "${SPEC_DIR}/project.yml" ]; then
  if ! command -v xcodegen >/dev/null 2>&1; then
    echo "project.yml found but xcodegen is missing. Install it once:  brew install xcodegen" >&2
    exit 1
  fi
  ( cd "$SPEC_DIR" && xcodegen generate )
  echo "regenerated from project.yml: $PROJ"
else
  echo "using the committed project (no project.yml — see apple/WORKFLOW.md §2)"
fi

if [ ! -d "$PROJ" ]; then
  echo "Project not found: $PROJ" >&2
  echo "It is created once in Xcode and committed — see apple/WORKFLOW.md §2 for the steps." >&2
  exit 1
fi

# ⚠ Pre-flight, because this is the most common first-run failure and it reads like a code error.
# `xcodebuild` lives INSIDE Xcode, and installing Xcode does not move this pointer — anything that
# once ran `xcode-select --install` (Homebrew, a git prompt) leaves it on the Command Line Tools,
# and every build then dies with "requires Xcode, but active developer directory … is a command
# line tools instance". Fail fast with the fix rather than wasting a build on it.
DEV_DIR="$(xcode-select -p 2>/dev/null || true)"
case "$DEV_DIR" in
  */Xcode*.app/Contents/Developer) ;;
  *)
    echo "xcodebuild is not pointed at Xcode." >&2
    echo "  active developer directory: ${DEV_DIR:-<none>}" >&2
    echo "  fix:  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer" >&2
    echo "  then: sudo xcodebuild -license accept   # if it complains about the licence" >&2
    exit 1
    ;;
esac

# ---------------------------------------------------------------- 3. build
mkdir -p apple/logs
STAMP="$(date +%Y%m%d-%H%M%S)"
BUILD_LOG="apple/logs/build-${TARGET}-${STAMP}.log"

if [ "$WANT_SIM" = "--sim" ]; then
  # ⚠ A destination that names a device this Xcode does not have fails the BUILD, not just the
  # install+launch step, and the error says nothing about simulators.
  #
  # ⚠⚠ **THE DEVICE THAT RUNS IS THE ONE HE IS LOOKING AT, SO A BOOTED ONE WINS.** The committed
  # default is `iPhone 16` and his Mac has `iPhone 17` *and* `iPhone 17 Pro`, so this fell through to
  # "the first available iPhone" — and a build+install+launch on a DIFFERENT simulator than the one on
  # screen reads exactly like "the spike is broken": on 2026-09-16 it booted `iPhone 17`, while the app
  # — and the stored server address the probe file is downloaded from — were on `iPhone 17 Pro`. The
  # spike would have said `no stored server address` and the round would have been wasted.
  #
  # Order: an **already booted** device of the right family → the committed default if it exists →
  # the first available one. ⚠ `simctl list devices booted` needs no boot, so this is also the only
  # branch that can be sure the name exists on this Mac.
  SIM_FAMILY="iPhone"
  if [ "$TARGET" = "tvos" ]; then SIM_FAMILY="Apple TV"; fi
  SIM_MATCH=""
  # ⚠ `|| true` on purpose: `set -o pipefail` + `set -e` means a `grep` that matches nothing would
  # END THE SCRIPT here (silently, before the "no simulator available" branch below can speak). With
  # an empty result the assignment is simply empty and the next branch decides.
  BOOTED_MATCH="$(xcrun simctl list devices booted 2>/dev/null | grep -E "$SIM_FAMILY" | head -1 | sed -E 's/^[[:space:]]+//; s/ \(.*//' || true)"
  if [ -n "$BOOTED_MATCH" ]; then
    SIM_MATCH="$BOOTED_MATCH"
    echo "note: using the simulator that is ALREADY BOOTED — '${SIM_MATCH}'."
    echo "      (That is the one on screen; shut it down to let this script choose instead.)"
  elif xcrun simctl list devices available 2>/dev/null | grep -q "$SIM_DEVICE"; then
    SIM_MATCH="$SIM_DEVICE"
  else
    # ⚠ Fall back to the first AVAILABLE iPhone rather than giving up: "the build succeeded but
    # nothing launched" is indistinguishable from "the change does not work", and that is exactly how
    # a stale simulator list would read (the committed default is iPhone 16; his Mac has 17 Pro).
    SIM_MATCH="$(xcrun simctl list devices available 2>/dev/null | grep -E "$SIM_FAMILY" | head -1 | sed -E 's/^[[:space:]]+//; s/ \(.*//' || true)"
    echo "note: no simulator named '$SIM_DEVICE' — using '${SIM_MATCH:-none}' instead."
  fi
  if [ -n "$SIM_MATCH" ]; then
    DEST="platform=${PLATFORM} Simulator,name=${SIM_MATCH}"
  else
    echo "note: no iPhone-class simulator available — building for any iOS Simulator, and the"
    echo "      install+launch step will be skipped. Xcode > Window > Devices to add one."
    DEST="generic/platform=${PLATFORM} Simulator"
  fi
else
  # ⚠ A DEVICE build is SIGNED. It needs a team set in Xcode > Signing & Capabilities, and
  # the profile for the bundle id has to be creatable — which is what -allowProvisioningUpdates
  # below grants. Without it the build dies with "No profiles for '…' were found", which looks
  # like a code error and is not.
  DEST="generic/platform=${PLATFORM}"
fi

say "3. building ($DEST)"
echo "   full log: $BUILD_LOG"
set +e
xcodebuild -project "$PROJ" -scheme "$SCHEME" -destination "$DEST" -allowProvisioningUpdates build >"$BUILD_LOG" 2>&1
RC=$?
set -e

# ---------------------------------------------------------------- 4. summary
say "4. result"
if [ $RC -eq 0 ]; then
  echo "BUILD SUCCEEDED"
else
  echo "BUILD FAILED (exit $RC) — the errors:"
  grep -E "(error|warning): " "$BUILD_LOG" | sort -u | head -40 || true
  # A fresh Xcode refuses CLI builds until the licence is accepted — a confusing
  # failure the first time, so name it explicitly.
  if grep -qi "agree to the Xcode license\|license agreement" "$BUILD_LOG"; then
    echo
    echo "This is the Xcode licence, not a code error. Fix:  sudo xcodebuild -license accept" >&2
  fi
  # ⚠ Same idea for signing: it reads like a code failure and is not, and the fix depends on
  # whether he wants a simulator run (no signing at all) or a device build (needs a team).
  if grep -qi "no profiles for\|requires a development team\|provisioning profile" "$BUILD_LOG"; then
    echo
    echo "This is a SIGNING failure, not a code error." >&2
    echo "  - Simulator builds need no signing:   ./apple/scripts/mac-round.sh ${TARGET} --sim" >&2
    echo "  - For a device build: Xcode > Signing & Capabilities > set your Team, then run again." >&2
    echo "  - This script passes -allowProvisioningUpdates, so Xcode can create the profile itself." >&2
  fi
fi

echo
echo "--- last 25 lines of $BUILD_LOG ---"
tail -25 "$BUILD_LOG"

# ---------------------------------------------------------------- 5. optional run
if [ $RC -eq 0 ] && [ "$WANT_SIM" = "--sim" ]; then
  say "5. installing + launching on ${SIM_MATCH:-the simulator}"
  # ⚠ The name is anchored (`^ *NAME (`), not a bare substring: `iPhone 17` is a PREFIX of
  # `iPhone 17 Pro`, so the old `grep -m1` could hand back the other device's UDID and install
  # there — the same "which device did it actually run on?" fault, one line later.
  DEV_ID="$(xcrun simctl list devices available | grep -m1 -E "^[[:space:]]*${SIM_MATCH} \(" | grep -oE '[0-9A-F-]{36}' || true)"
  if [ -z "$DEV_ID" ]; then
    echo "No available simulator matching '${SIM_MATCH:-$SIM_DEVICE}' — open Xcode > Window > Devices and add one." >&2
  else
    echo "device: $DEV_ID"
    xcrun simctl boot "$DEV_ID" 2>/dev/null || true
    # ⚠ WAIT FOR IT TO BE USABLE. `simctl boot` returns before the device is ready, and an install or
    # launch that races a half-booted simulator fails in ways that read like a broken app.
    # `bootstatus -b` boots it if needed and blocks until it is up (a no-op when it already is).
    xcrun simctl bootstatus "$DEV_ID" -b >/dev/null 2>&1 || true
    open -a Simulator

    # ⚠⚠ **THIS STEP HAD NEVER WORKED, AND IT IS WHY THE SPIKE ONLY EVER RAN FROM XCODE.** It looked
    # for `*iOS*` in the DerivedData path — and a simulator build lands in
    # `…/Build/Products/Debug-iphonesimulator/`, which contains no "iOS" at all. So every round printed
    # "Built .app not found in DerivedData" (his 2026-09-14 terminal, verbatim) and the install+launch
    # fell to him, by hand, in Xcode. It now asks Xcode where the product is — authoritative, and it
    # survives a moved or renamed DerivedData — with a correctly-spelled DerivedData glob as fallback,
    # newest first, printing the app's DATE so a stale pick is visible rather than silent.
    APP=""
    SETTINGS="$(xcodebuild -project "$PROJ" -scheme "$SCHEME" -destination "$DEST" -showBuildSettings 2>/dev/null || true)"
    APP_DIR="$(printf '%s\n' "$SETTINGS" | awk -F' = ' '/^ *BUILT_PRODUCTS_DIR = /{print $2; exit}')"
    APP_NAME="$(printf '%s\n' "$SETTINGS" | awk -F' = ' '/^ *FULL_PRODUCT_NAME = /{print $2; exit}')"
    if [ -n "$APP_DIR" ] && [ -n "$APP_NAME" ] && [ -d "${APP_DIR}/${APP_NAME}" ]; then
      APP="${APP_DIR}/${APP_NAME}"
      echo "app: $APP   (from xcodebuild -showBuildSettings)"
    else
      APP="$(ls -dt ~/Library/Developer/Xcode/DerivedData/*/Build/Products/Debug-${PRODUCT_SUFFIX}/"${SCHEME}.app" 2>/dev/null | head -1)"
      if [ -n "$APP" ]; then
        echo "app: $APP   (from DerivedData; built $(date -r "$APP" '+%Y-%m-%d %H:%M:%S'))"
      fi
    fi
    if [ -n "$APP" ]; then
      xcrun simctl install "$DEV_ID" "$APP"
      # ⚠ The pass-through, and what it is for: a spike or a debug switch is enabled for ONE round
      # (`-RKMOfflineSpike YES`) instead of being committed into a scheme. Printed so the log says
      # which arguments the run actually had.
      if [ ${#EXTRA[@]} -gt 0 ]; then
        echo "launching with: ${EXTRA[*]}"
        xcrun simctl launch --console-pty "$DEV_ID" "com.helloraj1986.rkmcinema.${BUNDLE_SUFFIX}" "${EXTRA[@]}"
      else
        xcrun simctl launch --console-pty "$DEV_ID" "com.helloraj1986.rkmcinema.${BUNDLE_SUFFIX}"
      fi
    else
      echo "Built .app not found in DerivedData — open the project in Xcode and run it there." >&2
    fi
  fi
fi

echo
echo "Paste this summary back (and the log tail for the failing correlation id, per apple/LOGGING.md §7)."
exit $RC
