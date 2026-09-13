#!/usr/bin/env bash
# Regenerate the tvOS Swift API types from the FROZEN contract.
#
# Mirrors `npm run generate:types` in frontend/ (openapi-typescript → src/lib/api/types.ts):
# one committed contract, generated clients, no handwritten model drift.
#
# ⚠ THIS SCRIPT HAS NOT BEEN RUN — it cannot be, in the Linux sandbox (no `swift`).
# The subcommand/flags below are the intended invocation; verify them against
# `swift-openapi-generator --help` on the Mac before trusting the output. The guard below
# fails loudly rather than producing a half-generated tree.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SPEC="$REPO_ROOT/docs/api/openapi.v1.json"
OUT="$REPO_ROOT/tvos/RKMCinemaTV/RKMCinemaTV/Core/GeneratedAPI"

if ! command -v swift-openapi-generator >/dev/null 2>&1; then
  echo "swift-openapi-generator not found." >&2
  echo "Install: brew install swift-openapi-generator   (or use it as a SwiftPM plugin)" >&2
  exit 1
fi

if [ ! -f "$SPEC" ]; then
  echo "Contract not found: $SPEC" >&2
  exit 1
fi

mkdir -p "$OUT"
swift-openapi-generator generate \
  --mode types \
  --mode client \
  --output-directory "$OUT" \
  "$SPEC"

echo "Generated into: $OUT"
echo "Commit the result (the frontend commits its generated types too) and re-run the tvOS build."
