"""
Snapshot the live FastAPI OpenAPI schema to docs/api/openapi.v1.json.

Contract freeze (Phase 0 of docs/modular-scalable-architecture.md). The /api surface is
treated as immutable v1 — this snapshot is the single source of truth the React client's
generated types (openapi-typescript, Phase 2) are built from. New fields/endpoints are
additive only; regenerate and commit this file whenever the API shape changes.

Usage:  python scripts/snapshot_openapi.py   (run from repo root)
"""
import json

import api.main as m


def main() -> None:
    schema = m.app.openapi()
    info = schema.get("info", {})
    info["description"] = (info.get("description") or "") + (
        " (FROZEN v1 contract — see docs/adr/ADR-0001; additive-only)"
    )
    schema["info"] = info
    with open("docs/api/openapi.v1.json", "w") as fh:
        json.dump(schema, fh, indent=2)
    print(f"OK wrote docs/api/openapi.v1.json ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()