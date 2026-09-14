/**
 * Harness: the REAL app shell + home view, over a stubbed api, with the REAL disk cache wired the way
 * `main.tsx` wires it — so "the rows came off the disk" can be measured in a browser.
 *
 * `tools/check_query_cache.py` drives this in two cold loads of the SAME origin (a `page.goto`, i.e. a
 * real relaunch — localStorage survives it, which is exactly the mechanism under test):
 *
 *   PHASE 1  `?phase=prime&owner=uid-raj`
 *            the session answers, the library calls answer, the home view paints a title that exists
 *            in NO other stub (`PRIME_ONLY_TITLE`) — and the persister writes it to localStorage.
 *
 *   PHASE 2  `?phase=replay&owner=uid-raj&dead=1`
 *            a cold load with every LIBRARY route REJECTING (the network is dead for data). The rows
 *            must still be there — and `libraryCalls` must be 0, which is what makes it the disk and
 *            not a lucky stub: nothing asked the server for them.
 *
 * ⚠ WHY THE SESSION CALL IS NOT BLOCKED TOO — a re-reading of the plan's gate, recorded here because
 * the next session will wonder. `NATIVE_FEEL_AND_OFFLINE_PLAN.md` §3.2 asks for "cold launch paints
 * rows with the network blocked in the harness". The app ALREADY refuses to render any content until
 * `me()` answers (`RequireSession` → `SessionSkeleton`) and that is a deliberate Phase-1 rule this
 * work does not touch — so with the session call dead, the honest outcome is the login screen, cache
 * or no cache. What A1 claims, and what is measured here, is narrower and true: the DATA is free.
 *
 * `?owner=` decides who the server says is watching; `?nopersist=1` skips `startQueryCachePersistence`
 * (the writer) and is the FALSE direction — with it, phase 2 must paint NOTHING, or the check is
 * measuring something other than the disk.
 */
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { AuthProvider } from "../src/features/auth/AuthProvider";
import { RequireSession } from "../src/features/auth/RequireSession";
import { AppShell } from "../src/app/layout/AppShell";
import { LibraryLayout } from "../src/features/library/LibraryLayout";
import { LibraryHomeView } from "../src/features/library/LibraryHomeView";
import { CACHE_GC_TIME_MS, CACHE_STORAGE_KEY, startQueryCachePersistence } from "../src/lib/query/persist";
import "../src/styles/index.css";

const params = new URLSearchParams(location.search);
const PHASE = params.get("phase") === "prime" ? "prime" : "replay";
const OWNER = params.get("owner") || "uid-raj";
const DEAD = params.get("dead") === "1";
const NO_PERSIST = params.get("nopersist") === "1";

/** A title that exists in NO library stub except the priming one, so seeing it in phase 2 can only
 *  mean the disk carried it across the relaunch. */
const PRIME_ONLY_TITLE = "PRIME-ONLY-FILM";

const MOVIE = {
  item_id: "i-prime",
  title: PRIME_ONLY_TITLE,
  year: 1999,
  type: "movie",
  played: false,
  playback_position: 0,
  runtime: 8160,
};

const calls: { url: string; ok: boolean }[] = [];

window.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const raw = typeof input === "string" ? input : String((input as Request).url ?? input);
  const path = raw.slice(raw.indexOf("/api"));
  const send = (payload: unknown) => {
    calls.push({ url: path, ok: true });
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  // -- the session (never blocked: see the header note) ---------------------------------------
  if (path === "/api/auth/me") {
    return send({
      user: { id: OWNER, name: OWNER === "uid-kid" ? "Geetanjali" : "Rajeev" },
      profile: { id: OWNER, name: OWNER === "uid-kid" ? "Geetanjali" : "Rajeev" },
      profile_selected: true,
      on_own_profile: true,
      expires: "2026-10-12T00:00:00Z",
    });
  }
  if (path === "/api/auth/profiles") {
    return send({
      profiles: [{ id: OWNER, name: "Whoever", is_admin: true, has_password: true, disabled: false, last_login: "" }],
      current: { id: OWNER, name: "Whoever", is_admin: true, has_password: true, disabled: false, last_login: "" },
      profile_selected: true,
      warning: "",
    });
  }

  // -- the library reads: dead in phase 2 ------------------------------------------------------
  if (path.startsWith("/api/library")) {
    if (DEAD) {
      calls.push({ url: path, ok: false });
      throw new TypeError("Network request failed"); // an unreachable server, not an error status
    }
    if (path === "/api/library/items") return send({ provider: "jellyfin", items: [MOVIE], warnings: [] });
    if (path === "/api/library") return send({ provider: "jellyfin", available: true, counts: {}, recent: [MOVIE] });
    if (path === "/api/library/continue-watching" || path === "/api/library/recently-watched") {
      return send({ provider: "jellyfin", items: [], warnings: [] });
    }
    if (path === "/api/library/folders") return send({ libraries: [], warnings: [] });
    return send({ provider: "jellyfin", items: [], warnings: [] });
  }
  calls.push({ url: path, ok: true });
  return send({});
}) as typeof fetch;

/** Built EXACTLY as `main.tsx` builds it — a harness that softened `staleTime`/`gcTime` would be
 *  measuring its own settings rather than the app's. */
function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 0, gcTime: CACHE_GC_TIME_MS } },
  });
}

(window as unknown as { __probe: () => unknown }).__probe = () => ({
  phase: PHASE,
  owner: OWNER,
  dead: DEAD,
  noPersist: NO_PERSIST,
  body: document.body.textContent ?? "",
  hasPrimeTitle: (document.body.textContent ?? "").includes(PRIME_ONLY_TITLE),
  libraryCalls: calls.filter((c) => c.url.startsWith("/api/library")).map((c) => c.url),
  libraryFailures: calls.filter((c) => c.url.startsWith("/api/library") && !c.ok).length,
  stored: (() => {
    try {
      return localStorage.getItem(CACHE_STORAGE_KEY);
    } catch {
      return null;
    }
  })(),
});

/**
 * ⚠ THE ROUTE TREE IS THE APP'S OWN, `RequireSession` INCLUDED, AND THAT IS NOT DECORATION.
 * The first version of this frame mounted `LibraryHomeView` under a plain `<MemoryRouter>` — no
 * guard — and every scenario "worked" while measuring the WRONG THING: the home view's queries mounted
 * during the first render, BEFORE `me()` answered, so they fired at a dead network and A1's whole claim
 * looked true-but-not-quite. In the real app the guard holds a skeleton until the session is known, so
 * the restored rows are in the cache before the first observer exists and NOTHING is fetched. The
 * difference is four requests per launch (`tools/check_query_cache.py` asserts the zero).
 */
function makeRouter() {
  return createMemoryRouter(
    [
      {
        path: "/",
        element: (
          <RequireSession>
            <AppShell />
          </RequireSession>
        ),
        children: [
          {
            path: "library",
            element: <LibraryLayout />,
            children: [{ path: "home", element: <LibraryHomeView /> }],
          },
        ],
      },
    ],
    { initialEntries: ["/library/home"] },
  );
}

function Frame() {
  const [queryClient] = useState(() => {
    const qc = makeClient();
    // …wired as `main.tsx` wires it. The writer is a no-op until a profile is adopted, which the REAL
    // `AuthProvider` does from `me()` — so this frame cannot accidentally persist for nobody.
    if (!NO_PERSIST) startQueryCachePersistence(qc);
    // The harness's own handle on the client, so a check can ask WHY a query refetched (its own
    // `staleTime` and `dataUpdatedAt`) rather than inferring it from the request log.
    (window as unknown as { __qc: QueryClient }).__qc = qc;
    return qc;
  });
  const [router] = useState(makeRouter);

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
