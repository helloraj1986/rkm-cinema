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

/* --------------------------------------------------------------------------------------------
 * The redesigned page (HOUSEHOLD_UX_PLAN.md Phase 1, 2026-09-13)
 *
 * The four layers his mockup asks for — header, summary, cards, modals — are all derived from
 * the payload the page ALREADY has. Nothing here fetches, and nothing here invents a rule the
 * server owns: these are the LABELS, the COUNTS and the PAYLOAD the switches send.
 * ------------------------------------------------------------------------------------------ */

/** The three numbers on the summary row. */
export interface HouseholdSummary {
  members: number;
  /** Everyone who is not disabled. */
  active: number;
  /** Distinct libraries granted across non-administrator members. */
  librariesShared: number;
}

/**
 * Compute the summary row's three numbers from the household list alone.
 *
 * Two deliberate readings, both matching the mockup's own labels:
 *  * an ADMINISTRATOR is not "granted" libraries — the server gives an administrator everything,
 *    so counting them would inflate "Libraries shared" with libraries nobody shares;
 *  * a DISABLED member's grants still count as shared (the grant is on the account), while the
 *    member counts towards the total but not towards "Active profiles".
 */
export function householdSummary(
  users: HouseholdUser[],
  libraries: GrantableLibrary[],
): HouseholdSummary {
  const known = libraries.map((library) => library.id);
  const shared = new Set<string>();
  for (const user of users) {
    if (user.is_admin) continue;
    const granted = user.enable_all_folders ? known : user.enabled_folders ?? [];
    for (const id of granted) {
      // A grant whose library is gone grants NOTHING (it is an ItemId) — see `accessSummary`.
      if (known.includes(id)) shared.add(id);
    }
  }
  return {
    members: users.length,
    active: users.filter((user) => !user.disabled).length,
    librariesShared: shared.size,
  };
}

export type MemberBadgeTone = "accent" | "neutral" | "warn" | "muted";

export interface MemberBadge {
  key: "you" | "admin" | "disabled" | "no-password";
  /** Already UPPERCASE: the browser checks read `innerText`, and CSS `uppercase` is invisible to it. */
  label: string;
  tone: MemberBadgeTone;
}

/**
 * The pills on a profile card, in the mockup's order — the same facts the old row's `Tag`s showed.
 *
 * `label` is written uppercase HERE rather than by a CSS class, because a browser check reads
 * `innerText` and a CSS-transformed label comes back in whatever case the DOM holds (his §7 QA
 * checklist is asserted by content).
 */
export function memberBadges(
  user: Pick<HouseholdUser, "id" | "is_admin" | "disabled" | "has_password">,
  signedInAs: string,
): MemberBadge[] {
  const badges: MemberBadge[] = [];
  if (user.id === signedInAs) badges.push({ key: "you", label: "YOU", tone: "accent" });
  if (user.is_admin) badges.push({ key: "admin", label: "ADMINISTRATOR", tone: "neutral" });
  if (user.disabled) badges.push({ key: "disabled", label: "DISABLED", tone: "warn" });
  if (!user.has_password) badges.push({ key: "no-password", label: "NO PASSWORD", tone: "muted" });
  return badges;
}

export interface MemberChip {
  key: string;
  label: string;
  /** The single "Every library" chip an administrator (or a member granted everything) gets. */
  every: boolean;
}

/**
 * The library chips on a card.
 *
 * An administrator — and a member whose policy is `EnableAllFolders` — gets ONE chip rather than
 * an enumeration, exactly as the mockup asks. Unresolvable grants are NOT silently dropped: the
 * card still carries `accessSummary().unknown` as the amber note that explains why a grant does
 * nothing.
 */
export function memberLibraryChips(
  user: Pick<HouseholdUser, "is_admin" | "enable_all_folders" | "enabled_folders">,
  libraries: GrantableLibrary[],
): MemberChip[] {
  if (user.is_admin || user.enable_all_folders) {
    return [{ key: "all", label: "Every library", every: true }];
  }
  const byId = new Map(libraries.map((library) => [library.id, library.name]));
  const chips: MemberChip[] = [];
  for (const id of user.enabled_folders ?? []) {
    const name = byId.get(id);
    if (name) chips.push({ key: id, label: name, every: false });
  }
  return chips.length ? chips : [{ key: "none", label: "No libraries", every: false }];
}

/**
 * What the card's password button says — the mockup's three labels, and the reason there are three.
 *
 * ⚠ They are LABELS, not three different calls: every one of them opens the same modal and posts
 * to the same route with the same body (`POST /admin/users/{id}/password`). "Set password" is the
 * no-password state, "Change password" is your own account, "Reset password" is somebody else's —
 * the wording he asked for, and never a claim about the payload.
 */
export function passwordActionLabel(
  user: Pick<HouseholdUser, "id" | "has_password">,
  signedInAs: string,
): string {
  if (!user.has_password) return "Set password";
  return user.id === signedInAs ? "Change password" : "Reset password";
}

/** The password MODAL's title, matching the button that opened it. */
export function passwordModalTitle(
  user: Pick<HouseholdUser, "id" | "has_password">,
  signedInAs: string,
): string {
  const label = passwordActionLabel(user, signedInAs);
  return label === "Set password" ? "Set a password" : label;
}

/**
 * Why this password cannot be saved yet — the modal's own gate, checked BEFORE any request.
 *
 * Two rules only, and both are the app's business rather than the server's: the value has to be
 * non-empty (the route refuses a blank one outright — *"an account is created without one, not
 * emptied afterwards"*), and the two fields have to agree (the server only ever receives one, so a
 * typo here is unrecoverable from the member's side).
 */
export function passwordConfirmIssue(next: string, confirm: string): string {
  if (!next) return "Type the new password.";
  if (next !== confirm) return "The two passwords do not match.";
  return "";
}

/** A stable index into the avatar palette, so a person keeps the same colour between renders. */
export function avatarToneIndex(name: string, tones = 5): number {
  const raw = (name || "").trim().toLowerCase();
  let hash = 0;
  for (let i = 0; i < raw.length; i += 1) hash = (hash * 31 + raw.charCodeAt(i)) % 100003;
  return Math.abs(hash) % Math.max(1, tones);
}

/**
 * The `library_ids` a "Save access" must send.
 *
 * ⚠ **Measured against the live route, 2026-09-13 — this is the one place the old inline form was
 * wrong, and it is a wire-level bug, not a layout one.** The route passes the ids straight to
 * `set_folder_access(ids)` with `enable_all` defaulting to **False**, and the request model's own
 * docstring says *"an empty list means none"* (create route: `None` = every library, `[]` = none).
 * The old form sent `[]` for "Every library" — i.e. ticking that box and saving granted the member
 * **NOTHING** (`EnableAllFolders=false` + `EnabledFolders=[]`), which reads afterwards as
 * "Sees: None". The app has no way to ask for `EnableAllFolders=true` on this route at all, so
 * "every library" has to MEAN the full id list.
 *
 * Pure, so the rule is testable: `all` ⇒ every library id; otherwise the ticked ids verbatim
 * (which is still how "none" is expressed, and the modal warns before that is sent).
 */
export function folderSelectionPayload(
  all: boolean,
  ticked: string[],
  libraries: GrantableLibrary[],
): string[] {
  return all ? libraries.map((library) => library.id) : [...ticked];
}
