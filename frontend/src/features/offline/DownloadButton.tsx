import { useCallback } from "react";

import { Icon } from "../../components/ui/Icon";
import { IconAction } from "../../components/ui/IconAction";
import {
  ACTION_LABELS,
  actionsFor,
  downloadSummary,
  fmtBytes,
  modeLabel,
  percentOf,
  rowStatusText,
  serverNote,
  transcodeWarning,
  type OfflineActionKind,
} from "./lib";
import { cancelTitle, deleteTitle, downloadTitle, useOffline } from "./session";
import { useOfflineBundle } from "./api";

/**
 * The Download affordance on the detail page (B4, plan §4.6).
 *
 * ⚠ **It renders NOTHING when this web view has no bridge.** `window.__rkmOffline` exists only inside
 * the iOS shell, so in a desktop browser there is no offline store to put a film in — and a Download
 * button there would be a control that cannot work, which is exactly what §4.5 forbids. The feature is
 * invisible outside the app rather than broken inside it.
 *
 * ⚠ **Which control is shown is decided ONCE, by `actionsFor`** (pure, unit-tested), so this page
 * cannot reach the state where it offers "Download" for a film already on the phone: the row the app
 * reports is the only input to that decision, and the app is the side that can see the filesystem.
 *
 * ⚠ **There is no "Play offline" button here, deliberately.** The page's own Play button already goes
 * through `Player`, which prefers a local file over the server when one exists — so a second play
 * affordance would be a second path to the same film, and the one that forgot to prefer the local
 * copy is the one that would be pressed. The Downloads screen, which has no other way to start a
 * film, is where that action lives.
 */

const BASE =
  "inline-flex h-10 items-center gap-2 rounded-[10px] px-4 text-sm font-bold transition disabled:opacity-60";
const PRIMARY = `${BASE} bg-accent text-black shadow-lg shadow-accent/20 hover:bg-accent-hover`;
const SECONDARY = `${BASE} border border-white/10 bg-white/[.07] text-zinc-100 hover:bg-white/[.12]`;
const GHOST = `${BASE} px-3 text-zinc-400 hover:text-white`;

const ACTION_VARIANT: Record<OfflineActionKind, string> = {
  download: PRIMARY,
  play: PRIMARY,
  cancel: SECONDARY,
  resume: SECONDARY,
  retry: SECONDARY,
  delete: GHOST,
};

const ACTION_ICON: Record<OfflineActionKind, "play" | "download" | "close" | "trash" | "refresh"> = {
  download: "download",
  play: "play",
  cancel: "close",
  resume: "refresh",
  retry: "refresh",
  delete: "trash",
};

/**
 * A donut that shows live progress. ⚠ With no known total it shows the BYTES instead of a ring: a
 * ring at 0% over a file whose size nobody knows is a lie that looks like progress (`percentOf`
 * returns null in exactly that case, and the same rule is enforced natively in the event planner).
 */
function ProgressRing({ percent, bytes }: { percent: number | null; bytes: number }) {
  if (percent === null) {
    return <span className="text-[11px] font-medium tabular-nums text-zinc-400">{fmtBytes(bytes)} downloaded</span>;
  }
  const radius = 7;
  const circumference = 2 * Math.PI * radius;
  return (
    <span className="flex items-center gap-1.5" title={`${percent}% downloaded`}>
      <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" className="-rotate-90">
        <circle cx="9" cy="9" r={radius} fill="none" stroke="currentColor" strokeWidth="2" className="text-white/15" />
        <circle
          cx="9"
          cy="9"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          className="text-accent"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - percent / 100)}
        />
      </svg>
      <span className="text-[11px] font-bold tabular-nums text-accent">{percent}%</span>
    </span>
  );
}

/**
 * ⚠ ONE derivation, TWO places to render it — and the split is the fix for his "the options are all
 * over the place" (2026-09-17).
 *
 * A download is a CONTROL and a REPORT: the control belongs in the action row with the other actions
 * (same box as Watched and More), and the report — "1.4 GB downloaded", "no longer on the server", a
 * transcode warning — belongs on its own line under that row. One component returning both is why the
 * button had to carry its own paragraph and why its size-summary text pushed it onto a line of its own
 * inside the action row: the row was measuring a button AND a sentence.
 *
 * Both halves call this, so the facts cannot disagree between the tile and the line.
 */
function useDownloadFacts(itemId: string, title: string) {
  const available = useOffline((state) => state.available);
  const row = useOffline((state) => state.items.find((item) => item.itemId === itemId) ?? null);
  const busy = useOffline((state) => Boolean(state.pending[itemId]));
  const notice = useOffline((state) => (state.notice?.itemId === itemId ? state.notice : null));

  // ⚠ Asked even when a row already exists: the answer is what lets the page say "no longer on the
  // server" about a film the DEVICE still holds (§4.7) — those are two facts about two machines.
  const bundle = useOfflineBundle(itemId, available);

  const onDownload = useCallback(() => {
    void downloadTitle(itemId, title, "auto");
  }, [itemId, title]);

  // `null` = we could not ask (the server is unreachable), which must never be shown as "the server
  // has forgotten this title": offline, the second sentence would be a lie about the first fact.
  const serverKnows = bundle.isError ? null : bundle.data === null ? false : bundle.data ? true : null;

  return {
    available,
    row,
    busy,
    notice,
    onDownload,
    serverKnows,
    summary: downloadSummary(bundle.data),
    warning: transcodeWarning(bundle.data),
    note: row ? serverNote(serverKnows, row) : "",
    // ⚠ `actionsFor` is the ONE decision about what a download can do in its current state
    // (offline/lib.ts) — this file renders what it returns and decides nothing itself. `play` is
    // filtered out because the page's own Play button is the one that starts a film; the offline
    // entry point for it is the item row on the Downloads screen.
    actions: actionsFor(row).filter((kind) => kind !== "play"),
  };
}

/**
 * The download CONTROL, as tiles for the action row — one per action the rule returns (a state can
 * offer two: cancel/delete, resume/delete, retry/delete, delete).
 */
export function DownloadAction({ itemId, title }: { itemId: string; title: string }) {
  const { available, row, busy, actions, onDownload } = useDownloadFacts(itemId, title);
  if (!available) return null;

  /** No row yet: the one action is Download, and it is the only thing to draw. */
  if (actions.length === 0) {
    return (
      <IconAction
        icon="download"
        label={busy ? "Starting…" : "Download"}
        disabled={busy}
        onClick={onDownload}
      />
    );
  }

  const percent = row ? percentOf(row.bytes, row.totalBytes) : 0;
  return (
    <>
      {actions.map((kind) => (
        <IconAction
          key={kind}
          label={ACTION_LABELS[kind]}
          danger={kind === "delete"}
          disabled={busy}
          onClick={() => {
            if (kind === "delete") void deleteTitle(itemId);
            else if (kind === "cancel") void cancelTitle(itemId);
            else onDownload(); // download · resume · retry — the app decides which of the three
          }}
        >
          {kind === "cancel" ? (
            <ProgressRing percent={percent} bytes={row?.bytes ?? 0} />
          ) : (
            <Icon name={ACTION_ICON[kind]} size={19} />
          )}
        </IconAction>
      ))}
    </>
  );
}

/**
 * The download REPORT, as lines under the action row: the row's own status, a transcode warning, the
 * "the server no longer has this" note, and any failure the app reported. Each takes the full width so
 * it reads as a caption for the row above it rather than as another control.
 */
export function DownloadNotice({ itemId }: { itemId: string }) {
  const { available, row, warning, note, notice } = useDownloadFacts(itemId, "");
  if (!available) return null;
  if (!row && !warning && !note && !notice) return null;

  return (
    <>
      {row ? (
        <p className={`w-full text-[11px] ${row.state === "failed" ? "text-red-400" : "text-zinc-500"}`}>
          {/* ⚠ The rendition rides WITH the status, not as a chip beside the button: it is a report
              about the copy on the device, and a badge in the action row made it look like something
              you could change here. */}
          {rowStatusText(row)}
          {row.mode ? ` · ${modeLabel(row.mode)}` : ""}
        </p>
      ) : null}
      {warning ? <p className="w-full text-[11px] text-amber-300/90">{warning}</p> : null}
      {note ? <p className="w-full text-[11px] text-amber-300/90">{note}</p> : null}
      {notice ? <p className="w-full text-[11px] text-red-400">{notice.text}</p> : null}
    </>
  );
}
