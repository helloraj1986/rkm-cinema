import { useState } from "react";
import { useLibraryItems, useContinueWatching, useRecentlyWatched, useScanLibrary, useMutateItemState } from "./api";
import { isSeries } from "./lib";
import { MediaCard } from "./MediaCard";
import { ContinueWatchingRow } from "./ContinueWatchingRow";
import { ItemDetail } from "./ItemDetail";
import { Player, type PlayTarget } from "../playback/Player";
import { startPosition, type QueueEntry } from "../playback/lib";
import type { EpisodeShape, MediaItem } from "../../lib/api/client";

interface PlayState {
  item: PlayTarget;
  resume: number;
  queue: QueueEntry[];
  runtime: number;
}

export function LibraryView() {
  const items = useLibraryItems();
  const continueWatching = useContinueWatching();
  const recentlyWatched = useRecentlyWatched();
  const scan = useScanLibrary();
  const mutateState = useMutateItemState();
  const [playing, setPlaying] = useState<PlayState | null>(null);
  const [detail, setDetail] = useState<MediaItem | null>(null);

  const all = items.data?.items ?? [];
  const movies = all.filter((i) => !isSeries(i)).length;
  const shows = all.length - movies;

  function handleToggleWatched(item: MediaItem) {
    mutateState.mutate({ itemId: item.item_id, watched: !item.played });
  }

  /** Whole-card click → Plex-style detail/preplay overlay (movie or series). */
  function handleOpenDetail(item: MediaItem) {
    setDetail(item);
  }

  /** Hover primary action: movies play now; series open detail (episodes live there). */
  function handleQuickPlay(item: MediaItem) {
    if (isSeries(item)) {
      setDetail(item);
      return;
    }
    setPlaying({ item: { item_id: item.item_id, title: item.title }, resume: item.playback_position || 0, queue: [], runtime: item.runtime || 0 });
  }

  /** Movie Play/Resume from the detail overlay. */
  function handlePlayMovie(itemId: string, title: string, resume: number, runtime: number) {
    setDetail(null);
    setPlaying({ item: { item_id: itemId, title }, resume, queue: [], runtime });
  }

  /** Episode Play/Resume from the detail overlay (queue rides for Up Next). */
  function handlePlayEpisode(ep: EpisodeShape, queue: QueueEntry[]) {
    setDetail(null);
    setPlaying({ item: { item_id: ep.id, title: ep.name }, resume: startPosition(ep), queue, runtime: ep.runtime || 0 });
  }

  function handleSwitch(entry: QueueEntry) {
    setPlaying({ item: { item_id: entry.id, title: entry.name }, resume: entry.position, queue: playing?.queue ?? [], runtime: entry.runtime ?? playing?.runtime ?? 0 });
  }

  const cardProps = (item: MediaItem) => ({
    item,
    onQuickPlay: handleQuickPlay,
    onOpenDetail: handleOpenDetail,
    onToggleWatched: handleToggleWatched,
  });

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
        onQuickPlay={handleQuickPlay}
        onOpenDetail={handleOpenDetail}
        onToggleWatched={handleToggleWatched}
      />

      {recentlyWatched.data && recentlyWatched.data.items.length > 0 && (
        <section>
          <h2 className="mb-3 text-base font-semibold text-white">
            <span className="mr-2 inline-block h-3 w-1.5 rounded bg-emerald-400 align-middle" />
            Recently Watched
          </h2>
          <div className="flex flex-wrap gap-3">
            {recentlyWatched.data.items.map((item) => (
              <MediaCard key={item.item_id} {...cardProps(item)} />
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-base font-semibold text-white">
          <span className="mr-2 inline-block h-3 w-1.5 rounded bg-amber-400 align-middle" />
          Full Library
        </h2>
        {items.isLoading ? (
          <p className="text-sm text-zinc-400">Loading library…</p>
        ) : all.length === 0 ? (
          <p className="text-sm text-zinc-500">No titles yet.</p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {all.map((item) => (
              <MediaCard key={item.item_id} {...cardProps(item)} />
            ))}
          </div>
        )}
      </section>

      {detail && (
        <ItemDetail
          key={detail.item_id}
          item={detail}
          onPlayMovie={handlePlayMovie}
          onPlayEpisode={handlePlayEpisode}
          onToggleWatched={handleToggleWatched}
          onClose={() => setDetail(null)}
        />
      )}
      {playing && (
        <Player
          key={playing.item.item_id}
          item={playing.item}
          resume={playing.resume}
          queue={playing.queue}
          runtime={playing.runtime}
          onSwitch={handleSwitch}
          onClose={() => setPlaying(null)}
        />
      )}
    </div>
  );
}
