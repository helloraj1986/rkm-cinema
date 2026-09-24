#!/usr/bin/env bash
#
# test-build-ipa.sh — run apple/scripts/build-ipa.sh on LINUX, with no Mac, no Xcode and no iPad.
#
#   ./apple/scripts/test-build-ipa.sh          # all cases
#   ./apple/scripts/test-build-ipa.sh -v       # ...and print each case's output
#
# The pattern is mac-round.sh's (`test-mac-round.sh`, and references/round-script-stub-testing.md): put
# stub `xcodebuild` / `otool` / `codesign` / `file` / `ditto` / `xcode-select` FIRST on PATH, and assert on
# the stubs' CALL LOG rather than on the script's stdout — because stdout can be right for the wrong reason.
#
# ⚠ WHAT IS *NOT* STUBBED, DELIBERATELY: `unzip`, `shasum`, `stat`, `grep`. The IPA structure assertions
# in step 7 of build-ipa.sh therefore run FOR REAL against an archive the `ditto` stub genuinely produced
# with python's zipfile. That is the half of this script that is not Xcode-dependent, so it gets no help.
#
# ⚠ Falsify this harness before trusting a green from it (`falsifiable-checks`): break a check in
# build-ipa.sh (delete the `platform 2` branch) and confirm the matching case goes red. A harness that has
# never once been wrong is the suspicious one.

set -euo pipefail

VERBOSE=0
[ "${1:-}" = "-v" ] && VERBOSE=1

SRC_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/build-ipa.sh"
[ -f "$SRC_SCRIPT" ] || { echo "cannot find build-ipa.sh beside this harness" >&2; exit 1; }

# ⚠⚠ A TEMP DIRECTORY THAT CANNOT EXECUTE MAKES EVERY STUB FAIL, AND IT LOOKS LIKE A BROKEN HARNESS.
# On macOS /tmp is fine. In a container it is often a tmpfs mounted `noexec` (this sandbox's is), and the
# only symptom is `bash: …/bin/xcode-select: Permission denied` with rc 126 — which reads as a bug in the
# stubs rather than a property of the filesystem, and sends you hunting in entirely the wrong file.
# So: probe, and fall back to a directory beside the harness's own working dir.
probe_exec() {
  local d="$1"
  mkdir -p "$d" 2>/dev/null || return 1
  printf '#!/bin/sh\necho ok\n' > "$d/.rkm-exec-probe" 2>/dev/null || return 1
  chmod +x "$d/.rkm-exec-probe" 2>/dev/null || return 1
  local got; got="$("$d/.rkm-exec-probe" 2>/dev/null || true)"
  rm -f "$d/.rkm-exec-probe"
  [ "$got" = "ok" ]
}

TMP_BASE=""
for cand in "${RKM_IPA_HARNESS_DIR:-}" "${TMPDIR:-/tmp}" "$(pwd)/.rkm-ipa-harness"; do
  [ -n "$cand" ] || continue
  if probe_exec "$cand"; then TMP_BASE="$cand"; break; fi
done
[ -n "$TMP_BASE" ] || { echo "no exec-capable temp directory available" >&2; exit 1; }
[ "$TMP_BASE" = "${TMPDIR:-/tmp}" ] || echo "note: ${TMPDIR:-/tmp} is not exec-capable — working in $TMP_BASE instead"

TMP="$(mktemp -d "$TMP_BASE/rkm-ipa-harness.XXXXXX")"
# ⚠ Remove the fallback base dir too, or a run leaves an empty `.rkm-ipa-harness/` in the repo and git
# reports it as untracked work that is nobody's.
trap 'rm -rf "$TMP"; rmdir "$TMP_BASE" 2>/dev/null || true' EXIT

HARNESS="$TMP/harness"
STUB="$HARNESS/stub"
BIN="$HARNESS/bin"
SKEL="$HARNESS/repo"
mkdir -p "$STUB" "$BIN" "$SKEL/apple/scripts" "$SKEL/apple/ios/RKMCinema.xcodeproj" "$HARNESS/home"
cp "$SRC_SCRIPT" "$SKEL/apple/scripts/build-ipa.sh"
chmod +x "$SKEL/apple/scripts/build-ipa.sh"

# ================================================================================================
# The stubs. Each logs its invocation, then behaves according to the STUB STATE a case has set.
# ================================================================================================

write_stub() { # write_stub <name> <body...>
  local name="$1"; shift
  { echo '#!/usr/bin/env bash'
    echo 'STUB="$(cd "$(dirname "${BASH_SOURCE[0]}")/../stub" && pwd)"'
    echo 'printf "%s\n" "'"$name"' $*" >> "$STUB/calllog"'
    printf '%s\n' "$@"
  } > "$BIN/$name"
  chmod +x "$BIN/$name"
}

write_stub xcode-select '
case "$(cat "$STUB/devdir" 2>/dev/null || echo xcode)" in
  clt) echo "/Library/Developer/CommandLineTools" ;;
  *)   echo "/Applications/Xcode.app/Contents/Developer" ;;
esac
exit 0'

write_stub xcodebuild '
MODE="$(cat "$STUB/mode" 2>/dev/null || echo happy)"
BUILT="$(cat "$STUB/products_path")"
case " $* " in
  *" -resolvePackageDependencies "*)
    if [ "$MODE" = "resolve-fail" ]; then
      echo "error: Dependencies could not be resolved; RKMServerKit not found" >&2
      exit 1
    fi
    echo "Resolved source packages:"
    echo "  RKMServerKit @ local"
    exit 0 ;;
  *" -showBuildSettings "*)
    echo "Build settings for action build and target RKMCinema:"
    echo "    ACTION = build"
    echo "    BUILT_PRODUCTS_DIR = $BUILT"
    echo "    FULL_PRODUCT_NAME = RKMCinema.app"
    echo "    EXECUTABLE_NAME = RKMCinema"
    echo "    PRODUCT_BUNDLE_IDENTIFIER = com.helloraj1986.rkmcinema.ios"
    echo "    IPHONEOS_DEPLOYMENT_TARGET = 16.4"
    exit 0 ;;
  *" build "*)
    if [ "$MODE" = "build-fail" ]; then
      echo "note: Building targets in dependency order" >&2
      echo "error: cannot find RKMLog in scope" >&2
      echo "error: cannot infer contextual base in reference to member app" >&2
      echo "** BUILD FAILED **" >&2
      exit 1
    fi
    APP="$BUILT/RKMCinema.app"
    rm -rf "$APP"; mkdir -p "$APP"
    printf "fake device macho\n" > "$APP/RKMCinema"; chmod +x "$APP/RKMCinema"
    printf "<plist/>\n" > "$APP/Info.plist"
    if [ "$MODE" = "signed" ]; then
      mkdir -p "$APP/_CodeSignature"
      printf "profile\n" > "$APP/embedded.mobileprovision"
    fi
    echo "** BUILD SUCCEEDED **"
    exit 0 ;;
esac
echo "stub xcodebuild: unhandled invocation: $*" >&2
exit 1'

write_stub file 'cat "$STUB/file_out"'

write_stub otool '
case "$(cat "$STUB/otool_mode" 2>/dev/null || echo normal)" in
  empty) exit 0 ;;
  *) cat <<EOF
Load command 9
      cmd LC_BUILD_VERSION
  cmdsize 32
     platform $(cat "$STUB/otool_platform")
        sdk 26.5
      minos 16.4
    ntools 1
      tool 3
   version 1115.7.3
EOF
     exit 0 ;;
esac'

write_stub codesign '
case "$(cat "$STUB/codesign_mode" 2>/dev/null || echo unsigned)" in
  unsigned)
    echo "${2:-<app>}: code object is not signed at all" >&2
    exit 1 ;;
  adhoc)
    echo "Executable=${2:-<app>}" >&2
    echo "Identifier=com.helloraj1986.rkmcinema.ios" >&2
    echo "CodeDirectory v=20500 size=512 flags=0x2(adhoc) hashes=1+3 location=embedded" >&2
    echo "Signature=adhoc" >&2
    echo "Info.plist=not bound" >&2
    exit 0 ;;
  unrecognised)
    echo "Executable=${2:-<app>}" >&2
    echo "out of the ordinary" >&2
    exit 0 ;;
  *)
    echo "Executable=${2:-<app>}" >&2
    echo "Identifier=com.helloraj1986.rkmcinema.ios" >&2
    echo "Authority=Apple Development: Rajeev (ABCDE12345)" >&2
    echo "TeamIdentifier=J65A2F5SQM" >&2
    exit 0 ;;
esac'

# ⚠ ditto is the ONE stub with a real implementation: it makes a genuine zip, so build-ipa.sh step 7's
# structure assertions run against a real archive rather than a description of one.
cat > "$BIN/ditto" <<'PYEOF'
#!/usr/bin/env python3
import os, sys, zipfile
stub = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stub")
with open(os.path.join(stub, "calllog"), "a") as f:
    f.write("ditto " + " ".join(sys.argv[1:]) + "\n")
args = sys.argv[1:]
src, out = args[-2], args[-1]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _dirs, files in os.walk(src):
        for name in files:
            p = os.path.join(root, name)
            z.write(p, p)
PYEOF
chmod +x "$BIN/ditto"

# ================================================================================================
# Case runner
# ================================================================================================

PASS=0; FAILED=0; FAILED_NAMES=""

# case <name> <mode> <devdir> <products> <otool_platform> <otool_mode> <codesign_mode> <file_out> <project> <expect_rc>
case_run() {
  local name="$1" mode="$2" devdir="$3" products="$4" oplatform="$5" omode="$6" csign="$7" fout="$8" proj="$9" expect="${10}"

  rm -rf "$STUB" "$HARNESS/home"; mkdir -p "$STUB" "$HARNESS/home"
  : > "$STUB/calllog"
  echo "$mode"     > "$STUB/mode"
  echo "$devdir"   > "$STUB/devdir"
  echo "$oplatform"> "$STUB/otool_platform"
  echo "$omode"    > "$STUB/otool_mode"
  echo "$csign"    > "$STUB/codesign_mode"
  echo "$fout"     > "$STUB/file_out"
  echo "$HARNESS/products/$products" > "$STUB/products_path"

  # A missing project is a case of its own (round-script-stub-testing trap: laying it out per case is how
  # the "project not found → here is the fix" message gets exercised at all).
  if [ "$proj" = "present" ]; then
    mkdir -p "$SKEL/apple/ios/RKMCinema.xcodeproj"
  else
    rm -rf "$SKEL/apple/ios/RKMCinema.xcodeproj"
  fi

  local out rc
  set +e
  out="$(env -i \
      PATH="$BIN:/usr/local/bin:/usr/bin:/bin" \
      HOME="$HARNESS/home" \
      TMPDIR="$TMP" \
      bash "$SKEL/apple/scripts/build-ipa.sh" 2>&1)"
  rc=$?
  set -e

  local ipa="$HARNESS/home/dev/rkm-cinema-dist/RKMCinema-unsigned.ipa"
  local problems=""
  if [ "$expect" = "0" ]; then
    [ $rc -eq 0 ] || problems="$problems exit=$rc (expected 0);"
    [ -f "$ipa" ] || problems="$problems no IPA at $ipa;"
  else
    [ $rc -ne 0 ] || problems="$problems exit=0 (expected NON-zero);"
    [ ! -f "$ipa" ] || problems="$problems an IPA was written despite the failure;"
  fi

  if [ $VERBOSE -eq 1 ]; then
    echo "---------------------------------------- $name"
    printf '%s\n' "$out" | sed 's/^/    /'
  fi

  # Per-case assertions on the CALL LOG — never on stdout.
  case "$name" in
    A-happy)
      grep -q -- "-destination generic/platform=iOS" "$STUB/calllog" || problems="$problems calllog: destination wrong;"
      grep -q "CODE_SIGNING_ALLOWED=NO" "$STUB/calllog"               || problems="$problems calllog: not unsigned;"
      grep -q -- "-derivedDataPath /tmp/rkm-ipa-build" "$STUB/calllog" || problems="$problems calllog: dirty DerivedData;"
      grep -q " -allowProvisioningUpdates" "$STUB/calllog" && problems="$problems calllog: -allowProvisioningUpdates present (should be absent);"
      printf '%s\n' "$out" | grep -q "platform: 2 (iOS device)" || problems="$problems stdout: platform assertion missing;"
      printf '%s\n' "$out" | grep -q "not signed at all"        || problems="$problems stdout: unsigned assertion missing;"
      printf '%s\n' "$out" | grep -q "0 provisioning profiles"  || problems="$problems stdout: IPA structure not verified;"
      ;;
    D-no-xcode)
      grep -q " build " "$STUB/calllog" && problems="$problems calllog: it BUILT anyway;"
      printf '%s\n' "$out" | grep -q "xcode-select -s" || problems="$problems stdout: fix not named;"
      ;;
    G-platform-7-device-dir)
      # ⚠ The otool check must catch this ON ITS OWN: the products dir looks like a device build.
      grep -q "generic/platform=iOS" "$STUB/calllog" || problems="$problems calllog: unexpected destination;"
      printf '%s\n' "$out" | grep -qi "SIMULATOR binary" || problems="$problems stdout: did not name the simulator binary;"
      ;;
    I-otool-silent)
      printf '%s\n' "$out" | grep -q "could not read LC_BUILD_VERSION" || problems="$problems stdout: silent otool not treated as failure;"
      ;;
    K-adhoc-signature)
      printf '%s\n' "$out" | grep -q "ad-hoc only" || problems="$problems stdout: ad-hoc signature not accepted;"
      grep -q -- "-destination generic/platform=iOS" "$STUB/calllog" || problems="$problems calllog: destination wrong;"
      ;;
    L-codesign-unrecognised)
      printf '%s\n' "$out" | grep -q "does not recognise" || problems="$problems stdout: unrecognised codesign output not treated as a failure;"
      ;;
    F-build-fail)
      printf '%s\n' "$out" | grep -q "cannot find RKMLog in scope" || problems="$problems stdout: compiler error not surfaced;"
      printf '%s\n' "$out" | grep -q "BUILD FAILED"                || problems="$problems stdout: failure not announced;"
      ;; 
    H-no-project)
      printf '%s\n' "$out" | grep -q "WORKFLOW.md" || problems="$problems stdout: fix not named;"
      grep -q " build " "$STUB/calllog" && problems="$problems calllog: it BUILT anyway;"
      ;;
  esac

  if [ -z "$problems" ]; then
    PASS=$((PASS + 1)); printf '  \033[32mPASS\033[0m  %s\n' "$name"
  else
    FAILED=$((FAILED + 1)); FAILED_NAMES="$FAILED_NAMES $name"
    printf '  \033[31mFAIL\033[0m  %s\n' "$name"
    printf '%s\n' "$problems" | tr ';' '\n' | sed '/^ *$/d;s/^/         ·/'
    printf '%s\n' "$out" | tail -20 | sed 's/^/         | /'
  fi
}

echo "build-ipa.sh harness — $(uname -s), no Mac required"
echo
echo "  positive path"
case_run A-happy happy xcode "Debug-iphoneos" 2 normal unsigned "Mach-O 64-bit executable arm64" present 0

echo "  the silent failures that would produce a plausible-looking IPA (§5 of the plan)"
case_run B-products-are-simulator happy xcode "Debug-iphonesimulator" 2 normal unsigned   "Mach-O 64-bit executable arm64" present 1
case_run C-real-identity         happy xcode "Debug-iphoneos" 2 normal identity   "Mach-O 64-bit executable arm64" present 1
case_run G-platform-7-device-dir happy xcode "Debug-iphoneos" 7 normal unsigned   "Mach-O 64-bit executable arm64" present 1
case_run I-otool-silent          happy xcode "Debug-iphoneos" 2 empty   unsigned   "Mach-O 64-bit executable arm64" present 1
case_run L-codesign-unrecognised happy xcode "Debug-iphoneos" 2 normal unrecognised "Mach-O 64-bit executable arm64" present 1

echo "  the FALSE-POSITIVE path — an Apple Silicon ad-hoc signature must NOT block the build"
case_run K-adhoc-signature       happy xcode "Debug-iphoneos" 2 normal adhoc    "Mach-O 64-bit executable arm64" present 0

echo "  pre-flight and build failures"
case_run D-no-xcode    happy clt           "Debug-iphoneos" 2 normal unsigned "Mach-O 64-bit executable arm64" present 1
case_run E-resolve-fail resolve-fail xcode "Debug-iphoneos" 2 normal unsigned "Mach-O 64-bit executable arm64" present 1
case_run F-build-fail  build-fail xcode    "Debug-iphoneos" 2 normal unsigned "Mach-O 64-bit executable arm64" present 1
case_run H-no-project  happy xcode         "Debug-iphoneos" 2 normal unsigned "Mach-O 64-bit executable arm64" absent  1
case_run J-wrong-arch  happy xcode         "Debug-iphoneos" 2 normal unsigned "Mach-O 64-bit executable x86_64" present 1

echo
printf '  %d passed, %d failed' "$PASS" "$FAILED"
[ -n "$FAILED_NAMES" ] && printf ' — failed:%s' "$FAILED_NAMES"
echo
[ $FAILED -eq 0 ] || exit 1
