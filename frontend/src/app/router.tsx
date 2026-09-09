import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { ConfigHealthView } from "../features/settings/ConfigHealthView";
import { LibraryLayout } from "../features/library/LibraryLayout";
import { LibraryHomeView } from "../features/library/LibraryHomeView";
import { LibraryFolderView } from "../features/library/LibraryFolderView";
import { ItemDetailPage } from "../features/library/ItemDetailPage";
import { DiscoverView } from "../features/discover/DiscoverView";
import { WatchlistView } from "../features/watchlist/WatchlistView";
import { SuggestView } from "../features/suggest/SuggestView";

/**
 * One router for the React shell (the legacy vanilla app was removed).
 *
 * Library routes (PLEX_VIEWS_PLAN): a layout owns the full-screen player + card
 * handlers, and the children are URL-backed views — /library/home, the Movies /
 * TV Shows "folders", and each item's OWN page (/library/item/:id).
 *
 * Legacy parity (LEGACY_PARITY_PLAN): /discover, /watchlist, /search and
 * /suggest are React views fed by live /api data. Playback lives inside the
 * library routes (item pages / library layout player), not a top-level route.
 */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/library/home" replace /> },
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
      { path: "discover", element: <DiscoverView /> },
      { path: "watchlist", element: <WatchlistView /> },
      { path: "suggest", element: <SuggestView /> },
      // Global search lives in the top bar (GLOBAL_SEARCH_PLAN) — the old
      // standalone /search results page was removed; deep links land Home.
      { path: "search", element: <Navigate to="/library/home" replace /> },
    ],
  },
]);
