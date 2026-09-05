import type { MediaItem } from "../../lib/api/client";
import { isContinueWatching } from "./lib";
import { MediaCard } from "./MediaCard";

export function ContinueWatchingRow({
  items,
  onPlay,
}: {
  items: MediaItem[];
  onPlay: (item: MediaItem) => void;
}) {
  const watch = items.filter(isContinueWatching);
  if (watch.length === 0) return null;
  return (
    <section>
      <h2 className="mb-3 text-base font-semibold text-white">
        <span className="mr-2 inline-block h-3 w-1.5 rounded bg-amber-400 align-middle" />
        Continue Watching
      </h2>
      <div className="flex gap-3 overflow-x-auto pb-2">
        {watch.map((item) => (
          <MediaCard key={item.item_id} item={item} onPlay={onPlay} />
        ))}
      </div>
    </section>
  );
}