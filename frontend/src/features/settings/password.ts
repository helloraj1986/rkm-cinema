/**
 * "Change my password" rules (ADMIN_CREDENTIALS_PLAN.md §6, Phase 3) — PURE.
 *
 * Everything the screen decides without React or the network. The server (Jellyfin, through the
 * api) is the authority for whether a change is allowed; this side exists so the button is honest
 * BEFORE it is pressed — and, just as importantly, so it does not invent a rule the media server
 * does not have.
 *
 * The distinction that matters here: `hasPassword` is what the SERVER says about this profile
 * (`GET /api/auth/profiles`). While it is `null` (not yet known) the current-password field must
 * NOT be required, because a password-less account is a legitimate Jellyfin account that accepts
 * anything — requiring one would make those accounts unable to change their own password, which is
 * the exact bug that once made them unable to sign in.
 */

import type { PasswordConfirmation } from "../../lib/api/client";

export interface ChangeDecision {
  allowed: boolean;
  /** Why not — shown beside the button, and the same shape the server's refusal would take. */
  reason: string;
}

/** Does this account currently have a password? `null` = the server has not told us yet. */
export type HasPassword = boolean | null;

/**
 * What the server answered about a change it accepted: did signing in with the new password work?
 *
 * `refused` and `unavailable` are NOT the same thing and must never be worded as one: the first says
 * the server would not let us in with the new password (so it likely did not take), the second says
 * we could not ask (so we know nothing). Both are reported as what they are — the live lesson from
 * 2026-09-12 was a screen telling somebody their change had not been applied when it had.
 */
export type Confirmation = PasswordConfirmation;

export function confirmationMessage(
  confirmation: Confirmation | undefined,
  /** The account the change was made against, as the server names it. Shown ALWAYS: if the profile
   *  in effect is not the one the user thought, that must be visible, not silent. */
  account = "",
): { ok: boolean; text: string } {
  const who = account ? ` for ${account}` : "";
  if (confirmation === "verified") return { ok: true, text: `Password changed${who}.` };
  if (confirmation === "refused") {
    return {
      ok: false,
      text: `The server accepted the change${who} but would not sign in with the new password, ` +
        "so it may not have been applied. Sign in with the new password to check — if that fails, " +
        "your old one is unchanged and the administrator can set one from Household.",
    };
  }
  return {
    ok: false,
    text: `The server accepted the change${who} but it could not be confirmed. Sign in with the ` +
      "new password to check — if that fails, the administrator can set one from Household.",
  };
}

export const MIN_HINT =
  "Use something you have not used here before. There is no length rule — the media server " +
  "accepts what you choose.";

export function changeIssue(
  current: string,
  next: string,
  confirm: string,
  hasPassword: HasPassword,
): ChangeDecision {
  if (!next) {
    // TRULY empty only. A whitespace-only password is a footgun, but the media server accepts it,
    // and refusing it here would be a second implementation of the server's contract — the trap
    // that once made a password-LESS account unusable.
    return { allowed: false, reason: "Choose a new password." };
  }
  if (next !== confirm) {
    return { allowed: false, reason: "The two new passwords do not match." };
  }
  if (hasPassword === true && !current) {
    return { allowed: false, reason: "Enter your current password." };
  }
  if (hasPassword === false && current) {
    // Not an error — Jellyfin accepts whatever is supplied for an account with no password. But
    // saying so stops somebody believing they just proved they knew a password they never had.
    return {
      allowed: true,
      reason: "Your account has no password yet, so anything (or nothing) works here.",
    };
  }
  return { allowed: true, reason: "" };
}

/**
 * What to tell the user about a refused change.
 *
 * The server's own words win when it HAS any (`ApiError.detail`) — it knows why better than we do.
 * When it said nothing, the wording comes from here instead of the HTTP client's
 * `METHOD path -> status` fallback, which is an HTTP trace, not a sentence for a person.
 *
 * The 502 line matters: a refusal is not a typo, and the one thing the user needs to know is that
 * they are not locked out.
 */
export function changeErrorMessage(error: unknown): string {
  const status = (error as { status?: unknown } | null | undefined)?.status;
  const detail = (error as { detail?: unknown } | null | undefined)?.detail;
  const said = typeof detail === "string" && detail.trim() ? detail.trim() : "";
  if (status === 401) return said || "That current password is not correct.";
  if (status === 400) return said || "A new password is required.";
  if (status === 503) {
    return said || "Could not reach the media server. Nothing was changed.";
  }
  if (status === 502) {
    return said ||
      "The media server refused the change. Nothing was changed — your old password still works.";
  }
  if (typeof status === "number") return said || `The change failed (HTTP ${status}).`;
  return "Could not reach the server.";
}
