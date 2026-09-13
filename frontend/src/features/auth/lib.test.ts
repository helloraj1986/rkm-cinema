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
  mayScanLibrary,
  accountDestinations,
  accountSubtitle,
  watchingName,
  type GuardDecision,
  type GuardInput,
} from "./lib";

/**
 * The guard's inputs, with the facts these tests are not about defaulted IN ONE PLACE.
 *
 * `profileStale` and `profileSelected` are both REQUIRED in the type on purpose — each can take the
 * app away, so no caller may inherit a silent default. The defaults for the tests live here, where
 * every case can see them, instead of inside the rule.
 */
function guard(overrides: Partial<GuardInput> = {}): GuardDecision {
  return guardDecision({
    status: "signedIn",
    enforcementSeen: false,
    profileSelected: true,
    profileStale: false,
    ...overrides,
  });
}

describe("guardDecision", () => {
  it("shows a skeleton until the session check answers", () => {
    expect(guard({ status: "loading", profileSelected: false })).toBe("skeleton");
    // …even when enforcement is already known: the answer may change the screen, and a
    // flash of the wrong one is exactly what the skeleton exists to prevent.
    expect(guard({ status: "loading", enforcementSeen: true })).toBe("skeleton");
  });

  it("lets a signed-out visitor use the app while nothing is enforced (Phase 1)", () => {
    expect(guard({ status: "signedOut", profileSelected: false })).toBe("app");
  });

  it("forces the login view once the SERVER has refused an app call", () => {
    // This is how Phase 2 arms the frontend without touching it: the 401 is the signal.
    expect(guard({ status: "signedOut", enforcementSeen: true, profileSelected: false })).toBe(
      "login",
    );
  });

  it("renders the app for a signed-in session that has CHOSEN a profile", () => {
    expect(guard({})).toBe("app");
    expect(guard({ enforcementSeen: true })).toBe("app");
  });

  it("sends a signed-in session with NO profile to the picker (Phase B)", () => {
    // The fresh-sign-in state. Nothing else may claim the app in this world: a session with
    // nobody watching is exactly what "Who's watching?" is for.
    expect(guard({ profileSelected: false })).toBe("picker");
    expect(guard({ enforcementSeen: true, profileSelected: false })).toBe("picker");
  });

  it("sends a session whose PROFILE credential was refused to the picker, never to login", () => {
    // Phase 5. The session is ALIVE — the server refused the credential the profile was acting as.
    // Logging out would throw a working session away and could not fix anything; choosing that
    // profile again is what re-authenticates it. This is the distinction between the two 401s.
    expect(guard({ profileStale: true })).toBe("picker");
    expect(guard({ profileStale: true })).not.toBe("login");
  });

  it("lets a stale notice out-rank the profile that is already selected", () => {
    // ⚠ A profile IS selected in exactly the world where its credential can go stale, so the stale
    // fact has to be read BEFORE `profileSelected` — otherwise the app would render over the notice
    // and the person would see the same blank library again.
    expect(guard({ profileSelected: true, profileStale: true })).toBe("picker");
  });

  it("keeps a signed-OUT session at the login view even with a stale notice lying around", () => {
    // The stale fact is about a live session; a leftover notice must not redirect a signed-out
    // visitor to a picker they have no session for.
    expect(guard({ status: "signedOut", enforcementSeen: true, profileStale: true })).toBe("login");
  });

  it("takes the app away for the SERVER's flag, never for a remembered click", () => {
    // The distinction this whole rule turns on: signed OUT with enforcement seen is a login
    // problem; signed IN without a profile is a picker problem. They are different screens.
    expect(guard({ status: "signedOut", enforcementSeen: true, profileSelected: false })).not.toBe(
      "picker",
    );
    expect(guard({ profileSelected: false })).not.toBe("login");
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

describe("mayScanLibrary", () => {
  // Phase E (2026-09-13): `GET /api/library/scan` and `POST /api/jobs/{name}/run` became
  // administrators-only, and `require_admin_session` is strict EVEN WHILE enforcement is off — so
  // a member's "Scan Library" button would answer 403 on today's stack. The app must not offer it.
  it("is true only for an administrator profile", () => {
    expect(mayScanLibrary(true)).toBe(true);
  });

  it("is false for a member profile", () => {
    expect(mayScanLibrary(false)).toBe(false);
  });

  it("fails CLOSED while the server has not answered", () => {
    // `undefined` is the moment before /api/auth/profiles replies — the same rule as the
    // household gate, and also the signed-out case, which the route refuses too.
    expect(mayScanLibrary(undefined)).toBe(false);
  });
});

describe("accountDestinations", () => {
  const keys = (isAdmin: boolean | undefined) =>
    accountDestinations(isAdmin, true).map((d) => d.key);

  it("offers Account & password to EVERY profile — it is the lock on your own profile", () => {
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

  it("offers Settings to every profile — it is session-scoped, not administrator-only", () => {
    // The mockup lists it for the administrator; the server's own gate (SESSION_SCOPED, not
    // require_admin_session) is what decides that a member may open it too.
    expect(keys(false)).toContain("settings");
    expect(keys(true)).toContain("settings");
  });

  it("keeps the mockup's order: Household · Account & password · Switch profile · Settings", () => {
    // His brief §2 gives the order; a reorder here is a change to the reference he handed over.
    expect(keys(true)).toEqual(["household", "password", "switch", "settings"]);
    expect(keys(false)).toEqual(["password", "switch", "settings"]);
  });

  it("labels the password entry 'Account & password' — his wording, and the same destination", () => {
    const entry = accountDestinations(true, true).find((d) => d.key === "password");
    expect(entry?.label).toBe("Account & password");
    // The destination did NOT move: it is still the screen that changes the profile in effect's
    // password (`/settings/password`).
    expect(entry?.to).toBe("/settings/password");
  });

  it("tags Household ADMIN and nothing else", () => {
    const tagged = accountDestinations(true, true).filter((d) => d.tag);
    expect(tagged.map((d) => d.key)).toEqual(["household"]);
    expect(tagged[0].tag).toBe("ADMIN");
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
