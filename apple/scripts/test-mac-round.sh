#!/usr/bin/env bash
# ⚠ **RUN THIS AFTER TOUCHING `mac-round.sh` — it needs no Mac, no Xcode and no simulator.** It stubs
# `xcrun`/`xcodebuild`/`git`/`open`/`xcode-select` on PATH and asserts what the script DID (which device
# it chose, what it installed, what it passed to the launch), so the Mac side of the loop can be
# falsified from Linux — which is the only way it gets checked at all, since the sandbox has no Xcode.
#
#   bash apple/scripts/test-mac-round.sh
#
# Why it exists: step 5 was broken twice, and BOTH failures cost a whole Mac round *each* while looking
# like something else —
#   * the `.app` lookup searched for `*iOS*` in a DerivedData path that says `Debug-iphonesimulator`,
#     so nothing was ever installed or launched and the run silently depended on him using Xcode by
#     hand (his 2026-09-14 terminal, verbatim: "Built .app not found in DerivedData");
#   * the device was chosen without regard to the one already booted — his Mac has `iPhone 17` AND
#     `iPhone 17 Pro`, the app and its stored server address were on the Pro, and the fallback picks
#     the first available iPhone, so the spike would have run on the wrong device and reported
#     `no stored server address` — which reads like "the spike is broken", not like "wrong simulator".
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# ⚠⚠ **A STUB THAT CANNOT BE EXECUTED IS NOT A STUB.** When bash's PATH search hits a file it cannot
# exec (EACCES) it **continues searching** — so a stub in a `noexec` directory is silently skipped and
# the REAL `git`/`xcrun`/`xcodebuild` runs instead. That is exactly what happened here: `/tmp` is
# `noexec` on this host, and this harness reported "6/6 PASS" only because a stale stub directory was
# still on PATH from an earlier run. So the root is chosen by PROBING executability, and the PATH is
# then ASSERTED before a single case is believed.
pick_stub_root() {
  local candidate probe
  for candidate in "${TMPDIR:-}" /root/tmp /var/tmp "$HOME" "$REPO"; do
    [ -n "$candidate" ] || continue
    mkdir -p "$candidate" 2>/dev/null || continue
    probe="$candidate/.rkm-exec-probe.$$"
    printf '#!/bin/sh\nexit 0\n' > "$probe" 2>/dev/null || continue
    chmod +x "$probe" 2>/dev/null
    if "$probe" >/dev/null 2>&1; then rm -f "$probe"; echo "$candidate"; return 0; fi
    rm -f "$probe"
  done
  return 1
}

STUB_ROOT="$(pick_stub_root)" || {
  echo "no dir where a stub can be EXECUTED (tried \$TMPDIR, /root/tmp, /var/tmp, \$HOME, the repo)" >&2
  exit 2
}
echo "stub root: $STUB_ROOT"
STUB="$(mktemp -d "$STUB_ROOT/rkm-macround-stub.XXXXXX")"
trap 'rm -rf "$STUB"' EXIT
BIN="$STUB/bin"
STATE="$STUB/state"
HOME_DIR="$STUB/home"
mkdir -p "$BIN" "$STATE" "$HOME_DIR"

U17="11111111-1111-1111-1111-111111111111"
U17P="22222222-2222-2222-2222-222222222222"
U16="33333333-3333-3333-3333-333333333333"
APP_DIR="$HOME_DIR/Library/Developer/Xcode/DerivedData/RKMCinema-abc123/Build/Products/Debug-iphonesimulator"
mkdir -p "$APP_DIR/RKMCinema.app"
# ⚠ The tvOS target builds RKMCinemaTV.app out of Debug-appletvsimulator. Without this directory the
# tvOS cases below would silently exercise the DerivedData fallback instead of -showBuildSettings, i.e.
# they would test a different code path from the one that runs.
APP_DIR_TV="$HOME_DIR/Library/Developer/Xcode/DerivedData/RKMCinema-abc123/Build/Products/Debug-appletvsimulator"
mkdir -p "$APP_DIR_TV/RKMCinemaTV.app"

cat > "$BIN/xcrun" <<'EOF'
#!/usr/bin/env bash
STATE="$STUB_STATE"
[ "$1" = "simctl" ] || exit 0
shift
case "$1" in
  list)
    case "$3" in
      booted)    cat "$STATE/devices_booted" ;;
      available) cat "$STATE/devices_available" ;;
    esac
    exit 0 ;;
  boot|bootstatus|install|launch)
    echo "CALL simctl $*" >> "$STATE/calls.log"
    exit 0 ;;
  *) exit 0 ;;
esac
EOF

cat > "$BIN/xcodebuild" <<'EOF'
#!/usr/bin/env bash
STATE="$STUB_STATE"
# ⚠ The product differs per platform: the tvOS scheme builds RKMCinemaTV.app out of
# Debug-appletvsimulator. A stub that always answered `RKMCinema.app` would let every tvOS assertion below
# pass against a filename the real build never produces.
NAME="RKMCinema"; SUFFIX="iphonesimulator"; BUNDLE="ios"
for arg in "$@"; do
  [ "$arg" = "RKMCinemaTV" ] && { NAME="RKMCinemaTV"; SUFFIX="appletvsimulator"; BUNDLE="tvos"; }
done
# ⚠ `$STATE/bundle_id` exists so a case can set an identifier the script's own fallback would NOT produce —
# which is the only way to prove the launch id is read from the PROJECT rather than assumed.
if [ -f "$STATE/bundle_id" ]; then
  BUNDLE_ID="$(cat "$STATE/bundle_id")"
else
  BUNDLE_ID="com.helloraj1986.rkmcinema.$BUNDLE"
fi
for arg in "$@"; do
  if [ "$arg" = "-showBuildSettings" ]; then
    # Case E marks this, to make -showBuildSettings useless and exercise the DerivedData fallback.
    [ -f "$STATE/no_settings" ] && exit 0
    echo "    BUILT_PRODUCTS_DIR = $HOME/Library/Developer/Xcode/DerivedData/RKMCinema-abc123/Build/Products/Debug-$SUFFIX"
    echo "    FULL_PRODUCT_NAME = $NAME.app"
    echo "    PRODUCT_BUNDLE_IDENTIFIER = $BUNDLE_ID"
    exit 0
  fi
done
echo "stub xcodebuild: ** BUILD SUCCEEDED **"
exit 0
EOF

cat > "$BIN/git" <<'EOF'
#!/usr/bin/env bash
echo "stub git $*" >&2
exit 0
EOF

cat > "$BIN/open" <<'EOF'
#!/usr/bin/env bash
echo "CALL open $*" >> "$STUB_STATE/calls.log"
exit 0
EOF

cat > "$BIN/xcode-select" <<'EOF'
#!/usr/bin/env bash
echo "/Applications/Xcode.app/Contents/Developer"
EOF

chmod +x "$BIN"/*
export STUB_STATE="$STATE"
export PATH="$BIN:$PATH"
export HOME="$HOME_DIR"

# ⚠ PROVE THE STUBS WIN BEFORE BELIEVING ANYTHING THEY SAY. A stub that is skipped (noexec, a bad
# PATH, an overridden command) hands the case to the REAL tool, and every assertion below then
# describes a machine the test does not control.
for tool in git xcrun xcodebuild open xcode-select; do
  resolved="$(command -v "$tool" || true)"
  if [ "$resolved" != "$BIN/$tool" ]; then
    echo "FATAL: '$tool' resolves to '${resolved:-<nothing>}', not the stub at '$BIN/$tool'" >&2
    echo "       — the harness would be testing the real toolchain. Aborting." >&2
    exit 2
  fi
done

devices() {  # $1 = booted lines, $2 = available lines
  { echo ""; echo "== Devices =="; echo "-- iOS 26.5 --"; } > "$STATE/devices_booted"
  { echo ""; echo "== Devices =="; echo "-- iOS 26.5 --"; } > "$STATE/devices_available"
  printf '%s\n' "$1" >> "$STATE/devices_booted"
  printf '%s\n' "$2" >> "$STATE/devices_available"
}

# ⚠⚠ THE SCRIPT IS TESTED IN A TEMP REPO SKELETON, NOT IN THE REAL TREE — and case G found out why.
# `mac-round.sh` exits early with "Project not found" when the `.xcodeproj` is missing, which is CORRECT
# behaviour and also means the tvOS cases could never reach the device-selection code at all: the tvOS
# project does not exist until he creates it once in Xcode (apple/WORKFLOW.md §2). Running the real script
# from a skeleton means the harness checks the SCRIPT — what it chooses, where it installs, what it
# launches — independently of how far along the repo is. Case I pins the "project not found" message too,
# because that is the first thing the next round will print.
SCRIPT_REPO="$STUB/repo"
PROJECT_DIRS="$SCRIPT_REPO/apple"
mkdir -p "$SCRIPT_REPO/apple/scripts" "$SCRIPT_REPO/apple/logs"
cp "$REPO/apple/scripts/mac-round.sh" "$SCRIPT_REPO/apple/scripts/mac-round.sh"
projects() {  # $1 = yes|no — whether a tvOS .xcodeproj is present
  rm -rf "$PROJECT_DIRS/ios/RKMCinema.xcodeproj" "$PROJECT_DIRS/tvos/RKMCinemaTV.xcodeproj"
  mkdir -p "$PROJECT_DIRS/ios/RKMCinema.xcodeproj"
  [ "$1" = "yes" ] && mkdir -p "$PROJECT_DIRS/tvos/RKMCinemaTV.xcodeproj"
  return 0
}
projects yes

fails=0
total=0
run() {  # $1 = label, rest = expected grep patterns (matched against OUTPUT + the stubs' call log)
  local label="$1"; shift
  : > "$STATE/calls.log"
  local out subject pattern ok=1
  total=$(( total + 1 ))
  out="$(cd "$SCRIPT_REPO" && bash apple/scripts/mac-round.sh "${RUN_TARGET:-ios}" --sim -RKMOfflineSpike YES 2>&1)"
  subject="$out
$(cat "$STATE/calls.log" 2>/dev/null)"
  echo "───── $label"
  for pattern in "$@"; do
    if printf '%s' "$subject" | grep -qE "$pattern"; then
      echo "  ✅ /$pattern/"
    else
      echo "  ❌ MISSING /$pattern/"; ok=0
    fi
  done
  [ $ok -eq 1 ] || { echo "$subject" | sed 's/^/     | /'; fails=$((fails+1)); }
}

devices "    iPhone 17 Pro ($U17P) (Booted)" \
        "    iPhone 17 ($U17) (Shutdown)
    iPhone 17 Pro ($U17P) (Booted)
    iPhone 16 ($U16) (Shutdown)"
run "A · the BOOTED device wins (the one on screen, the one with the stored address)" \
    "ALREADY BOOTED — 'iPhone 17 Pro'" \
    "installing \+ launching on iPhone 17 Pro" \
    "CALL simctl bootstatus $U17P -b" \
    "CALL simctl install $U17P .*RKMCinema.app" \
    "CALL simctl launch --console-pty $U17P com.helloraj1986.rkmcinema.ios -RKMOfflineSpike YES" \
    "CALL open -a Simulator" \
    "app: .*RKMCinema.app   \(from xcodebuild -showBuildSettings\)"

devices "" \
        "    iPhone 17 ($U17) (Shutdown)
    iPhone 17 Pro ($U17P) (Shutdown)
    iPhone 16 ($U16) (Shutdown)"
run "B · nothing booted, the committed default exists — it is used, as before" \
    "installing \+ launching on iPhone 16" \
    "CALL simctl install $U16 .*RKMCinema.app" \
    "CALL simctl launch --console-pty $U16"

# ⚠ CASE C/D: the first-available-iPhone fallback, and the no-iPhone-at-all path.
devices "" \
        "    iPhone 17 Pro ($U17P) (Shutdown)
    iPhone 17 ($U17) (Shutdown)"
run "C · no default on this Mac — the first available iPhone is what runs (the Pro, listed first)" \
    "no simulator named 'iPhone 16' — using 'iPhone 17 Pro' instead" \
    "installing \+ launching on iPhone 17 Pro" \
    "CALL simctl install $U17P .*RKMCinema.app"

devices "" \
        "    Apple TV (44444444-4444-4444-4444-444444444444) (Shutdown)"
run "D · no iPhone at all — must SAY so, not die silently under set -e/pipefail" \
    "no iPhone-class simulator available" \
    "install\+launch step will be skipped"

# ⚠⚠ CASE F IS THE PREFIX TRAP: `iPhone 16` is a PREFIX of `iPhone 16 Pro`, and the committed default
# IS `iPhone 16`. With a bare `grep -m1 "iPhone 16"` the first line in the list wins — so the run would
# build for the default and then install+launch on the *Pro*, a device it never built for, while every
# printed line still said "iPhone 16". The UDID lookup is anchored to the whole name (`^ *NAME (`).
U16P="55555555-5555-5555-5555-555555555555"
devices "" \
        "    iPhone 16 Pro ($U16P) (Shutdown)
    iPhone 16 ($U16) (Shutdown)"
run "F · the default's name is a PREFIX of another device — the UDID must be the exact one" \
    "installing \+ launching on iPhone 16" \
    "CALL simctl install $U16 .*RKMCinema.app" \
    "CALL simctl launch --console-pty $U16 "

devices "    iPhone 17 Pro ($U17P) (Booted)" \
        "    iPhone 17 Pro ($U17P) (Booted)"
touch "$STATE/no_settings"
run "E · -showBuildSettings is useless — the DerivedData fallback still finds the app (and DATES it)" \
    "app: .*RKMCinema.app   \(from DerivedData; built " \
    "CALL simctl install $U17P .*RKMCinema.app"
rm -f "$STATE/no_settings"

# ⚠⚠ CASES G/H ARE tvOS, AND THEY EXIST BECAUSE THE PREVIOUS SCRIPT COULD NOT HAVE RUN ON A TV AT ALL.
# Its committed default was `Apple TV` — the FAMILY name, not a device — and its name extraction cut at the
# first bracket, so `Apple TV 4K (3rd generation)` came back as `Apple TV 4K`: a name that matches no
# device, so the UDID lookup found nothing and the round would have ended at
# "No available simulator matching 'Apple TV'". Both faults are invisible on iOS, where no device name
# contains a bracket.
UTV3="66666666-6666-6666-6666-666666666666"
UTV2="77777777-7777-7777-7777-777777777777"
RUN_TARGET=tvos

devices "" \
        "    Apple TV 4K (3rd generation) ($UTV3) (Shutdown)"
run "G · tvOS: the first available Apple TV is chosen, under its FULL bracketed name" \
    "no committed default for Apple TV — using the first available: 'Apple TV 4K \(3rd generation\)'" \
    "installing \+ launching on Apple TV 4K \(3rd generation\)" \
    "CALL simctl install $UTV3 .*RKMCinemaTV.app" \
    "CALL simctl launch --console-pty $UTV3 com.helloraj1986.rkmcinema.tvos" \
    "app: .*RKMCinemaTV.app   \(from xcodebuild -showBuildSettings\)"

# ⚠ H is the Apple-TV version of the prefix trap, and it is NOT a hypothetical: the two Apple TVs a Mac
# would have on hand are `Apple TV 4K (2nd generation)` and `Apple TV 4K (3rd generation)`, which share the
# prefix `Apple TV 4K (`. A regex anchor on that prefix matches whichever line comes first — build for one
# device, install on the other, with every printed line naming the wrong one.
devices "    Apple TV 4K (2nd generation) ($UTV2) (Booted)" \
        "    Apple TV 4K (2nd generation) ($UTV2) (Booted)
    Apple TV 4K (3rd generation) ($UTV3) (Shutdown)"
run "H · tvOS: the booted Apple TV wins, and the 3rd-gen line must not be mistaken for it" \
    "ALREADY BOOTED — 'Apple TV 4K \(2nd generation\)'" \
    "CALL simctl install $UTV2 .*RKMCinemaTV.app" \
    "CALL simctl launch --console-pty $UTV2"

# ⚠⚠ J: THE LAUNCH ID MUST COME FROM THE PROJECT, NOT FROM THE SCRIPT'S ASSUMPTION. Xcode's template
# names a new project's identifier `<org>.<ProductName>` — i.e. `com.helloraj1986.RKMCinemaTV` — while the
# script used to hardcode `com.helloraj1986.rkmcinema.tvos`. With the hardcoded value the app builds,
# installs, and then refuses to launch ("the application is not installed"), which reads as a build fault.
# This case sets the identifier to Xcode's own default and requires BOTH that it is reported and that it is
# what gets launched.
RUN_TARGET=tvos
# ⚠ Its own fixture: case H left a BOOTED Apple TV, and the booted device wins by design — so without this
# the launch would (correctly) name UTV2 while this case asserts UTV3.
devices "" \
        "    Apple TV 4K (3rd generation) ($UTV3) (Shutdown)"
printf 'com.helloraj1986.RKMCinemaTV' > "$STATE/bundle_id"
run "J · the bundle id is read from the PROJECT — Xcode's default is not the script's assumption" \
    "bundle id: com.helloraj1986.RKMCinemaTV   \\(from xcodebuild -showBuildSettings\\)" \
    "CALL simctl launch --console-pty $UTV3 com.helloraj1986.RKMCinemaTV"
rm -f "$STATE/bundle_id"
# ⚠ RUN_TARGET stays `tvos` for case I — it is about the tvOS project being absent, and pointing it at the
# iOS project (which is committed) would make the case assert a branch it never reaches.

# ⚠ I: WITHOUT THE PROJECT, THE SCRIPT MUST SAY SO AND STOP. This is the exact state of the repo right
# now — the tvOS project is created ONCE in Xcode and committed (apple/WORKFLOW.md §2) — so this is the
# message the first tvOS round will print, and it has to name the fix rather than fail confusingly.
projects no
run "I · no tvOS project in the tree — the script says what to do instead of failing obscurely" \
    "Project not found: apple/tvos/RKMCinemaTV.xcodeproj" \
    "It is created once in Xcode and committed"
projects yes
RUN_TARGET=ios

echo
if [ $fails -eq 0 ]; then echo "STUB TEST PASS — $total/$total"; else echo "STUB TEST FAIL — $fails of $total case(s)"; fi
exit $fails
