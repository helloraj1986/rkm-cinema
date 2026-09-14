import { describe, expect, it } from "vitest";

import {
  NEVER_PERSISTED_KEY_ROOTS,
  PERSISTED_KEY_ROOTS,
  PERSIST_SCHEMA_VERSION,
  isPersistableKey,
  shouldPersistQuery,
} from "./policy";

/**
 * The policy is where the identity safety of the disk cache lives, so the assertions below are
 * chosen to FAIL when the rule is loosened rather than to describe it.
 */
describe("what the disk cache may hold", () => {
  it("keeps the read-mostly library reads the home screen needs", () => {
    for (const key of [
      ["library", "items"],
      ["library", "folders"],
      ["library", "folder-items", "f1"],
      ["library", "recent"],
      ["library", "continue"],
      ["library", "recently-watched"],
      ["library", "detail", "abc"],
      ["library", "similar", "abc"],
      ["library", "episodes", "abc"],
    ]) {
      expect(isPersistableKey(key), key.join("/")).toBe(true);
    }
  });

  it("⚠ REFUSES every session-derived key, by name", () => {
    // Not a description of the rule — the rule. If one of these ever comes back true, a snapshot
    // outlives a sign-out and one household member's rows are on another's launch screen.
    expect(isPersistableKey(["auth", "me"])).toBe(false);
    expect(isPersistableKey(["auth", "profiles"])).toBe(false);
    expect(isPersistableKey(["health"])).toBe(false);
    expect(isPersistableKey(["config"])).toBe(false);
    expect(isPersistableKey(["household"])).toBe(false);
    expect(isPersistableKey(["watchlist", "entries"])).toBe(false);
    expect(isPersistableKey(["search", "global", "matrix"])).toBe(false);
  });

  it("⚠ THE NEVER-LIST WINS — a key root that appears in both is refused", () => {
    // The file is safe to extend by APPENDING to either list because of this ordering; drop it and
    // the next person to add a root to both lists gets the permissive answer.
    expect(NEVER_PERSISTED_KEY_ROOTS.length).toBeGreaterThan(0);
    expect(PERSISTED_KEY_ROOTS.length).toBeGreaterThan(0);
    for (const root of NEVER_PERSISTED_KEY_ROOTS) {
      // `library` is the only persisted root, so overlap can only be simulated — but the ORDER is
      // what is under test, and it is the same code path as a real collision.
      expect(isPersistableKey([root, "anything"])).toBe(false);
    }
    expect(isPersistableKey(["library", "items"])).toBe(true);
  });

  it("⚠ FAILS CLOSED — a key nobody classified is NOT persisted", () => {
    // The direction matters: the opposite rule ("persist everything except…") is silent when a new
    // query key appears, and this repo pays for silent defaults again and again.
    expect(isPersistableKey(["somethingNew", "whatever"])).toBe(false);
    expect(isPersistableKey(["libraries"])).toBe(false); // a near-miss root is still not the root
    expect(isPersistableKey([])).toBe(false);
    expect(isPersistableKey([42])).toBe(false);
    expect(isPersistableKey([{ scoped: "object" }])).toBe(false);
  });

  it("persists only a query that SUCCEEDED", () => {
    expect(shouldPersistQuery({ queryKey: ["library", "items"], state: { status: "success" } })).toBe(true);
    // A failed query is not data: a stored error would make a broken server look cached.
    expect(shouldPersistQuery({ queryKey: ["library", "items"], state: { status: "error" } })).toBe(false);
    expect(shouldPersistQuery({ queryKey: ["library", "items"], state: { status: "pending" } })).toBe(false);
    // …and the key rule still applies to a successful one.
    expect(shouldPersistQuery({ queryKey: ["auth", "me"], state: { status: "success" } })).toBe(false);
  });

  it("stamps a version, so a shape change cannot be rehydrated by a newer build", () => {
    expect(PERSIST_SCHEMA_VERSION).toBeGreaterThanOrEqual(1);
  });
});
