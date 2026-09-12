/**
 * "Who's watching?" harness (sandbox, not shipped).
 *
 * Mounts the REAL `AuthProvider`, `RequireSession`, `ProfilesView` and `Header` over a STUBBED api
 * so `tools/check_profile_picker.py` can drive the picker in a real browser: which rows are offered,
 * which ones ask for a password, what a refusal says, where a selection lands, and — the assertion
 * that matters most — that the app NEVER appears while nobody has been chosen.
 *
 * Nothing here ships: `vite build` only builds /index.html. Query params:
 *   ?signedIn=0|1         — what GET /api/auth/me says at load
 *   ?profileSelected=0|1  — has the server already got a profile on this session?
 *   ?route=/app           — initial location
 *   ?next=/x              — what the picker was asked to return to
 *
 * `window.__calls` records every stubbed call (url, method, status, body) and `window.__probe()`
 * reports what is actually rendered — the tool asserts on those.
 */
import { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { api } from "../src/lib/api/client";
import { AuthProvider } from "../src/features/auth/AuthProvider";
import { RequireSession } from "../src/features/auth/RequireSession";
import { ProfilesView } from "../src/features/profiles/ProfilesView";
import { Header } from "../src/app/layout/Header";
import "../src/styles/index.css";

const params = new URLSearchParams(window.location.search);
const SIGNED_IN = params.get("signedIn") !== "0";
const PROFILE_SELECTED = params.get("profileSelected") === "1";

const ADMIN_PW = "admin-pw";
const LOCKED_PW = "locked-pw";

const OWNER = { id: "uid-admin", name: "admin" };

/**
 * The household this harness models — deliberately the LIVE shapes (Phase A's payloads), including
 * the two cases the picker must get right: a password-LESS member (created that way on purpose)
 * and an administrator whose profile always asks for a password.
 */
const PROFILES = [
  { id: "uid-admin", name: "admin", is_admin: true, has_password: true, disabled: false,
    last_login: "2026-09-12T07:25:10Z" },
  // An administrator who never set a password of their own. The picker MUST still ask (the server
  // refuses a blank attempt on that profile whatever the account holds — decision 3), which is what
  // makes this row worth modelling rather than assuming.
  { id: "uid-owner-nopw", name: "Owner", is_admin: true, has_password: false, disabled: false,
    last_login: "" },
  { id: "uid-guest", name: "Guest", is_admin: false, has_password: false, disabled: false,
    last_login: "" },
  { id: "uid-locked", name: "Locked", is_admin: false, has_password: true, disabled: false,
    last_login: "" },
  { id: "uid-off", name: "Off", is_admin: false, has_password: false, disabled: true,
    last_login: "" },
];

const GRANTS: Record<string, { id: string; name: string }[]> = {
  "uid-admin": [
    { id: "f1", name: "Movies" },
    { id: "f2", name: "TV Shows" },
    { id: "f3", name: "Movies Kids" },
  ],
  "uid-owner-nopw": [
    { id: "f1", name: "Movies" },
    { id: "f2", name: "TV Shows" },
    { id: "f3", name: "Movies Kids" },
  ],
  "uid-guest": [{ id: "f1", name: "Movies" }],
  "uid-locked": [{ id: "f2", name: "TV Shows" }],
  "uid-off": [],
};

interface Call {
  url: string;
  method: string;
  status: number;
  /** The request body as sent (so a check can prove what the picker POSTed). */
  body: string;
}

const calls: Call[] = [];
(window as unknown as { __calls: Call[] }).__calls = calls;

// Did app content EVER appear? A signed-in session with nobody chosen must go straight to the
// picker: asserting this catches the regression where the app mounts and is then replaced.
(window as unknown as { __sawAppContent: boolean }).__sawAppContent = false;
const observer = new MutationObserver(() => {
  if (document.querySelector('[data-testid="app-content"]')) {
    (window as unknown as { __sawAppContent: boolean }).__sawAppContent = true;
  }
});
observer.observe(document.documentElement, { childList: true, subtree: true });

let signedIn = SIGNED_IN;
let profileId = PROFILE_SELECTED ? "uid-admin" : "";

const current = () =>
  PROFILES.find((p) => p.id === profileId) ?? PROFILES[0];

window.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const raw = typeof input === "string" ? input : String((input as Request).url ?? input);
  const method = String(init.method || "GET").toUpperCase();
  const path = raw.slice(raw.indexOf("/api"));
  const body = String(init.body ?? "");

  const send = (status: number, payload: unknown = null) => {
    calls.push({ url: path, method, status, body });
    const text = payload === null ? "" : JSON.stringify(payload);
    return new Response(text, { status, headers: { "content-type": "application/json" } });
  };

  if (path === "/api/auth/me") {
    if (!signedIn) return send(401, { detail: "Not signed in" });
    return send(200, {
      user: OWNER,
      // The server's own fallback: with no profile chosen, the profile in effect is the owner's…
      profile: current(),
      on_own_profile: current().id === OWNER.id,
      // …and `profile_selected` is the ONLY thing that says whether anybody actually chose.
      profile_selected: Boolean(profileId),
      expires: "2026-10-12T00:00:00Z",
    });
  }

  if (path === "/api/auth/profiles") {
    if (!signedIn) return send(401, { detail: "Sign in to see the profiles on this server" });
    return send(200, {
      profiles: PROFILES,
      current: current(),
      profile_selected: Boolean(profileId),
      warning: "",
    });
  }

  if (path === "/api/auth/profile" && method === "POST") {
    if (!signedIn) return send(401, { detail: "Sign in before choosing a profile" });
    const parsed = JSON.parse(body || "{}") as { user_id?: string; password?: string };
    const target = PROFILES.find((p) => p.id === parsed.user_id);
    const password = parsed.password ?? "";
    if (!target) return send(404, { detail: "No such profile on this server" });
    if (target.disabled) {
      return send(403, { detail: "That profile is disabled — ask the administrator to enable it" });
    }
    // The shared-device rule, as the SERVER states it: a blank attempt never lands on the
    // administrator's profile (a deliberate non-empty one does, since there is nothing to
    // compare against when the account has no password of its own).
    if (target.is_admin && !password) {
      return send(401, { detail: "Enter the administrator's password to switch to that profile" });
    }
    if (target.has_password && password !== (target.is_admin ? ADMIN_PW : LOCKED_PW)) {
      return send(401, { detail: "That profile's password is not correct" });
    }
    profileId = target.id;
    return send(200, { ok: true, profile: target, libraries: GRANTS[target.id] ?? [] });
  }

  if (path === "/api/auth/login") {
    const parsed = JSON.parse(body || "{}") as { password?: string };
    if (parsed.password === ADMIN_PW) {
      signedIn = true;
      profileId = ""; // a fresh session has NO profile — that is the picker's trigger
      return send(200, { ok: true, user: OWNER, expires: "2026-10-12T00:00:00Z" });
    }
    return send(401, { detail: "Incorrect username or password" });
  }

  if (path === "/api/auth/logout") {
    signedIn = false;
    profileId = "";
    return send(200, { ok: true, revoked: true });
  }

  // Every other app call: this world is UNENFORCED (RKM_AUTH_REQUIRED=false), which is why the
  // picker is a screen and not a wall.
  return send(200, {});
}) as typeof fetch;

/** A stand-in Home page, so "the app is reachable" means something concrete. */
function FakeHome() {
  const [value, setValue] = useState("call in flight");
  useEffect(() => {
    api
      .getConfig()
      .then(() => setValue("app data loaded"))
      .catch(() => setValue("app data refused"));
  }, []);
  return (
    <div className="min-h-dvh bg-canvas text-zinc-100">
      <Header />
      <main className="p-6" data-testid="app-content">
        <h1 className="text-lg font-semibold">Harness home</h1>
        <p data-testid="app-value">{value}</p>
      </main>
    </div>
  );
}

(window as unknown as { __probe: () => unknown }).__probe = () => {
  const text = (selector: string) => document.querySelector(selector)?.textContent?.trim() ?? "";
  const rows = [...document.querySelectorAll('[data-testid^="profile-uid-"]')].map((row) => {
    const id = (row.getAttribute("data-testid") || "").replace("profile-", "");
    const lock = row.querySelector(`[data-testid="lock-${id}"]`);
    return {
      id,
      name: row.getAttribute("data-profile-name") || "",
      text: (row.textContent || "").replace(/\s+/g, " ").trim(),
      disabled: (row as HTMLButtonElement).disabled,
      locked: !!lock,
    };
  });
  return {
    calls: [...calls],
    rows,
    hasPicker: !!document.querySelector('[data-testid="profile-picker"]'),
    hasAppContent: !!document.querySelector('[data-testid="app-content"]'),
    sawAppContent: (window as unknown as { __sawAppContent: boolean }).__sawAppContent,
    appValue: text('[data-testid="app-value"]'),
    passwordForm: !!document.querySelector('[data-testid="profile-password-form"]'),
    prompt: text('[data-testid="profile-password-form"]'),
    chipLabel:
      document
        .querySelector('[data-testid="account-menu-trigger"]')
        ?.getAttribute("aria-label") ?? "",
    // Since 2026-09-13 "Switch profile" is an ITEM in the account menu, not a link in the header —
    // `switchLink` below is the menu's own text, so a check opens the menu first.
    switchLink: document.querySelector('a[href="/profiles?switch=1"]')?.textContent?.trim() ?? "",
    accountMenuItems: [
      ...(document.querySelector('[role="menu"]')?.querySelectorAll('[role="menuitem"]') ?? []),
    ].map((b) => b.textContent?.trim() ?? ""),
    signOutButton: [...document.querySelectorAll("button")].some(
      (b) => b.textContent?.trim() === "Sign out",
    ),
    error: text('[role="alert"]'),
    body: document.body.innerText,
  };
};

ReactDOM.createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <AuthProvider>
      <MemoryRouter initialEntries={[params.get("route") || "/app"]}>
        <Routes>
          <Route path="/login" element={<div>harness login</div>} />
          <Route path="/profiles" element={<ProfilesView />} />
          <Route
            path="/app"
            element={
              <RequireSession>
                <FakeHome />
              </RequireSession>
            }
          />
          {/* ProfilesView lands here after a selection (its default `next`). */}
          <Route
            path="/library/home"
            element={
              <RequireSession>
                <FakeHome />
              </RequireSession>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  </QueryClientProvider>,
);
