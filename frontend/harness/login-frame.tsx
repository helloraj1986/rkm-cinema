/**
 * Sign-in flow harness (sandbox, not shipped).
 *
 * The real `AuthProvider`, `RequireSession`, `LoginView`, `ProfilesView` and `Header` mounted over a
 * STUBBED api, so `tools/check_login_flow.py` can drive the flow in a real browser:
 * signed-out but usable (nothing is enforced), sign in, a wrong password, sign out, the `?enforce=1`
 * world where an app call answers 401 — and (Phase B) the fact that a successful sign-in lands on
 * "Who's watching?" rather than straight in the app.
 *
 * Nothing here ships: `vite build` only builds /index.html. Query params:
 *   ?enforce=0|1   — does an ordinary app call answer 401? (the server-side enforcement)
 *   ?signedIn=0|1  — what GET /api/auth/me says at load
 *   ?route=/app    — initial location
 *
 * ⚠ This stub models the picker only as far as the LOGIN flow needs: one row, for the account that
 * just signed in, always asking for a password (the administrator's profile always does). The
 * picker's own rules — the lock badge, a password-less member, a disabled profile, refusals — are
 * proven by `profile-frame.tsx` + `tools/check_profile_picker.py`, over the REAL `ProfilesView`.
 *
 * `window.__authCalls` records every stubbed call (url, method, status) and
 * `window.__probe()` reports what is actually rendered — the tool asserts on those.
 */
import { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { api } from "../src/lib/api/client";
import { AuthProvider } from "../src/features/auth/AuthProvider";
import { LoginView } from "../src/features/auth/LoginView";
import { RequireSession } from "../src/features/auth/RequireSession";
import { ProfilesView } from "../src/features/profiles/ProfilesView";
import { Header } from "../src/app/layout/Header";
import "../src/styles/index.css";

const params = new URLSearchParams(window.location.search);
const ENFORCED = params.get("enforce") === "1";
const SIGNED_IN = params.get("signedIn") === "1";
const GOOD_PASSWORD = "correct-horse";
const USER = { id: "harness-uid", name: "Harness User" };
const PASSWORDLESS_USER = { id: "harness-uid-nopw", name: "No-Password User" };

interface Call {
  url: string;
  method: string;
  status: number;
  /** The request body as sent (so a check can prove what the form POSTed). */
  body: string;
}

const calls: Call[] = [];
(window as unknown as { __authCalls: Call[] }).__authCalls = calls;

// Did app content EVER appear? The enforced world must go straight to the login view — asserting
// this catches a regression that mounts the app and then bounces it.
(window as unknown as { __sawAppContent: boolean }).__sawAppContent = false;
const observer = new MutationObserver(() => {
  if (document.querySelector('[data-testid="app-content"]')) {
    (window as unknown as { __sawAppContent: boolean }).__sawAppContent = true;
  }
});
observer.observe(document.documentElement, { childList: true, subtree: true });

/** The stubbed api: the auth routes are precise, everything else is the switch.
 *
 *  Enforcement refuses ONLY an unsigned caller — a VALID session must keep working in the
 *  enforced world (a cruder stub that refused everything made a correct app look broken). */
let hasSession = SIGNED_IN;
let sessionUser = USER;
let profileId = SIGNED_IN ? USER.id : "";

window.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const raw =
    typeof input === "string"
      ? input
      : "url" in (input as Request)
        ? (input as Request).url
        : String(input);
  const method = String(init.method || (input as Request).method || "GET").toUpperCase();
  const path = raw.slice(raw.indexOf("/api"));

  const send = (status: number, payload: unknown = null) => {
    const text = payload === null ? "" : JSON.stringify(payload);
    calls.push({ url: path, method, status, body: String(init.body ?? "") });
    return new Response(text, { status, headers: { "content-type": "application/json" } });
  };

  // The one selectable profile here: the account that signed in. `is_admin: true` because that is
  // the only account the REAL sign-in accepts — and an administrator's profile always asks for a
  // password, so the picker's prompt is part of this flow.
  const profile = {
    id: sessionUser.id,
    name: sessionUser.name,
    is_admin: true,
    has_password: sessionUser.id === USER.id,
    disabled: false,
    last_login: "",
  };

  if (path === "/api/auth/me") {
    if (!hasSession) return send(401, { detail: "Not signed in" });
    return send(200, {
      user: sessionUser,
      profile,
      on_own_profile: profileId === sessionUser.id,
      // The picker's trigger: a fresh sign-in has chosen nobody yet.
      profile_selected: Boolean(profileId),
      expires: "2026-10-12T00:00:00Z",
    });
  }
  if (path === "/api/auth/profiles") {
    if (!hasSession) return send(401, { detail: "Sign in to see the profiles on this server" });
    return send(200, {
      profiles: [profile],
      current: profile,
      profile_selected: Boolean(profileId),
      warning: "",
    });
  }
  if (path === "/api/auth/profile" && method === "POST") {
    if (!hasSession) return send(401, { detail: "Sign in before choosing a profile" });
    const body = JSON.parse(String(init.body || "{}")) as { user_id?: string; password?: string };
    if (body.user_id !== profile.id) return send(404, { detail: "No such profile on this server" });
    // The administrator's own profile ALWAYS asks: a blank attempt never lands on it.
    if (!body.password) {
      return send(401, { detail: "Enter the administrator's password to switch to that profile" });
    }
    // …and when the account has no password of its own, Jellyfin accepts ANY supplied value.
    if (profile.has_password && body.password !== GOOD_PASSWORD) {
      return send(401, { detail: "That profile's password is not correct" });
    }
    profileId = profile.id;
    return send(200, { ok: true, profile, libraries: [{ id: "f1", name: "Movies" }] });
  }
  if (path === "/api/auth/login") {
    const body = JSON.parse(String(init.body || "{}")) as { password?: string };
    // A BLANK password is a real Jellyfin case: an account can have no password at all
    // (the household "create without password" decision), and it must authenticate.
    if (body.password === GOOD_PASSWORD || body.password === "") {
      hasSession = true;
      sessionUser = body.password === "" ? PASSWORDLESS_USER : USER;
      profileId = ""; // a fresh session has NO profile — the picker asks who is watching
      return send(200, { ok: true, user: sessionUser, expires: "2026-10-12T00:00:00Z" });
    }
    return send(401, { detail: "Incorrect username or password" });
  }
  if (path === "/api/auth/logout") {
    hasSession = false;
    profileId = "";
    return send(200, { ok: true, revoked: true });
  }
  return ENFORCED && !hasSession ? send(401, { detail: "Sign in to use this app" }) : send(200, {});
}) as typeof fetch;

/** A stand-in Home page: its first real app call is what reveals enforcement. */
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
  const text = (selector: string) =>
    document.querySelector(selector)?.textContent?.trim() ?? "";
  return {
    calls: [...calls],
    hasLoginForm: !!document.querySelector("#rkm-username"),
    hasPicker: !!document.querySelector('[data-testid="profile-picker"]'),
    hasAppContent: !!document.querySelector('[data-testid="app-content"]'),
    sawAppContent: (window as unknown as { __sawAppContent: boolean }).__sawAppContent,
    appValue: text('[data-testid="app-value"]'),
    chipLabel:
      document
        .querySelector('[data-testid="account-menu-trigger"]')
        ?.getAttribute("aria-label") ?? "",
    // The account affordance is a MENU since 2026-09-13: Sign out (and everything else about the
    // signed-in person) lives inside it, so a check reads the items rather than a bare button.
    accountMenuItems: [
      ...(document.querySelector('[role="menu"]')?.querySelectorAll('[role="menuitem"]') ?? []),
    ].map((b) => b.textContent?.trim() ?? ""),
    signInLink: !!document.querySelector('a[href="/login"]'),
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
          <Route path="/login" element={<LoginView />} />
          <Route path="/profiles" element={<ProfilesView />} />
          <Route
            path="/app"
            element={
              <RequireSession>
                <FakeHome />
              </RequireSession>
            }
          />
          {/* A successful sign-in and a chosen profile both land here. */}
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
