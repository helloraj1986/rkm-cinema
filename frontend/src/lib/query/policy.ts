/**
 * WHAT is worth keeping on disk — one rule, in one place (NATIVE_FEEL_AND_OFFLINE_PLAN §3.2, phase A1).
 *
 * ⚠ THE RULE IS AN ALLOW-LIST, AND THE DIRECTION IS THE SAFETY PROPERTY. A query key nobody has
 * classified is NOT persisted. The opposite shape — "persist everything except…" — fails silently in
 * exactly the way this repo keeps paying for: a new query key is added months later, it happens to
 * carry something session-derived, and nothing anywhere says it went to disk. Here a new key needs
 * somebody to come to this file and argue for it.
 *
 * The never-list is not decoration either: `auth` holds the session truth (`me()`) and the profile
 * list, and a snapshot that outlives a sign-out would be an identity leak on a device the whole
 * household shares. It is named explicitly so that a reader can see the exclusions were decisions.
 */

/**
 * Bump when the SHAPE of what is persisted changes (a payload field renamed, a route's response
 * restructured). Every stored snapshot from a different version is dropped on read rather than
 * rehydrated into a component that no longer speaks its shape.
 */
export const PERSIST_SCHEMA_VERSION = 1;

/** Read-mostly, per-profile MEDIA metadata: rows, folders, item detail, related titles, episodes. */
export const PERSISTED_KEY_ROOTS: readonly string[] = ["library"];

/**
 * Refused even if a future edit moves them under a persisted root. Each line is a reason, not a
 * policy statement — the tests assert these keys are refused.
 */
export const NEVER_PERSISTED_KEY_ROOTS: readonly string[] = [
  "auth", // session truth (`/auth/me`) and the profile list — the picker is a SERVER fact
  "health", // a stored liveness answer is a lie: it is the one thing that must be live
  "config", // server build/appearance facts; 60 s staleTime, tiny, and re-read on launch anyway
  "household", // account administration — an administrator's view, invalidated by its own writes
  "watchlist", // app-owned state whose MUTATIONS change what a poster does; a stale copy misleads
  "search", // per-keystroke result sets: no launch value, and an ever-growing pile of keys
  "suggest",
];

/**
 * Does this query go to disk?
 *
 * ⚠ Two clauses, never one: a key root that appears in BOTH lists is REFUSED (the never-list wins).
 * That ordering is what makes the file safe to extend by appending.
 *
 * Pure and synchronous so it can be unit-tested without a browser — the whole policy is here, and
 * `persist.ts` only decides WHEN to write.
 */
export function isPersistableKey(queryKey: readonly unknown[]): boolean {
  const root = queryKey[0];
  if (typeof root !== "string") return false;
  if (NEVER_PERSISTED_KEY_ROOTS.includes(root)) return false;
  return PERSISTED_KEY_ROOTS.includes(root);
}

/** The shape `dehydrate()`'s `shouldDehydrateQuery` hands us — narrowed to what the rule needs. */
export interface DehydratableQuery {
  queryKey: readonly unknown[];
  state: { status: string };
}

/**
 * …and the same rule as `dehydrate()` wants it.
 *
 * ⚠ `status === "success"` is asserted HERE rather than relied on from TanStack's default: a failed
 * query is not data, and persisting one error's payload would make a broken server look cached.
 * Waiting queries are refused for the same reason (data is `undefined`).
 */
export function shouldPersistQuery(query: DehydratableQuery): boolean {
  if (query.state.status !== "success") return false;
  return isPersistableKey(query.queryKey);
}

/**
 * The trade-off, recorded where the next session will read it: Continue Watching and Recently
 * Watched DO carry a resume position, and they ARE persisted — they are the home screen's hero row
 * and dropping them would remove most of the win. That is safe only because the restored snapshot
 * keeps its original `dataUpdatedAt` (TanStack's dehydrate does this), so a row older than the
 * query's own `staleTime` (30 s by default, `main.tsx`) is painted AND revalidated immediately:
 * freshness is bounded by `staleTime`, not by the snapshot's age. A moment of "Resume 43:00" that
 * corrects itself within a second is worth an instant home screen; a permanently stale one would
 * not be, which is why nothing here raises `staleTime`.
 */
export const PERSIST_STALE_TIME_NOTE =
  "restored entries keep dataUpdatedAt, so staleTime — not the snapshot's age — bounds freshness";
