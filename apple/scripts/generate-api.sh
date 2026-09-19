#!/usr/bin/env bash
# ⚠⚠ **SUPERSEDED 2026-09-19 — DO NOT RUN THIS AS THE FIRST STEP OF ANY PHASE.** The tvOS models are
# HAND-WRITTEN (`apple/tvos/RKMCinemaTV/Core/Models/`) and kept honest by
# `apple/scripts/check-tvos-models.py`, which runs on Linux with no Mac and no `brew` — see the header of
# the models file for why that trade was taken (the generator needs a tool this sandbox cannot exercise,
# and the drift risk is caught either way).
#
# It is kept, un-run and un-verified, as the escape hatch: if the tvOS type surface ever grows past a few
# screens, a generator becomes worth its weight. ⚠ Until then, nothing should depend on this file working.
#
# Regenerate the tvOS Swift API types from the FROZEN contract (ESCAPE HATCH — see the note above).
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
OUT="$REPO_ROOT/apple/tvos/RKMCinemaTV/Core/GeneratedAPI"

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
