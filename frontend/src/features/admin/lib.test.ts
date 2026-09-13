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
  avatarToneIndex,
  confirmsName,
  defaultLibrarySelection,
  deleteDecision,
  folderSelectionPayload,
  householdErrorMessage,
  householdSummary,
  lastLoginLabel,
  memberBadges,
  memberLibraryChips,
  passwordActionLabel,
  passwordConfirmIssue,
  passwordModalTitle,
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

/* ------------------------------------------------------------------------------------------------
 * The redesigned page (HOUSEHOLD_UX_PLAN.md Phase 1, 2026-09-13) — the new pure rules.
 * ---------------------------------------------------------------------------------------------- */

describe("householdSummary", () => {
  it("counts every profile and excludes the disabled from Active", () => {
    const summary = householdSummary(
      [
        user({ id: "u1", is_admin: true, enable_all_folders: true }),
        user({ id: "u2", enabled_folders: ["f1"] }),
        user({ id: "u3", enabled_folders: ["f2"], disabled: true }),
      ],
      LIBRARIES,
    );
    expect(summary.members).toBe(3);
    expect(summary.active).toBe(2);
    expect(summary.librariesShared).toBe(2);
  });

  it("does not count the administrator as sharing libraries — the server grants them everything", () => {
    const summary = householdSummary(
      [user({ id: "u1", is_admin: true, enable_all_folders: true })],
      LIBRARIES,
    );
    expect(summary.librariesShared).toBe(0);
  });

  it("reads a member granted everything as sharing every library", () => {
    const summary = householdSummary([user({ enable_all_folders: true })], LIBRARIES);
    expect(summary.librariesShared).toBe(LIBRARIES.length);
  });

  it("counts a library only once however many members have it", () => {
    const summary = householdSummary(
      [user({ id: "u2", enabled_folders: ["f1"] }), user({ id: "u3", enabled_folders: ["f1", "f2"] })],
      LIBRARIES,
    );
    expect(summary.librariesShared).toBe(2);
  });

  it("ignores a grant whose library no longer exists", () => {
    // Otherwise the count promises a library that nobody can actually watch.
    const summary = householdSummary([user({ enabled_folders: ["gone"] })], LIBRARIES);
    expect(summary.librariesShared).toBe(0);
  });
});

describe("memberBadges", () => {
  const admin = user({ id: "u1", name: "rkm", is_admin: true, has_password: true });

  it("marks your own account, the role, and both warnings — in the mockup's order", () => {
    const labels = memberBadges(
      user({ id: "u2", is_admin: true, disabled: true, has_password: false }),
      "u2",
    ).map((badge) => badge.label);
    expect(labels).toEqual(["YOU", "ADMINISTRATOR", "DISABLED", "NO PASSWORD"]);
  });

  it("says nothing an ordinary member does not need", () => {
    expect(memberBadges(user({ id: "u2", has_password: true }), "u1")).toEqual([]);
  });

  it("rides the ACCOUNT, not the name — a rename does not move the ADMINISTRATOR badge", () => {
    // Phase 2's whole point, re-asserted here because the badge moved into a pure function.
    expect(memberBadges(admin, "u1").map((badge) => badge.key)).toEqual(["you", "admin"]);
    // A rename changes the label and nothing else, because the badge reads `is_admin`, never `name`.
    const renamed = { ...admin, name: "Rajeev" };
    expect(memberBadges(renamed, "u1")).toEqual(memberBadges(admin, "u1"));
  });
});

describe("memberLibraryChips", () => {
  it("gives an administrator ONE chip instead of enumerating", () => {
    const chips = memberLibraryChips(user({ is_admin: true, enable_all_folders: true }), LIBRARIES);
    expect(chips).toEqual([{ key: "all", label: "Every library", every: true }]);
  });

  it("gives a member granted everything the same single chip", () => {
    expect(memberLibraryChips(user({ enable_all_folders: true }), LIBRARIES)).toHaveLength(1);
  });

  it("names the libraries a member can actually see", () => {
    expect(memberLibraryChips(user({ enabled_folders: ["f1", "f2"] }), LIBRARIES).map((c) => c.label))
      .toEqual(["Movies", "TV Shows"]);
  });

  it("does not silently drop an unresolvable grant, and says so when there is nothing to show", () => {
    // The card carries `accessSummary().unknown` as its own note; the chips stay honest.
    expect(memberLibraryChips(user({ enabled_folders: ["gone"] }), LIBRARIES)).toEqual([
      { key: "none", label: "No libraries", every: false },
    ]);
  });
});

describe("passwordActionLabel", () => {
  it("labels the three states and never claims three different calls", () => {
    expect(passwordActionLabel(user({ id: "u2", has_password: false }), "u1")).toBe("Set password");
    expect(passwordActionLabel(user({ id: "u2", has_password: true }), "u1")).toBe("Reset password");
    expect(passwordActionLabel(user({ id: "u1", has_password: true }), "u1")).toBe("Change password");
  });

  it("prefers the no-password state over 'your own account' — that is the fact that matters", () => {
    expect(passwordActionLabel(user({ id: "u1", has_password: false }), "u1")).toBe("Set password");
  });

  it("titles its modal after the button that opened it", () => {
    expect(passwordModalTitle(user({ has_password: false }), "u1")).toBe("Set a password");
    expect(passwordModalTitle(user({ id: "u2", has_password: true }), "u1")).toBe("Reset password");
  });
});

describe("passwordConfirmIssue", () => {
  it("refuses an empty new password before any request — the route refuses one too", () => {
    expect(passwordConfirmIssue("", "")).toMatch(/type the new password/i);
    expect(passwordConfirmIssue("", "typed")).toMatch(/type the new password/i);
  });

  it("refuses a mismatch — the server only ever sees ONE value", () => {
    expect(passwordConfirmIssue("hunter2", "hunter3")).toMatch(/do not match/i);
  });

  it("allows an exact match, and says nothing then", () => {
    expect(passwordConfirmIssue("hunter2", "hunter2")).toBe("");
  });
});

describe("folderSelectionPayload", () => {
  it("⚠ sends the FULL id list for 'Every library' — never an empty list", () => {
    // Measured 2026-09-13: the route's `[]` means EnableAllFolders=false + EnabledFolders=[],
    // i.e. NO libraries. The old inline form sent [] here, so ticking "Every library" and saving
    // took access away. This is the regression guard for that bug.
    expect(folderSelectionPayload(true, [], LIBRARIES)).toEqual(["f1", "f2"]);
    expect(folderSelectionPayload(true, ["f1"], LIBRARIES)).toEqual(["f1", "f2"]);
  });

  it("passes a partial selection through verbatim", () => {
    expect(folderSelectionPayload(false, ["f2"], LIBRARIES)).toEqual(["f2"]);
  });

  it("still expresses 'no libraries' as an empty list, which is what that means", () => {
    expect(folderSelectionPayload(false, [], LIBRARIES)).toEqual([]);
  });
});

describe("avatarToneIndex", () => {
  it("is stable for a name and inside the palette", () => {
    for (const name of ["rkm", "Geetanjali", "sharanya", ""]) {
      const index = avatarToneIndex(name, 5);
      expect(index).toBeGreaterThanOrEqual(0);
      expect(index).toBeLessThan(5);
      expect(avatarToneIndex(name, 5)).toBe(index);
    }
  });

  it("does not collapse every name onto one colour", () => {
    const tones = new Set(
      ["rkm", "Geetanjali", "sharanya", "meenu", "raj", "Priya"].map((n) => avatarToneIndex(n)),
    );
    expect(tones.size).toBeGreaterThan(1);
  });
});
