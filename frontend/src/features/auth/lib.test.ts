/**
 * Sign-in rules (AUTH_MULTIUSER_PLAN Phase 1) — the guard matrix and the messages.
 *
 * These are the tests that stop the two ways this feature can hurt the user:
 * taking the app away when nothing is enforced, and showing a login form to someone who
 * is already signed in (a flash of the wrong screen on every page load).
 */
import { describe, expect, it } from "vitest";

import { displayName, guardDecision, initials, loginErrorMessage } from "./lib";

describe("guardDecision", () => {
  it("shows a skeleton until the session check answers", () => {
    expect(guardDecision({ status: "loading", enforcementSeen: false })).toBe("skeleton");
    // …even when enforcement is already known: the answer may change the screen, and a
    // flash of the wrong one is exactly what the skeleton exists to prevent.
    expect(guardDecision({ status: "loading", enforcementSeen: true })).toBe("skeleton");
  });

  it("lets a signed-out visitor use the app while nothing is enforced (Phase 1)", () => {
    expect(guardDecision({ status: "signedOut", enforcementSeen: false })).toBe("app");
  });

  it("forces the login view once the SERVER has refused an app call", () => {
    // This is how Phase 2 arms the frontend without touching it: the 401 is the signal.
    expect(guardDecision({ status: "signedOut", enforcementSeen: true })).toBe("login");
  });

  it("renders the app for a signed-in session", () => {
    expect(guardDecision({ status: "signedIn", enforcementSeen: false })).toBe("app");
    expect(guardDecision({ status: "signedIn", enforcementSeen: true })).toBe("app");
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
