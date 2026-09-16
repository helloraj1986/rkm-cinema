import { Icon, type IconName } from "../../components/ui/Icon";
import { useLibraryOutlet } from "../library/LibraryLayout";
import { posterUrl } from "../library/lib";
import {
  ACTION_LABELS,
  actionsFor,
  diskSummary,
  fmtBytes,
  modeLabel,
  percentOf,
  rowStatusText,
  type OfflineActionKind,
} from "./lib";
import { cancelTitle, deleteTitle, downloadTitle, useOffline } from "./session";

/**
 * The Downloads screen (B4, plan §4.6) — **what this device is holding, and what can be done with it.**
 *
 * Three rules shape it, and all three come from the same fact: this screen is the one that has to
 * work when nothing else does.
 *
 * 1. ⚠ **Every fact on a row comes from the DEVICE, not from the API.** Offline is exactly when this
 *    screen matters, and offline the API cannot be asked. So there is no per-row server lookup here:
 *    the rows are native's own (`list` + events), and the only server-side question the screen asks is
 *    none at all. (The detail page does ask, because there the server's answer is the point.)
 * 2. ⚠ **It plays films itself.** The library views start playback through `LibraryLayout`, and this
 *    route is mounted by the same layout for exactly that reason: offline, the item's detail page
 *    cannot fetch its data, so routing him through it to reach a downloaded film would be routing him
 *    through a page that may not render.
 * 3. ⚠ **A film that cannot be played says why, and one that can is one press away.** Every action on
 *    a row comes from `actionsFor` — the same pure decision the detail page uses — so the two surfaces
 *    can never disagree about what is on the device.
 */

const ACTION_ICON: Record<OfflineActionKind, IconName> = {
  play: "play",
  download: "download",
  cancel: "close",
  resume: "refresh",
  retry: "refresh",
  delete: "trash",
};

const BTN = "inline-flex h-9 items-center gap-1.5 rounded-[10px] px-3 text-xs font-bold transition disabled:opacity-60";
const BTN_PRIMARY = `${BTN} bg-accent text-black hover:bg-accent-hover`;
const BTN_SECONDARY = `${BTN} border border-white/10 bg-white/[.07] text-zinc-100 hover:bg-white/[.12]`;
const BTN_GHOST = `${BTN} px-2.5 text-zinc-400 hover:text-white`;

function variantFor(kind: OfflineActionKind): string {
  return kind === "play" ? BTN_PRIMARY : kind === "delete" ? BTN_GHOST : BTN_SECONDARY;
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-white/[.08] py-16 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-2xl bg-surface-2 text-zinc-500">
        <Icon name="download" size={24} />
      </div>
      <p className="max-w-md text-sm text-zinc-400">{children}</p>
    </div>
  );
}

export function DownloadsView() {
  const available = useOffline((state) => state.available);
  const loaded = useOffline((state) => state.loaded);
  const items = useOffline((state) => state.items);
  const pending = useOffline((state) => state.pending);
  const notice = useOffline((state) => (state.notice && state.notice.itemId === null ? state.notice : null));
  const queued = useOffline((state) => state.queuedReports);
  const { startMovie } = useLibraryOutlet();

  if (!available) {
    // Reachable by URL in a browser, and it says why rather than pretending to be empty: an empty
    // list would read as "nothing downloaded", which is a different and wrong statement.
    return (
      <section aria-label="Downloads" className="flex flex-col gap-6">
        <h1 className="text-2xl font-bold tracking-[-0.02em] text-white">Downloads</h1>
        <Empty>
          Downloads live on the device. Open RKM Cinema on your iPhone or iPad to keep a film on it —
          this browser has no offline store to put one in.
        </Empty>
      </section>
    );
  }

  return (
    <section aria-label="Downloads" className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-2xl font-bold tracking-[-0.02em] text-white">Downloads</h1>
        <p className="text-sm text-zinc-400" data-testid="downloads-summary">
          {diskSummary(items)}
        </p>
        {/* ⚠ Positions recorded with no server, waiting to be replayed. Silently holding them would
            make "Continue Watching did not update" a mystery with nothing on screen to explain it. */}
        {queued > 0 ? (
          <p className="text-xs text-amber-300/90" data-testid="downloads-queued">
            {queued} watching position{queued === 1 ? "" : "s"} waiting to sync — they will be sent the
            next time this server can be reached.
          </p>
        ) : null}
        {notice ? <p className="text-xs text-red-400">{notice.text}</p> : null}
      </div>

      {items.length === 0 ? (
        <Empty>
          {loaded
            ? "Nothing is downloaded yet. Open a film and press Download to keep it on this device."
            : "Asking the device what it holds…"}
        </Empty>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((row) => {
            const poster = posterUrl({ item_id: row.itemId });
            const percent = percentOf(row.bytes, row.totalBytes);
            const busy = Boolean(pending[row.itemId]);
            return (
              <li
                key={row.itemId}
                data-testid={`download-row-${row.itemId}`}
                data-state={row.state}
                className="flex items-center gap-4 rounded-xl border border-transparent bg-surface-2/50 p-3 transition-colors hover:bg-surface-2"
              >
                <div className="relative h-[66px] w-[46px] shrink-0 overflow-hidden rounded-lg bg-surface-3">
                  {poster ? (
                    <img
                      src={poster}
                      alt=""
                      loading="lazy"
                      className="h-full w-full object-cover"
                      onError={(e) => {
                        (e.currentTarget as HTMLImageElement).style.display = "none";
                      }}
                    />
                  ) : null}
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2.5">
                    <span className="truncate text-sm font-semibold text-zinc-100">{row.title}</span>
                    {row.mode ? (
                      <span className="shrink-0 rounded-full border border-white/[.08] bg-white/[.06] px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em] text-zinc-400">
                        {modeLabel(row.mode)}
                      </span>
                    ) : null}
                  </div>
                  <p
                    className={`mt-0.5 text-xs ${row.state === "failed" ? "text-red-400" : "text-zinc-400"}`}
                    data-testid={`download-status-${row.itemId}`}
                  >
                    {rowStatusText(row)}
                  </p>
                  {row.state === "downloading" && percent !== null ? (
                    <div className="mt-1.5 h-[3px] w-full max-w-[280px] overflow-hidden rounded-full bg-white/10">
                      <div className="h-full bg-accent" style={{ width: `${percent}%` }} />
                    </div>
                  ) : null}
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  {row.state === "ready" ? (
                    <span className="mr-1 hidden text-[11px] font-medium tabular-nums text-zinc-500 sm:inline">
                      {fmtBytes(row.bytes)}
                    </span>
                  ) : null}
                  {actionsFor(row).map((kind) => (
                    <button
                      key={kind}
                      type="button"
                      disabled={busy}
                      className={variantFor(kind)}
                      onClick={() => {
                        if (kind === "play") {
                          // ⚠ `resume: 0` and `runtime: 0` on purpose. The player resolves the real
                          // starting point itself (`spooledResumeSeconds`), because offline the two
                          // facts it needs — where he got to, and how long the film is — are on the
                          // DEVICE, not on a server this screen cannot reach.
                          startMovie(row.itemId, row.title, 0, 0);
                        } else if (kind === "delete") {
                          void deleteTitle(row.itemId);
                        } else if (kind === "cancel") {
                          void cancelTitle(row.itemId);
                        } else {
                          void downloadTitle(row.itemId, row.title, row.mode || "auto");
                        }
                      }}
                    >
                      <Icon name={ACTION_ICON[kind]} size={13} filled={kind === "play"} />
                      {ACTION_LABELS[kind]}
                    </button>
                  ))}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
