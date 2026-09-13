#!/usr/bin/env bash
# The Mac side of the loop — ONE command per round of testing.
#
#   ./apple/scripts/mac-round.sh ios        # pull · generate · build iOS
#   ./apple/scripts/mac-round.sh tvos       # pull · generate · build tvOS
#   ./apple/scripts/mac-round.sh ios --sim  # ...then install+launch on a simulator
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

case "$TARGET" in
  ios)  PROJ="apple/ios/RKMCinema.xcodeproj";    SCHEME="RKMCinema";    PLATFORM="iOS";     SIM_DEVICE="iPhone 16" ;;
  tvos) PROJ="apple/tvos/RKMCinemaTV.xcodeproj"; SCHEME="RKMCinemaTV";  PLATFORM="tvOS";    SIM_DEVICE="Apple TV" ;;
  *) echo "usage: $0 ios|tvos [--sim]" >&2; exit 2 ;;
esac

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- 1. pull
say "1. pulling"
git fetch origin
git pull --ff-only
echo "HEAD: $(git log --oneline -1)"

# ---------------------------------------------------------------- 2. generate
say "2. generating the Xcode project from project.yml"
if ! command -v xcodegen >/dev/null 2>&1; then
  echo "xcodegen not found. Install it once:  brew install xcodegen" >&2
  exit 1
fi
SPEC_DIR="$(dirname "$PROJ")"
( cd "$SPEC_DIR" && xcodegen generate )
echo "generated: $PROJ"

# ---------------------------------------------------------------- 3. build
mkdir -p apple/logs
STAMP="$(date +%Y%m%d-%H%M%S)"
BUILD_LOG="apple/logs/build-${TARGET}-${STAMP}.log"

if [ "$WANT_SIM" = "--sim" ]; then
  DEST="platform=${PLATFORM} Simulator,name=${SIM_DEVICE}"
else
  DEST="generic/platform=${PLATFORM}"
fi

say "3. building ($DEST)"
say "   full log: $BUILD_LOG"
set +e
xcodebuild -project "$PROJ" -scheme "$SCHEME" -destination "$DEST" build >"$BUILD_LOG" 2>&1
RC=$?
set -e

# ---------------------------------------------------------------- 4. summary
say "4. result"
if [ $RC -eq 0 ]; then
  echo "BUILD SUCCEEDED"
else
  echo "BUILD FAILED (exit $RC) — the errors:"
  # The lines that matter, deduped: compiler errors and warnings-with-context.
  grep -E "(error|warning): " "$BUILD_LOG" | sort -u | head -40 || true
fi

echo
echo "--- last 25 lines of $BUILD_LOG ---"
tail -25 "$BUILD_LOG"

# ---------------------------------------------------------------- 5. optional run
if [ $RC -eq 0 ] && [ "$WANT_SIM" = "--sim" ]; then
  say "5. installing + launching on the simulator"
  # Boot the first available device matching the name, then install the built .app.
  DEV_ID="$(xcrun simctl list devices available | grep -m1 "$SIM_DEVICE" | grep -oE '[0-9A-F-]{36}' || true)"
  if [ -z "$DEV_ID" ]; then
    echo "No available simulator matching '$SIM_DEVICE' — open Xcode > Window > Devices and add one." >&2
  else
    xcrun simctl boot "$DEV_ID" 2>/dev/null || true
    open -a Simulator
    APP="$(find ~/Library/Developer/Xcode/DerivedData -name "${SCHEME}.app" -path "*${PLATFORM}*" -newermt '-10 minutes' 2>/dev/null | head -1)"
    if [ -n "$APP" ]; then
      xcrun simctl install "$DEV_ID" "$APP"
      xcrun simctl launch --console-pty "$DEV_ID" "com.helloraj1986.rkmcinema.$( [ "$TARGET" = ios ] && echo ios || echo tvos )"
    else
      echo "Built .app not found in DerivedData — open the project in Xcode and run it there." >&2
    fi
  fi
fi

echo
echo "Paste this summary back (and the log tail for the failing correlation id, per apple/LOGGING.md §7)."
exit $RC
