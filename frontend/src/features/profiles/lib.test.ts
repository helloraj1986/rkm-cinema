/**
 * "Who's watching?" rules (PLEX_PROFILE_AUTH_PLAN Phase B).
 *
 * These are the tests that stop the two ways the picker can hurt somebody:
 * asking for a password where none is needed (a household member created without one must open
 * with nothing typed), and NOT asking where one is required (the administrator's profile always
 * asks, even with no password set — a blank post would take a 401 and read as a broken app).
 */
import { describe, expect, it } from "vitest";

import {
  HOME_ROUTE,
  blockedReason,
  isSelectable,
  pickerErrorMessage,
  pickerSubtitle,
  requiresPassword,
  safeNext,
  watchingNow,
} from "./lib";
import type { ProfileUserShape } from "../../lib/api/client";

function profile(over: Partial<ProfileUserShape> = {}): ProfileUserShape {
  return {
    id: "uid-1",
    name: "Someone",
    is_admin: false,
    has_password: false,
    disabled: false,
    last_login: "",
    ...over,
  };
}

describe("requiresPassword", () => {
  it("asks for an ordinary protected profile", () => {
    expect(requiresPassword(profile({ has_password: true }))).toBe(true);
  });

  it("does NOT ask for a password-less household profile", () => {
    // User decision 1c: a member is created with no password, so the picker must POST an empty
    // one rather than blocking on a prompt nobody can fill.
    expect(requiresPassword(profile({ has_password: false }))).toBe(false);
  });

  it("ALWAYS asks for the administrator's own profile — even with no password set", () => {
    // The server refuses a blank attempt on that profile whatever its account holds (decision 3,
    // the shared-device rule). Keying the prompt off `has_password` alone would post blank, take
    // a 401, and look like a bug in the app.
    expect(requiresPassword(profile({ is_admin: true, has_password: false }))).toBe(true);
    expect(requiresPassword(profile({ is_admin: true, has_password: true }))).toBe(true);
  });
});

describe("isSelectable / blockedReason", () => {
  it("offers an enabled profile", () => {
    expect(isSelectable(profile())).toBe(true);
    expect(blockedReason(profile())).toBe("");
  });

  it("refuses a disabled one and says why", () => {
    const off = profile({ disabled: true });
    expect(isSelectable(off)).toBe(false);
    expect(blockedReason(off)).toContain("switched off");
  });
});

describe("watchingNow", () => {
  it("claims it only for the profile the SERVER reported, and only once one was chosen", () => {
    expect(watchingNow("uid-1", "uid-1", true)).toBe(true);
    expect(watchingNow("uid-2", "uid-1", true)).toBe(false);
  });

  it("claims nothing before a profile has been chosen", () => {
    // `current` falls back to the OWNER, so without the server's flag the administrator's row
    // would be labelled "Watching now" on a session where nobody has picked anything.
    expect(watchingNow("uid-1", "uid-1", false)).toBe(false);
    expect(watchingNow("", "", true)).toBe(false);
  });
});

describe("safeNext", () => {
  it("keeps an internal path", () => {
    expect(safeNext("/library/item/abc?t=1")).toBe("/library/item/abc?t=1");
  });

  it("refuses an off-app redirect — the value arrives in a URL", () => {
    expect(safeNext("https://evil.example")).toBe(HOME_ROUTE);
    expect(safeNext("//evil.example")).toBe(HOME_ROUTE);
    expect(safeNext("/\\evil.example")).toBe(HOME_ROUTE);
    expect(safeNext("javascript:alert(1)")).toBe(HOME_ROUTE);
  });

  it("never sends anyone back to the frames that have no content (a loop)", () => {
    expect(safeNext("/login")).toBe(HOME_ROUTE);
    expect(safeNext("/profiles")).toBe(HOME_ROUTE);
  });

  it("falls back to Home for nothing at all", () => {
    expect(safeNext(null)).toBe(HOME_ROUTE);
    expect(safeNext("")).toBe(HOME_ROUTE);
    expect(safeNext("   ")).toBe(HOME_ROUTE);
  });
});

describe("pickerErrorMessage", () => {
  it("is generic on 401 and never echoes the password", () => {
    expect(pickerErrorMessage({ status: 401 })).toBe("That profile's password is not correct.");
  });

  it("passes the server's own sentence through on 403 (a disabled profile, a locked switch-back)", () => {
    expect(
      pickerErrorMessage({ status: 403, message: "That profile is disabled — ask the administrator" }),
    ).toContain("ask the administrator");
  });

  it("names an unavailable media server as such (503)", () => {
    expect(pickerErrorMessage({ status: 503 })).toContain("not available");
  });

  it("explains a profile that has gone (404) and any other status", () => {
    expect(pickerErrorMessage({ status: 404 })).toContain("no longer on the server");
    expect(pickerErrorMessage({ status: 500, message: "" })).toBe("Could not switch profile (HTTP 500).");
  });

  it("says so when the request never reached the server", () => {
    expect(pickerErrorMessage(new TypeError("fetch failed"))).toContain("Could not reach");
  });
});

describe("pickerSubtitle", () => {
  it("counts the profiles and says whether one is in effect", () => {
    expect(pickerSubtitle(1, false)).toContain("1 profile");
    expect(pickerSubtitle(4, false)).toContain("4 profiles");
    expect(pickerSubtitle(4, true)).toContain("pick who is watching");
  });
});
