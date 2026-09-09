import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLibraryRecent } from "../library/api";
import { EmptyState } from "./CardRow";
import { WatchCard } from "./WatchCard";
import { WatchlistDetail } from "./WatchlistDetail";
import { useCardActions } from "./actions";
import { useWatchlist } from "./api";
import {
  filterWatchlist,
  WATCHLIST_CHIPS,
  WATCHLIST_SORTS,
  type WatchlistChip,
  type WatchlistEntry,
  type WatchlistSort,
} from "./lib";

const PAGE = 36;

/**
 * Watchlist (LEGACY_PARITY_PLAN): chips (All/Movies/TV Shows/Downloaded/Not
 * Downloaded) + sort (Recently Added/Rating/Release Date/Title) over the live
 * rich entries, state-aware cards, page-in after 36, and the My Library strip.
 */
export function WatchlistView() {
  const navigate = useNavigate();
  const { entries, stateFor, isLoading, isError } = useWatchlist();
  const { data: lib } = useLibraryRecent();
  const actions = useCardActions();
  const [type, setType] = useState<WatchlistChip>("all");
  const [sort, setSort] = useState<WatchlistSort>("recent");
  const [shown, setShown] = useState(PAGE);
  const [detail, setDetail] = useState<{ entry: WatchlistEntry; trailer?: boolean } | null>(null);

  const list = useMemo(
    () => filterWatchlist(entries, stateFor, { type, sort }),
    [entries, stateFor, type, sort],
  );
  const page = list.slice(0, shown);
  const openEntry = (entry: WatchlistEntry, trailer = false) => setDetail({ entry, trailer });

  const sub =
    list.length === entries.length
      ? `${entries.length} title${entries.length === 1 ? "" : "s"}`
      : `${list.length} of ${entries.length} titles`;

  return (
    <div className="flex flex-col gap-7 pb-8">
      <div className="flex flex-wrap items-end justify-between gap-4 pt-2">
        <div>
          <h1 className="text-[32px] font-bold leading-none tracking-[-0.02em] text-zinc-50">Watchlist</h1>
          <div className="mt-2 text-[13px] text-zinc-500">
            {isLoading ? "Loading…" : `${list.length} ${list.length === 1 ? "title" : "titles"}${sub.includes(" of ") ? ` · ${sub}` : ""}`}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {WATCHLIST_CHIPS.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={() => {
                setType(c.key);
                setShown(PAGE);
              }}
              aria-pressed={type === c.key}
              className={`shrink-0 rounded-full px-3.5 py-1.5 text-xs font-semibold transition ${
                type === c.key
                  ? "bg-accent text-black hover:bg-accent-hover"
                  : "border border-white/[.08] bg-white/[.06] text-zinc-300 hover:bg-white/[.1] hover:text-white"
              }`}
            >
              {c.label}
            </button>
          ))}
          <select
            value={sort}
            onChange={(e) => {
              setSort(e.target.value as WatchlistSort);
              setShown(PAGE);
            }}
            aria-label="Sort by"
            className="rounded-[8px] border border-white/[.08] bg-surface-2 px-2.5 py-2 text-xs font-medium text-zinc-200 outline-none transition focus:border-accent/50"
          >
            {WATCHLIST_SORTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isLoading && !entries.length ? (
        <div
          className="grid grid-cols-[repeat(auto-fill,minmax(158px,1fr))] gap-x-4 gap-y-7"
          data-testid="watchlist-loading"
          aria-hidden="true"
        >
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="skeleton aspect-[2/3] rounded-[10px]" />
          ))}
        </div>
      ) : list.length ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(158px,1fr))] gap-x-4 gap-y-7">
          {page.map((e) => (
            <WatchCard
              key={String(e.tmdbId ?? e.imdbId)}
              entry={e}
              state={stateFor(e)}
              fluid
              onOpen={openEntry}
              onDownload={actions.download}
              onPlayInRkm={actions.playInRkm}
              onWatchLink={actions.watchLink}
              onTrailer={(en) => openEntry(en, true)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title={
            type === "downloaded"
              ? "Nothing downloaded yet"
              : type === "not"
                ? "Everything is downloaded or requested"
                : "Nothing here yet"
          }
          sub={
            type === "downloaded"
              ? "Downloaded titles will collect here when you grab something from Radarr or Sonarr."
              : "Your watchlist is empty — the daily recommendation engine will bring fresh picks."
          }
        />
      )}

      {shown < list.length ? (
        <button
          type="button"
          onClick={() => setShown((n) => n + PAGE)}
          className="mx-auto inline-flex h-10 items-center gap-2 rounded-full border border-white/10 bg-white/[.07] px-6 text-sm font-semibold text-zinc-200 transition hover:bg-white/[.12]"
        >
          Load more ({list.length - shown} remaining)
        </button>
      ) : null}

      {isError && !entries.length ? (
        <EmptyState title="Could not load the watchlist" sub="Check the api container, then reload." />
      ) : null}

      <LibraryStripFooter counts={lib?.counts} server={lib?.server} available={lib?.available} onOpen={() => navigate("/library/home")} />

      {detail ? (
        <WatchlistDetail
          entry={detail.entry}
          state={stateFor(detail.entry)}
          openTrailer={detail.trailer}
          onClose={() => setDetail(null)}
          onDownload={actions.download}
          onPlayInRkm={actions.playInRkm}
          onWatchLink={actions.watchLink}
        />
      ) : null}
    </div>
  );
}

function LibraryStripFooter({
  counts,
  server,
  available,
  onOpen,
}: {
  counts?: Record<string, number>;
  server?: string | null;
  available?: boolean;
  onOpen: () => void;
}) {
  if (!available) return null;
  return (
    <div className="mt-2 flex items-center justify-between gap-4 rounded-xl border border-white/[.06] bg-surface-2/70 px-5 py-3.5">
      <div className="min-w-0 truncate text-sm text-zinc-400">
        <span className="font-semibold text-zinc-200">My Library</span> · {server || "Media server"} —{" "}
        {counts?.movie || 0} films · {counts?.show || 0} shows
      </div>
      <button
        type="button"
        onClick={onOpen}
        className="shrink-0 text-xs font-semibold text-accent transition hover:text-accent-hover"
      >
        Open
      </button>
    </div>
  );
}
