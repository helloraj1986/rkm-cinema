/**
 * Household screen harness (sandbox, not shipped).
 *
 * Mounts the REAL `HouseholdView` (and the real query client + auth provider) over a stubbed
 * api, so `tools/check_household_ui.py` can prove in a browser what the screen actually renders
 * and what it actually posts — now for the REDESIGNED screen (HOUSEHOLD_UX_PLAN.md Phase 1):
 * a header, three summary cards, one card per profile, and every action behind a modal.
 *
 *   ?admin=1  — a Jellyfin administrator: the household lists, the summary counts, chips resolve
 *               to library NAMES, a password-less member says so, the rails keep Rename/Disable/
 *               Remove OFF your own card, and every modal posts the same body the old inline form
 *               did.
 *   ?admin=0  — a non-administrator session: the screen must say so plainly instead of looking
 *               broken or, worse, appearing to work.
 *
 * ⚠ The stub is deliberately faithful, not generous — the differences that matter here are the
 * ones that once made a correct screen look broken or a broken one look correct:
 *  * `/api/admin/libraries` and `/api/admin/users` answer **403** to a non-administrator;
 *  * `/api/auth/profiles` carries the SERVER's own row for the profile in effect (`current` with
 *    `is_admin`), which is what the header's account menu gates on (a name-only stub hid Household
 *    from the administrator — ADMIN_CREDENTIALS_PLAN §6g);
 *  * a `/policy` write MUTATES the fixture, so "the chips and the counts update after saving"
 *    is proved by the next render rather than assumed.
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
const DISABLED_ID = "uid-meenu";

const LIBRARY_ROWS = [
  { id: "f1", name: "Movies", collection_type: "movies", path: "/data/Movies" },
  { id: "f2", name: "TV Shows", collection_type: "tvshows", path: "/media2/TV Shows" },
];

/** The admin profile's own row — the shape `/api/auth/profiles` really sends as `current`. */
const PROFILE = {
  id: ADMIN_ID,
  name: "admin",
  is_admin: true,
  disabled: false,
  has_password: true,
  enable_all_folders: true,
  enabled_folders: [],
  last_login: "2026-09-12T07:25:10Z",
};

function household() {
  return {
    users: [
      { ...PROFILE },
      {
        id: GUEST_ID,
        name: "Guest",
        is_admin: false,
        disabled: false,
        has_password: false,
        enable_all_folders: false,
        enabled_folders: ["f1"],
        last_login: "",
      },
      {
        id: DISABLED_ID,
        name: "meenu",
        is_admin: false,
        disabled: true,
        has_password: true,
        enable_all_folders: false,
        enabled_folders: ["f2"],
        last_login: "2026-09-01T22:10:00Z",
      },
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
  const parse = () => JSON.parse(body || "{}") as Record<string, unknown>;
  const patchUser = (id: string, patch: Record<string, unknown>) => {
    householdBody = {
      ...householdBody,
      users: householdBody.users.map((u) => (u.id === id ? { ...u, ...patch } : u)),
    };
    return householdBody.users.find((u) => u.id === id) ?? householdBody.users[0];
  };
  const idFromPath = () => decodeURIComponent(path.split("/").slice(-2, -1)[0] ?? "");

  if (path === "/api/auth/me") {
    return send(200, {
      user: { id: ADMIN_ID, name: "admin" },
      expires: "2026-10-12T00:00:00Z",
      profile_selected: true,
    });
  }
  if (path === "/api/auth/profiles") {
    // The server's own answer: `current` IS the profile's row (admin when ?admin=1).
    const current = AS_ADMIN ? PROFILE : { ...PROFILE, name: "Guest", is_admin: false };
    return send(200, { profiles: householdBody.users, current, profile_selected: true, warning: "" });
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
    const parsed = parse();
    const ids = (parsed.library_ids as string[]) ?? [];
    const created = {
      id: "uid-new",
      name: String(parsed.name ?? "New"),
      is_admin: false,
      disabled: false,
      has_password: Boolean(parsed.password),
      enable_all_folders: false,
      enabled_folders: ids,
      last_login: "",
    };
    householdBody = { ...householdBody, users: [...householdBody.users, created] };
    return send(200, { ok: true, user: created, granted: ids, warning: "" });
  }
  if (path.endsWith("/policy")) {
    const parsed = parse();
    const patch: Record<string, unknown> = {};
    // Exactly the server's reading: an EMPTY list is what the account may see (the route passes it
    // straight to `set_folder_access`, whose `enable_all` defaults to False — see the check's
    // regression guard for the `[]`-means-nothing trap).
    if (Array.isArray(parsed.library_ids)) {
      patch.enabled_folders = parsed.library_ids;
      patch.enable_all_folders = false;
    }
    if (typeof parsed.disabled === "boolean") patch.disabled = parsed.disabled;
    const updated = patchUser(idFromPath(), patch);
    return send(200, { ok: true, user: updated, was: "Guest" });
  }
  if (path.endsWith("/rename")) {
    const updated = patchUser(idFromPath(), { name: String(parse().name ?? "") });
    return send(200, { ok: true, user: updated, was: "Guest", warning: "" });
  }
  if (path.endsWith("/password")) return send(200, { ok: true });
  if (method === "DELETE") {
    const name = String(parse().confirm_name ?? "");
    return send(200, { ok: true, name });
  }
  return send(200, {});
}) as typeof fetch;

(window as unknown as { __probe: () => unknown }).__probe = () => {
  const text = (selector: string) => document.querySelector(selector)?.textContent?.trim() ?? "";
  const modal = document.querySelector('[role="dialog"]');
  const modalText = (modal?.textContent || "").replace(/\s+/g, " ").trim();
  const rows = [...document.querySelectorAll('[data-testid^="member-"]')]
    .filter((row) => !(row.getAttribute("data-testid") || "").startsWith("member-more-"))
    .map((row) => {
      const name = (row.getAttribute("data-testid") || "").replace("member-", "");
      const buttons = [...row.querySelectorAll("button")].map((b) =>
        (b.textContent || "").replace(/\s+/g, " ").trim(),
      );
      return {
        name,
        text: (row.textContent || "").replace(/\s+/g, " ").trim(),
        buttons,
        badges: [...row.querySelectorAll('[data-testid^="badge-"]')].map((b) =>
          (b.textContent || "").trim(),
        ),
        chips: [...row.querySelectorAll('[data-testid="library-chip"]')].map((c) =>
          (c.textContent || "").trim(),
        ),
        // The ⋯ trigger is the only button in the card with no text — and it carries the testid.
        hasOverflow: !!document.querySelector(`[data-testid="member-more-${name}"]`),
      };
    });
  const summaryValue = (testId: string) =>
    Number(text(`[data-testid="${testId}"] p`) || "NaN");
  const removeButton = [...document.querySelectorAll('[role="dialog"] button')].find((b) =>
    (b.textContent || "").trim() === "Remove member",
  );
  return {
    calls: [...calls],
    rows,
    summary: {
      members: summaryValue("summary-members"),
      active: summaryValue("summary-active"),
      libraries: summaryValue("summary-libraries"),
    },
    addModal: !!document.querySelector('[data-testid="add-member-modal"]'),
    libraryModal: !!document.querySelector('[data-testid="library-modal"]'),
    passwordModal: !!document.querySelector('[data-testid="password-modal"]'),
    renameModal: !!document.querySelector('[data-testid="rename-modal"]'),
    removeModal: !!document.querySelector('[data-testid="remove-modal"]'),
    modalText,
    modalTitle: modal?.querySelector("h2")?.textContent?.trim() ?? "",
    /** Is every watched element inside the dialog? Proves the focus trap, not just its presence. */
    focusInsideModal: modal ? modal.contains(document.activeElement) : null,
    confirmEnabled: removeButton ? !(removeButton as HTMLButtonElement).disabled : null,
    refusal: text('[role="alert"]'),
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
