/**
 * Feature-flag gating for the React re-platform (docs/modular-scalable-architecture.md,
 * Phase 2). In many cases the legacy app (`app.js`) still owns the route until it's
 * ported to parity. The React shell renders only when enabled.
 *
 * - `npm run dev` → the shell shows immediately (DEV = enabled) for working on it.
 * - production build → enabled only when built with `VITE_ENABLE_REACT=1`, so the
 *   legacy app keeps serving until the Phase-4 cut-over.
 */
export const ENABLE_REACT: boolean =
  import.meta.env.DEV || import.meta.env.VITE_ENABLE_REACT === "1";

/** Documented env knob name, shown in the UI so it's discoverable. */
export const REACT_FLAG_NAME = "VITE_ENABLE_REACT";