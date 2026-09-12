/**
 * "Change my password" rules (ADMIN_CREDENTIALS_PLAN.md §6, Phase 3) — the parts that must not be
 * got wrong.
 *
 * The server is the authority for whether a change is allowed. These tests are about the screen
 * being honest and, above all, about NOT inventing a rule the media server does not have: an
 * account with NO password is a legitimate Jellyfin account, and a rule that demanded a current
 * password from it would lock those accounts out of their own screen — the same class of bug that
 * once made them unable to sign in at all.
 */
import { describe, expect, it } from "vitest";

import { changeErrorMessage, changeIssue, confirmationMessage, MIN_HINT } from "./password";

describe("changeIssue", () => {
  it("allows a well-formed change when the account HAS a password", () => {
    expect(changeIssue("old", "new", "new", true)).toEqual({ allowed: true, reason: "" });
  });

  it("requires the current password when the server says there IS one", () => {
    const d = changeIssue("", "new", "new", true);
    expect(d.allowed).toBe(false);
    expect(d.reason).toMatch(/current password/i);
  });

  it("does NOT require the current password while the server has not said", () => {
    // `null` = the profiles list has not arrived. Assuming "required" would break password-less
    // accounts; assuming "not required" only defers to the server, which is the authority.
    expect(changeIssue("", "new", "new", null).allowed).toBe(true);
  });

  it("does NOT require the current password for an account that has none", () => {
    expect(changeIssue("", "new", "new", false).allowed).toBe(true);
  });

  it("says so when a password-less account supplies one anyway — allowed, not an error", () => {
    // Jellyfin accepts any value for an account with no password, so refusing this would be a lie.
    const d = changeIssue("guessed", "new", "new", false);
    expect(d.allowed).toBe(true);
    expect(d.reason).toMatch(/no password/i);
  });

  it("refuses a truly empty new password", () => {
    const d = changeIssue("old", "", "", true);
    expect(d.allowed).toBe(false);
    expect(d.reason).toMatch(/choose a new password/i);
  });

  it("allows a whitespace-only password, because the media server does", () => {
    // A footgun, but real: blocking it here would be a second implementation of the server's
    // contract — the trap that once made a password-LESS account unusable.
    expect(changeIssue("old", "   ", "   ", true).allowed).toBe(true);
  });

  it("refuses a mismatch, and says which field is wrong", () => {
    const d = changeIssue("old", "new", "new-ish", true);
    expect(d.allowed).toBe(false);
    expect(d.reason).toMatch(/do not match/i);
  });

  it("checks the mismatch before the current password, so both are not blamed at once", () => {
    const d = changeIssue("", "new", "other", true);
    expect(d.reason).toMatch(/do not match/i);
  });

  it("does not invent a length rule", () => {
    expect(changeIssue("old", "a", "a", true).allowed).toBe(true);
    expect(MIN_HINT).toMatch(/no length rule/i);
  });

  it("allows re-setting the SAME password (the server does; nothing here blocks it)", () => {
    expect(changeIssue("same", "same", "same", true).allowed).toBe(true);
  });
});

describe("confirmationMessage", () => {
  it("claims a change only when the new password actually signed in", () => {
    expect(confirmationMessage("verified")).toEqual({ ok: true, text: "Password changed." });
  });

  it("does NOT call a refusal applied, and does not call it a failure of the user either", () => {
    const m = confirmationMessage("refused");
    expect(m.ok).toBe(false);
    expect(m.text).toMatch(/may not have been applied/i);
    expect(m.text).toMatch(/administrator/i);
  });

  it("treats 'could not ask' as unknown, never as 'not applied'", () => {
    // The live lesson: a check that could not be completed said "it was not applied" to somebody
    // whose change HAD landed.
    const m = confirmationMessage("unavailable");
    expect(m.ok).toBe(false);
    expect(m.text).not.toMatch(/not been applied|not applied/i);
    expect(m.text).toMatch(/could not be confirmed/i);
  });

  it("does NOT read a MISSING confirmation as success", () => {
    // An api that says nothing has told us nothing. Defaulting to "changed" here is exactly the
    // lie this whole round of work was about, so silence falls into the honest branch.
    const m = confirmationMessage(undefined);
    expect(m.ok).toBe(false);
    expect(m.text).toMatch(/could not be confirmed/i);
  });
});

describe("changeErrorMessage", () => {
  it("maps a 401 to the current password being wrong", () => {
    expect(changeErrorMessage({ status: 401, message: "" })).toMatch(/current password/i);
  });

  it("prefers the SERVER's own words when it sent any", () => {
    expect(changeErrorMessage({ status: 400, detail: "A new password is required — an account is created without one" }))
      .toMatch(/created without one/);
    expect(changeErrorMessage({ status: 502, detail: "The media server refused the password change" }))
      .toMatch(/refused the password change/);
  });

  it("never shows the HTTP client's trace as if it were a message", () => {
    // `ApiError.message` is `METHOD path -> status` when the server said nothing. It is the one
    // thing the screen must not put in front of a person — the browser check caught exactly this.
    expect(changeErrorMessage({ status: 502, message: "POST /auth/profile/password -> 502", detail: null }))
      .toMatch(/old password still works/i);
    expect(changeErrorMessage({ status: 502, message: "POST /auth/profile/password -> 502", detail: null }))
      .not.toMatch(/->/);
  });

  it("maps a 502 with no explanation to a message that says the OLD password still works", () => {
    const message = changeErrorMessage({ status: 502, detail: null });
    expect(message).toMatch(/refused/i);
    expect(message).toMatch(/old password still works/i);
  });

  it("maps a 503 to 'could not reach', never to a refusal", () => {
    // The difference matters: one sends the user to their keyboard, the other to the server.
    expect(changeErrorMessage({ status: 503, detail: null })).toMatch(/could not reach/i);
  });

  it("falls back honestly when there is no HTTP status at all", () => {
    expect(changeErrorMessage(new Error("boom"))).toMatch(/could not reach the server/i);
  });
});
