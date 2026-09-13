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
export type GuardDecision = "skeleton" | "app" | "login" | "picker";

export interface AuthUser {
  id: string;
  name: string;
}

export interface GuardInput {
  status: AuthStatus;
  /** True once an app route has answered 401 (i.e. the server enforces sessions). */
  enforcementSeen: boolean;
  /**
   * Has the SERVER said a profile has been chosen on this session (`me().profile_selected`)?
   *
   * Required, not optional, on purpose: this fact decides whether the app is taken away, so every
   * caller has to supply it rather than inherit a default that silently means "admin".
   */
  profileSelected: boolean;
}

/**
 * The guard rule, in one place.
 *
 * - `loading` ⇒ SKELETON. Never flash the app (which may then be replaced by a login
 *   form) and never show a login form to someone who is already signed in.
 * - signed out AND the server has refused an app call ⇒ LOGIN. That refusal is the only
 *   evidence enforcement exists.
 * - signed in but NO PROFILE CHOSEN ⇒ PICKER ("Who's watching?") — Phase B. The fact comes from
 *   the server, not from a click remembered in this browser: the session lives for 30 days and is
 *   the same one every device sees, so a locally-remembered answer would disagree with it after a
 *   reload, a second tab, or on the phone.
 * - anything else ⇒ APP. Phase 1's unenforced world, where a signed-out visitor is
 *   still a legitimate user of the app exactly as it was before auth existed.
 */
export function guardDecision({
  status,
  enforcementSeen,
  profileSelected,
}: GuardInput): GuardDecision {
  if (status === "loading") return "skeleton";
  if (status === "signedOut") return enforcementSeen ? "login" : "app";
  return profileSelected ? "app" : "picker";
}

/** The name to show for a session, falling back to the id, then to a generic label. */
export function displayName(user: AuthUser | null | undefined): string {
  if (!user) return "";
  const name = (user.name || "").trim();
  if (name) return name;
  return (user.id || "").trim() || "Signed in";
}

/**
 * The name to show as "who is watching" — the PROFILE, falling back to the session's owner.
 *
 * The profile is the identity media runs as, so it is the honest answer for a chip or a sidebar
 * card. The owner is only a fallback for the moment before the picker has been used.
 */
/**
 * May this profile see the Household (account-management) UI?
 *
 * TRUE only when the server says the profile in effect **is** an administrator. While the answer is
 * unknown the admin UI stays hidden — failing closed, because a briefly-visible admin link is worse
 * than a briefly-missing one. The server refuses those routes regardless; this only decides what the
 * app offers, so a member is never invited to a screen that will refuse them.
 */
export function mayManageHousehold(isAdmin: boolean | undefined): boolean {
  return isAdmin === true;
}

/**
 * May this profile trigger server-side library work — the library scan?
 *
 * The same shape as `mayManageHousehold`, for the same reason: **the server refuses these routes
 * to anyone who is not an administrator, so the app must not OFFER them.** Phase E (his decision,
 * 2026-09-13) put `require_admin_session` on `GET /api/library/scan` and
 * `POST /api/jobs/{name}/run` — a full media-server scan and a generic job runner are operator
 * verbs, and that gate is strict *even while* `RKM_AUTH_REQUIRED` is false, so a member's "Scan
 * Library" button would answer 403 on today's stack.
 *
 * Fails closed, like the household gate: `undefined` is the state before `/api/auth/profiles` has
 * answered, and a control that appears a moment late is better than one that turns into a refusal.
 * A signed-out visitor gets the same answer — the route refuses them too.
 */
export function mayScanLibrary(isAdmin: boolean | undefined): boolean {
  return isAdmin === true;
}

/**
 * What the ACCOUNT MENU offers, in order (2026-09-13, his request: *"consolidate the ui elements to
 * make it premium"*).
 *
 * Everything that belongs to *the person signed in* lives here — not scattered across the sidebar.
 * The rules, all pure so they are testable without a browser:
 *
 * * **My password** — EVERY profile, because a member's password is the lock on their profile and
 *   until Phase 3 only an administrator could change it (from Household, for somebody else).
 * * **Household** — administrators only, through the SAME `mayManageHousehold` the nav used, so the
 *   gate cannot drift between two surfaces. The server refuses the routes regardless.
 * * **Switch profile** — the only way back to "Who's watching?" without signing out.
 *
 * `key` is stable so the UI (and the browser checks) can address an entry; `adminOnly` documents
 * which entries the gate filtered out, so a test can assert on the RULE rather than on the DOM.
 */
export interface AccountDestination {
  key: "switch" | "password" | "household";
  label: string;
  to: string;
  icon: "switch" | "lock" | "users";
  adminOnly?: boolean;
}

export function accountDestinations(
  isAdmin: boolean | undefined,
  profileSelected: boolean,
): AccountDestination[] {
  const switchEntry = {
    key: "switch" as const,
    label: profileSelected ? "Switch profile" : "Choose profile",
    to: "/profiles?switch=1",
    icon: "switch" as const,
  };
  const password: AccountDestination = {
    key: "password",
    label: "My password",
    to: "/settings/password",
    icon: "lock",
  };
  const household: AccountDestination = {
    key: "household",
    label: "Household",
    to: "/settings/household",
    icon: "users",
    adminOnly: true,
  };
  return mayManageHousehold(isAdmin)
    ? [switchEntry, password, household]
    : [switchEntry, password];
}

/**
 * The one-line description of who this session IS (the menu's own header).
 *
 * Both facts matter on a shared device: the PROFILE is who media runs as, the signed-in account is
 * who holds the session — and they differ exactly when somebody else's profile is selected, which
 * is the situation a guest must not be able to mistake.
 */
export function accountSubtitle(
  profileName: string,
  ownerName: string,
  isAdmin: boolean | undefined,
): string {
  const role = mayManageHousehold(isAdmin) ? "Administrator" : "Profile";
  if (!ownerName || ownerName === profileName) return role;
  return `${role} · signed in as ${ownerName}`;
}

export function watchingName(profile: AuthUser | null, user: AuthUser | null): string {
  return displayName(profile) || displayName(user);
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
