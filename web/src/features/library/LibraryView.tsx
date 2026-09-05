import { useState } from "react";
import { useLibraryItems, useContinueWatching, useScanLibrary } from "./api";
import { isSeries } from "./lib";
import { MediaCard } from "./MediaCard";
import { ContinueWatchingRow } from "./ContinueWatchingRow";
import { Player } from "./Player";
import type { MediaItem } from "../../lib/api/client";

export function LibraryView() {
  const items = useLibraryItems();
  const continueWatching = useContinueWatching();
  const scan = useScanLibrary();
  const [playing, setPlaying] = useState<MediaItem | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const all = items.data?.items ?? [];
  const movies = all.filter((i) => !isSeries(i)).length;
  const shows = all.length - movies;

  function handlePlay(item: MediaItem) {
    if (isSeries(item)) {
      // Episode picker is part of the playback slice (Phase 3b), not this pass.
      setNotice(`"${item.title}" is a series — the episode picker lands with the playback slice (Phase 3b).`);
      return;
    }
    setNotice(null);
    setPlaying(item);
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-1">
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
        {scan.isError && (
          <p className="mt-1 text-xs text-red-400">Scan failed — check the backend.</p>
        )}
        {notice && (
          <p className="mt-1 rounded bg-zinc-800/70 px-2 py-1 text-xs text-zinc-300">{notice}</p>
        )}
      </div>

      <ContinueWatchingRow items={continueWatching.data?.items ?? []} onPlay={handlePlay} />

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
              <MediaCard key={item.item_id} item={item} onPlay={handlePlay} />
            ))}
          </div>
        )}
      </section>

      {playing && <Player item={playing} onClose={() => setPlaying(null)} />}
    </div>
  );
}