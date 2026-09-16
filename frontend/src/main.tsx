import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { router } from "./app/router";
import { AuthProvider } from "./features/auth/AuthProvider";
import { LayoutModeProvider } from "./layouts/LayoutMode";
import { LayoutDebugReadout } from "./layouts/LayoutDebug";
import { CACHE_GC_TIME_MS, startQueryCachePersistence } from "./lib/query/persist";
import "./styles/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
      // ⚠ `gcTime` is raised to match the on-disk snapshot's lifetime (NATIVE_FEEL plan §3.2).
      // The default 5 minutes garbage-collects a query once nothing is watching it, which would
      // throw away rows we are deliberately keeping for the NEXT launch — and would drop them
      // out from under a restore on a slow boot. See `lib/query/persist.ts` for what is stored.
      gcTime: CACHE_GC_TIME_MS,
    },
  },
});

/**
 * ⚠ NOTHING IS RESTORED ON THIS LINE, DELIBERATELY — it is the whole identity guarantee.
 * `AuthProvider` calls `adoptPersistedCache()` the moment the server has told it WHO is watching,
 * and `purgePersistedCache()` when there is nobody. Restoring here instead would paint the last
 * session's rows for whoever is holding the device, before any check could run — on a shared iPad
 * that is one person seeing another's Continue Watching. The cost of waiting is ZERO: `RequireSession`
 * renders a skeleton until `me()` answers, so no app content can paint before then anyway.
 *
 * This line only starts the WRITER, which does nothing at all while no profile is adopted.
 */
startQueryCachePersistence(queryClient);

// AuthProvider sits ABOVE the router: the sign-in route lives outside the app shell, so
// the session state cannot live inside it (AUTH_MULTIUSER_PLAN Phase 1).
//
// ⚠ LayoutModeProvider sits between them, and THAT POSITION IS LOAD-BEARING (MOBILE_FIRST_UI_PLAN §3.2):
// above the router, so crossing 1024px re-renders the routed element without remounting the app; and
// BELOW QueryClientProvider and AuthProvider, so the React Query cache and the session survive the
// swap. That is what makes "rotating an iPad does not refetch and does not sign you out" a measured
// fact rather than a hope — `tools/check_mobile_layout_switch.py` asserts both.
//
// `LayoutDebugReadout` renders nothing unless `?layout=debug` is in the URL. It lives inside the
// provider so that what it reports is the PROVIDER's answer — the value the app is actually building
// from — and not a second opinion from its own `matchMedia` call.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <LayoutModeProvider>
          <RouterProvider router={router} />
          <LayoutDebugReadout />
        </LayoutModeProvider>
      </AuthProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
