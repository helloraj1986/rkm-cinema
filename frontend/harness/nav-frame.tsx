/**
 * Harness: the REAL `Header`, `Sidebar` and `MobileNav` over a stubbed api.
 *
 * `tools/check_nav_access.py` uses this to prove the account destinations (My password, Household)
 * are offered to administrators and NOT to members — on BOTH surfaces, which are separate code
 * paths: the header avatar (every breakpoint) and the sidebar footer (desktop).
 *
 * History worth keeping: until 2026-09-13 the sidebar and the mobile sheet carried their own copies
 * of those links. The check passed while the real app hid Household from the ADMINISTRATOR too,
 * because this stub handed the UI an `is_admin` the server was incapable of sending — `current` was
 * built backend-side as `ProfileUser(id=…, name=…)`, leaving `is_admin` at its False default. The
 * stub below therefore mirrors what `/api/auth/profiles` really answers: `current` IS the profile's
 * row (see `TestProfiles::test_the_current_profile_carries_the_SERVERS_own_answer`).
 *
 * `?admin=1` — the profile in effect is an administrator. `?admin=0` — it is a member.
 */
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AuthProvider } from "../src/features/auth/AuthProvider";
import { Header } from "../src/app/layout/Header";
import { Sidebar } from "../src/app/layout/Sidebar";
import { MobileNav } from "../src/app/layout/MobileNav";
// The app's REAL stylesheet, like every other frame in this directory. Without it the check still
// proves what it asserts (visibility is by TEXT), but any screenshot or geometry measurement of
// this frame is unstyled — which is how the account menu's screenshots came out full-width once
// (2026-09-13), and it is the kind of difference that makes a picture worthless as evidence.
import "../src/styles/index.css";

const PARAMS = new URLSearchParams(location.search);
const ADMIN = PARAMS.get("admin") !== "0";

/**
 * `?libs=N` — how many libraries the stubbed profile can see. **Three is his real number**, and the
 * reason `tools/check_nav_access.py` scenario F exists: on the iPad only two of the three were
 * reachable at a glance (2026-09-14).
 */
const LIB_COUNT = Math.max(0, Number(PARAMS.get("libs") ?? "0") || 0);

/** `?broken=1` — add ONE library the server could not resolve (`ok: false`, no folder id). */
const BROKEN = PARAMS.get("broken") === "1";

/** His real names first, so a screenshot of this frame looks like the screen he reported. */
const LIB_NAMES = [
  "Movies Kids",
  "Movies",
  "TV Shows",
  "Documentaries",
  "Home Videos",
  "Concerts",
  "Workouts",
  "Music",
];

const PROFILE = {
  id: ADMIN ? "uid-admin" : "uid-kid",
  name: ADMIN ? "rkm" : "Geetanjali",
  is_admin: ADMIN,
  has_password: true,
  disabled: false,
  last_login: "",
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
    return send({
      profiles: [PROFILE],
      // The server's own row for the profile in effect — NOT a name-only stub (see the header).
      current: PROFILE,
      profile_selected: true,
      warning: "",
    });
  }
  if (path.startsWith("/api/library/folders")) {
    const libraries: {
      name: string;
      path: string;
      folder_id: string | null;
      collection_type: string;
      ok: boolean;
      warning: string;
    }[] = Array.from({ length: LIB_COUNT }, (_, i) => ({
      name: LIB_NAMES[i] ?? `Library ${i + 1}`,
      path: `/data/lib${i + 1}`,
      folder_id: `folder-${i + 1}`,
      collection_type: i % 2 === 0 ? "movies" : "tvshows",
      ok: true,
      warning: "",
    }));
    if (BROKEN) {
      // A library the profile IS entitled to, whose folder the server could not resolve — the case
      // the mobile bar used to drop silently while the sidebar showed it with a warning.
      libraries.push({
        name: "Old Drive",
        path: "B:/gone",
        folder_id: null,
        collection_type: "mixed",
        ok: false,
        warning: "folder not found on the server",
      });
    }
    return send({ provider: "jellyfin", folders: [], libraries, warnings: [] });
  }
  return send({});
}) as typeof fetch;

function text(selector: string): string {
  return document.querySelector(selector)?.textContent ?? "";
}

(window as unknown as { __probe: () => unknown }).__probe = () => ({
  calls: [...calls],
  // The whole sidebar, not just its <nav>: the Settings link is rendered after the nav element.
  sidebar: text("aside"),
  header: text("header"),
  sheet: text('[aria-label="More destinations"]'),
  // The account menu is PORTALLED to <body>; the mobile sheet is not — so this picks the menu even
  // when both are open.
  accountMenu: [...document.querySelectorAll('[role="menu"]')]
    .filter((m) => !m.closest('nav[aria-label="Mobile"]'))
    .map((m) => m.textContent ?? "")
    .join(" | "),
  accountTriggers: {
    header: !!document.querySelector('header [aria-haspopup="menu"]'),
    sidebar: !!document.querySelector('aside [aria-haspopup="menu"]'),
  },
  // The MOBILE BAR — the surface his iPad report was about (`check_nav_access.py` scenario F).
  // Tab labels only, so the check can say exactly which libraries are one tap away.
  mobileTabs: [...document.querySelectorAll('nav[aria-label="Mobile"] a')].map(
    (a) => a.textContent ?? "",
  ),
  mobileBar: text('nav[aria-label="Mobile"] > div:last-child'),
  // The "there is something behind More" dot.
  mobileBadge: !!document.querySelector('nav[aria-label="Mobile"] button [aria-hidden="true"]'),
  mobileUnavailable: [...document.querySelectorAll('nav[aria-label="Mobile"] [aria-label$="— unavailable"]')]
    .map((n) => n.getAttribute("aria-label") ?? ""),
  // ⚠ Horizontal overflow is how a measured layout fails: a bar that fits its own box while pushing
  // the page sideways is still broken on the device it was measured on.
  overflowX: document.documentElement.scrollWidth - window.innerWidth,
});

function Frame() {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false } } }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/library/home"]}>
          <div className="min-h-dvh bg-canvas text-zinc-100">
            <div className="flex min-h-dvh">
              <Sidebar />
              <div className="flex min-w-0 flex-1 flex-col">
                <Header />
              </div>
            </div>
            <MobileNav />
          </div>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
