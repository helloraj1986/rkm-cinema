/**
 * Harness: the REAL `Sidebar` and `MobileNav` over a stubbed api.
 *
 * `tools/check_nav_access.py` uses this to prove the account-management entry is offered to
 * administrators and NOT to members — on both surfaces (his request, 2026-09-12). The desktop
 * sidebar and the mobile sheet are separate code paths, so both are mounted here.
 *
 * `?admin=1` — the profile in effect is an administrator. `?admin=0` — it is a member.
 */
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AuthProvider } from "../src/features/auth/AuthProvider";
import { Sidebar } from "../src/app/layout/Sidebar";
import { MobileNav } from "../src/app/layout/MobileNav";

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

(window as unknown as { __probe: () => unknown }).__probe = () => ({
  calls: [...calls],
  // The whole sidebar, not just its <nav>: the settings links (Settings / Household / My password)
  // are rendered after the nav element, and missing that put "Household" outside the probe.
  sidebar: document.querySelector("aside")?.textContent ?? "",
  body: document.body.innerText,
  sheet: document.querySelector('[aria-label="More destinations"]')?.textContent ?? "",
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
            <div className="hidden md:block">
              <Sidebar />
            </div>
            <MobileNav />
          </div>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
