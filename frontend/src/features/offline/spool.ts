/**
 * B4 — the PROGRESS SPOOL: positions recorded with no server, replayed when one is back.
 *
 * §4.6: *"Without this, a film watched on a plane never appears in Continue Watching."* This is the
 * part of the phase that makes the feature feel finished rather than merely working, and it is also
 * the part that can silently CORRUPT a viewer's history — so every rule lives here, as pure
 * functions over plain data, where it can be executed and falsified on Linux (`spool.test.ts`).
 *
 * ⚠ The failure this file exists to prevent, stated once: **a replay that REWINDS someone.**
 * Offline on a plane he watches to 1:04:00. The queue holds that. He lands, the Wi-Fi comes back,
 * the queue is flushed — fine. But suppose instead he reconnects and keeps watching ONLINE first;
 * the server hears 1:20:00 from the live player, and THEN the stale 1:04:00 arrives from the spool.
 * Every other rule in this phase recovers from a mistake; this one just loses the last twenty
 * minutes of his evening. Hence `SPOOL_WATERMARK` below.
 *
 * ⚠ And the second one, which is a privacy bug rather than a correctness bug: this queue outlives
 * the page, so it outlives a SIGN-OUT and a PROFILE SWITCH. A spool written by one member and
 * replayed under another's session would put a stranger's viewing position into their Continue
 * Watching. The envelope is stamped with the owner and the server origin, and an envelope that does
 * not match the person now watching is DROPPED, not replayed (`parseSpoolEnvelope`) — the same rule,
 * for the same reason, as `lib/query/persist.ts`.
 */

/** Jellyfin's tick: 10,000,000 per second. The api stores positions in ticks (`ProgressPayload`). */
export const TICKS_PER_SECOND = 10_000_000;

/** Storage key. A separate key from the query cache: different lifetime, different purge, and one
 *  key that holds two unrelated things is a key whose purge rules fight each other. */
export const SPOOL_STORAGE_KEY = "rkm.offline-spool.v1";

/** Bump when the entry shape changes; an envelope from another shape is dropped, never migrated. */
export const SPOOL_SCHEMA_VERSION = 1;

/** A queued position older than this is dropped on read: a weeks-old position replayed into
 *  Continue Watching would move a genuine resume point of today's. (The query cache uses the same
 *  bounded-age idea.) */
export const SPOOL_MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000;

/** ⚠ Near the end of a film, a position stops meaning "resume here" and starts meaning "watched".
 *  Kept identical to the api's own rule and to the player's (`reportProgress`'s `runtime_ticks`). */
export const FINISHED_FRACTION = 0.95;

export type ProgressEvent = "start" | "timeupdate" | "stopped";

export interface SpoolEntry {
  itemId: string;
  /** Position on the ITEM timeline, in ticks — the same unit and the same meaning the api stores. */
  position_ticks: number;
  /** Total runtime in ticks when the player knew it, so a replay near the end marks it watched. */
  runtime_ticks: number;
  play_method: string;
  event: ProgressEvent;
  /** When the DEVICE saw this position, in ms. The ordering key for "newest wins". */
  recorded_at: number;
}

export interface SpoolState {
  entries: Record<string, SpoolEntry>;
}

export interface SpoolEnvelope {
  schemaVersion: number;
  server: string;
  owner: string;
  savedAt: number;
  entries: Record<string, SpoolEntry>;
}

export function emptySpool(): SpoolState {
  return { entries: {} };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function asFinite(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function isProgressEvent(value: unknown): value is ProgressEvent {
  return value === "start" || value === "timeupdate" || value === "stopped";
}

/**
 * ⚠ **THE WATERMARK RULE: within one title the spool keeps the FURTHEST position, never the
 * latest one.**
 *
 * The intuition ("last write wins") is wrong here, and the way it is wrong is invisible in testing:
 * every time a film is REOPENED the player reports `start` at the resume point — or at 0 after a
 * deliberate restart — and with last-write-wins that report would overwrite a 1:04:00 watermark
 * with 0:00:00. The replay would then be a rewind, which is the exact failure this file exists to
 * prevent.
 *
 * The price, stated plainly: a deliberate rewind while offline is not replayed. The film resumes
 * where it was furthest watched, and the live (online) path is untouched — online writes go to the
 * server directly and this spool only ever holds what could NOT be written.
 */
export function recordSpool(state: SpoolState, entry: SpoolEntry): SpoolState {
  if (!entry.itemId) return state;
  if (!Number.isFinite(entry.position_ticks) || entry.position_ticks < 0) return state;
  if (!Number.isFinite(entry.recorded_at)) return state;

  const current = state.entries[entry.itemId];
  if (current && current.position_ticks > entry.position_ticks) {
    // The watermark stands. ⚠ The runtime is still absorbed: a later report may be the first one
    // that knew the real duration, and the replay needs it to be read as "finished".
    if (entry.runtime_ticks <= current.runtime_ticks) return state;
    return {
      entries: { ...state.entries, [entry.itemId]: { ...current, runtime_ticks: entry.runtime_ticks } },
    };
  }
  if (current && current.position_ticks === entry.position_ticks && current.recorded_at >= entry.recorded_at) {
    return state; // nothing moved — do not rewrite storage for an identical tick
  }
  return { entries: { ...state.entries, [entry.itemId]: entry } };
}

/**
 * ⚠ **A LIVE POST IS EVIDENCE.** When a report reaches the server directly, everything the spool
 * holds for that title at or below that position is now redundant — and if it were replayed it
 * would pull the viewer BACK. Called on every successful direct post, this is what makes the
 * "newest wins" guarantee hold across the two paths rather than only inside one of them.
 */
export function confirmSpoolPosted(state: SpoolState, itemId: string, positionTicks: number): SpoolState {
  const current = state.entries[itemId];
  if (!current) return state;
  if (current.position_ticks > positionTicks) return state;
  const entries = { ...state.entries };
  delete entries[itemId];
  return { entries };
}

/**
 * Remove exactly the entry that was just replayed.
 *
 * ⚠ By `recorded_at`, not by item: a newer position for the same title may have been recorded while
 * the request was in flight (the player keeps ticking), and a delete-by-item would silently throw
 * that away — losing the last minutes of a viewer's session to a race.
 */
export function dropSpoolEntry(state: SpoolState, itemId: string, recordedAt: number): SpoolState {
  const current = state.entries[itemId];
  if (!current || current.recorded_at !== recordedAt) return state;
  const entries = { ...state.entries };
  delete entries[itemId];
  return { entries };
}

/** The entries to replay, OLDEST FIRST — deterministic order, and the order a timeline deserves. */
export function dueSpool(state: SpoolState): SpoolEntry[] {
  return Object.values(state.entries).sort((a, b) =>
    a.recorded_at - b.recorded_at || a.itemId.localeCompare(b.itemId),
  );
}

export function spoolSize(state: SpoolState): number {
  return Object.keys(state.entries).length;
}

export function spoolEntry(state: SpoolState, itemId: string): SpoolEntry | null {
  return state.entries[itemId] ?? null;
}

/** Has this position reached the point where the api reads it as "watched"? */
export function isFinished(positionTicks: number, runtimeTicks: number): boolean {
  if (!Number.isFinite(runtimeTicks) || runtimeTicks <= 0) return false;
  return positionTicks >= runtimeTicks * FINISHED_FRACTION;
}

/**
 /**
  * What to tell the person when a replay did not land (`session.ts::flushSpool`).
  *
  * ⚠ This exists because the queue was SILENT: three positions sat on his phone with nothing on screen
  * to say whether they were waiting, failing, or being refused — and the answer turned out to be the
  * worst of the three (accepted reports read as failures, `client.ts::request`'s 204 bug). A count plus
  * a reason is the difference between a feature that is waiting and a feature that is broken.
  */
 export function replayFailureNotice(status: number | null): string {
   if (status === 401 || status === 403) {
     return "Sign in again and they will be sent.";
   }
   if (status === null) {
     return "The server could not be reached — they are kept and tried again.";
   }
   if (status >= 500) {
     return "The server could not record them just now — they are kept and tried again.";
   }
   return "The server refused them — they are kept, and will be tried again.";
 }

 /**
 * Where an OFFLINE play should start.
 *
 * ⚠ `max`, and the reason is asymmetry: a resume point that is too far forward skips a scene, one
 * that is too far back repeats one. The server's answer can only be as new as the last time this
 * device was online, and the spool is by definition newer — but a spool entry can ALSO be stale
 * (the position was reached on another device since). Taking the larger value means a replayed
 * position can never cost him a scene he has already watched twice.
 *
 * ⚠ And a position near the end is not a resume point at all: it means the film is done, and
 * `isFinished` sends it back to the start rather than dropping him into the credits.
 */
export function resumeSecondsFrom(
  state: SpoolState,
  itemId: string,
  serverResumeSeconds: number,
  runtimeSeconds: number,
): number {
  const entry = state.entries[itemId];
  const server = Number.isFinite(serverResumeSeconds) && serverResumeSeconds > 0 ? serverResumeSeconds : 0;
  const spooled = entry ? entry.position_ticks / TICKS_PER_SECOND : 0;
  const best = Math.max(server, spooled);
  if (isFinished(best * TICKS_PER_SECOND, runtimeSeconds * TICKS_PER_SECOND)) return 0;
  return best;
}

// ------------------------------------------------------------------ the envelope (storage)

function parseEntry(raw: unknown): SpoolEntry | null {
  const record = asRecord(raw);
  if (!record) return null;
  const itemId = asString(record.itemId);
  const position = asFinite(record.position_ticks);
  const runtime = asFinite(record.runtime_ticks);
  const recordedAt = asFinite(record.recorded_at);
  if (!itemId || position === null || recordedAt === null) return null;
  return {
    itemId,
    position_ticks: position,
    runtime_ticks: runtime ?? 0,
    play_method: asString(record.play_method) ?? "",
    event: isProgressEvent(record.event) ? record.event : "timeupdate",
    recorded_at: recordedAt,
  };
}

export function spoolEnvelope(state: SpoolState, owner: string, server: string, now: number): SpoolEnvelope {
  return { schemaVersion: SPOOL_SCHEMA_VERSION, server, owner, savedAt: now, entries: state.entries };
}

/**
 * Read + validate an envelope. **Every rejection path returns null, and the caller DELETES**, so an
 * unreadable or foreign envelope cannot cost the same parse on the next launch — the rule
 * `persist.ts::readEnvelope` already established.
 *
 * ⚠ `owner` and `server` are compared, not merely recorded: somebody else's queue, or a queue for a
 * different server (whose item ids name different films), must never be replayed by this page.
 */
export function parseSpoolEnvelope(
  raw: unknown,
  context: { owner: string; server: string; now: number; maxAgeMs?: number },
): SpoolState | null {
  const record = asRecord(raw);
  if (!record) return null;
  if (record.schemaVersion !== SPOOL_SCHEMA_VERSION) return null;
  if (asString(record.owner) !== context.owner) return null;
  if (asString(record.server) !== context.server) return null;
  const savedAt = asFinite(record.savedAt);
  if (savedAt === null) return null;
  const maxAge = context.maxAgeMs ?? SPOOL_MAX_AGE_MS;
  if (context.now - savedAt > maxAge) return null;

  const rawEntries = asRecord(record.entries);
  if (!rawEntries) return null;
  const entries: Record<string, SpoolEntry> = {};
  for (const value of Object.values(rawEntries)) {
    const entry = parseEntry(value);
    // ⚠ Re-keyed by the entry's OWN itemId, never by the dictionary key: a mismatch between the two
    // is exactly how a queue written by hand (or by an older shape) replays one title's position
    // under another title's id.
    if (entry) entries[entry.itemId] = entry;
  }
  return { entries };
}

/** Read the stored JSON, or null. ⚠ Never throws: private mode, a quota refusal and a hand-edited
 *  value are all ordinary states for a browser store. */
export function readSpool(
  storage: SpoolStorage | null,
  context: { owner: string; server: string; now: number },
): SpoolState | null {
  if (!storage) return null;
  // ⚠⚠ **AN UNKNOWN OWNER MUST NOT DESTROY THE QUEUE.** A page that loads with no network cannot ask
  // `/api/auth/me`, so it cannot say who is watching — and that is exactly the launch where the
  // positions on disk matter most. Nothing is READ (they may be somebody else's) and nothing is
  // deleted: the envelope stays where it is, for the next load that CAN identify the viewer. An
  // identity purge belongs to "we know this is a different person", never to "we cannot tell".
  if (!context.owner) return null;
  let raw: string | null = null;
  try {
    raw = storage.getItem(SPOOL_STORAGE_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    dropSpool(storage);
    return null;
  }
  const state = parseSpoolEnvelope(parsed, context);
  if (!state) {
    // A foreign or unreadable envelope is DELETED, not left to be re-parsed: leaving it also leaves
    // the previous person's positions on a shared iPad.
    dropSpool(storage);
    return null;
  }
  return state;
}

/** Write the queue out. Returns the serialised length, or null when nothing was written. */
export function writeSpool(
  storage: SpoolStorage | null,
  state: SpoolState,
  context: { owner: string; server: string; now: number },
): number | null {
  if (!storage) return null;
  if (!context.owner) return null; // ⚠ no owner = nobody signed in = nothing is written
  if (spoolSize(state) === 0) {
    // ⚠ Nothing to store = no write at all, rather than an empty envelope that would then need its
    // own "is it empty or is it broken?" handling on the way back in.
    dropSpool(storage);
    return null;
  }
  const serialised = JSON.stringify(spoolEnvelope(state, context.owner, context.server, context.now));
  try {
    storage.setItem(SPOOL_STORAGE_KEY, serialised);
  } catch {
    return null; // quota, private mode — the position is lost, the app is not
  }
  return serialised.length;
}

export function dropSpool(storage: SpoolStorage | null): void {
  if (!storage) return;
  try {
    storage.removeItem(SPOOL_STORAGE_KEY);
  } catch {
    /* nothing useful to do */
  }
}

/** The slice of `Storage` this needs — so the tests can run without a browser. */
export interface SpoolStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}
