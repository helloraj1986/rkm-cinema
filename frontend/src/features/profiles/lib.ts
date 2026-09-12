/**
 * "Who's watching?" rules and messages (PLEX_PROFILE_AUTH_PLAN Phase B) — PURE.
 *
 * Everything the picker decides without React or the network lives here, so the rules that matter
 * are testable in node: which rows may be entered, WHICH rows need a password, what "watching now"
 * may honestly claim, where a selection may send the browser afterwards, and what each refusal
 * actually says.
 *
 * The server re-checks all of it — this side exists so the UI never OFFERS something the server
 * will refuse, and never states something the server has not said.
 */
import type { ProfileUserShape } from "../../lib/api/client";

/** Where a selection goes when the caller did not ask for anywhere in particular. */
export const HOME_ROUTE = "/library/home";

/**
 * Does entering this profile need a password typed here?
 *
 * TWO cases, and the second one is the trap:
 *   * `has_password` — an ordinary protected profile;
 *   * `is_admin`     — the server ALWAYS refuses a blank attempt on the administrator's own
 *                      profile (the shared-device rule, decision 3), even when that account has
 *                      no password set. A picker that keyed the prompt off `has_password` alone
 *                      would post a blank password, take a 401, and look broken.
 *
 * The reverse case matters too: a password-less household profile must open with NOTHING typed
 * (that is how members were created — user decision 1c).
 */
export function requiresPassword(profile: Pick<ProfileUserShape, "has_password" | "is_admin">): boolean {
  return Boolean(profile.has_password) || Boolean(profile.is_admin);
}

/** May this profile be entered at all? A disabled account cannot use the server, so it cannot browse. */
export function isSelectable(profile: ProfileUserShape): boolean {
  return !profile.disabled;
}

/** Is this the profile in effect right now? Only the SERVER's flag makes that claim honest. */
export function watchingNow(
  profileId: string,
  currentId: string,
  profileSelected: boolean,
): boolean {
  return Boolean(profileSelected) && Boolean(profileId) && profileId === currentId;
}

/** The reason a row is not enterable, in the words the screen shows ("" when it is fine). */
export function blockedReason(profile: ProfileUserShape): string {
  if (!profile.disabled) return "";
  return "This profile is switched off — ask the administrator to enable it.";
}

/**
 * Sanitise a `?next=` target: an INTERNAL path or nothing.
 *
 * A redirect target that arrives in a URL is attacker-controllable, so `https://evil.example`,
 * protocol-relative `//evil.example` and a backslash form (`/\evil.example`, which some browsers
 * treat as protocol-relative) are all refused. Anything else lands Home — never off the app.
 */
export function safeNext(raw: string | null | undefined): string {
  const value = (raw || "").trim();
  if (!value.startsWith("/")) return HOME_ROUTE;
  if (value.startsWith("//") || value.startsWith("/\\")) return HOME_ROUTE;
  if (value === "/login" || value === "/profiles") return HOME_ROUTE;
  return value;
}

/**
 * What to tell the user when a selection is refused.
 *
 * 401 is the profile's OWN password — deliberately generic, and it never echoes what was typed.
 * 403 is the server's own sentence (a disabled profile, or an attempt on the administrator's from
 * somebody else's), which is more useful verbatim than anything invented here. 503 is the media
 * server being unreachable, which is a different problem and says so.
 */
export function pickerErrorMessage(error: unknown): string {
  const status = (error as { status?: unknown } | null | undefined)?.status;
  if (status === 401) return "That profile's password is not correct.";
  if (status === 403) {
    const detail = (error as { message?: string }).message;
    return detail && detail.trim() ? detail : "That profile cannot be used right now.";
  }
  if (status === 404) return "That profile is no longer on the server — pick another.";
  if (status === 503) {
    return "The media server is not available — check that Jellyfin is running.";
  }
  if (typeof status === "number") {
    const detail = (error as { message?: string }).message;
    return detail && detail.trim() ? detail : `Could not switch profile (HTTP ${status}).`;
  }
  return "Could not reach the server. Check your connection and try again.";
}

/** The line under the heading: how many people can be picked, and where this one is. */
export function pickerSubtitle(count: number, hasCurrent: boolean): string {
  const people = count === 1 ? "1 profile" : `${count} profiles`;
  return hasCurrent
    ? `${people} on this server — pick who is watching.`
    : `${people} on this server.`;
}
