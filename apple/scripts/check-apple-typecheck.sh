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
SHELL_SRC="$REPO/apple/ios/RKMCinema/Shell"
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

# ⚠ ADR-0012 — the cold-launch ladder. It lives in `Shell/`, not `Offline/`, so it needs its own loop; and
# it is Foundation-only on purpose (no WebKit, no `URLRequest`), which is why it typechecks here with no
# synthetic import and no filtered error. ⚠ `WebShellModel.swift`, which CARRIES THE LADDER OUT, cannot be
# checked here — SwiftUI and WebKit are not stubbable in this scaffold — so that half is the Mac round's
# business, and saying so is the reason files are listed one at a time.
for name in ShellLaunchPlan ShellStorePlan ShellStore ShellFetcher ShellAssetSchemeHandler; do
  if [ ! -f "$SHELL_SRC/$name.swift" ]; then
    echo "missing source: $SHELL_SRC/$name.swift"; exit 3
  fi
  # ⚠ S2 (`ShellStore`/`ShellFetcher`/`ShellAssetSchemeHandler`) calls URLSession and WebKit, so the Shell
  # loop needs the same treatment the Offline loop gives its Apple-facing files. The two PURE files get it
  # too and are unharmed by it — the synthetic import is guarded by `canImport`, and neither imports a
  # framework that gets stripped.
  {
    printf '#if canImport(FoundationNetworking)\nimport FoundationNetworking\n#endif\n'
    cat "$SHELL_SRC/$name.swift"
  } | sed -E '/^import (UIKit|Combine|WebKit|Network)$/d' > "$TMP/$name.swift"
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
echo "== tvOS sources (RKMCinemaTV) — every file that needs no Apple UI framework"
# ⚠ The count is deliberately NOT in that heading any more: it said "nineteen files" while the list grew to
# 21, which is this repo's "one rule in two places" defect wearing a heading.
# ⚠⚠ WHY THIS LIST IS NINETEEN FILES AND NOT THE WHOLE TARGET. The tvOS app is mostly SwiftUI, and there is
# no SwiftUI on Linux to stub (nor a UIKit, nor an AVFoundation), so the views are Mac-round business and
# saying so is the point. What CAN be checked here is the part where a mistake is silent and expensive:
#
#   ServerDefaults   the pre-filled address — one line, easy to typo, impossible to notice
#   APIClient        every request, every error path, and the log line for each
#   AuthModels       the wire format, also covered by check-tvos-models.py against the contract
#   ServerProbe      the reachable/unreachable rule — a 401 reported as "unreachable" is a wrong screen
#   AppLog           the launch banner, which is what makes a round diagnosable at all
#   AppModel         which screen the app is on, and the ONE place the Home/Browse/Detail stores are built
#   SessionStore     the session behind that, and the cookie handling
#   LibraryModels    Phase B's wire format — the item/episode/library shapes, R6/R7-checked against the
#                    frontend's own TypeScript interfaces where the contract is silent
#   DetailModels     Phase B4's wire format — the detail payload, same second source, same gate
#   HomeRails        Phase B2's Home RULES and its four screen states — also EXECUTED by check-tvos-core.py
#   BrowseRules      Phase B3's Browse rules: the library list and the wall's mounting plan — also EXECUTED
#   DetailRules      Phase B4's detail rules: the meta line, the episode progress, the season grouping and
#                    the screen's four states — also EXECUTED
#   RequestURL       ⚠ the URL builder, and the reason it is its own file: `appendingPathComponent` escapes a
#                    query into the PATH, and `APIClient` (which would otherwise hold this rule) imports
#                    `RKMServerKit`, so nothing in it can be RUN here. Also EXECUTED.
#   LibraryAPI       the endpoints, so no view spells a path
#   HomeStore        the two Home requests and the APIError -> sentence mapping
#   BrowseStore      the library list + one folder's wall, same mapping
#   DetailStore      Phase B4's one item — the detail request, the episode request, and the 404 -> notFound
#   PosterURL        the artwork URL builder — a 404 poster and a broken screen look identical
#   PosterLoader     the artwork fetch, and the log line that says whether the session cookie reached it
#   DesignTokens     ⚠ GENERATED from `frontend/src/styles/index.css` by apple/scripts/generate-design-tokens.py,
#                    and drift-gated by apple/scripts/check-design-tokens.py (R1). It is Foundation-only on
#                    purpose so this list can compile it — the SwiftUI bridge is Design/DesignColours.swift,
#                    which no gate here can see (there is no SwiftUI on Linux) and which holds no rule.
#   TVTokens         the tvOS-only token layer (the one adjusted grey, the tvOS metrics) — Foundation-only for
#                    the same reason, and the file whose diffability IS the design.
#
# ⚠ AppModel is the newest member of this list and it was a real gap: it decides which screen the app is on,
# and until Phase B2 nothing compiled it here.
#
# ⚠ The tvOS stubs are a SEPARATE file (see typecheck-stubs/TVStubs.swift): the iOS stub references iOS
# types in its WebKit slice, so including it here would fail the gate on symbols tvOS does not have.
TV_SRC="$REPO/apple/tvos/RKMCinemaTV"
TV_STUBS="$REPO/apple/scripts/typecheck-stubs/TVStubs.swift"
TMP_TV="$TMP/tvos"
mkdir -p "$TMP_TV" || exit 3

TV_WORK=()
for rel in Core/ServerDefaults.swift Core/APIClient.swift Core/Models/AuthModels.swift \
           Core/Models/LibraryModels.swift Core/Models/DetailModels.swift \
           Core/HomeRails.swift Core/BrowseRules.swift Core/DetailRules.swift Core/RequestURL.swift \
           Core/ProfileRules.swift \
           Core/LibraryAPI.swift Core/HomeStore.swift Core/BrowseStore.swift Core/DetailStore.swift \
           Core/PosterURL.swift Core/PosterLoader.swift \
           Design/DesignTokens.swift Design/TVTokens.swift \
           Server/ServerProbe.swift App/AppLog.swift App/AppModel.swift Auth/SessionStore.swift; do
  if [ ! -f "$TV_SRC/$rel" ]; then
    echo "missing source: $TV_SRC/$rel"; exit 3
  fi
  name="$(basename "$rel" .swift)"
  # ⚠ The synthetic `FoundationNetworking` import is what lets `URLSession` and `HTTPCookieStorage`
  # typecheck here at all, and `Combine` is stripped because TVStubs supplies the shape.
  {
    printf '#if canImport(FoundationNetworking)\nimport FoundationNetworking\n#endif\n'
    cat "$TV_SRC/$rel"
  } | sed -E '/^import (UIKit|Combine|WebKit|Network)$/d' > "$TMP_TV/$name.swift"
  TV_WORK+=("$TMP_TV/$name.swift")
done
cp "$TV_STUBS" "$TMP_TV/TVStubs.swift"
TV_ALL=("${TV_WORK[@]}" "$TMP_TV/TVStubs.swift")

tv_real_errors=0
for primary in "${TV_WORK[@]}"; do
  others=()
  for file in "${TV_ALL[@]}"; do
    [ "$file" != "$primary" ] && others+=("$file")
  done
  output="$(swiftc -frontend -typecheck -module-name RKMCinemaTV -D DEBUG -I "$MODULES" \
              -primary-file "$primary" "${others[@]}" 2>&1)"
  unexpected="$(printf '%s\n' "$output" | grep -E ': error:' | grep -v '^ *|' || true)"
  if [ -n "$unexpected" ]; then
    echo "✗ $(basename "$primary")"
    printf '%s\n' "$unexpected" | sed 's/^/    /'
    tv_real_errors=$(( tv_real_errors + 1 ))
  else
    echo "✓ $(basename "$primary")"
  fi
done

echo ""
if [ "$real_errors" -gt 0 ] || [ "$tv_real_errors" -gt 0 ]; then
  echo "FAIL — $real_errors iOS file(s) and $tv_real_errors tvOS file(s) have real type errors."
  echo "⚠ These are Mac build failures, caught here."
  exit 1
fi
echo "PASS — every file typechecks, with $expected_errors Darwin-only API error(s) filtered by name."
echo "⚠ Still not a Mac build: this proves types and call shapes, NOT behaviour."
echo "⚠ And it does NOT cover the tvOS SwiftUI views — no SwiftUI exists here to stub. Those are"
echo "  verified only on the Mac, and this script will not claim otherwise."
