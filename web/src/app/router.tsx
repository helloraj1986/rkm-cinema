import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { ConfigHealthView } from "../features/settings/ConfigHealthView";
import { PortedPlaceholder } from "../components/PortedPlaceholder";
import { LibraryLayout } from "../features/library/LibraryLayout";
import { LibraryHomeView } from "../features/library/LibraryHomeView";
import { LibraryFolderView } from "../features/library/LibraryFolderView";
import { ItemDetailPage } from "../features/library/ItemDetailPage";
import { ENABLE_REACT } from "../lib/flags";

/**
 * One router for the whole React shell. Views not yet ported to parity render
 * a `PortedPlaceholder` (they stay live in the legacy app until Phase 3).
 * The shell itself is gated by the `VITE_ENABLE_REACT` flag (see lib/flags).
 *
 * Library routes (PLEX_VIEWS_PLAN): a layout owns the full-screen player + card
 * handlers, and the children are URL-backed views — /library/home, the Movies /
 * TV Shows "folders", and each item's OWN page (/library/item/:id).
 */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell enabled={ENABLE_REACT} />,
    children: [
      { index: true, element: <Navigate to="/settings" replace /> },
      { path: "settings", element: <ConfigHealthView /> },
      {
        path: "library",
        element: <LibraryLayout />,
        children: [
          { index: true, element: <Navigate to="/library/home" replace /> },
          { path: "home", element: <LibraryHomeView /> },
          { path: "movies", element: <LibraryFolderView kind="movies" /> },
          { path: "shows", element: <LibraryFolderView kind="shows" /> },
          { path: "item/:itemId", element: <ItemDetailPage /> },
        ],
      },
      { path: "playback", element: <PortedPlaceholder label="Playback" /> },
      { path: "discover", element: <PortedPlaceholder label="Discover" /> },
      { path: "watchlist", element: <PortedPlaceholder label="Watchlist" /> },
      { path: "search", element: <PortedPlaceholder label="Search" /> },
      { path: "suggest", element: <PortedPlaceholder label="Suggest" /> },
    ],
  },
]);
