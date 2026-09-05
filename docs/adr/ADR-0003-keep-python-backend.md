# ADR-0003: Keep the Python/FastAPI backend — consolidate, don't rewrite

- **Status:** Accepted
- **Date:** 2026-09-06
- **Phase:** 0/1 (`docs/modular-scalable-architecture.md`)

## Context
The backend is modular (thin routes, DI-capable services, provider ABC, repository seam, one
cache primitive) but carries **backward-compat facade debt**: `services/plex.py`, `emby.py`,
`radarr.py`, `sonarr.py`, `recommendations.py`, `media_status.py` coexist with canonical
`services/library`, `acquisition`, `recommendation`, `reconciliation`. Newer cost-effective
provider methods (`all_items`, `continue_watching`, `episodes`, `refresh_library`, `get_poster`)
exist only on the Jellyfin provider, not declared on the `LibraryProvider` ABC.

## Decision
- **Keep Python/FastAPI.** Rewriting a working, test-covered backend (247 pytest) is the
  classic trap and buys nothing.
- **Phase 1:** delete the BC facades behind one-release re-export stubs
  (`DeprecationWarning`), and promote the capability methods onto the ABC so routes call the
  interface, not `getattr(provider, …)`.
- Alternative considered: all-TypeScript (NestJS) backend — rejected (same result, full rewrite).

## Consequences
- The app keeps a stable, deployable backend while the frontend re-platform proceeds.
- One rule per rule (§43): no parallel implementations of a capability.