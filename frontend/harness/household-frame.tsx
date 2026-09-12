/**
 * Household screen harness (sandbox, not shipped).
 *
 * Mounts the REAL `HouseholdView` (and the real query client + auth provider) over a stubbed
 * api, so `tools/check_household_ui.py` can prove in a browser what the screen actually renders
 * and what it actually posts:
 *
 *   ?admin=1  — a Jellyfin administrator: the household lists, access resolves to NAMES, the
 *               rails disable Remove where the server would refuse, and adding a member posts
 *               a blank password + only the ticked folders.
 *   ?admin=0  — a non-administrator session: the screen must say so plainly instead of looking
 *               broken or, worse, appearing to work.
 *
 * `window.__calls` records every stubbed request (url, method, body) and `window.__probe()`
 * reports what is on screen.
 */
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AuthProvider } from "../src/features/auth/AuthProvider";
import { HouseholdView } from "../src/features/admin/HouseholdView";
import { Header } from "../src/app/layout/Header";
import "../src/styles/index.css";

const params = new URLSearchParams(window.location.search);
const AS_ADMIN = params.get("admin") !== "0";

interface Call {
  url: string;
  method: string;
  body: string;
  status: number;
}

const calls: Call[] = [];
(window as unknown as { __calls: Call[] }).__calls = calls;

const ADMIN_ID = "uid-admin";
const GUEST_ID = "uid-guest";

const LIBRARY_ROWS = [
  { id: "f1", name: "Movies", collection_type: "movies", path: "/data/Movies" },
  { id: "f2", name: "TV Shows", collection_type: "tvshows", path: "/media2/TV Shows" },
];

function household() {
  return {
    users: [
      { id: ADMIN_ID, name: "admin", is_admin: true, disabled: false, has_password: true,
        enable_all_folders: true, enabled_folders: [], last_login: "2026-09-12T07:25:10Z" },
      { id: GUEST_ID, name: "Guest", is_admin: false, disabled: false, has_password: false,
        enable_all_folders: false, enabled_folders: ["f1"], last_login: "" },
    ],
    signed_in_as: ADMIN_ID,
    warning: "",
  };
}

let householdBody = household();

window.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const raw = typeof input === "string" ? input : String((input as Request).url ?? input);
  const method = String(init.method || "GET").toUpperCase();
  const path = raw.slice(raw.indexOf("/api"));
  const body = String(init.body ?? "");

  const send = (status: number, payload: unknown = null) => {
    calls.push({ url: path, method, body, status });
    const text = payload === null ? "" : JSON.stringify(payload);
    return new Response(text, { status, headers: { "content-type": "application/json" } });
  };

  if (path === "/api/auth/me") {
    return send(200, { user: { id: ADMIN_ID, name: "admin" }, expires: "2026-10-12T00:00:00Z" });
  }
  if (path === "/api/admin/libraries") {
    return AS_ADMIN
      ? send(200, { libraries: LIBRARY_ROWS, warning: "" })
      : send(403, { detail: "Only a Jellyfin administrator can manage household accounts" });
  }
  if (path === "/api/admin/users" && method === "GET") {
    return AS_ADMIN
      ? send(200, householdBody)
      : send(403, { detail: "Only a Jellyfin administrator can manage household accounts" });
  }
  if (path === "/api/admin/users" && method === "POST") {
    const parsed = JSON.parse(body || "{}") as { name?: string };
    // Echo the created member back the way the API does, so the list refreshes visibly.
    householdBody = {
      ...householdBody,
      users: [
        ...householdBody.users,
        {
          id: "uid-new",
          name: String(parsed.name ?? "New"),
          is_admin: false,
          disabled: false,
          has_password: Boolean((JSON.parse(body || "{}") as { password?: string }).password),
          enable_all_folders: false,
          enabled_folders: ((JSON.parse(body || "{}") as { library_ids?: string[] })
            .library_ids) ?? [],
          last_login: "",
        },
      ],
    };
    return send(200, { ok: true, user: householdBody.users.at(-1), granted: [], warning: "" });
  }
  if (path.includes("/policy")) return send(200, { ok: true, user: householdBody.users[1], was: "Guest" });
  if (path.includes("/password")) return send(200, { ok: true });
  if (method === "DELETE") {
    const name = (JSON.parse(body || "{}") as { confirm_name?: string }).confirm_name ?? "";
    return send(200, { ok: true, name });
  }
  return send(200, {});
}) as typeof fetch;

(window as unknown as { __probe: () => unknown }).__probe = () => {
  const text = (selector: string) => document.querySelector(selector)?.textContent?.trim() ?? "";
  const rows = [...document.querySelectorAll('[data-testid^="member-"]')].map((row) => {
    const remove = [...row.querySelectorAll("button")].find((b) =>
      (b.textContent || "").trim() === "Remove");
    return {
      name: (row.getAttribute("data-testid") || "").replace("member-", ""),
      text: (row.textContent || "").replace(/\s+/g, " ").trim(),
      removeDisabled: remove ? (remove as HTMLButtonElement).disabled : null,
    };
  });
  const confirmButton = [...document.querySelectorAll("button")].find((b) =>
    (b.textContent || "").trim() === "Remove member");
  return {
    calls: [...calls],
    rows,
    addForm: !!document.querySelector('[data-testid="add-member-form"]'),
    folderTicks: !!document.querySelector('[data-testid="folder-ticks"]'),
    refusal: text('[role="alert"]'),
    confirmEnabled: confirmButton ? !(confirmButton as HTMLButtonElement).disabled : null,
    body: document.body.innerText,
  };
};

/** The real screen, plus the real Header inside a router (the view links nothing itself). */
function Frame() {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/library/home"]}>
          <div className="min-h-dvh bg-canvas text-zinc-100">
            <Header />
            <main className="mx-auto max-w-[1100px] p-6">
              <HouseholdView />
            </main>
          </div>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
