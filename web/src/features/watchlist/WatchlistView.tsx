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
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Watchlist</h1>
          <div className="text-sm text-zinc-500">{isLoading ? "Loading…" : sub}</div>
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
              className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                type === c.key
                  ? "bg-amber-400 text-black"
                  : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
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
            className="rounded-lg border border-zinc-800 bg-zinc-900 px-2 py-1 text-xs text-zinc-300 focus:outline-amber-400"
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
        <div className="flex flex-wrap gap-3" data-testid="watchlist-loading">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="h-60 w-40 animate-pulse rounded-lg bg-zinc-900" />
          ))}
        </div>
      ) : list.length ? (
        <div className="flex flex-wrap gap-3">
          {page.map((e) => (
            <WatchCard
              key={String(e.tmdbId ?? e.imdbId)}
              entry={e}
              state={stateFor(e)}
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
          className="mx-auto rounded-full bg-zinc-800 px-6 py-2 text-sm font-semibold text-zinc-200 hover:bg-zinc-700"
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
    <div className="mt-2 flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-900/50 px-5 py-3">
      <div className="text-sm text-zinc-400">
        <span className="font-semibold text-zinc-200">My Library</span> · {server || "Media server"} —{" "}
        {counts?.movie || 0} films · {counts?.show || 0} shows
      </div>
      <button type="button" onClick={onOpen} className="text-xs font-semibold text-amber-300 hover:text-amber-200">
        Open ›
      </button>
    </div>
  );
}
