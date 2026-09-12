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

const ADMIN = new URLSearchParams(location.search).get("admin") !== "0";

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
    return send({ libraries: [], warnings: [] });
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
