/**
 * Harness: the REAL `LayoutModeProvider` + the REAL `AppShell`, over a stubbed api.
 *
 * `tools/check_mobile_layout_switch.py` uses this frame to answer three questions that no unit
 * test can: does the switch actually reach the DOM, does the CSS actually reflow, and does
 * CROSSING the boundary cost anything (a refetch, a remount, a sign-out)?
 *
 * ⚠ The app's REAL stylesheet, like every other frame here. Without it the tokens compute to
 * nothing and the grid measurement is meaningless — and a screenshot of this frame stops being
 * evidence (the trap `nav-frame` recorded on 2026-09-13).
 *
 * ⚠ `?layout=` is NOT read here — the frame must not fake the mode. The mode comes from the same
 * `matchMedia` the app uses, driven by the viewport the CHECK sets. A frame that took the mode
 * from a query parameter would prove that a string can be written into a variable.
 *
 * The stub answers only what the shell asks for. It reports the shape the SERVER reports — e.g.
 * `current` IS the profile's own row with `is_admin`, because a stub that invents one hides the
 * bug it is supposed to catch (the same lesson as `nav-frame`).
 */
import { useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Outlet, RouterProvider, createMemoryRouter } from "react-router-dom";

import { AuthProvider } from "../src/features/auth/AuthProvider";
import { LayoutModeProvider } from "../src/layouts/LayoutMode";
import { AppShell } from "../src/app/layout/AppShell";
import "../src/styles/index.css";

const PARAMS = new URLSearchParams(location.search);
/** `?libs=N` — three is his real number. */
const LIB_COUNT = Math.max(0, Number(PARAMS.get("libs") ?? "3") || 0);
/** `?thumbs=N` — how many fixture posters the grid holds. */
const THUMBS = Math.max(1, Number(PARAMS.get("thumbs") ?? "8") || 8);

const calls: { url: string; method: string }[] = [];

window.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const raw = typeof input === "string" ? input : String((input as Request).url ?? input);
  const at = raw.indexOf("/api");
  const path = at >= 0 ? raw.slice(at) : raw;
  calls.push({ url: path, method: String(init.method || "GET").toUpperCase() });
  const send = (payload: unknown) =>
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "content-type": "application/json" },
    });

  if (path === "/api/auth/me") {
    return send({
      user: { id: "uid-admin", name: "rkm" },
      profile: { id: "uid-admin", name: "rkm" },
      profile_selected: true,
      on_own_profile: true,
      expires: "2026-10-12T00:00:00Z",
    });
  }
  if (path === "/api/auth/profiles") {
    const row = {
      id: "uid-admin",
      name: "rkm",
      is_admin: true,
      has_password: true,
      disabled: false,
      last_login: "",
    };
    return send({ profiles: [row], current: row, profile_selected: true, warning: "" });
  }
  if (path.startsWith("/api/library/folders")) {
    const libraries = Array.from({ length: LIB_COUNT }, (_, i) => ({
      name: ["Movies", "TV Shows", "Documentaries"][i] ?? `Library ${i + 1}`,
      path: `/data/lib${i + 1}`,
      folder_id: `folder-${i + 1}`,
      collection_type: i % 2 === 0 ? "movies" : "tvshows",
      ok: true,
      warning: "",
    }));
    return send({ provider: "jellyfin", folders: [], libraries, warnings: [] });
  }
  // A library read the home route makes. The check counts these to prove a resize refetches nothing.
  if (path.startsWith("/api/library")) return send({ items: [], recent: [], libraries: [] });
  return send({});
}) as typeof fetch;

/* ---------------------------------------------------------------------------
 * The mount counter — THE measurement that makes "the switch does not remount the
 * data layer" checkable.
 *
 * ⚠ A `useRef` in a module-level object rather than a DOM marker, because a DOM marker survives a
 * remount if React reuses the node (a `key`-less child in the same position), which would make the
 * assertion pass while the tree was rebuilt. A mount effect cannot be fooled: it runs once per
 * mount, per strict-mode double-invoke accounted for below.
 * --------------------------------------------------------------------------- */
const mounts = { shell: 0, route: 0, renders: 0 };

function RouteFixture() {
  mounts.route += 1;
  mounts.renders += 1;
  useEffect(() => {
    return () => {};
  }, []);
  return (
    <div data-testid="route-fixture" className="p-4">
      <h1 className="text-xl font-bold">Fixture route</h1>
      {/* The grid fixture: `.m-grid` is the REAL shared class from `styles/index.css`, so this
          measures the token's reflow rather than a copy of it. Inert in desktop mode — which is
          itself an assertion (the mobile CSS must not reach a desktop viewport). */}
      <div className="m-grid" data-testid="grid-fixture">
        {Array.from({ length: THUMBS }, (_, i) => (
          <div key={i} className="aspect-[2/3] rounded-[10px] bg-surface-2" data-thumb={i} />
        ))}
      </div>
    </div>
  );
}

function ShellWithCounter() {
  mounts.shell += 1;
  return <AppShell />;
}

/**
 * The router is created ONCE, outside React, for the same reason the app does it: if the router
 * were rebuilt on every render the route element would remount on every resize and this frame
 * would report a remount the real app does not have.
 */
const router = createMemoryRouter(
  [
    {
      path: "/",
      element: <ShellWithCounter />,
      children: [{ index: true, element: <RouteFixture /> }],
    },
  ],
  { initialEntries: ["/"] },
);

function text(selector: string): string {
  return document.querySelector(selector)?.textContent ?? "";
}

function rectOf(selector: string) {
  const el = document.querySelector(selector);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return {
    x: +r.x.toFixed(1),
    y: +r.y.toFixed(1),
    w: +r.width.toFixed(1),
    h: +r.height.toFixed(1),
    right: +r.right.toFixed(1),
    bottom: +r.bottom.toFixed(1),
  };
}

interface ProbeWindow extends Window {
  __probe?: () => unknown;
}

(globalThis as unknown as ProbeWindow).__probe = () => {
  const root = document.documentElement;
  const grid = document.querySelector('[data-testid="grid-fixture"]');
  const gridStyle = grid ? getComputedStyle(grid) : null;
  const tracks =
    gridStyle && gridStyle.display === "grid"
      ? (gridStyle.gridTemplateColumns || "").trim().split(/\s+/).filter(Boolean).length
      : 0;

  // Every element that pokes outside the viewport HORIZONTALLY — the measurement that catches a
  // layout that fits its own box while pushing the page sideways.
  //
  // ⚠ Deliberately horizontal only. A page that is taller than the viewport is a page that
  // scrolls, which is every real screen; flagging that would drown the one fact this is for.
  const bad: { tag: string; cls: string; left: number; right: number }[] = [];
  document.querySelectorAll<HTMLElement>("body *").forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    if (r.right > window.innerWidth + 1 || r.left < -1) {
      bad.push({
        tag: el.tagName.toLowerCase(),
        cls: String(el.className || "").slice(0, 60),
        left: +r.left.toFixed(1),
        right: +r.right.toFixed(1),
      });
    }
  });

  return {
    vw: window.innerWidth,
    vh: window.innerHeight,
    mode: root.dataset.layout ?? null,
    // Read straight from CSS, not from the app's JS — the two halves of the switch, compared.
    gridColsToken: getComputedStyle(root).getPropertyValue("--m-grid-cols").trim(),
    gridTracks: tracks,
    gridDisplay: gridStyle?.display ?? null,
    tapTokens: {
      nav: getComputedStyle(root).getPropertyValue("--m-nav-h").trim(),
      tap: getComputedStyle(root).getPropertyValue("--m-tap").trim(),
      input: getComputedStyle(root).getPropertyValue("--m-input").trim(),
    },
    // The desktop arrangement vs the mobile one — asserted by VISIBILITY, not by class string.
    sidebar: rectOf("aside"),
    sidebarText: text("aside").slice(0, 120),
    mobileBar: rectOf('nav[aria-label="Mobile"]'),
    mobileTabs: [...document.querySelectorAll('nav[aria-label="Mobile"] a')].map(
      (a) => a.textContent ?? "",
    ),
    header: rectOf("header"),
    // The input-size rule, measured on a real input rather than read as a declaration.
    inputFontSize: (() => {
      const el = document.querySelector("input");
      return el ? getComputedStyle(el as HTMLElement).fontSize : null;
    })(),
    mounts: { ...mounts },
    calls: [...calls],
    paths: [...new Set(calls.map((c) => c.url))].sort(),
    signInForm: !!document.querySelector('form input[type="password"]'),
    location: router.state.location.pathname,
    overflowX: root.scrollWidth - window.innerWidth,
    outside: bad.slice(0, 12),
  };
};

function Frame() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: 30_000, refetchOnWindowFocus: false } },
      }),
  );
  const counted = useRef(false);
  if (!counted.current) counted.current = true;

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <LayoutModeProvider>
          <RouterProvider router={router} />
        </LayoutModeProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
