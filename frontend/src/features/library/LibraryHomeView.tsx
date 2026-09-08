import {
  useContinueWatching,
  useLibraryItems,
  useLibraryRecent,
  useRecentlyWatched,
  useScanLibrary,
} from "./api";
import { ContinueWatchingRow } from "./ContinueWatchingRow";
import { MediaCard } from "./MediaCard";
import { useLibraryOutlet } from "./LibraryLayout";
import { isSeries } from "./lib";

/**
 * /library/home — the Plex-style "Home": Continue Watching + Recently Watched +
 * Recently Added rows (plan docs/PLEX_VIEWS_PLAN.md route table). Card clicks
 * navigate to the item's own page; the full type grids live in the Movies /
 * TV Shows folders.
 */
export function LibraryHomeView() {
  const items = useLibraryItems();
  const continueWatching = useContinueWatching();
  const recentlyWatched = useRecentlyWatched();
  const recent = useLibraryRecent();
  const scan = useScanLibrary();
  const { quickPlay, openItem, toggleWatched } = useLibraryOutlet();

  const all = items.data?.items ?? [];
  const movies = all.filter((i) => !isSeries(i)).length;
  const shows = all.length - movies;
  // Recently-added cards need an id to navigate/play (provider shape guard).
  const recentlyAdded = (recent.data?.recent ?? []).filter((i) => Boolean(i.item_id));

  const cardProps = {
    onQuickPlay: quickPlay,
    onOpenDetail: openItem,
    onToggleWatched: toggleWatched,
  };

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">My Library</h2>
          <p className="text-xs text-zinc-500">
            {items.data?.provider
              ? `${items.data.provider} · ${all.length} titles (${movies} films · ${shows} shows)`
              : "No library backend connected."}
          </p>
        </div>
        <button
          onClick={() => scan.mutate()}
          disabled={scan.isPending}
          className="rounded-lg bg-amber-400 px-3 py-1.5 text-sm font-semibold text-black hover:bg-amber-300 disabled:opacity-50"
        >
          {scan.isPending ? "Scanning…" : "Scan"}
        </button>
      </div>
      {scan.isError && <p className="text-xs text-red-400">Scan failed — check the backend.</p>}

      <ContinueWatchingRow
        items={continueWatching.data?.items ?? []}
        onQuickPlay={quickPlay}
        onOpenDetail={openItem}
        onToggleWatched={toggleWatched}
      />

      {recentlyWatched.data && recentlyWatched.data.items.length > 0 && (
        <section>
          <h2 className="mb-3 text-base font-semibold text-white">
            <span className="mr-2 inline-block h-3 w-1.5 rounded bg-emerald-400 align-middle" />
            Recently Watched
          </h2>
          <div className="flex flex-wrap gap-3">
            {recentlyWatched.data.items.map((item) => (
              <MediaCard key={item.item_id} item={item} {...cardProps} />
            ))}
          </div>
        </section>
      )}

      {recentlyAdded.length > 0 && (
        <section>
          <h2 className="mb-3 text-base font-semibold text-white">
            <span className="mr-2 inline-block h-3 w-1.5 rounded bg-amber-400 align-middle" />
            Recently Added
          </h2>
          <div className="flex flex-wrap gap-3">
            {recentlyAdded.map((item) => (
              <MediaCard key={item.item_id} item={item} {...cardProps} />
            ))}
          </div>
        </section>
      )}

      {items.isLoading && <p className="text-sm text-zinc-400">Loading library…</p>}
      {!items.isLoading && all.length === 0 && (
        <p className="text-sm text-zinc-500">
          No titles yet — add media to the library and hit Scan.
        </p>
      )}
    </div>
  );
}
