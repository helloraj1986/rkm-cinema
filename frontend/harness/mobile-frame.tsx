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
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createMemoryRouter } from "react-router-dom";

import { AuthProvider } from "../src/features/auth/AuthProvider";
import { LayoutModeProvider } from "../src/layouts/LayoutMode";
import { AppShell } from "../src/app/layout/AppShell";
import { Sheet } from "../src/components/ui/Sheet";
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

/** Live state the route fixture publishes so the check can read it (see `sheetOpen` in the probe). */
const live = { sheetOpen: false };

function RouteFixture() {
  mounts.route += 1;
  mounts.renders += 1;
  const [sheetOpen, setSheetOpen] = useState(false);
  // The sheet's state is published so the check can watch it CLOSE, not merely stop rendering.
  live.sheetOpen = sheetOpen;
  return (
    <div data-testid="route-fixture" className="p-4">
      <h1 className="text-xl font-bold">Fixture route</h1>

      {/* A real trigger for the real `Sheet`. The sheet itself is NOT a fixture: it is the production
          component, portalled to `body` exactly as it is in the app, so what the check drives is the
          gesture and the lock rather than a mock of them. */}
      <button
        type="button"
        data-testid="open-sheet"
        onClick={() => setSheetOpen(true)}
        className="mt-3 rounded-[10px] bg-accent px-4 py-2 text-sm font-bold text-black"
      >
        Open sheet
      </button>

      {sheetOpen && (
        <Sheet labelledBy="fixture-sheet-title" onClose={() => setSheetOpen(false)}>
          <div className="px-5 pb-5 pt-1">
            <h2 id="fixture-sheet-title" className="text-base font-semibold">
              Fixture sheet
            </h2>
            <p className="mt-1 text-sm text-zinc-400">
              A sheet is dismissed by dragging it down, not by hunting for an X.
            </p>
            {/* Enough rows to make the sheet scroll, so the lock and overscroll can be measured. */}
            {Array.from({ length: 14 }, (_, i) => (
              <button
                key={i}
                type="button"
                data-testid="sheet-row"
                className="mt-2 block w-full rounded-lg bg-white/[.04] px-3 py-3 text-left text-sm"
              >
                Row {i + 1}
              </button>
            ))}
          </div>
        </Sheet>
      )}

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
      children: [
        { index: true, element: <RouteFixture /> },
        // A catch-all inside the shell, so a tab tap actually navigates and the check can watch the
        // location change. ⚠ Without it, tapping a library tab would navigate to a route with no
        // element and the frame would render an empty page — which is indistinguishable from "the
        // tap did nothing", the very thing the assertion is for.
        { path: "*", element: <RouteFixture /> },
      ],
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
    // The tab bar's own geometry — the thumb-zone question, as numbers.
    tabBar: rectOf('nav[aria-label="Mobile"]'),
    tabRects: [...document.querySelectorAll('nav[aria-label="Mobile"] > div:last-child > *')].map(
      (el) => {
        const r = el.getBoundingClientRect();
        return {
          label: (el.textContent ?? "").trim().slice(0, 20),
          w: +r.width.toFixed(1),
          h: +r.height.toFixed(1),
        };
      },
    ),
    tabBarBottomGap: (() => {
      const r = document.querySelector('nav[aria-label="Mobile"]')?.getBoundingClientRect();
      return r ? +(window.innerHeight - r.bottom).toFixed(1) : null;
    })(),
    /**
     * ⚠ THE CLEARANCE, as a measured number: how much room the page's own bottom padding leaves for
     * the fixed bar. This is the pair that put the bar ON TOP of the page on his phone — a flat 96px
     * of padding against a 64px bar PLUS a 34px home-indicator inset, i.e. −2px.
     *
     * ⚠ It cannot be reproduced here (`env(safe-area-inset-bottom)` is 0px in every desktop browser),
     * which is exactly why the padding must be DERIVED from the inset rather than written as a number:
     * `shell-contract.test.ts` pins the expression, and this measures the result on an inset-free
     * device where the two must agree.
     */
    navHeight: (() => {
      const el = document.querySelector('nav[aria-label="Mobile"]');
      return el ? +el.getBoundingClientRect().height.toFixed(1) : null;
    })(),
    /**
     * ⚠ The bar's ROW height, which is what `--m-nav-h` describes — NOT the nav's total height.
     *
     * The nav is taller than its row by 1px (its top border) and by the device's bottom inset, so
     * comparing the token to `navHeight` reports "the token and the bar have drifted" on a correct
     * build, and reports it as 65px on an inset-free one. Two different questions: the token is the
     * ROW, the clearance is the TOTAL.
     */
    navRowHeight: (() => {
      const el = document.querySelector('nav[aria-label="Mobile"] > div:last-child');
      return el ? +el.getBoundingClientRect().height.toFixed(1) : null;
    })(),
    navToken: getComputedStyle(root).getPropertyValue("--m-nav-h").trim(),
    contentBottomPad: (() => {
      const el = document.querySelector("main > div");
      return el ? getComputedStyle(el).paddingBottom : null;
    })(),
    tabHrefs: [...document.querySelectorAll<HTMLAnchorElement>('nav[aria-label="Mobile"] a')].map(
      (a) => a.getAttribute("href") ?? "",
    ),
    // ⚠ The measured font-size of a real input, not a declaration: the 16px rule is invisible in
    // every screenshot and is the difference between a usable form and one that zooms the page.
    inputFontSize: (() => {
      const el = document.querySelector("input");
      return el ? getComputedStyle(el as HTMLElement).fontSize : null;
    })(),
    // The sheet, as the check sees it: open, where it sits, whether the body is locked, and whether
    // the rows really scroll.
    sheetOpen: live.sheetOpen,
    sheetPanel: rectOf('[data-testid="sheet-panel"]'),
    sheetRadius: (() => {
      const el = document.querySelector<HTMLElement>('[data-testid="sheet-panel"]');
      return el ? getComputedStyle(el).borderTopLeftRadius : null;
    })(),
    sheetScrollable: (() => {
      const el = document.querySelector<HTMLElement>('[data-testid="sheet-panel"]');
      return el ? el.scrollHeight > el.clientHeight + 1 : null;
    })(),
    sheetOverscroll: (() => {
      const el = document.querySelector<HTMLElement>('[data-testid="sheet-panel"]');
      return el ? getComputedStyle(el).overscrollBehaviorY : null;
    })(),
    bodyLock: {
      position: document.body.style.position,
      top: document.body.style.top,
      overflow: document.body.style.overflow,
    },
    focusInSheet: (() => {
      const panel = document.querySelector('[data-testid="sheet-panel"]');
      return !!panel && !!document.activeElement && panel.contains(document.activeElement);
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
