/**
 * B4 — the offline SESSION: the one place the device's downloads, the bridge and the progress spool
 * are wired together.
 *
 * Three things live here and nowhere else:
 *
 * 1. **The rows.** Native is the truth about what is on the phone, so the page never invents or
 *    remembers a row — it asks (`list`) and it listens (events). A screen that cached its own copy
 *    would disagree with the phone after a delete made from the HUD.
 * 2. **The spool's lifetime**, which is bound to WHO IS WATCHING. The queue is on disk, so it
 *    outlives a sign-out: this module stamps every write with the profile and the server origin, and
 *    refuses to read anything stamped with someone else's (ADR-0010; `spool.ts` holds the rule, this
 *    file holds the wiring).
 * 3. **The one function the player calls** to report a position (`reportProgressFromPlayer`), so the
 *    decision "direct or spooled" is made HERE, once, instead of inside an 1,800-line component.
 *
 * ⚠ The session is idempotent and keyed by owner: mounting it twice (a re-render, a route change)
 * must not produce a second subscription or a second flush loop — two loops replaying one queue is
 * how a position gets posted twice, and a queue drained by a loop that then reports "0 flushed"
 * while another loop still holds the old entries is a bug with no symptom until it matters.
 */

import { create } from "zustand";

import { api, type ProgressPayload } from "../../lib/api/client";
import {
  bridgeAvailable,
  requestCancel,
  requestDelete,
  requestDownload,
  requestPlay,
  subscribeOfflineEvents,
  listDownloads,
} from "./bridge";
import {
  applyEvent,
  percentOf,
  rowFor,
  sumBytes,
  type OfflineEvent,
  type OfflineItem,
  type OfflinePlayTarget,
  type OfflineReply,
} from "./lib";
import {
  confirmSpoolPosted,
  dropSpool,
  dropSpoolEntry,
  dueSpool,
  emptySpool,
  readSpool,
  replayFailureNotice,
  recordSpool,
  resumeSecondsFrom,
  spoolSize,
  writeSpool,
  type SpoolEntry,
  type SpoolState,
  type SpoolStorage,
} from "./spool";

export interface OfflineNotice {
  kind: "ok" | "err";
  text: string;
  /** ⚠ WHICH title the refusal was about, when it was about one. A screen with ten rows must not
   *  print one row's failure under all of them, and the detail page must not show a refusal that
   *  belongs to whatever else the person pressed a moment ago. `null` = about the device, not a
   *  title (a `list` that could not be read). */
  itemId: string | null;
}

interface OfflineStoreState {
  /** ⚠ The flag every offline affordance is gated on: no bridge = no button, anywhere (§4.5). */
  available: boolean;
  /** Native has answered `list` at least once this page — so an empty list means "nothing
   *  downloaded" rather than "we have not asked yet". */
  loaded: boolean;
  items: OfflineItem[];
  /** The last refusal, in words a person can act on. Cleared by the next successful command. */
  notice: OfflineNotice | null;
  /** Titles with a command in flight, so a button cannot be double-pressed. */
  pending: Record<string, true>;
  /** Positions still waiting for a server (the Downloads screen says how many). */
  queuedReports: number;
  /**
   * ⚠ WHY the last replay did not land, when it did not. The count alone is not enough: "3 waiting"
   * reads the same whether the server is refusing them, the network is down, or the session expired —
   * and the first real round of this feature proved a silent queue costs a Mac round to diagnose.
   */
  queueNotice: string | null;
}

export const useOffline = create<OfflineStoreState>(() => ({
  available: false,
  loaded: false,
  items: [],
  notice: null,
  pending: {},
  queuedReports: 0,
  queueNotice: null,
}));

/** The store's own accessors for non-React callers (the player, the flush loop). */
export const offlineRows = (): OfflineItem[] => useOffline.getState().items;
export const offlineAvailable = (): boolean => useOffline.getState().available;
export const offlineRow = (itemId: string): OfflineItem | null => rowFor(offlineRows(), itemId);
export const offlinePercent = (itemId: string): number | null => {
  const row = offlineRow(itemId);
  return row ? percentOf(row.bytes, row.totalBytes) : null;
};
export const offlineIsReady = (itemId: string): boolean => offlineRow(itemId)?.state === "ready";

// ------------------------------------------------------------------ storage + identity

function defaultStorage(): SpoolStorage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    // Private mode throws on ACCESS, not on write.
    return null;
  }
}

function serverOrigin(): string {
  try {
    return globalThis.location?.origin ?? "";
  } catch {
    return "";
  }
}

interface Session {
  owner: string;
  server: string;
  unsubscribe: () => void;
  onOnline: () => void;
  onVisible: () => void;
  timer: ReturnType<typeof setInterval> | null;
}

let session: Session | null = null;
let spool: SpoolState = emptySpool();
let flushing = false;
let flushSoon: ReturnType<typeof setTimeout> | null = null;

// ------------------------------------------------------------------ lifecycle

/**
 * Attach the session to the profile now watching. Idempotent per owner.
 *
 * ⚠ Called from ONE component (`OfflineWiring`, mounted by the shell) rather than from each offline
 * surface, because the flush loop must be running when the player is NOT on screen: he watches a film
 * offline, closes the app, opens it in the lounge with Wi-Fi — and the position has to find its way
 * to Continue Watching without anyone opening a downloaded title first.
 */
export function startOfflineSession(owner: string): void {
  if (session && session.owner === owner) return;
  if (session) stopOfflineSession();

  const server = serverOrigin();
  const available = bridgeAvailable();
  useOffline.setState({ available, items: [], loaded: false, notice: null, pending: {}, queueNotice: null });

  // ⚠ `readSpool` DELETES a foreign or unreadable envelope on the way out, so a queue left by
  // another profile (or another server, whose item ids name different films) is gone rather than
  // replayed under this session.
  spool = owner ? readSpool(defaultStorage(), { owner, server, now: Date.now() }) ?? emptySpool() : emptySpool();
  useOffline.setState({ queuedReports: spoolSize(spool) });

  const onOnline = () => {
    // The browser's own idea of "we have a network again", which is the cheapest trigger we have.
    void flushSpool();
    void refreshOffline();
  };
  const onVisible = () => {
    if (globalThis.document?.visibilityState === "visible") void flushSpool();
  };

  session = {
    owner,
    server,
    unsubscribe: available
      ? subscribeOfflineEvents((event) => {
          receiveEvent(event);
        })
      : () => {},
    onOnline,
    onVisible,
    timer: null,
  };

  try {
    globalThis.addEventListener?.("online", onOnline);
    globalThis.document?.addEventListener("visibilitychange", onVisible);
  } catch {
    /* an environment without these is a test, not a shell */
  }

  // ⚠ A periodic retry as well as the `online` event: the event fires on the NETWORK coming back,
  // which is not the same moment the SERVER came back (a Tailscale reconnect, a container restart,
  // a session that has just been signed in again). It no-ops when the queue is empty.
  session.timer = setInterval(() => {
    if (spoolSize(spool) > 0) void flushSpool();
  }, 60_000);

  void refreshOffline();
}

export function stopOfflineSession(): void {
  if (!session) return;
  session.unsubscribe();
  try {
    globalThis.removeEventListener?.("online", session.onOnline);
    globalThis.document?.removeEventListener("visibilitychange", session.onVisible);
  } catch {
    /* see start */
  }
  if (session.timer) clearInterval(session.timer);
  if (flushSoon) {
    clearTimeout(flushSoon);
    flushSoon = null;
  }
  // ⚠ A last best-effort replay of whatever is still queued. It may well 401 (a sign-out is one of
  // the ways this runs), and that is fine: the entries stay on disk, stamped with their owner, and
  // are either replayed the next time that person is watching or dropped as foreign by the next one.
  void flushSpool();
  session = null;
}

function persistSpool(next: SpoolState): void {
  spool = next;
  useOffline.setState({ queuedReports: spoolSize(next) });
  if (!session) return;
  writeSpool(defaultStorage(), next, {
    owner: session.owner,
    server: session.server,
    now: Date.now(),
  });
}

// ------------------------------------------------------------------ reading the device

/** Ask native what it holds. The ONE source of the rows. */
export async function refreshOffline(): Promise<void> {
  const state = useOffline.getState();
  if (!state.available) {
    // ⚠ Still mark it loaded: "this browser cannot hold downloads" is an ANSWER, and a screen that
    // showed a spinner forever would be reporting a bridge that will never answer.
    useOffline.setState({ loaded: true, items: [] });
    return;
  }
  const reply = await listDownloads();
  applyReply(reply, () => {
    useOffline.setState({ loaded: true });
  });
  // ⚠ Reaching native is evidence the PAGE works, not that the SERVER does — but it is also the
  // moment a download that just finished becomes playable, and a queued position is cheap to retry.
  void flushSpool();
}

function applyReply(reply: OfflineReply, onOk: (items: OfflineItem[]) => void): void {
  if (reply.ok && reply.kind === "list") {
    useOffline.setState({ items: reply.items, notice: null });
    onOk(reply.items);
    return;
  }
  if (!reply.ok) {
    useOffline.setState({ notice: { kind: "err", text: reply.error.message, itemId: null } });
    onOk(useOffline.getState().items);
  }
}

/** One native event → the rows. */
function receiveEvent(event: OfflineEvent): void {
  if (event.e === "probe") return; // the DEBUG probe's channel, not the page's
  const next = applyEvent(useOffline.getState().items, event);
  useOffline.setState({ items: next, loaded: true });
}

// ------------------------------------------------------------------ commands

async function command(
  itemId: string,
  run: () => Promise<OfflineReply>,
): Promise<OfflineReply> {
  useOffline.setState((state) => ({ pending: { ...state.pending, [itemId]: true } }));
  let reply: OfflineReply;
  try {
    reply = await run();
  } catch {
    reply = {
      ok: false,
      unreadable: true,
      error: { code: "bridgeThrew", message: "The app did not answer that offline command." },
    };
  }
  const pending = { ...useOffline.getState().pending };
  delete pending[itemId];
  useOffline.setState({
    pending,
    notice: reply.ok ? null : { kind: "err", text: reply.error.message, itemId },
  });
  return reply;
}

/**
 * Start (or resume) a download.
 *
 * ⚠ `download` is the ONLY "go" the contract has: there is no `resume`, and a Resume is this same
 * call. The app decides whether that means "start", "carry on from the byte it stopped at" or
 * "the file is already whole" — which is right, because it is the side that can see the filesystem.
 */
export async function downloadTitle(itemId: string, title: string, mode = "auto"): Promise<boolean> {
  const reply = await command(itemId, () => requestDownload(itemId, title, mode));
  if (reply.ok) await refreshOffline();
  return reply.ok;
}

/** ⚠ Cancel is the only stop the contract has; the `.part` survives it, so the row becomes
 *  `paused` and Resume re-sends `download`. */
export async function cancelTitle(itemId: string): Promise<boolean> {
  const reply = await command(itemId, () => requestCancel(itemId));
  if (reply.ok) await refreshOffline();
  return reply.ok;
}

export async function deleteTitle(itemId: string): Promise<boolean> {
  const reply = await command(itemId, () => requestDelete(itemId));
  if (reply.ok) {
    // ⚠ The rows are re-read rather than edited: the app is the authority, and a local removal that
    // the app disagreed with would leave the file on the phone with no row to delete it from.
    await refreshOffline();
  }
  return reply.ok;
}

/**
 * Ask the app for a URL that plays THIS title from THIS device.
 *
 * ⚠ This is what the player calls before it asks the server anything. It also starts the loopback
 * server if it is not up, and the URL it returns is a capability for this process only — never
 * stored, never logged, never reused after a relaunch.
 */
export async function playLocal(itemId: string): Promise<OfflinePlayTarget | null> {
  if (!offlineAvailable()) return null;
  const row = offlineRow(itemId);
  // ⚠ A row that is not `ready` is not asked about: the app would refuse it, and the refusal would
  // be shown as an error for a film the person has not downloaded. Absent is not an error.
  if (!row || row.state !== "ready") return null;
  const reply = await command(itemId, () => requestPlay(itemId));
  if (reply.ok && reply.kind === "play") return reply.play;
  if (!reply.ok) useOffline.setState({ notice: { kind: "err", text: reply.error.message, itemId } });
  return null;
}

// ------------------------------------------------------------------ the progress spool

/**
 * The player's ONLY reporting call.
 *
 * ⚠ `offline` is a fact the player knows and this module cannot see: it is true when the media
 * element is playing a loopback URL, i.e. when the server is not assumed to be reachable at all.
 * Recording instead of attempting is not an optimisation — offline, the fetch would hang for its
 * twenty-second timeout on every report, on a film that is playing perfectly well.
 *
 * ⚠ And when the direct post SUCCEEDS, whatever the spool held for that title at or below the
 * reported position is now superseded. That is the monotonic rule, and it is applied here because
 * this is the moment the evidence arrives.
 */
export function reportProgressFromPlayer(payload: ProgressPayload, offline: boolean): void {
  const entry: SpoolEntry = {
    itemId: payload.item_id,
    position_ticks: payload.position_ticks,
    runtime_ticks: payload.runtime_ticks ?? 0,
    play_method: payload.play_method ?? "",
    event: payload.event,
    recorded_at: Date.now(),
  };

  if (offline) {
    queue(entry);
    return;
  }

  void api
    .reportProgress(payload)
    .then(() => {
      persistSpool(confirmSpoolPosted(spool, payload.item_id, payload.position_ticks));
    })
    .catch(() => {
      // ⚠ A failed report is not an error to show: it is exactly the case the spool exists for.
      queue(entry);
    });
}

function queue(entry: SpoolEntry): void {
  persistSpool(recordSpool(spool, entry));
  scheduleFlush();
}

function scheduleFlush(): void {
  if (flushSoon) return;
  flushSoon = setTimeout(() => {
    flushSoon = null;
    void flushSpool();
  }, 2_000);
}

/**
 * Replay queued positions, oldest first. Returns how many landed.
 *
 * ⚠ **Stops at the first failure rather than skipping it**, and keeps the rest: the queue is a
 * timeline, and a report that cannot reach the server means the next one cannot either. Skipping
 * past a failure would also reorder the history it is trying to repair.
 *
 * ⚠ The replay uses `reportProgressQueued` — a report that is NOT allowed to bounce the page to the
 * sign-in screen. A background flush is not a person doing something, and a 401 here means the
 * session expired while the queue waited; the entries stay on disk for when that person signs back
 * in, which is the honest answer and not a logout nobody asked for.
 */
export async function flushSpool(): Promise<number> {
  if (flushing || !session) return 0;
  const due = dueSpool(spool);
  if (due.length === 0) return 0;

  flushing = true;
  let sent = 0;
  try {
    for (const entry of due) {
      try {
        await api.reportProgressQueued({
          item_id: entry.itemId,
          position_ticks: entry.position_ticks,
          is_paused: false,
          event: entry.event,
          play_method: entry.play_method || undefined,
          runtime_ticks: entry.runtime_ticks || undefined,
        });
      } catch (error) {
        // ⚠ SAY WHY. The status is what tells the three cases apart — and only one of them is "try
        // later": a 401 waits for a sign-in, a 5xx or a dropped connection waits for the server, and a
        // refusal waits for nothing (but the entry is KEPT, because a position is worth more than the
        // tidiness of dropping it).
        const status = typeof (error as { status?: unknown } | null)?.status === "number"
          ? ((error as { status: number }).status)
          : null;
        useOffline.setState({ queueNotice: replayFailureNotice(status) });
        break; // the rest waits, in order
      }
      // ⚠ Dropped by `recorded_at`: a newer position for the same title may have been recorded
      // while this request was in flight, and it must survive the flush.
      persistSpool(dropSpoolEntry(spool, entry.itemId, entry.recorded_at));
      useOffline.setState({ queueNotice: null });
      sent += 1;
    }
  } finally {
    flushing = false;
  }
  return sent;
}

/** Where an offline play should start: the server's answer, or this device's own furthest-watched
 *  position, whichever is further along (`spool.ts::resumeSecondsFrom`). */
export function spooledResumeSeconds(itemId: string, serverResume: number, runtime: number): number {
  return resumeSecondsFrom(spool, itemId, serverResume, runtime);
}

export function queuedReportCount(): number {
  return spoolSize(spool);
}

// ------------------------------------------------------------------ test seams

/** ⚠ TEST-ONLY. Replaces the queue in memory (the browser harness drives the real page against a
 *  fake bridge and needs a known starting state). Never called by app code. */
export function __setSpoolForTests(state: SpoolState): void {
  persistSpool(state);
}

export function __readSpoolForTests(): SpoolState {
  return spool;
}

export function __clearSpoolForTests(): void {
  spool = emptySpool();
  dropSpool(defaultStorage());
  useOffline.setState({ queuedReports: 0 });
}

export { sumBytes };
