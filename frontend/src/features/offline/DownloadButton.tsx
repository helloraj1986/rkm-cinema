import { useCallback } from "react";

import { Icon } from "../../components/ui/Icon";
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

export function DownloadButton({ itemId, title }: { itemId: string; title: string }) {
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

  if (!available) return null;

  // `null` = we could not ask (the server is unreachable), which must never be shown as "the server
  // has forgotten this title": offline, the second sentence would be a lie about the first fact.
  const serverKnows = bundle.isError ? null : bundle.data === null ? false : bundle.data ? true : null;
  const summary = downloadSummary(bundle.data);
  const warning = transcodeWarning(bundle.data);
  const note = row ? serverNote(serverKnows, row) : "";
  // `play` is filtered out: the page's Play button is the one that starts a film (see above).
  const actions = actionsFor(row).filter((kind) => kind !== "play");

  return (
    <div className="flex flex-col items-start gap-1.5">
      <div className="flex flex-wrap items-center gap-2.5">
        {row ? (
          <>
            {row.state === "downloading" ? (
              <ProgressRing percent={percentOf(row.bytes, row.totalBytes)} bytes={row.bytes} />
            ) : null}
            {actions.map((kind) => (
              <button
                key={kind}
                type="button"
                disabled={busy}
                className={ACTION_VARIANT[kind]}
                onClick={() => {
                  if (kind === "delete") void deleteTitle(itemId);
                  else if (kind === "cancel") void cancelTitle(itemId);
                  else onDownload(); // download · resume · retry — the app decides which of the three
                }}
              >
                <Icon name={ACTION_ICON[kind]} size={15} />
                {ACTION_LABELS[kind]}
              </button>
            ))}
            {row.mode ? (
              <span className="rounded-full border border-white/[.08] bg-white/[.06] px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em] text-zinc-400">
                {modeLabel(row.mode)}
              </span>
            ) : null}
          </>
        ) : (
          <>
            <button type="button" onClick={onDownload} disabled={busy} className={PRIMARY}>
              <Icon name="download" size={15} />
              {busy ? "Starting…" : "Download"}
            </button>
            {/* ⚠ The rendition and the size BEFORE he commits to it, or nothing at all. */}
            {summary ? (
              <span className="text-[11px] font-medium text-zinc-500">{summary}</span>
            ) : bundle.isError ? (
              <span className="text-[11px] font-medium text-zinc-500">The server could not be asked.</span>
            ) : null}
          </>
        )}
      </div>

      {row ? (
        <p className={`text-[11px] ${row.state === "failed" ? "text-red-400" : "text-zinc-500"}`}>
          {rowStatusText(row)}
        </p>
      ) : null}
      {warning ? <p className="text-[11px] text-amber-300/90">{warning}</p> : null}
      {note ? <p className="text-[11px] text-amber-300/90">{note}</p> : null}
      {notice ? <p className="text-[11px] text-red-400">{notice.text}</p> : null}
    </div>
  );
}
