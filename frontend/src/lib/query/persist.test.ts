import { QueryClient } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CACHE_MAX_AGE_MS,
  CACHE_STORAGE_KEY,
  __resetPersisterForTests,
  adoptPersistedCache,
  clearCacheForIdentityChange,
  currentServer,
  purgePersistedCache,
  readEnvelope,
  setPersistedCacheOwner,
  startQueryCachePersistence,
  writePersistedCache,
  type CacheStorage,
} from "./persist";
import { PERSIST_SCHEMA_VERSION } from "./policy";

/**
 * The disk cache's rules, each asserted in the direction that FAILS when the rule is removed
 * (this repo's house rule: a check that cannot fail is documentation).
 *
 * These are node-env unit tests over a twelve-line storage stub — deliberately not a browser, so
 * they run fast and can be falsified cheaply. What they cannot prove is the WIRING (that the app
 * really restores, really purges, and paints with the network dead); that is `tools/check_query_cache.py`
 * over `frontend/harness/cache-frame.*`, plus the structural pin in `persist-wiring.test.ts`.
 */
function memoryStorage(initial: Record<string, string> = {}): CacheStorage & { readonly raw: Map<string, string> } {
  const raw = new Map(Object.entries(initial));
  return {
    raw,
    getItem: (key) => raw.get(key) ?? null,
    setItem: (key, value) => void raw.set(key, value),
    removeItem: (key) => void raw.delete(key),
  };
}

const LIBRARY = { items: [{ item_id: "i1", title: "The Matrix", year: 1999 }] };
const MOVIE = { item_id: "i1", title: "The Matrix" };

function clientWith(data: unknown = LIBRARY): QueryClient {
  const qc = new QueryClient();
  qc.setQueryData(["library", "items"], data);
  return qc;
}

beforeEach(() => {
  __resetPersisterForTests();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("a snapshot is restored only for the profile it was written for", () => {
  it("restores the rows the same profile left behind", () => {
    const store = memoryStorage();
    expect(writePersistedCache(clientWith(), "uid-raj", store)).toBeGreaterThan(0);

    const next = new QueryClient();
    expect(adoptPersistedCache(next, "uid-raj", store)).toBe("restored");
    expect(next.getQueryData(["library", "items"])).toEqual(LIBRARY);
  });

  it("⚠ REFUSES another profile's rows AND deletes them", () => {
    // The shared-iPad case. A "restore everything and let the picker sort it out" design paints one
    // person's Continue Watching at another; this one cannot, because the owner is checked first.
    const store = memoryStorage();
    writePersistedCache(clientWith(), "uid-raj", store);

    const next = new QueryClient();
    expect(adoptPersistedCache(next, "uid-kid", store)).toBe("foreign");
    expect(next.getQueryData(["library", "items"])).toBeUndefined();
    expect(store.getItem(CACHE_STORAGE_KEY)).toBeNull();
  });

  it("⚠ writes NOTHING while nobody is signed in", () => {
    const store = memoryStorage();
    expect(writePersistedCache(clientWith(), null, store)).toBeNull();
    expect(store.getItem(CACHE_STORAGE_KEY)).toBeNull();
  });

  it("remembers the new profile after a switch, so the next launch restores for THEM", () => {
    const store = memoryStorage();
    writePersistedCache(clientWith(), "uid-raj", store);
    purgePersistedCache(store);
    setPersistedCacheOwner("uid-kid");

    writePersistedCache(clientWith({ items: [{ item_id: "i2", title: "Frozen" }] }), undefined, store);
    const envelope = readEnvelope(store);
    expect(envelope?.owner).toBe("uid-kid");
    expect(adoptPersistedCache(new QueryClient(), "uid-raj", store)).toBe("foreign");
  });
});

describe("the snapshot's own header is checked before anything is restored", () => {
  const craft = (overrides: Record<string, unknown>): string =>
    JSON.stringify({
      schemaVersion: PERSIST_SCHEMA_VERSION,
      server: currentServer(),
      owner: "uid-raj",
      savedAt: Date.now(),
      state: { mutations: [], queries: [{ queryKey: ["library", "items"], state: { status: "success", data: LIBRARY, dataUpdatedAt: Date.now() } }] },
      ...overrides,
    });

  it("⚠ DROPS a snapshot from a different schema version", () => {
    const store = memoryStorage({ [CACHE_STORAGE_KEY]: craft({ schemaVersion: PERSIST_SCHEMA_VERSION + 1 }) });
    expect(readEnvelope(store)).toBeNull();
    expect(store.getItem(CACHE_STORAGE_KEY)).toBeNull(); // …and it is not re-read next launch
    expect(adoptPersistedCache(new QueryClient(), "uid-raj", store)).toBe("none");
  });

  it("⚠ DROPS a snapshot from a different server address", () => {
    // A different origin is a different library — the same browser profile may hold several.
    const store = memoryStorage({ [CACHE_STORAGE_KEY]: craft({ server: "http://some-other-box:8124" }) });
    expect(readEnvelope(store)).toBeNull();
    expect(adoptPersistedCache(new QueryClient(), "uid-raj", store)).toBe("none");
  });

  it("⚠ DROPS a snapshot older than the maximum age", () => {
    const store = memoryStorage({
      [CACHE_STORAGE_KEY]: craft({ savedAt: Date.now() - CACHE_MAX_AGE_MS - 1 }),
    });
    expect(readEnvelope(store)).toBeNull();
  });

  it("still accepts one that is INSIDE the age bound (the check is not simply always failing)", () => {
    const store = memoryStorage({ [CACHE_STORAGE_KEY]: craft({ savedAt: Date.now() - 60_000 }) });
    expect(readEnvelope(store)).not.toBeNull();
  });

  it("⚠ NEVER THROWS on a corrupt or truncated snapshot", () => {
    for (const junk of ["", "{", "not json", "[]", '{"owner":null}', '{"owner":"a","savedAt":"x"}', "null"]) {
      const store = memoryStorage({ [CACHE_STORAGE_KEY]: junk });
      expect(() => readEnvelope(store)).not.toThrow();
      expect(readEnvelope(store)).toBeNull();
      expect(adoptPersistedCache(new QueryClient(), "uid-raj", store)).toBe("none");
    }
  });

  it("⚠ NEVER THROWS when storage itself misbehaves", () => {
    const hostile: CacheStorage = {
      getItem: () => {
        throw new Error("storage disabled");
      },
      setItem: () => {
        throw new Error("quota exceeded");
      },
      removeItem: () => {
        throw new Error("storage disabled");
      },
    };
    expect(readEnvelope(hostile)).toBeNull();
    expect(writePersistedCache(clientWith(), "uid-raj", hostile)).toBeNull();
    expect(() => purgePersistedCache(hostile)).not.toThrow();
    expect(() => clearCacheForIdentityChange(new QueryClient(), hostile)).not.toThrow();
  });

  it("⚠ NEVER THROWS when there is no storage at all (Safari private browsing)", () => {
    const qc = clientWith();
    expect(() => writePersistedCache(qc, "uid-raj", null)).not.toThrow();
    expect(writePersistedCache(qc, "uid-raj", null)).toBeNull();
    expect(adoptPersistedCache(qc, "uid-raj", null)).toBe("none");
    expect(() => clearCacheForIdentityChange(qc, null)).not.toThrow();
    expect(startQueryCachePersistence(qc, null)).toBeTypeOf("function");
  });

  it("⚠ REFUSES what the policy refuses even when it is already sitting in storage", () => {
    // The rule is applied on the way OUT and on the way IN: a snapshot is a string in the user's own
    // browser, so a hand-edited (or older-build) one must not be able to rehydrate a session row.
    const store = memoryStorage({
      [CACHE_STORAGE_KEY]: JSON.stringify({
        schemaVersion: PERSIST_SCHEMA_VERSION,
        server: currentServer(),
        owner: "uid-raj",
        savedAt: Date.now(),
        state: {
          mutations: [],
          queries: [
            { queryKey: ["auth", "me"], state: { status: "success", data: { user: { id: "uid-raj" } }, dataUpdatedAt: Date.now() } },
            { queryKey: ["library", "items"], state: { status: "success", data: LIBRARY, dataUpdatedAt: Date.now() } },
          ],
        },
      }),
    });
    const qc = new QueryClient();
    expect(adoptPersistedCache(qc, "uid-raj", store)).toBe("restored");
    expect(qc.getQueryData(["library", "items"])).toEqual(LIBRARY);
    expect(qc.getQueryData(["auth", "me"])).toBeUndefined();
  });
});

describe("an identity change leaves nothing behind — memory OR disk", () => {
  it("⚠ clears the storage as well as the cache", () => {
    const store = memoryStorage();
    const qc = clientWith();
    writePersistedCache(qc, "uid-raj", store);
    expect(store.getItem(CACHE_STORAGE_KEY)).not.toBeNull();

    clearCacheForIdentityChange(qc, store);

    expect(qc.getQueryData(["library", "items"])).toBeUndefined();
    expect(store.getItem(CACHE_STORAGE_KEY)).toBeNull();
  });

  it("⚠ THE PERSISTER DOES NOT SURVIVE A PROFILE SWITCH — the plan's own gate", () => {
    const store = memoryStorage();
    const qc = clientWith();
    writePersistedCache(qc, "uid-raj", store);

    // …the switch, exactly as `AuthProvider.selectProfile` performs it:
    clearCacheForIdentityChange(qc, store);
    setPersistedCacheOwner("uid-kid");

    // Nothing is written for the new person until they have data…
    expect(writePersistedCache(qc, undefined, store)).toBeNull();

    // …and the OLD person's rows are gone for good: the next launch for them restores nothing.
    expect(readEnvelope(store)).toBeNull();
    expect(adoptPersistedCache(new QueryClient(), "uid-raj", store)).toBe("none");
  });

  it("⚠ nothing is written AFTER a sign-out, even if a late query lands", () => {
    const store = memoryStorage();
    const qc = clientWith();
    writePersistedCache(qc, "uid-raj", store);
    clearCacheForIdentityChange(qc, store);

    qc.setQueryData(["library", "items"], LIBRARY); // a straggler response after the sign-out
    expect(writePersistedCache(qc, undefined, store)).toBeNull();
    expect(store.getItem(CACHE_STORAGE_KEY)).toBeNull();
  });
});

describe("the writer", () => {
  it("coalesces a burst of cache changes into one write", () => {
    vi.useFakeTimers();
    const store = memoryStorage();
    const qc = new QueryClient();
    const stop = startQueryCachePersistence(qc, store);
    setPersistedCacheOwner("uid-raj");

    qc.setQueryData(["library", "items"], LIBRARY);
    qc.setQueryData(["library", "folders"], { libraries: [] });
    expect(store.getItem(CACHE_STORAGE_KEY)).toBeNull(); // not synchronously — a burst is one write
    vi.advanceTimersByTime(1000);
    expect(readEnvelope(store)?.owner).toBe("uid-raj");

    stop();
    vi.useRealTimers();
  });

  it("stops writing once stopped (and never throws without a document)", () => {
    vi.useFakeTimers();
    const store = memoryStorage();
    const qc = new QueryClient();
    const stop = startQueryCachePersistence(qc, store);
    setPersistedCacheOwner("uid-raj");
    stop();

    qc.setQueryData(["library", "items"], LIBRARY);
    vi.advanceTimersByTime(5000);
    expect(store.getItem(CACHE_STORAGE_KEY)).toBeNull();
    vi.useRealTimers();
  });

  it("⚠ drops an over-sized snapshot instead of writing a partial one", () => {
    const store = memoryStorage();
    const qc = new QueryClient();
    setPersistedCacheOwner("uid-raj");
    // A library far past any real one: many rows, each with a long title.
    qc.setQueryData(["library", "items"], {
      items: Array.from({ length: 4000 }, (_, i) => ({ item_id: `i${i}`, title: "x".repeat(400) })),
    });
    expect(writePersistedCache(qc, undefined, store)).toBeNull();
    expect(store.getItem(CACHE_STORAGE_KEY)).toBeNull();
    // ⚠ …and the owner SURVIVES the drop, so the session keeps writing once the data shrinks
    // (a drop that also forgot the owner would stop saving for the rest of the session — silently).
    const small = new QueryClient();
    small.setQueryData(["library", "items"], { items: [MOVIE] });
    expect(writePersistedCache(small, undefined, store)).toBeGreaterThan(0);
    expect(readEnvelope(store)?.owner).toBe("uid-raj");
  });
});

describe("what is written", () => {
  it("⚠ holds only the policy's queries — a session row in the cache is never stored", () => {
    const store = memoryStorage();
    const qc = new QueryClient();
    qc.setQueryData(["library", "items"], LIBRARY);
    qc.setQueryData(["auth", "me"], { user: { id: "uid-raj" } });
    qc.setQueryData(["auth", "profiles"], { profiles: [] });
    qc.setQueryData(["health"], { ok: true });
    qc.setQueryData(["watchlist", "entries"], { entries: [] });

    expect(writePersistedCache(qc, "uid-raj", store)).toBeGreaterThan(0);
    const stored = store.getItem(CACHE_STORAGE_KEY) as string;
    expect(stored).toContain("library");
    const envelope = readEnvelope(store);
    const keys = (envelope?.state as { queries: Array<{ queryKey: string[] }> }).queries.map((q) => q.queryKey.join("/"));
    expect(keys).toEqual(["library/items"]);
  });

  it("⚠ does not store a FAILED query", async () => {
    const store = memoryStorage();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    await qc
      .fetchQuery({ queryKey: ["library", "items"], queryFn: () => Promise.reject(new Error("boom")) })
      .catch(() => undefined);
    qc.setQueryData(["library", "folders"], { libraries: [] });

    writePersistedCache(qc, "uid-raj", store);
    const envelope = readEnvelope(store);
    const keys = (envelope?.state as { queries: Array<{ queryKey: string[] }> }).queries.map((q) => q.queryKey.join("/"));
    expect(keys).toEqual(["library/folders"]);
  });
});
