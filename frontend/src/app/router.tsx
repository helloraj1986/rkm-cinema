import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { RequireSession } from "../features/auth/RequireSession";
// ⚠ The views are imported THROUGH `layouts/desktop` (MOBILE_FIRST_UI_PLAN §2.2, brief §2a).
// That index is a thin re-export — nothing moved, and every view still lives exactly where it
// always did. The point is that a route reads symmetrically once a mobile counterpart exists
// (`desktop.LibraryHomeView` / `mobile.HomeScreen`), and that a future physical move would be a
// one-file change here instead of a sweep of every import in the router.
import * as desktop from "../layouts/desktop";
import * as mobile from "../layouts/mobile";
import { Screen } from "../layouts/Screen";

/**
 * One router for the React shell (the legacy vanilla app was removed).
 *
 * Library routes (PLEX_VIEWS_PLAN + MEDIA_LIBRARIES_PLAN): a layout owns the
 * full-screen player + card handlers, and the children are URL-backed views —
 * /library/home, the configured media library folders (/library/folder/:id)
 * and each item's OWN page (/library/item/:id). /library/movies and
 * /library/shows are legacy paths that redirect to the matching server folder
 * (global-search genre hints still deep-link there).
 *
 * Legacy parity (LEGACY_PARITY_PLAN): /discover, /watchlist, /search and
 * /suggest are React views fed by live /api data. Playback lives inside the
 * library routes (item pages / library layout player), not a top-level route.
 *
 * ⚠ MOBILE_FIRST_UI_PLAN M1: the routes below are deliberately UNCHANGED by the arrival of the
 * mobile shell. `AppShell` is the one component that decides which arrangement of chrome wraps
 * `<Outlet/>` — the sidebar and header, or the phone shell's header and tab bar. A route does not
 * know which it is inside, so no route had to learn, and no view was touched. The mobile
 * counterparts (a phone-shaped `HomeScreen`, a bottom `Sheet` instead of a centred `Dialog`)
 * replace these views ONE AT A TIME from M3 onwards, each behind `layouts/Screen.tsx`.
 */
export const router = createBrowserRouter([
  // Sign-in lives OUTSIDE the shell: it must render when nothing else can, including on
  // the day enforcement is switched on and every other route is refusing.
  { path: "/login", element: <desktop.LoginView /> },
  // "Who's watching?" (PLEX_PROFILE_AUTH_PLAN Phase B) — also outside the shell, for the same
  // reason: it renders while a session exists but the app itself must not.
  { path: "/profiles", element: <desktop.ProfilesView /> },
  {
    path: "/",
    element: (
      <RequireSession>
        <AppShell />
      </RequireSession>
    ),
    children: [
      { index: true, element: <Navigate to="/library/home" replace /> },
      { path: "settings", element: <desktop.ConfigHealthView /> },
      // Household accounts (AUTH_MULTIUSER_PLAN Phase 1b). The route needs no client-side
      // gate of its own: the API answers 401/403 and the screen says so plainly — a hidden
      // link is not security, and this way nothing pretends a refusal is a broken page.
      { path: "settings/household", element: <desktop.HouseholdView /> },
      { path: "settings/password", element: <desktop.PasswordView /> },
      {
        path: "library",
        element: <desktop.LibraryLayout />,
        children: [
          { index: true, element: <Navigate to="/library/home" replace /> },
          // ⚠ M3: the phone's own Home (the layout chooser renders exactly one of the two, §3.3).
          { path: "home", element: <Screen desktop={<desktop.LibraryHomeView />} mobile={<mobile.HomeScreen />} /> },
          // ⚠ M3: the folder route is the first one with a phone counterpart — the desktop view is
          // unchanged, and `Screen` renders exactly one of the two (§3.3).
          {
            path: "folder/:folderId",
            element: (
              <Screen desktop={<desktop.LibraryFolderView />} mobile={<mobile.BrowseScreen />} />
            ),
          },
          { path: "movies", element: <desktop.LibraryKindRedirect kind="movies" /> },
          { path: "shows", element: <desktop.LibraryKindRedirect kind="tvshows" /> },
          { path: "item/:itemId", element: <desktop.ItemDetailPage /> },
        ],
      },
      { path: "discover", element: <desktop.DiscoverView /> },
      { path: "watchlist", element: <desktop.WatchlistView /> },
      // Downloads (B4, NATIVE_FEEL plan §4.6): what THIS DEVICE is holding. It is mounted by
      // `LibraryLayout` — the same element the library routes use — because it starts films itself,
      // and offline is exactly when the item's detail page cannot fetch what it needs to render.
      {
        path: "downloads",
        element: <desktop.LibraryLayout />,
        children: [{ index: true, element: <desktop.DownloadsView /> }],
      },
      { path: "suggest", element: <desktop.SuggestView /> },
      // Global search lives in the top bar (GLOBAL_SEARCH_PLAN) — the old
      // standalone /search results page was removed; deep links land Home.
      { path: "search", element: <Navigate to="/library/home" replace /> },
    ],
  },
]);
