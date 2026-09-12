/**
 * Household rules (AUTH_MULTIUSER_PLAN Phase 1b) — the parts that must not be got wrong.
 *
 * The rails are re-checked on the server; these tests are about the UI not OFFERING what the
 * server will refuse, and about a grant that no longer resolves being visible instead of
 * looking like "the app hid my library".
 */
import { describe, expect, it } from "vitest";

import {
  accessSummary,
  confirmsName,
  defaultLibrarySelection,
  deleteDecision,
  householdErrorMessage,
  lastLoginLabel,
  renameIssue,
  type GrantableLibrary,
  type HouseholdUser,
} from "./lib";

const LIBRARIES: GrantableLibrary[] = [
  { id: "f1", name: "Movies", collection_type: "movies", path: "/data/Movies" },
  { id: "f2", name: "TV Shows", collection_type: "tvshows", path: "/media2/TV Shows" },
];

function user(overrides: Partial<HouseholdUser> = {}): HouseholdUser {
  return {
    id: "uid-1",
    name: "Guest",
    is_admin: false,
    disabled: false,
    has_password: false,
    enable_all_folders: false,
    enabled_folders: [],
    last_login: "",
    ...overrides,
  };
}

describe("accessSummary", () => {
  it("says Every library when all are granted", () => {
    expect(accessSummary(user({ enable_all_folders: true }), LIBRARIES).label).toBe(
      "Every library",
    );
  });

  it("names the granted libraries", () => {
    const summary = accessSummary(user({ enabled_folders: ["f1", "f2"] }), LIBRARIES);
    expect(summary.label).toBe("Movies, TV Shows");
    expect(summary.unknown).toEqual([]);
  });

  it("says None for an account with nothing granted", () => {
    expect(accessSummary(user(), LIBRARIES).label).toBe("None");
  });

  it("SURFACES a grant the server no longer knows", () => {
    // A grant is a library ItemId; a stale one grants nothing at all. Silently dropping it
    // would look like the app hiding a library.
    const summary = accessSummary(user({ enabled_folders: ["f1", "gone"] }), LIBRARIES);
    expect(summary.unknown).toEqual(["gone"]);
    expect(summary.label).toBe("Movies");
  });

  it("says so when EVERY grant is unknown", () => {
    const summary = accessSummary(user({ enabled_folders: ["gone1", "gone2"] }), LIBRARIES);
    expect(summary.label).toBe("2 unknown library(ies)");
    expect(summary.unknown).toHaveLength(2);
  });
});

describe("defaultLibrarySelection", () => {
  it("pre-ticks everything — a new member gets the admin's own access", () => {
    expect(defaultLibrarySelection(LIBRARIES)).toEqual(["f1", "f2"]);
  });

  it("is empty when the server offers nothing (and the request then means 'all')", () => {
    expect(defaultLibrarySelection([])).toEqual([]);
  });
});

describe("deleteDecision", () => {
  const me = user({ id: "uid-admin", name: "admin", is_admin: true });

  it("refuses the account you are signed in as", () => {
    const decision = deleteDecision(me, { signedInAs: me.id, household: [me] });
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toContain("signed in as");
  });

  it("refuses a sole administrator — the self rail fires first, and that is what protects it", () => {
    const sole = user({ id: "uid-2", name: "Sole", is_admin: true });
    const decision = deleteDecision(sole, { signedInAs: sole.id, household: [sole] });
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toContain("signed in as");
  });

  it("refuses the last administrator when the caller is not an administrator", () => {
    // Unreachable through the app — the API refuses a non-administrator caller outright — so
    // this mirrors the server's BACKSTOP rather than a path a user can take.
    const sole = user({ id: "uid-2", name: "Sole", is_admin: true });
    const decision = deleteDecision(sole, { signedInAs: "uid-someone-else", household: [sole] });
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toContain("only administrator");
  });

  it("allows a normal member, and a second administrator", () => {
    const member = user();
    expect(deleteDecision(member, { signedInAs: me.id, household: [me, member] }).allowed).toBe(
      true,
    );
    const second = user({ id: "uid-3", name: "Other", is_admin: true });
    const third = user({ id: "uid-4", name: "Third", is_admin: true });
    expect(
      deleteDecision(second, { signedInAs: me.id, household: [me, second, third] }).allowed,
    ).toBe(true);
  });
});

describe("confirmsName", () => {
  it("accepts the exact name, case-insensitively and trimmed", () => {
    expect(confirmsName("Guest", "Guest")).toBe(true);
    expect(confirmsName("  guest ", "Guest")).toBe(true);
  });

  it("refuses anything else", () => {
    expect(confirmsName("", "Guest")).toBe(false);
    expect(confirmsName("Gues", "Guest")).toBe(false);
  });
});

describe("householdErrorMessage", () => {
  it("explains each refusal in the user's terms", () => {
    expect(householdErrorMessage({ status: 401 })).toContain("Sign in");
    expect(householdErrorMessage({ status: 403 })).toContain("administrator");
    expect(householdErrorMessage({ status: 409, message: "There is already an account called X" }))
      .toContain("already");
    expect(householdErrorMessage({ status: 502 })).toContain("refused");
    // 503 is NOT a refusal about this person: the app could not ask the server at all.
    expect(householdErrorMessage({ status: 503, message: "" })).toContain("Could not reach");
    expect(householdErrorMessage({ status: 503 })).not.toContain("administrator");
    expect(householdErrorMessage({ status: 500, message: "" })).toBe("Failed (HTTP 500).");
    expect(householdErrorMessage(undefined)).toContain("Could not reach");
  });
});

describe("lastLoginLabel", () => {
  it("says never for an empty or unparseable timestamp", () => {
    expect(lastLoginLabel("")).toBe("Never signed in");
    expect(lastLoginLabel("not-a-date")).toBe("Never signed in");
  });

  it("formats a real timestamp", () => {
    expect(lastLoginLabel("2026-09-12T07:25:10.2169045Z")).toContain("Last seen");
  });
});


describe("renameIssue", () => {
  // Phase 2 (ADMIN_CREDENTIALS_PLAN.md §6): the ROLE is not the NAME. The UI mirrors only the
  // rules the server actually enforces — a made-up length or character rule here would be a second
  // implementation of the server's contract, and could forbid a name Jellyfin accepts.
  const household = [
    { id: "u1", name: "Rajeev" },
    { id: "u2", name: "Geetanjali" },
  ];

  it("allows a genuinely new name", () => {
    expect(renameIssue("Raj", "Geetanjali", household)).toEqual({ allowed: true, reason: "" });
  });

  it("refuses a blank name", () => {
    const d = renameIssue("   ", "Geetanjali", household);
    expect(d.allowed).toBe(false);
    expect(d.reason).toMatch(/required/i);
  });

  it("refuses the account's own current name — and says it is unchanged, not taken", () => {
    const d = renameIssue("Geetanjali", "Geetanjali", household);
    expect(d.allowed).toBe(false);
    expect(d.reason).toMatch(/already this account/i);
  });

  it("refuses a name another account has, whatever the casing or spacing", () => {
    expect(renameIssue("geetanjali", "Raj", household).allowed).toBe(false);
    expect(renameIssue("  GEETANJALI  ", "Raj", household).allowed).toBe(false);
    expect(renameIssue("Geetanjali", "Raj", household).reason).toMatch(/another account/i);
  });

  it("does NOT invent a length rule the server does not have", () => {
    // A 60-character name is the server's business. If it refuses, the screen says so (502) —
    // that is honest; silently blocking it here would be a second contract.
    expect(renameIssue("X".repeat(60), "Raj", household).allowed).toBe(true);
  });

  it("trims before comparing, so trailing spaces are not a 'new' name", () => {
    expect(renameIssue("Rajeev ", "Rajeev", household).allowed).toBe(false);
  });
});
