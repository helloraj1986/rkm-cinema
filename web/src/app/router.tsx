import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { ConfigHealthView } from "../features/settings/ConfigHealthView";
import { PortedPlaceholder } from "../components/PortedPlaceholder";
import { LibraryView } from "../features/library/LibraryView";
import { ENABLE_REACT } from "../lib/flags";

/**
 * One router for the whole React shell. Views not yet ported to parity render
 * a `PortedPlaceholder` (they stay live in the legacy app until Phase 3).
 * The shell itself is gated by the `VITE_ENABLE_REACT` flag (see lib/flags).
 */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell enabled={ENABLE_REACT} />,
    children: [
      { index: true, element: <Navigate to="/settings" replace /> },
      { path: "settings", element: <ConfigHealthView /> },
      { path: "library", element: <LibraryView /> },
      { path: "playback", element: <PortedPlaceholder label="Playback" /> },
      { path: "discover", element: <PortedPlaceholder label="Discover" /> },
      { path: "watchlist", element: <PortedPlaceholder label="Watchlist" /> },
      { path: "search", element: <PortedPlaceholder label="Search" /> },
      { path: "suggest", element: <PortedPlaceholder label="Suggest" /> },
    ],
  },
]);