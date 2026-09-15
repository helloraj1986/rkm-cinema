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
for arg in "$@"; do
  if [ "$arg" = "-showBuildSettings" ]; then
    # Case E marks this, to make -showBuildSettings useless and exercise the DerivedData fallback.
    [ -f "$STATE/no_settings" ] && exit 0
    echo "    BUILT_PRODUCTS_DIR = $HOME/Library/Developer/Xcode/DerivedData/RKMCinema-abc123/Build/Products/Debug-iphonesimulator"
    echo "    FULL_PRODUCT_NAME = RKMCinema.app"
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

fails=0
run() {  # $1 = label, rest = expected grep patterns (matched against OUTPUT + the stubs' call log)
  local label="$1"; shift
  : > "$STATE/calls.log"
  local out subject pattern ok=1
  out="$(cd "$REPO" && bash apple/scripts/mac-round.sh ios --sim -RKMOfflineSpike YES 2>&1)"
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

echo
if [ $fails -eq 0 ]; then echo "STUB TEST PASS — 6/6"; else echo "STUB TEST FAIL — $fails case(s)"; fi
exit $fails
