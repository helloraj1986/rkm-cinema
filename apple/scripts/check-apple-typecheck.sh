#!/usr/bin/env bash
# ⭐ TYPECHECK THE iOS SOURCES ON LINUX — the closest thing to a Mac build that exists here.
#
# `apple/WORKFLOW.md` §5: a BUILD that has not run on the Mac is not verified, but a *semantic* error can
# be reproduced here by mimicking the APIs. This script scales that up: it copies the iOS sources into a
# scratch directory, gives the copies a `FoundationNetworking` import, strips the framework imports it
# cannot resolve, adds a stub scaffold (`apple/scripts/typecheck-stubs/Stubs.swift`) and runs `swiftc
# -typecheck` against the real shared package module.
#
# ⚠⚠ WHY EACH FILE IS CHECKED IN ITS OWN COMPILER RUN, and this is the whole point of the script. The
# first version compiled every file in ONE invocation and reported "0 unexpected errors" while the Mac
# build failed on `OfflineStore.swift`. The cause: `swiftc` in batch mode stops after the first failing
# file, and that file is `OfflineDownloads.swift` (alphabetically early, and it ALWAYS fails here because
# two `URLSessionConfiguration` members are Darwin-only). Everything after it — `OfflineStore.swift`
# included — was never typechecked, and the gate was silently blind to the rest of the module. One
# compiler run per file removes the ordering.
#
# Escape hatches, both required:
#   `background(withIdentifier:)` and `sessionSendsLaunchEvents` have no Linux equivalent. They are
#   correct iOS API, so their errors are filtered BY NAME — and counted, so a new error of another kind
#   can never hide behind the filter.
#
# Usage:  bash apple/scripts/check-apple-typecheck.sh
# Exit codes: 0 clean · 1 a real error · 3 the toolchain or the shared module is missing.
set -u

export PATH="/opt/swift/usr/bin:$PATH"

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$REPO/apple/ios/RKMCinema/Offline"
STUBS="$REPO/apple/scripts/typecheck-stubs/Stubs.swift"
TMP="${RKM_TYPECHECK_TMP:-$HOME/tmp}/rkm-typecheck"
MODULES="$REPO/apple/Shared/.build/x86_64-unknown-linux-gnu/debug/Modules"

# ⚠ `/tmp` is `noexec` in this sandbox; `$HOME/tmp` is not. Same reason as `check-offline-core.py`.
mkdir -p "$TMP" || { echo "cannot write to $TMP"; exit 3; }

if ! command -v swiftc >/dev/null 2>&1; then
  echo "no swiftc — this check needs the toolchain at /opt/swift/usr/bin"; exit 3
fi

if [ ! -d "$MODULES" ]; then
  echo "the shared package is not built — running: swift build  (in apple/Shared)"
  ( cd "$REPO/apple/Shared" && TMPDIR="${RKM_TYPECHECK_TMP:-$HOME/tmp}" swift build ) || exit 3
fi

# The files the app target compiles, in the order they are checked. ⚠ Phase B3 added the loopback server,
# the bridge and the live probe, and the debug probe lives in another directory — both are listed, because a
# file nobody typechecks is a file the Mac finds out about.
WORK=()
for name in OfflineManifest OfflinePlan CookieHeader OfflineHTTP OfflineBridgeContract OfflineProbeCases \
            OfflineStore OfflineAPI OfflineDownloads OfflineServer OfflineBridge; do
  if [ ! -f "$SRC/$name.swift" ]; then
    echo "missing source: $SRC/$name.swift"; exit 3
  fi
  # A copy, because the files that call Apple frameworks get a synthetic import and their framework imports
  # stripped — the real sources must stay exactly as Xcode sees them.
  case "$name" in
    # The files that call Apple networking (and, for the bridge and the probe, WebKit).
    OfflineAPI|OfflineDownloads|OfflineServer|OfflineBridge)
      {
        printf '#if canImport(FoundationNetworking)\nimport FoundationNetworking\n#endif\n'
        cat "$SRC/$name.swift"
      } | sed -E '/^import (UIKit|Combine|WebKit|Network)$/d' > "$TMP/$name.swift"
      ;;
    *)
      cp "$SRC/$name.swift" "$TMP/$name.swift"
      ;;
  esac
  WORK+=("$TMP/$name.swift")
done

# ⚠ The DEBUG probe is `#if DEBUG`, so without `-D DEBUG` the whole file would be SKIPPED and this gate would
# silently check nothing in it. With the flag, the bridge's own DEBUG block (`debugWebView`,
# `forcePublishAll`) is checked too — which is exactly the code the Mac round depends on.
DEBUG_SRC="$REPO/apple/ios/RKMCinema/Debug"
for name in OfflineServerProbe; do
  if [ ! -f "$DEBUG_SRC/$name.swift" ]; then
    echo "missing source: $DEBUG_SRC/$name.swift"; exit 3
  fi
  {
    printf '#if canImport(FoundationNetworking)\nimport FoundationNetworking\n#endif\n'
    cat "$DEBUG_SRC/$name.swift"
  } | sed -E '/^import (UIKit|Combine|WebKit|Network)$/d' > "$TMP/$name.swift"
  WORK+=("$TMP/$name.swift")
done

cp "$STUBS" "$TMP/Stubs.swift"
ALL=("${WORK[@]}" "$TMP/Stubs.swift")

# The two Darwin-only API names. Counted, then filtered.
FILTER='background\(withIdentifier:\)|sessionSendsLaunchEvents'

real_errors=0
expected_errors=0
for primary in "${WORK[@]}"; do
  others=()
  for file in "${ALL[@]}"; do
    [ "$file" != "$primary" ] && others+=("$file")
  done
  # ⚠ `-frontend` IS REQUIRED for per-primary-file typechecking. In driver mode, `swiftc -typecheck
  # -primary-file …` mis-parses and dies with `error opening input file
  # '-in-process-plugin-server-path'` — which the first version of this script reported as six REAL type
  # errors, i.e. a gate that cries wolf on everything.
  output="$(swiftc -frontend -typecheck -module-name RKMCinema -D DEBUG -I "$MODULES" -primary-file "$primary" "${others[@]}" 2>&1)"
  unexpected="$(printf '%s\n' "$output" | grep -E ': error:' | grep -v '^ *|' || true)"
  if [ -n "$unexpected" ]; then
    filtered="$(printf '%s\n' "$unexpected" | grep -vE "$FILTER" || true)"
    expected_errors=$(( expected_errors + $(printf '%s\n' "$unexpected" | grep -cE "$FILTER" || true) ))
    if [ -n "$filtered" ]; then
      echo "✗ $(basename "$primary")"
      printf '%s\n' "$filtered" | sed 's/^/    /'
      real_errors=$(( real_errors + 1 ))
    else
      echo "· $(basename "$primary") — only the Darwin-only API errors (expected here)"
    fi
  else
    echo "✓ $(basename "$primary")"
  fi
done

echo ""
if [ "$real_errors" -gt 0 ]; then
  echo "FAIL — $real_errors file(s) have real type errors. ⚠ These are Mac build failures, caught here."
  exit 1
fi
echo "PASS — every file typechecks, with $expected_errors Darwin-only API error(s) filtered by name."
echo "⚠ Still not a Mac build: this proves types and call shapes, NOT behaviour."
