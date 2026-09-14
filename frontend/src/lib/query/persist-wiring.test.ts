import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The WIRING of the disk cache — pinned by reading the files, because neither a unit test nor a
 * browser in this sandbox can see the result of getting it wrong.
 *
 * The cache now exists in two places. Every identity event (sign-in, sign-out, profile switch, a 401)
 * has to clear BOTH, and the one that is easy to forget is the disk — nothing on screen changes when
 * it is missed. The failure is not a stale render either: it is one household member's rows surviving
 * into another's launch on a shared iPad, which is why it is asserted rather than trusted to care.
 *
 * ⚠ `persist.test.ts` proves `clearCacheForIdentityChange()` clears both. This file proves the app
 * USES it — the same split as `shell-contract.test.ts`, and the same reason: a rule nothing calls is
 * worth nothing.
 */
const here = fileURLToPath(new URL(".", import.meta.url));
const read = (relative: string) => readFileSync(`${here}${relative}`, "utf8");

describe("the disk cache's wiring", () => {
  it("⚠ AuthProvider routes EVERY identity purge through the one helper", () => {
    const source = read("../../features/auth/AuthProvider.tsx");
    // The helper clears memory AND storage. A bare clear() is exactly the bug this pins.
    expect(source).not.toMatch(/queryClient\.clear\(\)/);
    // Four call sites: the 401 handler, the stale-profile handler, sign-in, the profile switch,
    // plus sign-out. Asserted as a COUNT so deleting one is a failure, not a smaller number.
    const uses = source.match(/clearCacheForIdentityChange\(queryClient\)/g) ?? [];
    expect(uses.length).toBe(5);
  });

  it("⚠ …and it adopts the snapshot exactly where the profile becomes known", () => {
    const source = read("../../features/auth/AuthProvider.tsx");
    // Restoring anywhere else means painting for whoever held the device last. `applyMe` is the one
    // moment the server has said who is watching, and the profile switch must re-stamp the owner or
    // nothing is written for the rest of the session.
    expect(source).toMatch(/adoptPersistedCache\(queryClient, who\.id\)/);
    expect(source).toMatch(/setPersistedCacheOwner\(result\.profile\.id\)/);
  });

  it("⚠ main.tsx does NOT restore at module scope — it only starts the writer", () => {
    const source = read("../../main.tsx");
    expect(source).toMatch(/startQueryCachePersistence\(queryClient\)/);
    // No restore here, on purpose: at this point nobody has said who is watching. (The comment
    // above the line may NAME it — what must not exist is a CALL.)
    expect(source).not.toMatch(/adoptPersistedCache\(queryClient/);
    // …and gcTime must cover the snapshot's life, or a restored entry is garbage-collected out from
    // under the restore on a slow boot (the persist layer's own max age is the right number).
    expect(source).toMatch(/gcTime:\s*CACHE_GC_TIME_MS/);
  });

  it("⚠ the library queries are the app's own keys — the policy root is not a typo", () => {
    // The policy persists key root "library". If a hook ever moves to another root, the disk cache
    // silently stops holding that screen — which looks like "the cache does not work" and is chased
    // in the wrong file. Cheaper to assert the roots line up.
    const api = read("../../features/library/api.ts");
    const keys = api.match(/queryKey:\s*\["library"/g) ?? [];
    expect(keys.length).toBeGreaterThanOrEqual(7);
  });
});
