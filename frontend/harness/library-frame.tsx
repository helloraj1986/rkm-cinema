/**
 * Harness: the REAL library views over a stubbed api.
 *
 * `tools/check_library_scan.py` uses this to prove the rule Phase E (2026-09-13) put on the
 * library scan: the route is administrators-only and **strict even while enforcement is off**, so
 * the control that calls it must be OFFERED to an administrator and NOT to anybody else.
 *
 * Why a browser and not only a unit test: `mayScanLibrary` is a pure rule and is unit-tested, but
 * a rule nothing calls is worth nothing. What this frame proves is the WIRING — that the real
 * `LibraryHomeView` (empty state AND hero) and the real `LibraryFolderView` pass the rule through
 * to the DOM. The repo has already been bitten by the other kind of check: a harness that handed
 * the UI an answer the server could not produce (§6g), and a test that passed while inspecting
 * zero routes (§6f).
 *
 * ⚠ `?admin` decides the profile in effect, exactly as `nav-frame.tsx` does — and `current` is the
 * profile's OWN row, because that is what `/api/auth/profiles` really answers.
 *
 * `?empty=1` renders the library with no titles, which is the path where the scan button is the
 * empty state's ONLY call to action (the one a member would be left staring at).
 * `?folder=1` mounts the folder view instead, which has its own copy of the control.
 */
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "../src/features/auth/AuthProvider";
import { LibraryLayout } from "../src/features/library/LibraryLayout";
import { LibraryHomeView } from "../src/features/library/LibraryHomeView";
import { LibraryFolderView } from "../src/features/library/LibraryFolderView";
import { Toaster } from "../src/features/watchlist/Toaster";
// The app's REAL stylesheet (see nav-frame.tsx): without it a screenshot or a geometry
// measurement of this frame is unstyled and therefore not evidence of anything.
import "../src/styles/index.css";

const params = new URLSearchParams(location.search);
const ADMIN = params.get("admin") !== "0";
const EMPTY = params.get("empty") === "1";
const FOLDER = params.get("folder") === "1";
//: No session at all — `require_admin_session` answers 401 for the scan routes, so this is the
//: OTHER non-administrator state (a member is the first). The library reads still answer, because
//: the point is that the VIEW renders and still offers nothing.
const SIGNED_OUT = params.get("signedout") === "1";

const PROFILE = {
  id: ADMIN ? "uid-admin" : "uid-kid",
  name: ADMIN ? "rkm" : "Geetanjali",
  is_admin: ADMIN,
  has_password: true,
  disabled: false,
  last_login: "",
};

const MOVIE = {
  item_id: "i1",
  title: "The Matrix",
  year: 1999,
  media_type: "movie",
  played: false,
  playback_position: 0,
  runtime: 8160,
};

const calls: { url: string; method: string }[] = [];

window.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const raw = typeof input === "string" ? input : String((input as Request).url ?? input);
  const path = raw.slice(raw.indexOf("/api"));
  const method = String(init.method || "GET").toUpperCase();
  calls.push({ url: path, method });
  const send = (payload: unknown) =>
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "content-type": "application/json" },
    });

  if (path === "/api/auth/me" || path === "/api/auth/profiles") {
    if (SIGNED_OUT) {
      return new Response(JSON.stringify({ detail: "Sign in to use this app" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      });
    }
  }
  if (path === "/api/auth/me") {
    return send({
      user: { id: "uid-admin", name: "rkm" },
      profile: { id: PROFILE.id, name: PROFILE.name },
      profile_selected: true,
      on_own_profile: ADMIN,
      expires: "2026-10-12T00:00:00Z",
    });
  }
  if (path === "/api/auth/profiles") {
    return send({ profiles: [PROFILE], current: PROFILE, profile_selected: true, warning: "" });
  }
  // -- the library reads the two views use ------------------------------------------------
  if (path === "/api/library/items") {
    return send({ provider: "jellyfin", items: EMPTY ? [] : [MOVIE], warnings: [] });
  }
  if (path === "/api/library/continue-watching" || path === "/api/library/recently-watched") {
    return send({ provider: "jellyfin", items: [], warnings: [] });
  }
  if (path === "/api/library") {
    return send({ provider: "jellyfin", available: true, counts: {}, recent: EMPTY ? [] : [MOVIE] });
  }
  if (path === "/api/library/folders") {
    return send({
      libraries: [
        {
          name: "Movies",
          path: "/data/Movies",
          folder_id: "f1",
          collection_type: "movies",
          ok: true,
          warning: "",
        },
      ],
      warnings: [],
    });
  }
  if (path.startsWith("/api/library/folders/")) {
    return send({ provider: "jellyfin", items: EMPTY ? [] : [MOVIE], folder_id: "f1", warnings: [] });
  }
  // -- the route under test -----------------------------------------------------------------
  if (path === "/api/library/scan") {
    // A REAL administrator lands here and the gate passes; a member never gets this far. The
    // check asserts on the CALL COUNT, so a control that is offered to a member is visible even
    // without a click.
    return send({ name: "library_scan", status: "success", items_processed: 1, counts: {} });
  }
  return send({});
}) as typeof fetch;

const scanControl = () =>
  [...document.querySelectorAll("button")].find(
    (b) => (b.textContent || "").includes("Scan Library") || (b.getAttribute("aria-label") || "") === "Scan Library",
  ) as HTMLButtonElement | undefined;

(window as unknown as { __probe: () => unknown }).__probe = () => ({
  calls: [...calls],
  scanCalls: calls.filter((c) => c.url === "/api/library/scan"),
  scanButtons: document.querySelectorAll("button").length,
  hasScanControl: Boolean(scanControl()),
  hasHeroScan: Boolean(
    document.querySelector('button[aria-label="Scan Library"]'),
  ),
  body: document.body.textContent ?? "",
});

function Frame() {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false } } }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[FOLDER ? "/library/folder/f1" : "/library/home"]}>
          <div className="min-h-dvh bg-canvas text-zinc-100">
            <Routes>
              <Route path="/library" element={<LibraryLayout />}>
                <Route path="home" element={<LibraryHomeView />} />
                <Route path="folder/:folderId" element={<LibraryFolderView />} />
              </Route>
            </Routes>
            <Toaster />
          </div>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
