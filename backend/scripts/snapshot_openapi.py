"""
Snapshot the live FastAPI OpenAPI schema to docs/api/openapi.v1.json.

Contract freeze (Phase 0 of docs/modular-scalable-architecture.md). The /api surface is
treated as immutable v1 — this snapshot is the single source of truth the React client's
generated types (openapi-typescript, Phase 2) are built from. New fields/endpoints are
additive only; regenerate and commit this file whenever the API shape changes.

Usage:  python backend/scripts/snapshot_openapi.py   (from repo root)
        python scripts/snapshot_openapi.py            (from backend/)
"""
import json
import os
import sys
from pathlib import Path

# Parent of scripts/ == the backend dir (packages api/, services/, … live here).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Repo root = backend/.. — output path is anchored so CWD does not matter.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

import api.main as m  # noqa: E402


def main() -> None:
    schema = m.app.openapi()
    info = schema.get("info", {})
    info["description"] = (info.get("description") or "") + (
        " (FROZEN v1 contract — see docs/adr/ADR-0001; additive-only)"
    )
    schema["info"] = info
    with open(REPO_ROOT / "docs/api/openapi.v1.json", "w") as fh:
        json.dump(schema, fh, indent=2)
    print(f"OK wrote docs/api/openapi.v1.json ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()