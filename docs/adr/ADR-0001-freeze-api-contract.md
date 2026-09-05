# ADR-0001: Freeze the `/api` contract

- **Status:** Accepted
- **Date:** 2026-09-06
- **Phase:** 0 (`docs/modular-scalable-architecture.md`)

## Context
The frontend is being re-platformed (React/TS). The `/api` surface is the seam between the
backend (unchanged, Python/FastAPI) and the new `web/` client. Without a frozen contract the
two tiers can silently drift and the rewrite loses its de-risking guarantee.

## Decision
- Export the runtime OpenAPI schema to **`docs/api/openapi.v1.json`** and treat **`/api` as
  immutable v1**.
- Any new frontend need is expressed as an **additive** field/endpoint; the snapshot is
  regenerated (`python scripts/snapshot_openapi.py`) and committed whenever the shape changes.
- Typed client types are generated from the snapshot (`openapi-typescript`, Phase 2) so the
  frontend cannot reference a field the backend doesn't serve.
- Only if a breaking change is ever unavoidable, version under **`/api/v1/*`** (not today).

## Consequences
- Contract drift becomes impossible (CI rebuilds types from the frozen schema).
- The re-platform is de-risked: backend stays stable; the client is checked against one truth.
- Discipline cost: every schema change must update the snapshot in the same commit.