/**
 * B4 — the page half of offline downloads: **the rules, as pure functions**.
 *
 * `docs/NATIVE_FEEL_AND_OFFLINE_PLAN.md` §4.6 is the spec; `docs/adr/ADR-0010-offline-page.md` is
 * where each decision here is argued, including the ones this file deliberately does NOT decide.
 *
 * Three rules shape everything below, and all three are consequences of living in a BROWSER that is
 * only sometimes inside the iOS shell:
 *
 * 1. ⚠ **The bridge is a BOUNDARY, not a function call.** `window.__rkmOffline` is injected by a
 *    Swift file we cannot test from here, its payloads arrive as untyped `any` from
 *    `postMessage`, and a half-read payload is worse than a missing one: `bytes: NaN` renders
 *    "NaN GB", and an empty `state` string renders a row with no controls. So every payload is
 *    PARSED here, and anything that does not parse is DROPPED — the same discipline the backend
 *    applies to a request body.
 * 2. ⚠ **Absent is a state, and it is the common one.** `window.__rkmOffline` does not exist in a
 *    desktop browser, which is exactly how the page decides to draw no offline affordance at all
 *    (§4.5: never render a control that cannot work). Nothing here assumes a bridge, and nothing
 *    here renders a control for one that is not there.
 * 3. ⚠ **Native is the truth about the DEVICE; the API is the truth about the SERVER.** A row's
 *    state/size comes from `list`, never from the server's staging record — they are two different
 *    facts about two different machines, and conflating them is how a screen offers to play a film
 *    that is not on the phone (see `NO_SERVER`).
 */

/** ⚠ The contract version this page speaks. A reply carrying another one is refused, not guessed at
 *  (ADR-0009 D6). Bumping it is a deliberate act with a page+app pair behind it. */
export const OFFLINE_BRIDGE_VERSION = 1;

/** The states the app's own `OfflineState` enum can report (ADR-0008). ⚠ Exactly one is playable. */
export const OFFLINE_STATES = ["downloading", "paused", "ready", "failed"] as const;
export type OfflineState = (typeof OFFLINE_STATES)[number];

/** One title as the DEVICE reports it (`{v:1,c:"list"}` → `result.items[]`). */
export interface OfflineItem {
  itemId: string;
  title: string;
  state: OfflineState;
  /** Bytes on THIS device right now: the `.part` size while incomplete, the file size when ready. */
  bytes: number;
  /** The server's `Content-Length` for this rendition. 0 = not known yet. */
  totalBytes: number;
  /** The rendition: `direct` · `remux` · `transcode_audio` · `transcode` (the downloader records it). */
  mode: string;
  error: string | null;
  /** ⚠ Present only from a live process, and only while the loopback server is listening. Never
   *  cached, never constructed by the page (the port changes every launch). */
  url: string | null;
  contentType: string | null;
}

/** A native → page event: `window.__rkmOffline.on(listener)`. */
export type OfflineEvent =
  | { e: "state"; itemId: string; item: OfflineItem }
  | { e: "progress"; itemId: string; bytes: number; totalBytes: number; percent: number }
  | { e: "ready"; itemId: string; url: string; contentType: string | null; bytes: number }
  | { e: "removed"; itemId: string }
  /** ⚠ DEBUG-only, from the B3 probe: it asks the page to ask its own questions. Ignored here — it
   *  is the probe's channel, and the probe is not the page. */
  | { e: "probe" };

/** A refusal, or a successful reply, from `postMessage` (ADR-0009 D6). */
export interface OfflineError {
  code: string;
  message: string;
}

export interface OfflineListResult {
  items: OfflineItem[];
  bytes: number;
}

export interface OfflinePlayTarget {
  itemId: string;
  url: string;
  contentType: string;
  size: number;
}

/** The parsed answer to one command. ⚠ A reply that could not be read at all is NOT `ok:false` —
 *  it is `unreadable`, because "the app refused" and "we cannot tell what the app said" are
 *  different facts and the UI says a different sentence for each. */
export type OfflineReply =
  | { ok: true; kind: "list"; items: OfflineItem[]; bytes: number }
  | { ok: true; kind: "play"; play: OfflinePlayTarget }
  | { ok: true; kind: "accepted"; command: string }
  | { ok: true; kind: "ping" }
  | { ok: false; error: OfflineError }
  | { ok: false; unreadable: true; error: OfflineError };

// ------------------------------------------------------------------ the boundary

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** ⚠ NOT `Number(value)`: `Number(null)` is 0 and `Number("")` is 0, so a missing byte count would
 *  render as a confident "0 B" — and 0 B is a meaningful answer to us (an empty file), so the two
 *  must not be able to arrive the same way. Only real finite numbers pass. */
function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

export function isOfflineState(value: unknown): value is OfflineState {
  return typeof value === "string" && (OFFLINE_STATES as readonly string[]).includes(value);
}

/**
 * Parse one device row. Returns null for anything unreadable — including a row whose `itemId` is
 * missing, because a row the page cannot address cannot be cancelled, deleted or played, so
 * keeping it would only produce a dead control.
 *
 * ⚠ Missing NUMBERS are not a reason to drop a row (`bytes` is genuinely unknown before the first
 * byte): they become 0, and `percentOf` treats a 0 total as "unknown" rather than "0%".
 */
export function parseItem(raw: unknown): OfflineItem | null {
  const record = asRecord(raw);
  if (!record) return null;
  const itemId = asString(record.itemId);
  if (!itemId) return null;
  if (!isOfflineState(record.state)) return null;
  const title = asString(record.title) ?? itemId;
  return {
    itemId,
    title,
    state: record.state,
    bytes: asNumber(record.bytes) ?? 0,
    totalBytes: asNumber(record.totalBytes) ?? 0,
    mode: asString(record.mode) ?? "",
    error: asString(record.error),
    url: asString(record.url),
    contentType: asString(record.contentType),
  };
}

function parseItems(raw: unknown): OfflineItem[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(parseItem).filter((row): row is OfflineItem => row !== null);
}

/** Parse a `postMessage` answer. ⚠ The version is checked, not assumed: a reply from a build that
 *  speaks another contract may mean anything, and guessing at its shape is the bug the version
 *  field exists to prevent. */
export function parseReply(raw: unknown): OfflineReply {
  const record = asRecord(raw);
  if (!record) return { ok: false, unreadable: true, error: unreadableError("the reply was not an object") };
  if (record.v !== OFFLINE_BRIDGE_VERSION) {
    return {
      ok: false,
      unreadable: true,
      error: {
        code: "unsupportedVersion",
        message: `The app answers offline bridge v${String(record.v)}; this page speaks v${OFFLINE_BRIDGE_VERSION}.`,
      },
    };
  }
  if (record.ok !== true) {
    const error = asRecord(record.error);
    return {
      ok: false,
      error: {
        code: asString(error?.code) ?? "unknown",
        message: asString(error?.message) ?? "The app refused that offline command.",
      },
    };
  }

  const result = asRecord(record.result) ?? {};
  const play = asRecord(result.play);
  if (play && asString(play.url)) {
    return {
      ok: true,
      kind: "play",
      play: {
        itemId: asString(play.itemId) ?? "",
        url: asString(play.url) as string,
        contentType: asString(play.contentType) ?? "",
        size: asNumber(play.size) ?? 0,
      },
    };
  }
  if (Array.isArray(result.items)) {
    const items = parseItems(result.items);
    return { ok: true, kind: "list", items, bytes: asNumber(result.bytes) ?? sumBytes(items) };
  }
  const accepted = asString(result.accepted);
  if (accepted) {
    return accepted === "ping" ? { ok: true, kind: "ping" } : { ok: true, kind: "accepted", command: accepted };
  }
  return { ok: false, unreadable: true, error: unreadableError("the reply carried neither items nor a target") };
}

function unreadableError(reason: string): OfflineError {
  return { code: "unreadableReply", message: `The app answered something this page cannot read (${reason}).` };
}

/**
 * Parse a native event. ⚠ `state` reuses `parseItem` for the ROW fields, but the event's own
 * `state`/`title` are top-level, so a `state` event whose row is unreadable is dropped whole rather
 * than applied as a half-row: an event that updates some fields and not others is how a UI ends up
 * showing a size from one download and a state from another.
 */
export function parseEvent(raw: unknown): OfflineEvent | null {
  const record = asRecord(raw);
  if (!record) return null;
  if (record.v !== undefined && record.v !== OFFLINE_BRIDGE_VERSION) return null;
  const itemId = asString(record.itemId);
  switch (record.e) {
    case "probe":
      return { e: "probe" };
    case "progress": {
      if (!itemId) return null;
      return {
        e: "progress",
        itemId,
        bytes: asNumber(record.bytes) ?? 0,
        totalBytes: asNumber(record.totalBytes) ?? 0,
        percent: asNumber(record.percent) ?? 0,
      };
    }
    case "ready": {
      const url = asString(record.url);
      if (!itemId || !url) return null;
      return {
        e: "ready",
        itemId,
        url,
        contentType: asString(record.contentType),
        bytes: asNumber(record.bytes) ?? 0,
      };
    }
    case "removed":
      return itemId ? { e: "removed", itemId } : null;
    case "state": {
      if (!itemId) return null;
      return {
        e: "state",
        itemId,
        item: {
          itemId,
          title: asString(record.title) ?? itemId,
          state: isOfflineState(record.state) ? record.state : "paused",
          bytes: asNumber(record.bytes) ?? 0,
          totalBytes: asNumber(record.totalBytes) ?? 0,
          mode: asString(record.mode) ?? "",
          error: asString(record.error),
          url: asString(record.url),
          contentType: null,
        },
      };
    }
    default:
      return null;
  }
}

// ------------------------------------------------------------------ the rows

export function sumBytes(items: OfflineItem[]): number {
  return items.reduce((total, item) => total + (Number.isFinite(item.bytes) ? item.bytes : 0), 0);
}

/** Insert or replace by id, KEEPING the list's order (native's order is stable and meaningful). */
export function upsert(items: OfflineItem[], next: OfflineItem): OfflineItem[] {
  const index = items.findIndex((item) => item.itemId === next.itemId);
  if (index < 0) return [...items, next];
  const copy = items.slice();
  copy[index] = next;
  return copy;
}

/**
 * Apply one event to the rows.
 *
 * ⚠ A `removed` event for a title the page does not have is a no-op, not a reason to re-render: the
 * bridge re-announces on every page load, and a delete races its own `state` event.
 * ⚠ A `state` event REPLACES the row's `url` even when it carries none — "the URL disappeared" is a
 * real state change (ADR-0009 D8), and keeping the stale one would leave a Play button on a file
 * the loopback server can no longer name.
 */
export function applyEvent(items: OfflineItem[], event: OfflineEvent): OfflineItem[] {
  switch (event.e) {
    case "state":
      // The event's row carries no contentType, so the previous one is kept rather than nulled —
      // it describes the FILE, which has not changed.
      return upsert(items, { ...event.item, contentType: contentTypeOf(items, event.itemId) });
    case "ready":
      return upsert(items, {
        ...(items.find((item) => item.itemId === event.itemId) ?? blankItem(event.itemId)),
        state: "ready",
        bytes: event.bytes || bytesOf(items, event.itemId),
        url: event.url,
        contentType: event.contentType ?? contentTypeOf(items, event.itemId),
        error: null,
      });
    case "progress": {
      const current = items.find((item) => item.itemId === event.itemId);
      if (!current) return items; // progress for a title we have no row for — the `state` event owns it
      return upsert(items, {
        ...current,
        bytes: event.bytes,
        totalBytes: event.totalBytes || current.totalBytes,
      });
    }
    case "removed":
      // ⚠ `items` itself when nothing matched — NOT a fresh array. The bridge re-announces every
      // title on every page load and a delete races its own `state` event, so an unmatched removal is
      // the COMMON case, and returning a new array would re-render every row for a no-op.
      return items.some((item) => item.itemId === event.itemId)
        ? items.filter((item) => item.itemId !== event.itemId)
        : items;
    default:
      return items;
  }
}

export function applyEvents(items: OfflineItem[], events: OfflineEvent[]): OfflineItem[] {
  return events.reduce(applyEvent, items);
}

function bytesOf(items: OfflineItem[], itemId: string): number {
  return items.find((item) => item.itemId === itemId)?.bytes ?? 0;
}

function contentTypeOf(items: OfflineItem[], itemId: string): string | null {
  return items.find((item) => item.itemId === itemId)?.contentType ?? null;
}

function blankItem(itemId: string): OfflineItem {
  return {
    itemId, title: itemId, state: "paused", bytes: 0, totalBytes: 0,
    mode: "", error: null, url: null, contentType: null,
  };
}

export function rowFor(items: OfflineItem[], itemId: string): OfflineItem | null {
  return items.find((item) => item.itemId === itemId) ?? null;
}

/**
 * The percentage to draw, or **null when the total is unknown**.
 *
 * ⚠ This is the same rule the native event planner enforces (ADR-0009 D8): an unknown total must
 * never become a number, because a bar at 0% over a file whose size nobody knows is a lie that
 * looks like progress. The page and the app must agree on it or the bar would flicker between a
 * dash and 0% as events arrive.
 */
export function percentOf(bytes: number, totalBytes: number): number | null {
  if (!Number.isFinite(totalBytes) || totalBytes <= 0) return null;
  if (!Number.isFinite(bytes) || bytes <= 0) return 0;
  return Math.max(0, Math.min(100, Math.floor((bytes / totalBytes) * 100)));
}

/** ⚠ DECIMAL units, deliberately: `1543383346` bytes is "1.54 GB" — the same number the app's own
 *  HUD prints (`offline READY · 1.54 GB`), so the page and the log agree about one file. Binary
 *  units here would show 1.44 and read as a bug against every other surface in the house. */
export function fmtBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "kB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  const digits = unit <= 2 ? 0 : 2;
  return `${value.toFixed(digits)} ${units[unit]}`;
}

/** The one-line state text a row shows. ⚠ Every branch is a fact, including the failing one. */
export function rowStatusText(item: OfflineItem): string {
  const percent = percentOf(item.bytes, item.totalBytes);
  switch (item.state) {
    case "downloading":
      // ⚠⚠ **NOTHING HAS ARRIVED YET IS A STATE WORTH NAMING (2026-09-16, from his phone).** Before the
      // first byte lands, `bytes` and `totalBytes` are both 0 — because the SERVER is still PACKAGING the
      // rendition (the app's own log reads `offline packaging · packaging · 1.05 GB after 36s` while the
      // row says nothing is happening). A download that says "0 B downloaded" for a minute reads as a
      // download that is not working, and it is the one thing about this screen the household sees first.
      if (item.bytes <= 0 && item.totalBytes <= 0) return "Preparing on the server…";
      return percent === null
        ? `${fmtBytes(item.bytes)} downloaded`
        : `${fmtBytes(item.bytes)} / ${fmtBytes(item.totalBytes)} · ${percent}%`;
    case "paused":
      return percent === null
        ? `${fmtBytes(item.bytes)} downloaded — resumable`
        : `${fmtBytes(item.bytes)} of ${fmtBytes(item.totalBytes)} — resumable`;
    case "ready":
      return item.bytes > 0 ? `On this device · ${fmtBytes(item.bytes)}` : "On this device";
    case "failed":
      return item.error || "The download failed.";
  }
}

/** The chip beside a row's title: the rendition the DEVICE holds (or is fetching). */
export function modeLabel(mode: string): string {
  switch (mode) {
    case "direct":
      return "Direct";
    case "remux":
      return "Remux";
    case "transcode_audio":
      return "Audio transcode";
    case "transcode":
      return "Transcode";
    case "":
      return "";
    default:
      return mode;
  }
}

/**
 * What the detail page should offer for one title.
 *
 * ⚠ ONE decision, made once: the page renders exactly the control this returns and nothing else, so
 * "the button said Download while the film was already on the phone" is not a state this code can
 * reach. `delete` is offered for every state a row can be in, because a partial download that
 * cannot be thrown away is a phone with less space and no way to get it back.
 */
export type OfflineActionKind = "download" | "cancel" | "resume" | "retry" | "delete" | "play";

export function actionsFor(item: OfflineItem | null): OfflineActionKind[] {
  if (!item) return [];
  switch (item.state) {
    case "downloading":
      return ["cancel", "delete"];
    case "paused":
      return ["resume", "delete"];
    case "failed":
      return ["retry", "delete"];
    case "ready":
      // ⚠ Delete is offered here too — and in the app it is the ONLY way to free the bytes.
      return ["play", "delete"];
  }
}

export const ACTION_LABELS: Record<OfflineActionKind, string> = {
  download: "Download",
  cancel: "Cancel",
  resume: "Resume",
  retry: "Retry",
  delete: "Delete",
  play: "Play offline",
};

// ------------------------------------------------------------------ the server's own answer

/** Re-exported from the api client, where API response shapes live — this module owns the VIEW
 *  model, not the wire format. `lib/api/client.ts::OfflineBundleShape` is the definition. */
export type { OfflineBundleShape } from "../../lib/api/client";
import type { OfflineBundleShape } from "../../lib/api/client";

/**
 * The label under the Download button: **the rendition and the size, before he commits** (§4.6).
 *
 * ⚠ It says "about" when the number is the backend's estimate, because it is one — the real size is
 * only known once `prepare` has finished. A download button that promises 2.1 GB and delivers 3.4
 * teaches him to distrust every number on the screen.
 */
export function downloadSummary(bundle: OfflineBundleShape | null | undefined): string {
  if (!bundle) return "";
  const bits: string[] = [];
  const mode = modeLabel(bundle.mode);
  if (mode) bits.push(mode);
  // ⚠ No resolution is claimed. §4.6's example label reads "1080p · 2.1 GB · remux", but the bundle
  // carries no height (only `container` + codecs) and inventing "1080p" from a byte count is exactly
  // the kind of confident guess this feature cannot afford. The label is what the server really said.
  if (bundle.container) bits.push(bundle.container.toUpperCase());
  if (bundle.video_codec) bits.push(bundle.video_codec.toUpperCase());
  const size = bundle.size > 0 ? fmtBytes(bundle.size) : `about ${fmtBytes(bundle.estimate_bytes)}`;
  if (bundle.estimate_bytes > 0 || bundle.size > 0) bits.push(size);
  return bits.join(" · ");
}

/** The sentence under the button when the download will cost the server real work. */
export function transcodeWarning(bundle: OfflineBundleShape | null | undefined): string {
  if (!bundle || !bundle.needs_transcode) return "";
  return "The server has to re-encode this one — it will take longer than a copy.";
}

/**
 * ⚠ **A tile the device holds is never sourced from the server.** The badge below says so out loud
 * because "no longer in the library" and "the server has dropped the staging file" are the two ways
 * a download outlives its server record — and in both cases the film still plays (§4.7).
 */
export function serverNote(serverKnows: boolean | null, item: OfflineItem): string {
  if (serverKnows !== false) return "";
  return item.state === "ready"
    ? "No longer on the server — this copy still plays."
    : "No longer on the server — this download cannot finish.";
}

/** The header of the Downloads screen: how much of the phone this feature is using. */
export function diskSummary(items: OfflineItem[]): string {
  const ready = items.filter((item) => item.state === "ready");
  const bytes = sumBytes(ready);
  if (items.length === 0) return "Nothing is downloaded yet.";
  const titles = `${ready.length} title${ready.length === 1 ? "" : "s"}`;
  return bytes > 0 ? `${titles} · ${fmtBytes(bytes)} on this device` : `${titles} on this device`;
}
