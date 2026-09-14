/**
 * The React Query cache, on disk — phase A1 of docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md (§3.2).
 *
 * ⚠ WHY THIS EXISTS, MEASURED RATHER THAN ASSUMED: every `/api/` response is `no-store` by design,
 * and until now the QueryClient was memory-only (`main.tsx`), so a launch began with nothing and the
 * home screen paid for its own data again — his own device log shows ~6 calls and ~1 s for one home
 * screen (`/api/library/items`, `/api/library`, `recently-watched`, `continue-watching`, `/folders`,
 * a detail call). A0 made the SHELL arrive from cache; this makes the ROWS arrive from disk, so the
 * screen paints what it showed last time and then revalidates in the background.
 *
 * Four rules, each pinned by a test that fails when it is removed:
 *
 *   1. FAIL-CLOSED POLICY  — only what `policy.ts` names is written; a new query key is not
 *      persisted until somebody argues for it there.
 *   2. ONE IDENTITY, OR NOTHING — a snapshot is adopted only when it was written FOR the profile now
 *      in effect (`owner`). A shared iPad must never flash one person's rows at another, and this is
 *      the rule that makes it impossible rather than unlikely.
 *   3. A SWAPPABLE HEADER — every snapshot carries `{schemaVersion, server}`. A build that changes
 *      the stored shape, or a different server address, DROPS it instead of rendering it.
 *   4. IT NEVER THROWS — storage can be absent (Safari private browsing hands out the object and
 *      then throws on write), full, or corrupt. Every entry point is total: a persistence failure
 *      degrades to today's behaviour (no cache), never to a blank screen.
 *
 * ⚠ localStorage, NOT IndexedDB, and the trade is deliberate:
 *   * it is SYNCHRONOUS — "paint before the network" is the whole point, and an async adapter's
 *     restore lands a tick too late to be free;
 *   * it is not purgeable by the OS under storage pressure (unlike `Caches/`), so a downloaded-for-
 *     later cache cannot silently vanish;
 *   * zero new dependencies in an app that has six.
 * The whole persisted set measures in tens of kB (the largest single payload on his stack is
 * `/api/library/items` at 60.1 KB), and `CACHE_MAX_BYTES` below drops a snapshot that grows past a
 * sane bound rather than letting a 900-title library fill the ~5 MB quota. If that day ever comes,
 * the migration is a `CacheStorage` implementation behind this same interface and nothing else.
 *
 * ⚠ THE RESTORE IS GATED ON THE PROFILE, AND THAT COSTS NOTHING — VERIFIED, NOT ASSUMED. The app
 * renders `SessionSkeleton` until `me()` answers (`RequireSession` → `guardDecision`), so NO app
 * content can paint before the profile is known. Adopting the snapshot at that moment is therefore
 * free, and it buys the cross-profile guarantee above. (Restoring at module scope would paint for
 * whoever was on the device last, before anyone could check.)
 */
import { dehydrate, hydrate, type QueryClient } from "@tanstack/react-query";

import { PERSIST_SCHEMA_VERSION, isPersistableKey, shouldPersistQuery } from "./policy";

/** Key and lifetime of the single stored snapshot. */
export const CACHE_STORAGE_KEY = "rkm.query-cache.v1";

/** A snapshot older than this is dropped: a day-old poster wall is not a launch win, it is a lie. */
export const CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000;

/** Above this, the snapshot is dropped (and logged) rather than written: the quota is ~5 MB. */
export const CACHE_MAX_BYTES = 1_500_000;

/** Writes are coalesced this long; a burst of six landing queries is one write, not six. */
export const CACHE_WRITE_DELAY_MS = 1000;

/** The `gcTime` the client needs for a restored entry to survive in memory unobserved. */
export const CACHE_GC_TIME_MS = CACHE_MAX_AGE_MS;

/** The slice of Web Storage we use. Narrow on purpose: a test can hand in a 12-line object. */
export interface CacheStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** What a snapshot says about itself, and everything a read is allowed to reject on. */
export interface CacheEnvelope {
  schemaVersion: number;
  /** The origin the rows came from — a different address is a different library. */
  server: string;
  /** The profile id the rows belong to. */
  owner: string;
  savedAt: number;
  state: unknown;
}

/** `"restored"` — the rows are in memory; `"none"` — nothing stored; `"foreign"` — dropped (see the rules). */
export type AdoptVerdict = "restored" | "none" | "foreign";

/** The profile the persisted rows belong to, or null when nobody is watching (nothing is written). */
let cacheOwner: string | null = null;

/**
 * The browser's storage, or null when we may not have one.
 *
 * ⚠ Safari in private browsing returns a `localStorage` object and throws only on the first WRITE,
 * so the capability is probed rather than detected. A `try` around the access alone would look like
 * success and then fail silently at the first save.
 */
export function defaultStorage(): CacheStorage | null {
  try {
    const store = globalThis.localStorage;
    if (!store) return null;
    const probe = "__rkm_storage_probe__";
    store.setItem(probe, "1");
    store.removeItem(probe);
    return store;
  } catch {
    return null;
  }
}

/** The origin the app is served from — the same fact that decides which server's rows these are. */
export function currentServer(): string {
  try {
    return globalThis.location?.origin ?? "";
  } catch {
    return "";
  }
}

/** Who the stored rows belong to (exposed for the tests and for diagnostics). */
export function persistedCacheOwner(): string | null {
  return cacheOwner;
}

/**
 * Adopt a snapshot for the profile now in effect. Sets the owner either way, so subsequent writes
 * are stamped with the right person even when there was nothing to restore.
 */
export function adoptPersistedCache(
  queryClient: QueryClient,
  owner: string,
  storage: CacheStorage | null = defaultStorage(),
): AdoptVerdict {
  cacheOwner = owner;
  const envelope = readEnvelope(storage);
  if (!envelope) return "none";
  if (envelope.owner !== owner) {
    // Rule 2/the header rule: somebody else's rows, or another server's. Drop, do not render.
    purgePersistedCache(storage);
    return "foreign";
  }
  hydrate(queryClient, persistedQueriesOnly(envelope.state));
  return "restored";
}

/**
 * ⚠ THE POLICY IS APPLIED ON THE WAY OUT **AND ON THE WAY IN** — the second half is not redundancy.
 * A snapshot is a string in the user's own browser: it can be edited, produced by a build whose
 * policy was looser, or left behind by an older version of this file. Filtering on the way in means
 * the rule in `policy.ts` is the authority even when the caller is not, so a `["auth","me"]` row can
 * never be rehydrated even if it is sitting in storage.
 */
function persistedQueriesOnly(state: unknown): Parameters<typeof hydrate>[1] {
  const shape = state as { queries?: unknown; mutations?: unknown } | null;
  const queries = Array.isArray(shape?.queries)
    ? (shape?.queries as Array<{ queryKey?: unknown }>).filter(
        (query) => Array.isArray(query?.queryKey) && isPersistableKey(query.queryKey as readonly unknown[]),
      )
    : [];
  return { mutations: [], queries } as unknown as Parameters<typeof hydrate>[1];
}

/**
 * Record who is watching WITHOUT restoring anything — the profile-switch path, where the cache was
 * just purged and the next write must still be stamped with the new person.
 */
export function setPersistedCacheOwner(owner: string): void {
  cacheOwner = owner;
}

/** Remove the stored snapshot, keeping the owner. Storage that refuses a delete is useless anyway. */
function dropKey(storage: CacheStorage): void {
  try {
    storage.removeItem(CACHE_STORAGE_KEY);
  } catch {
    /* nothing useful to do */
  }
}

/** Delete the stored snapshot. Safe to call when there is none, or when there is no storage. */
export function purgePersistedCache(storage: CacheStorage | null = defaultStorage()): void {
  cacheOwner = null;
  if (!storage) return;
  dropKey(storage);
}

/**
 * ⚠ THE ONE CALL EVERY IDENTITY CHANGE MUST MAKE. Sign-in, sign-out, profile switch and the 401
 * path all need the SAME two effects — memory and disk — and doing them in five places is how one
 * gets forgotten. A stale snapshot outliving a sign-out is an identity leak, not a performance bug,
 * so it is one function with one test (and a structural pin that `AuthProvider` routes every purge
 * through it).
 */
export function clearCacheForIdentityChange(
  queryClient: QueryClient,
  storage: CacheStorage | null = defaultStorage(),
): void {
  queryClient.clear();
  purgePersistedCache(storage);
}

/**
 * Write the cache out. Returns the size written, or null when nothing was written (no owner, no
 * storage, too large, or storage refused).
 */
export function writePersistedCache(
  queryClient: QueryClient,
  owner: string | null = cacheOwner,
  storage: CacheStorage | null = defaultStorage(),
): number | null {
  // ⚠ No owner = nobody signed in = NOTHING is written. This is the rule that keeps a signed-out
  // device from holding rows at all, and it is why `purge` clears the owner as well as the key.
  if (!owner || !storage) return null;

  let serialised: string;
  try {
    const state = dehydrate(queryClient, {
      shouldDehydrateQuery: (query) =>
        shouldPersistQuery(query as unknown as { queryKey: readonly unknown[]; state: { status: string } }),
    });
    // ⚠ NOTHING WORTH STORING = NO WRITE AT ALL. A cache emptied by an identity purge (or by a
    // navigation that garbage-collected everything) must not be persisted as an empty snapshot: it
    // is pure noise, and it would replace a still-useful one. The caller's purge is what clears the
    // key, so "leave the storage alone" is the honest answer here.
    if (state.queries.length === 0) return null;
    const envelope: CacheEnvelope = {
      schemaVersion: PERSIST_SCHEMA_VERSION,
      server: currentServer(),
      owner,
      savedAt: Date.now(),
      state,
    };
    serialised = JSON.stringify(envelope);
  } catch {
    // A cache that cannot be serialised is not a reason to break the app.
    return null;
  }

  if (serialised.length > CACHE_MAX_BYTES) {
    // Over the bound: keep nothing rather than a partial set, which would restore a home screen
    // with silent holes in it. Dropping is honest; a half-cache looks like a server fault.
    // ⚠ `dropKey`, NOT `purgePersistedCache` — purge also forgets who is watching, which would
    // silently stop every write for the rest of the session.
    dropKey(storage);
    return null;
  }

  try {
    storage.setItem(CACHE_STORAGE_KEY, serialised);
  } catch {
    // Quota exceeded, or private browsing. Today's behaviour (no disk cache) is the fallback.
    return null;
  }
  return serialised.length;
}

/**
 * Read + validate. EVERY rejection path also DELETES, so an unreadable snapshot cannot be re-read
 * on the next launch and cost the same parse again.
 */
export function readEnvelope(storage: CacheStorage | null = defaultStorage()): CacheEnvelope | null {
  if (!storage) return null;
  let raw: string | null = null;
  try {
    raw = storage.getItem(CACHE_STORAGE_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;

  const drop = () => {
    try {
      storage.removeItem(CACHE_STORAGE_KEY);
    } catch {
      /* nothing useful to do */
    }
    return null;
  };

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return drop();
  }
  if (!parsed || typeof parsed !== "object") return drop();

  const envelope = parsed as Partial<CacheEnvelope>;
  if (typeof envelope.owner !== "string" || envelope.owner === "") return drop();
  if (typeof envelope.savedAt !== "number") return drop();
  if (envelope.schemaVersion !== PERSIST_SCHEMA_VERSION) return drop();
  if (envelope.server !== currentServer()) return drop();
  if (Date.now() - envelope.savedAt > CACHE_MAX_AGE_MS) return drop();
  if (!envelope.state || typeof envelope.state !== "object") return drop();

  return envelope as CacheEnvelope;
}

/**
 * Start writing the cache out as it changes. Returns the stop function.
 *
 * ⚠ The `pagehide`/`visibilitychange` flush is not a refinement — it is the whole thing on iOS. The
 * shell's web view is suspended (and later jettisoned) without warning, so a write that only ever
 * happens on a timer can be the one that never lands. `hidden` is the last reliable moment.
 */
export function startQueryCachePersistence(
  queryClient: QueryClient,
  storage: CacheStorage | null = defaultStorage(),
): () => void {
  if (!storage) return () => {};

  let timer: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;

  const flush = () => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    writePersistedCache(queryClient, cacheOwner, storage);
  };

  const schedule = () => {
    if (stopped || timer !== null) return;
    timer = setTimeout(() => {
      timer = null;
      writePersistedCache(queryClient, cacheOwner, storage);
    }, CACHE_WRITE_DELAY_MS);
  };

  const unsubscribe = queryClient.getQueryCache().subscribe(schedule);

  const doc: Document | undefined = globalThis.document;
  const onVisibility = () => {
    if (doc?.visibilityState === "hidden") flush();
  };
  doc?.addEventListener("visibilitychange", onVisibility);
  globalThis.addEventListener?.("pagehide", flush);

  return () => {
    stopped = true;
    unsubscribe();
    doc?.removeEventListener("visibilitychange", onVisibility);
    globalThis.removeEventListener?.("pagehide", flush);
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  };
}

/** Wipe the module's memory of who is watching — tests only; production goes through the verbs above. */
export function __resetPersisterForTests(): void {
  cacheOwner = null;
}
