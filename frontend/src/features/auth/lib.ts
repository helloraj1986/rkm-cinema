/**
 * Sign-in state, decisions and messages (AUTH_MULTIUSER_PLAN Phase 1) — PURE.
 *
 * Everything here is deliberately free of React and of the network so the rules that
 * matter can be tested in node: WHEN to show a skeleton, when the app may render
 * signed-out, when to force the login view, and what a failed sign-in says.
 *
 * The subtle rule is `guardDecision`. Phase 1 ships with NOTHING enforced, so the app
 * must keep working signed-out — a guard that redirected on "no session" would take the
 * whole app away for no reason. And Phase 2 flips enforcement on the SERVER, without a
 * frontend change: the app discovers it is enforced the moment a normal (non-auth) API
 * call comes back 401. So the guard needs two independent facts:
 *
 *   * `status`          — did `GET /api/auth/me` say we have a session?
 *   * `enforcementSeen` — has the server ever REFUSED an app call for want of one?
 *
 * Only the second one justifies taking the app away, and that is exactly what
 * `guardDecision` encodes.
 */

/** Where the session check has got to. `loading` until `me()` answers. */
export type AuthStatus = "loading" | "signedIn" | "signedOut";

/** What the route guard should render for the current state. */
export type GuardDecision = "skeleton" | "app" | "login";

export interface AuthUser {
  id: string;
  name: string;
}

export interface GuardInput {
  status: AuthStatus;
  /** True once an app route has answered 401 (i.e. the server enforces sessions). */
  enforcementSeen: boolean;
}

/**
 * The guard rule, in one place.
 *
 * - `loading` ⇒ SKELETON. Never flash the app (which may then be replaced by a login
 *   form) and never show a login form to someone who is already signed in.
 * - signed out AND the server has refused an app call ⇒ LOGIN. That refusal is the only
 *   evidence enforcement exists.
 * - anything else ⇒ APP. Phase 1's unenforced world, where a signed-out visitor is
 *   still a legitimate user of the app exactly as it was before auth existed.
 */
export function guardDecision({ status, enforcementSeen }: GuardInput): GuardDecision {
  if (status === "loading") return "skeleton";
  if (status === "signedOut" && enforcementSeen) return "login";
  return "app";
}

/** The name to show for a session, falling back to the id, then to a generic label. */
export function displayName(user: AuthUser | null | undefined): string {
  if (!user) return "";
  const name = (user.name || "").trim();
  if (name) return name;
  return (user.id || "").trim() || "Signed in";
}

/** Up to two initials for the header chip ("Rajeev Kumar" -> "RK"). */
export function initials(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * What to tell the user about a failed sign-in.
 *
 * Deliberately GENERIC on 401 — the API does not distinguish an unknown user from a
 * wrong password, and the UI must not invent that difference. A 503 is the media server
 * being unavailable, which is a different problem and says so. Nothing here ever echoes
 * the password, because nothing here is given it.
 */
export function loginErrorMessage(error: unknown): string {
  const status = (error as { status?: unknown } | null | undefined)?.status;
  if (status === 401) return "Incorrect username or password.";
  if (status === 503) {
    return "The media server is not available — check that Jellyfin is running.";
  }
  if (typeof status === "number") {
    const detail = (error as { message?: string }).message;
    return detail && detail.trim() ? detail : `Sign-in failed (HTTP ${status}).`;
  }
  return "Could not reach the server. Check your connection and try again.";
}
