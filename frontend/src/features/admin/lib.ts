/**
 * Household rules and labels (AUTH_MULTIUSER_PLAN Phase 1b) — PURE.
 *
 * Everything the screen decides without touching React or the network lives here, so the
 * rules that matter can be tested in node: what "sees" means when a granted id no longer
 * exists, who may be removed (mirroring the server's rails so the button is honest BEFORE
 * it is pressed), and what each failure actually says.
 *
 * The server re-checks every one of these — this side exists so the UI never OFFERS
 * something the server will refuse.
 */

export interface HouseholdUser {
  id: string;
  name: string;
  is_admin: boolean;
  disabled: boolean;
  has_password: boolean;
  enable_all_folders: boolean;
  enabled_folders: string[];
  last_login: string;
}

export interface GrantableLibrary {
  id: string;
  name: string;
  collection_type: string;
  path: string;
}

/** Which libraries an account can see, resolved to names. */
export interface AccessSummary {
  /** The human line: "Every library", "Movies, TV Shows", "None". */
  label: string;
  /** Granted ids the server no longer knows — a grant that silently does nothing. */
  unknown: string[];
}

/**
 * Resolve an account's access to names.
 *
 * `unknown` matters: a grant is a library **ItemId**, so a stale id grants nothing and
 * reads like "the app hid my library". Surfacing it is the difference between a mystery
 * and a fix.
 */
export function accessSummary(
  user: Pick<HouseholdUser, "enable_all_folders" | "enabled_folders">,
  libraries: GrantableLibrary[],
): AccessSummary {
  if (user.enable_all_folders) return { label: "Every library", unknown: [] };
  const ids = user.enabled_folders ?? [];
  if (ids.length === 0) return { label: "None", unknown: [] };
  const byId = new Map(libraries.map((lib) => [lib.id, lib.name]));
  const names: string[] = [];
  const unknown: string[] = [];
  for (const id of ids) {
    const name = byId.get(id);
    if (name) names.push(name);
    else unknown.push(id);
  }
  if (names.length === 0) {
    return { label: `${unknown.length} unknown library(ies)`, unknown };
  }
  return { label: names.join(", "), unknown };
}

/** The library ids a new member gets by default: everything (the admin's own access). */
export function defaultLibrarySelection(libraries: GrantableLibrary[]): string[] {
  return libraries.map((lib) => lib.id);
}

export interface DeleteDecision {
  allowed: boolean;
  /** Why not — the same wording the server would answer with. */
  reason: string;
}

/**
 * May this account be removed, mirroring the server's rails?
 *
 * The server is the authority; this is so the UI can disable the button and say why
 * instead of offering an action that comes back 400.
 */
export function deleteDecision(
  user: Pick<HouseholdUser, "id" | "name" | "is_admin">,
  opts: { signedInAs: string; household: Pick<HouseholdUser, "id" | "is_admin">[] },
): DeleteDecision {
  if (user.id === opts.signedInAs) {
    return { allowed: false, reason: "You cannot remove the account you are signed in as." };
  }
  const admins = opts.household.filter((u) => u.is_admin);
  if (user.is_admin && admins.length <= 1) {
    return {
      allowed: false,
      reason: "That is the only administrator — removing it would leave nobody able to manage the household.",
    };
  }
  return { allowed: true, reason: "" };
}

export interface RenameDecision {
  allowed: boolean;
  /** Why not — the same wording the server would answer with. */
  reason: string;
}

/**
 * May this rename be submitted, mirroring the server's rails?
 *
 * There is deliberately NO length or character rule here: inventing one would be a second
 * implementation of the server's contract, and it could forbid a name Jellyfin happily accepts
 * (the same trap that once made a password-LESS account unusable). The server owns what a name
 * may be; this side only mirrors the rules the server actually enforces.
 */
export function renameIssue(
  typed: string,
  current: string,
  household: Pick<HouseholdUser, "id" | "name">[],
): RenameDecision {
  const name = (typed || "").trim();
  if (!name) return { allowed: false, reason: "A name is required." };
  if (name === (current || "").trim()) {
    return { allowed: false, reason: "That is already this account's name." };
  }
  const taken = household.some(
    (u) => u.name.trim().toLowerCase() === name.toLowerCase(),
  );
  if (taken) return { allowed: false, reason: "Another account already has that name." };
  return { allowed: true, reason: "" };
}

/** Does the typed confirmation match the account's name? (case-insensitive, trimmed) */
export function confirmsName(typed: string, name: string): boolean {
  return (typed || "").trim().toLowerCase() === (name || "").trim().toLowerCase();
}

/** What to tell the user about a failed household action. */
export function householdErrorMessage(error: unknown): string {
  const status = (error as { status?: unknown } | null | undefined)?.status;
  const detail = (error as { message?: string } | null | undefined)?.message;
  if (status === 401) return "Sign in to manage household accounts.";
  if (status === 403) return "Only a Jellyfin administrator can manage household accounts.";
  if (status === 409) return detail?.trim() || "There is already an account with that name.";
  if (status === 503) {
    // The app could not ASK the media server whether this person is an administrator — which is
    // not a permission decision. Saying so is the difference between a ten-second check and a
    // hunt through the Jellyfin dashboard for a right that was never wrong.
    return detail?.trim() || "Could not reach the media server. Nothing was changed.";
  }
  if (status === 502) {
    return detail?.trim() || "The media server refused the change — nothing was saved.";
  }
  if (status === 400) return detail?.trim() || "That request was refused.";
  if (typeof status === "number") return detail?.trim() || `Failed (HTTP ${status}).`;
  return "Could not reach the server.";
}

/** A short "last seen" label; the server reports an ISO timestamp or nothing. */
export function lastLoginLabel(value: string): string {
  const raw = (value || "").trim();
  if (!raw) return "Never signed in";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "Never signed in";
  return `Last seen ${parsed.toLocaleDateString("en-AU")}`;
}
