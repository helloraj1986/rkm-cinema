# ADR-0002: Rewrite the frontend as React 18 + TypeScript + Vite

- **Status:** Accepted
- **Date:** 2026-09-06
- **Phase:** 0 (`docs/modular-scalable-architecture.md`)

## Context
`app.js` is a **2,191-line single-file monolith** (+ `api.js`, `app.css`) — global render
functions, delegated events, hand-rolled global state (`DATA`/`RES`/`LIBALL`/`LIBWATCH`).
Every feature appends joins to one file; it does not scale past the current handful of screens.

## Decision
- New `web/` directory: **React 18 + TypeScript + Vite + Tailwind**.
- **TanStack Query** for server state (cache + invalidation tied to library-scan/job runs) +
  a light **Zustand** store for UI state. No hand-rolled global maps.
- One feature slice per bounded context (`library`, `playback`, `discover`, `watchlist`,
  `search`, `suggest`, `settings`), each owning its API client + store.
- Capabilities/status remain **backend-derived** (`MediaResponse`); the UI renders, never
  reconstructs.
- **Feature-flag gated**, incremental port behind a config toggle; legacy `app.js` stays live
  until each view is at parity, then retired in Phase 4.

## Alternatives
Vue/Svelte (same modularity, weaker fit with the user's stack); keep-vanilla (no). Chosen for
senior-stack fit (React/TS/Next/Tailwind) and ecosystem.

## Consequences
- Re-platform is the largest roadmap effort, but items 2–5 then get built once on the right
  foundation.
- The frozen `/api` (ADR-0001) keeps it non-breaking.