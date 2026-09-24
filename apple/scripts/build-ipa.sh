#!/usr/bin/env bash
#
# build-ipa.sh — ONE command: an UNSIGNED, DEVICE-ARCHITECTURE .ipa for RKMCinema.
#
#   ./apple/scripts/build-ipa.sh             # Debug  (default — keeps the on-device diagnostics)
#   ./apple/scripts/build-ipa.sh --release   # Release (smaller; strips every `#if DEBUG` block)
#
# Output: ~/dev/rkm-cinema-dist/RKMCinema-unsigned.ipa   ← a stable name, overwritten each run
#         (⚠ OUTSIDE the repo on purpose — it is a build artefact, not source. See docs/UNSIGNED_IPA_PLAN.md §4.7.)
#
# ================================================================================================
# WHY UNSIGNED — and why that is not a downgrade
# ================================================================================================
# No Apple ID, no team, no provisioning profile, no `-allowProvisioningUpdates`. The build genuinely does
# not ask Apple for anything, so it cannot fail on a missing profile.
#
# ⚠ THE FILE IS NOT INSTALLABLE AS-IS. iOS validates code signatures at install; there is no
# configuration or trick that installs unsigned code. So this is an INPUT TO A SIGNER — Sideloadly on
# Windows — and that is the whole point of the arrangement: the free-account 7-day clock is unchanged
# either way (the profile travels inside the app whatever form it takes), but *renewal* now happens on
# Windows with one click instead of on the Mac with a cable. See docs/UNSIGNED_IPA_PLAN.md §0.
#
# ================================================================================================
# ⚠⚠ THIS SCRIPT PRODUCES A FILE THAT LOOKS FINE WHEN IT IS WRONG
# ================================================================================================
# Two failures are silent, and both are asserted in step 6 rather than described in a comment:
#
#   1. A SIMULATOR BINARY. `-destination 'generic/platform=iOS Simulator'` also yields an arm64 Mach-O,
#      so `file` reports exactly what a device build reports. But LC_BUILD_VERSION `platform` is 7
#      (iOS Simulator), not 2 (iOS) — the IPA packs, Sideloadly signs it, and the install is refused with
#      nothing in the message naming the real cause. Step 6 reads the platform NUMBER.
#   2. A STALE SIGNED `.app`. Reuse a DerivedData that an earlier Xcode ⌘R wrote to and the "unsigned"
#      IPA would carry a signature. Hence the dedicated `-derivedDataPath`, the product path read from
#      `-showBuildSettings` (⚠ never globbed — mac-round.sh's rule 3), and the `codesign` assertion.
#
# ================================================================================================
# Tested from Linux with no Mac: `apple/scripts/test-build-ipa.sh` stubs xcodebuild/otool/codesign/file/
# ditto and runs this script end to end — including the IPA structure assertions, which are NOT stubbed.
# Falsify the harness before trusting a green from it (`falsifiable-checks`).
# ================================================================================================

set -euo pipefail

# ---------------------------------------------------------------- helpers

usage() {
  cat <<'EOF'
usage: build-ipa.sh [--release]

  (no argument)  Debug-iphoneos — the default. Keeps the debug HUD, the offline debug panel and the
                 offline probe, i.e. every on-device diagnostic this app has. Recommended for the IPA.
  --release      Release-iphoneos — smaller and faster, and compiles out all of the above. Only worth
                 it once the sideload path is proven and the diagnostics are not wanted.

Output: ~/dev/rkm-cinema-dist/RKMCinema-unsigned.ipa
EOF
}

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

fail() {
  printf '\n\033[1;31mFAILED:\033[0m %s\n' "$*" >&2
  exit 1
}

# ---------------------------------------------------------------- args

CONFIG="Debug"
while [ $# -gt 0 ]; do
  case "$1" in
    --release) CONFIG="Release" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "build-ipa.sh: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PROJ="apple/ios/RKMCinema.xcodeproj"
SCHEME="RKMCinema"
DD="/tmp/rkm-ipa-build"
STAGE="/tmp/rkm-ipa-stage"
LOG_DIR="apple/logs"
DIST_DIR="${RKM_IPA_DIST_DIR:-$HOME/dev/rkm-cinema-dist}"
IPA="$DIST_DIR/RKMCinema-unsigned.ipa"

mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
BUILD_LOG="$LOG_DIR/build-ipa-${STAMP}.log"
RESOLVE_LOG="$LOG_DIR/resolve-package-${STAMP}.log"

# ---------------------------------------------------------------- 1. pre-flight: Xcode
say "1. pre-flight: Xcode"
# ⚠ `xcodebuild` lives INSIDE Xcode, and installing Xcode does not move this pointer. Anything that ever
# ran `xcode-select --install` (Homebrew, a git prompt) leaves it on the Command Line Tools, and every
# build then dies with "requires Xcode, but active developer directory … is a command line tools
# instance" — which reads like a code error. Same check as mac-round.sh, for the same reason.
DEV_DIR="$(xcode-select -p 2>/dev/null || true)"
case "$DEV_DIR" in
  */Xcode*.app/Contents/Developer) echo "xcodebuild: $DEV_DIR" ;;
  *)
    echo "xcode-select is not pointed at Xcode." >&2
    echo "  active developer directory: ${DEV_DIR:-<none>}" >&2
    echo "  fix:  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer" >&2
    echo "  then: sudo xcodebuild -license accept   # if it complains about the licence" >&2
    exit 1
    ;;
esac

if [ ! -d "$PROJ" ]; then
  echo "Project not found: $PROJ" >&2
  echo "It is created once in Xcode and committed — see apple/WORKFLOW.md §2 for the steps." >&2
  exit 1
fi

# ---------------------------------------------------------------- 2. pre-flight: the shared Swift package
say "2. pre-flight: the local Swift package"
# ⚠⚠ Run the FALSIFIER before the build, not after it fails. `Missing package product 'RKMServerKit'`
# reads as a code error and is almost never a repo problem — the reference is committed and correct, and
# the fault is Xcode's own gitignored per-machine SwiftPM state (apple-platform-clients §7g). If this
# resolves, a later failure is that state and the fix is `File → Packages → Reset Package Caches` (⚠ NOT
# a DerivedData delete, which wipes the resolution and creates the error). If it fails, it is real and
# its message is the finding.
set +e
xcodebuild -resolvePackageDependencies -project "$PROJ" >"$RESOLVE_LOG" 2>&1
RESOLVE_RC=$?
set -e
if [ $RESOLVE_RC -ne 0 ]; then
  echo "The local package did not resolve (exit $RESOLVE_RC). This one IS real:" >&2
  grep -E "error: " "$RESOLVE_LOG" | sort -u | head -10 || true
  echo "  full log: $RESOLVE_LOG" >&2
  exit 1
fi
echo "RKMServerKit resolves — a later 'missing package product' is Xcode's own state, not this repo."

# ---------------------------------------------------------------- 3. build, unsigned, to a dedicated DerivedData
say "3. building (unsigned, ${CONFIG}, generic/platform=iOS)"
echo "   full log: $BUILD_LOG"
# ⚠ `-derivedDataPath` is load-bearing, not tidiness: it is what stops an earlier Xcode ⌘R's SIGNED .app
# being found and packed under the name "unsigned".
# ⚠ `-allowProvisioningUpdates` is deliberately ABSENT — there is nothing to provision.
set +e
xcodebuild \
  -project "$PROJ" \
  -scheme "$SCHEME" \
  -configuration "$CONFIG" \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$DD" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGN_IDENTITY="" \
  CODE_SIGN_ENTITLEMENTS="" \
  build >"$BUILD_LOG" 2>&1
BUILD_RC=$?
set -e

if [ $BUILD_RC -ne 0 ]; then
  say "3b. BUILD FAILED (exit $BUILD_RC) — the errors"
  grep -E "(error|warning): " "$BUILD_LOG" | sort -u | head -40 || true
  if grep -qi "agree to the Xcode license\|license agreement" "$BUILD_LOG"; then
    echo
    echo "This is the Xcode licence, not a code error:  sudo xcodebuild -license accept" >&2
  fi
  if grep -qi "no profiles for\|requires a development team\|provisioning profile" "$BUILD_LOG"; then
    echo
    echo "UNEXPECTED: this build disables code signing entirely, so a profile error means the flags" >&2
    echo "did not reach the target. Check the log for CODE_SIGNING_ALLOWED." >&2
  fi
  echo
  echo "--- last 25 lines of $BUILD_LOG ---" >&2
  tail -25 "$BUILD_LOG" >&2 || true
  exit 1
fi
echo "BUILD SUCCEEDED"

# ---------------------------------------------------------------- 4. locate the product by ASKING Xcode
say "4. locating the product"
# ⚠⚠ Never glob DerivedData for it. mac-round.sh already paid for this: its filter looked for `*iOS*` in
# the path, but a simulator product lands in `Debug-iphonesimulator` — no "iOS" anywhere — so the lookup
# matched nothing and the install+launch silently never happened. Asking the toolchain costs one call.
SETTINGS="$(xcodebuild \
  -project "$PROJ" -scheme "$SCHEME" -configuration "$CONFIG" \
  -destination 'generic/platform=iOS' -derivedDataPath "$DD" \
  -showBuildSettings 2>/dev/null || true)"

setting() { # setting <NAME> -> the value, or empty
  printf '%s\n' "$SETTINGS" | awk -F' = ' -v k="$1" '
    $1 ~ "^ *" k " *$" { v = $2; sub(/^[ \t]+/, "", v); sub(/[ \t]+$/, "", v); print v; exit }'
}

BUILT_PRODUCTS_DIR="$(setting BUILT_PRODUCTS_DIR)"
FULL_PRODUCT_NAME="$(setting FULL_PRODUCT_NAME)"
EXECUTABLE_NAME="$(setting EXECUTABLE_NAME)"
BUNDLE_ID="$(setting PRODUCT_BUNDLE_IDENTIFIER)"
DEPLOY_TARGET="$(setting IPHONEOS_DEPLOYMENT_TARGET)"

if [ -z "$BUILT_PRODUCTS_DIR" ] || [ -z "$FULL_PRODUCT_NAME" ]; then
  # ⚠ PRINT WHAT THE TOOL ACTUALLY SAID. An empty value cannot distinguish "the tool failed" from "our
  # parsing failed", and those need opposite fixes. Same principle as mac-round.sh's empty-name dump.
  echo "Could not read BUILT_PRODUCTS_DIR / FULL_PRODUCT_NAME out of -showBuildSettings." >&2
  echo "  what xcodebuild actually returned (first 30 lines):" >&2
  printf '%s\n' "$SETTINGS" | sed -n '1,30p' | sed 's/^/        /' >&2
  exit 1
fi

APP="$BUILT_PRODUCTS_DIR/$FULL_PRODUCT_NAME"
[ -d "$APP" ] || fail "the product is not there: $APP"
EXE="$APP/$EXECUTABLE_NAME"
[ -f "$EXE" ] || fail "no executable inside the product: $EXE"
echo "app:      $APP"
echo "executable: $EXECUTABLE_NAME"
echo "built:    $(stat -c '%y' "$APP" 2>/dev/null || stat -f '%Sm' "$APP" 2>/dev/null || echo '?')  (a stale pick is visible here)"

# ---------------------------------------------------------------- 5. THE TWO ASSERTIONS
say "5. asserting: device build, and unsigned"

# 5a. the cheap check — the products directory itself
case "$BUILT_PRODUCTS_DIR" in
  *-iphonesimulator*)
    fail "this is a SIMULATOR build ($BUILT_PRODUCTS_DIR). A simulator IPA cannot install on a device.
      The destination must be 'generic/platform=iOS' — check for a -destination override or a stray
      SDKROOT setting." ;;
esac

# 5b. the architecture
FILE_OUT="$(file -b "$EXE" 2>/dev/null || true)"
case "$FILE_OUT" in
  *arm64*) : ;;
  *) fail "unexpected architecture — 'file' says: ${FILE_OUT:-<nothing>}
      Expected a Mach-O arm64 executable. An x86_64 build cannot run on the iPad." ;;
esac
echo "arch:     ${FILE_OUT}"

# 5c. ⚠⚠ THE AUTHORITATIVE CHECK — the Mach-O platform NUMBER, which `file` cannot see.
#     2 = iOS device  ✅      7 = iOS Simulator  ✗      (1 macOS · 3 tvOS · 4 watchOS · 6 macCatalyst)
#     awk only: no regex intervals, no GNU-isms — macOS's BSD awk is old enough not to be trusted with
#     them, and the failure mode is empty output rather than an error (apple-platform-clients §7e rule 12).
PLATFORM="$(otool -l "$EXE" 2>/dev/null | awk '
  /LC_BUILD_VERSION/ { seen = 1; next }
  seen == 1 && $1 == "platform" { print $2; exit }' || true)"
case "$PLATFORM" in
  2) echo "platform: 2 (iOS device) ✅" ;;
  7) fail "LC_BUILD_VERSION platform is 7 — this is an iOS SIMULATOR binary.
      It would pack into an IPA, sign, and be refused at install with nothing naming the cause.
      The destination must be 'generic/platform=iOS'." ;;
  "") fail "could not read LC_BUILD_VERSION out of the executable (otool gave nothing).
      This is a live check, so an unreadable answer is treated as a failure rather than assumed good." ;;
  *) fail "LC_BUILD_VERSION platform is $PLATFORM, which is not 2 (iOS device). See <mach-o/loader.h>." ;;
esac

# 5d. unsigned — the claim the whole arrangement rests on, so it gets a gate
#
# ⚠⚠ THE ASSERTION IS "NO SIGNING IDENTITY", NOT "the words 'not signed at all'".
# On Apple Silicon the linker AD-HOC signs arm64 binaries automatically, so a build that made no
# signing decision at all can still come back with a signature — and ad-hoc signing also creates the
# `_CodeSignature/` directory, which is why that directory is NOT a reliable test either. An ad-hoc
# signature carries no identity and Sideloadly replaces it, so it is fine; only a real Developer/Apple
# signature (an `Authority=` or a `TeamIdentifier=`) means a stale signed product got packed.
# ⚠ The ad-hoc branch below is reasoned from the platform, not observed on a Mac. Note which way it
# errs: a wrong guess here lets an ad-hoc app through (harmless — it is re-signed anyway) instead of
# blocking a perfectly good build with a confusing message.
SIG="$(codesign -dv "$APP" 2>&1 || true)"
SIGNED_BY=""
case "$SIG" in
  *"not signed at all"*) SIGNED_BY="none" ;;
esac
if [ -z "$SIGNED_BY" ]; then
  if printf '%s\n' "$SIG" | grep -qE "^Authority=|^TeamIdentifier="; then
    SIGNED_BY="identity"
  elif printf '%s\n' "$SIG" | grep -q "^Signature=adhoc"; then
    SIGNED_BY="adhoc"
  else
    fail "codesign produced an output this script does not recognise, so it cannot tell whether the
      app is signed. Refusing to guess on the one property the artefact is named after:
$(printf '%s\n' "$SIG" | sed 's/^/        /')"
  fi
fi

case "$SIGNED_BY" in
  none)  echo "signature: none ✅ (codesign: not signed at all)" ;;
  adhoc) echo "signature: ad-hoc only ✅ (linker-applied, carries no identity — Sideloadly replaces it)" ;;
  identity)
    fail "this app carries a REAL signing identity, so the IPA would not be the unsigned artefact this
      script promises. codesign said:
$(printf '%s\n' "$SIG" | sed 's/^/        /')
      Most likely a stale product from an earlier signed build — remove $DD and run again." ;;
esac

if [ -e "$APP/embedded.mobileprovision" ]; then
  fail "the app carries an embedded provisioning profile: $APP/embedded.mobileprovision"
fi

# ---------------------------------------------------------------- 6. package
say "6. packaging"
rm -rf "$STAGE"
mkdir -p "$STAGE/Payload" "$DIST_DIR"
cp -R "$APP" "$STAGE/Payload/"
rm -f "$IPA"

# ⚠ ditto, not zip, on a Mac: it preserves symlinks and extended attributes, which plain zip does not —
# and it ships with macOS, so there is nothing to install. zip is the fallback purely so the stub harness
# on Linux can exercise the same code path.
if command -v ditto >/dev/null 2>&1; then
  PACKER="ditto"
  ( cd "$STAGE" && ditto -c -k --sequesterRsrc --keepParent Payload "$IPA" )
elif command -v zip >/dev/null 2>&1; then
  PACKER="zip"
  ( cd "$STAGE" && zip -qry "$IPA" Payload )
else
  fail "neither ditto nor zip is available, so there is no way to build the IPA."
fi
echo "packer:   $PACKER"

# ---------------------------------------------------------------- 7. verify the IPA — real files, real tools
say "7. verifying the IPA"
[ -f "$IPA" ] || fail "the packer reported success but $IPA does not exist."
ENTRIES="$(unzip -l "$IPA" 2>/dev/null || true)"
[ -n "$ENTRIES" ] || fail "unzip could not read back the IPA we just wrote: $IPA"

printf '%s\n' "$ENTRIES" | grep -q "Payload/${FULL_PRODUCT_NAME}/" \
  || fail "the IPA does not contain Payload/${FULL_PRODUCT_NAME}/ — the archive is the wrong shape.
      What it does contain:
$(printf '%s\n' "$ENTRIES" | sed -n '1,20p')"

MP_COUNT="$(printf '%s\n' "$ENTRIES" | grep -c -i 'mobileprovision' || true)"
[ "$MP_COUNT" = "0" ] || fail "the IPA contains $MP_COUNT provisioning profile entry(ies). An unsigned IPA must contain none."

SIG_COUNT="$(printf '%s\n' "$ENTRIES" | grep -c '_CodeSignature' || true)"
[ "$SIG_COUNT" = "0" ] || fail "the IPA contains $SIG_COUNT _CodeSignature entry(ies) — it is signed."

echo "structure: Payload/${FULL_PRODUCT_NAME}/ present · 0 provisioning profiles · 0 _CodeSignature ✅"

if command -v shasum >/dev/null 2>&1; then
  SHA="$(shasum -a 256 "$IPA" | awk '{print $1}')"
else
  SHA="$(sha256sum "$IPA" | awk '{print $1}')"
fi
SIZE="$(du -h "$IPA" | awk '{print $1}')"

# ---------------------------------------------------------------- 8. result
say "8. result — IPA READY"
cat <<EOF
  file:          $IPA
  size:          $SIZE
  sha256:        $SHA
  configuration: $CONFIG
  bundle id:     ${BUNDLE_ID:-<unknown>}
  deployment:    iOS ${DEPLOY_TARGET:-?}
  architecture:  arm64, Mach-O platform 2 (iOS device), UNSIGNED

NEXT (on Windows / RKM-HP):
  1. Open Sideloadly, connect the iPad by cable, and drag in the .ipa above.
  2. Apple ID: use the DEDICATED sideloading Apple ID, not the primary one.
     ⚠ Sideloadly asks for the password — that is expected. Never hand it to a "free signing service".
  3. Install, then on the iPad trust the developer profile:
     Settings → General → VPN & Device Management.  (Developer Mode is already on.)
  4. The signature lasts 7 days on a free Apple ID. Sideloadly's daemon re-signs it automatically
     when the device is next seen — no Mac, no cable, no rebuild.
     ⚠ An EXPIRED profile blocks the app from LAUNCHING while the icon remains, which reads as
     "the app is broken". That is the renewal, not a bug.
  ⚠ Keep the bundle id at ${BUNDLE_ID:-<unknown>}. A new one creates a new App ID (10 per 7 days) AND a
     new app container, so the stored server address is lost.
EOF
