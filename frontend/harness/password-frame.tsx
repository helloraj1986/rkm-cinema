/**
 * Harness: the REAL "Settings → My password" screen (ADMIN_CREDENTIALS_PLAN.md §6, Phase 3).
 *
 * Mounts `PasswordView` inside the real `AuthProvider` + query client against a STUBBED api, so
 * `tools/check_password_change.py` can prove in a browser what the screen actually does — which
 * requests it sends, with what body, and when it sends none at all.
 *
 * `?has_password=0` — the profile in effect has NO password (the case that must not be blocked).
 * `?has_password=1` — it has one (the current password is then required).
 * `?refuse=wrong`   — the change api answers 401 (a wrong current password).
 * `?refuse=server`  — it answers 502 (refused for another reason — NOT the user's typo).
 * `?refuse=silent`  — it answers 502 with NO body, so the screen's own wording is what speaks.
 * `?refuse=none`    — it answers 200 and the screen must say the password changed.
 *
 * The stub is deliberately FAITHFUL about the two things that could make a correct screen look
 * broken: a password-less account accepts ANY current password, and a 401 is about the CURRENT
 * password only.
 */
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AuthProvider } from "../src/features/auth/AuthProvider";
import { PasswordView } from "../src/features/settings/PasswordView";

const params = new URLSearchParams(location.search);
const HAS_PASSWORD = params.get("has_password") !== "0";
const REFUSE = params.get("refuse") ?? "none";

const PROFILE_ID = "uid-kid";

type Call = { url: string; method: string; body: string; status: number };
const calls: Call[] = [];

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
    return send(200, {
      user: { id: "uid-admin", name: "admin" },
      profile: { id: PROFILE_ID, name: "Geetanjali" },
      profile_selected: true,
      on_own_profile: false,
      expires: "2026-10-12T00:00:00Z",
    });
  }
  if (path === "/api/auth/profiles") {
    return send(200, {
      profiles: [
        { id: "uid-admin", name: "admin", is_admin: true, has_password: true, disabled: false, last_login: "" },
        { id: PROFILE_ID, name: "Geetanjali", is_admin: false, has_password: HAS_PASSWORD, disabled: false, last_login: "" },
      ],
      current: { id: PROFILE_ID, name: "Geetanjali", is_admin: false, has_password: HAS_PASSWORD, disabled: false, last_login: "" },
      profile_selected: true,
      warning: "",
    });
  }
  if (path === "/api/auth/profile/password") {
    if (REFUSE === "wrong") return send(401, { detail: "That current password is not correct" });
    if (REFUSE === "server") {
      return send(502, { detail: "The media server refused the password change" });
    }
    if (REFUSE === "silent") return send(502, {});
    return send(200, { ok: true });
  }
  return send(200, {});
}) as typeof fetch;

(window as unknown as { __probe: () => unknown }).__probe = () => ({
  calls: [...calls],
  submitDisabled: (() => {
    const button = [...document.querySelectorAll("button")].find(
      (b) => (b.textContent || "").trim() === "Change password",
    );
    return button ? (button as HTMLButtonElement).disabled : null;
  })(),
  notice: document.querySelector('[data-testid="password-notice"]')?.textContent ?? "",
  done: document.querySelector('[data-testid="password-done"]')?.textContent ?? "",
  error: document.querySelector('[data-testid="password-error"]')?.textContent ?? "",
  body: document.body.innerText,
});

function Frame() {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false } } }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/settings/password"]}>
          <div className="min-h-dvh bg-canvas p-6 text-zinc-100">
            <PasswordView />
          </div>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
