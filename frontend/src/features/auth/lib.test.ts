/**
 * Sign-in rules (AUTH_MULTIUSER_PLAN Phase 1) — the guard matrix and the messages.
 *
 * These are the tests that stop the two ways this feature can hurt the user:
 * taking the app away when nothing is enforced, and showing a login form to someone who
 * is already signed in (a flash of the wrong screen on every page load).
 */
import { describe, expect, it } from "vitest";

import {
  displayName,
  guardDecision,
  initials,
  loginErrorMessage,
  mayManageHousehold,
  accountDestinations,
  accountSubtitle,
  watchingName,
} from "./lib";

describe("guardDecision", () => {
  it("shows a skeleton until the session check answers", () => {
    expect(guardDecision({ status: "loading", enforcementSeen: false, profileSelected: false })).toBe(
      "skeleton",
    );
    // …even when enforcement is already known: the answer may change the screen, and a
    // flash of the wrong one is exactly what the skeleton exists to prevent.
    expect(guardDecision({ status: "loading", enforcementSeen: true, profileSelected: true })).toBe(
      "skeleton",
    );
  });

  it("lets a signed-out visitor use the app while nothing is enforced (Phase 1)", () => {
    expect(guardDecision({ status: "signedOut", enforcementSeen: false, profileSelected: false })).toBe(
      "app",
    );
  });

  it("forces the login view once the SERVER has refused an app call", () => {
    // This is how Phase 2 arms the frontend without touching it: the 401 is the signal.
    expect(guardDecision({ status: "signedOut", enforcementSeen: true, profileSelected: false })).toBe(
      "login",
    );
  });

  it("renders the app for a signed-in session that has CHOSEN a profile", () => {
    expect(guardDecision({ status: "signedIn", enforcementSeen: false, profileSelected: true })).toBe(
      "app",
    );
    expect(guardDecision({ status: "signedIn", enforcementSeen: true, profileSelected: true })).toBe(
      "app",
    );
  });

  it("sends a signed-in session with NO profile to the picker (Phase B)", () => {
    // The fresh-sign-in state. Nothing else may claim the app in this world: a session with
    // nobody watching is exactly what "Who's watching?" is for.
    expect(guardDecision({ status: "signedIn", enforcementSeen: false, profileSelected: false })).toBe(
      "picker",
    );
    expect(guardDecision({ status: "signedIn", enforcementSeen: true, profileSelected: false })).toBe(
      "picker",
    );
  });

  it("takes the app away for the SERVER's flag, never for a remembered click", () => {
    // The distinction this whole rule turns on: signed OUT with enforcement seen is a login
    // problem; signed IN without a profile is a picker problem. They are different screens.
    expect(
      guardDecision({ status: "signedOut", enforcementSeen: true, profileSelected: false }),
    ).not.toBe("picker");
    expect(
      guardDecision({ status: "signedIn", enforcementSeen: false, profileSelected: false }),
    ).not.toBe("login");
  });
});

describe("mayManageHousehold", () => {
  it("is true only for an administrator profile", () => {
    expect(mayManageHousehold(true)).toBe(true);
  });

  it("is false for a member profile", () => {
    expect(mayManageHousehold(false)).toBe(false);
  });

  it("fails CLOSED while the server has not answered", () => {
    // A briefly-visible admin link is worse than a briefly-missing one.
    expect(mayManageHousehold(undefined)).toBe(false);
  });
});

describe("accountDestinations", () => {
  const keys = (isAdmin: boolean | undefined) =>
    accountDestinations(isAdmin, true).map((d) => d.key);

  it("offers My password to EVERY profile — it is the lock on your own profile", () => {
    expect(keys(true)).toContain("password");
    expect(keys(false)).toContain("password");
    expect(keys(undefined)).toContain("password");
  });

  it("offers Household to administrators ONLY — his report, 2026-09-13", () => {
    expect(keys(true)).toContain("household");
    expect(keys(false)).not.toContain("household");
    // ⚠ While the server has not answered, the administrator does NOT get it either — the same
    // fail-closed rule the nav used. The bug he hit was the opposite: `is_admin` never arrived at
    // all, so Household vanished for EVERYONE including him.
    expect(keys(undefined)).not.toContain("household");
  });

  it("says Choose profile until one has been picked, then Switch profile", () => {
    const label = (selected: boolean) =>
      accountDestinations(true, selected).find((d) => d.key === "switch")?.label;
    expect(label(false)).toBe("Choose profile");
    expect(label(true)).toBe("Switch profile");
  });

  it("never offers an administrator destination to a member", () => {
    for (const isAdmin of [false, undefined]) {
      expect(accountDestinations(isAdmin, true).some((d) => d.adminOnly)).toBe(false);
    }
  });
});

describe("accountSubtitle", () => {
  it("names the role, and only names the account when it differs from the profile", () => {
    expect(accountSubtitle("rkm", "rkm", true)).toBe("Administrator");
    expect(accountSubtitle("Kid", "rkm", false)).toBe("Profile · signed in as rkm");
    expect(accountSubtitle("Kid", "", false)).toBe("Profile");
  });

  it("never calls a member an administrator", () => {
    expect(accountSubtitle("Kid", "rkm", false)).not.toContain("Administrator");
    expect(accountSubtitle("Kid", "rkm", undefined)).not.toContain("Administrator");
  });
});

describe("watchingName", () => {
  it("names the PROFILE — the identity media runs as", () => {
    expect(watchingName({ id: "kid", name: "Kid" }, { id: "admin", name: "admin" })).toBe("Kid");
  });

  it("falls back to the session's owner only when there is no profile at all", () => {
    expect(watchingName(null, { id: "admin", name: "admin" })).toBe("admin");
  });

  it("never names the OWNER for a profile that exists — that would be the wrong person", () => {
    // A nameless profile still has an id, so `displayName` uses it: falling back to the owner here
    // would put the administrator's name on somebody else's session.
    expect(watchingName({ id: "kid", name: "" }, { id: "admin", name: "admin" })).toBe("kid");
  });

  it("never returns a stray name for nobody at all", () => {
    expect(watchingName(null, null)).toBe("");
  });
});

describe("displayName", () => {
  it("prefers the Jellyfin name", () => {
    expect(displayName({ id: "uid-1", name: "Rajeev" })).toBe("Rajeev");
  });

  it("falls back to the id, then to a label — never an empty chip", () => {
    expect(displayName({ id: "uid-1", name: "" })).toBe("uid-1");
    expect(displayName({ id: "  ", name: " " })).toBe("Signed in");
    expect(displayName(null)).toBe("");
  });
});

describe("initials", () => {
  it("uses first + last initials", () => {
    expect(initials("Rajeev Kumar")).toBe("RK");
  });

  it("handles a single name, extra spaces and an empty one", () => {
    expect(initials("rajeev")).toBe("RA");
    expect(initials("  Rajeev   Kumar  ")).toBe("RK");
    expect(initials("")).toBe("?");
  });
});

describe("loginErrorMessage", () => {
  it("is generic on 401 — unknown user and wrong password are one message", () => {
    expect(loginErrorMessage({ status: 401 })).toBe("Incorrect username or password.");
  });

  it("names an unavailable media server as such (503)", () => {
    expect(loginErrorMessage({ status: 503 })).toContain("not available");
  });

  it("passes through a server detail for other HTTP failures", () => {
    expect(loginErrorMessage({ status: 429, message: "Too many attempts" })).toBe(
      "Too many attempts",
    );
    expect(loginErrorMessage({ status: 500, message: "" })).toBe("Sign-in failed (HTTP 500).");
  });

  it("says so when the request never reached the server", () => {
    expect(loginErrorMessage(new TypeError("fetch failed"))).toContain("Could not reach");
    expect(loginErrorMessage(undefined)).toContain("Could not reach");
  });
});
