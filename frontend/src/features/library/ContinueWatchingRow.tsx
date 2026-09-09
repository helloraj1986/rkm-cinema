import type { MediaItem } from "../../lib/api/client";
import { isContinueWatching, seriesTargetForEpisode } from "./lib";
import { ContinueWatchingCard } from "./ContinueWatchingCard";
import { SectionHeader } from "../../components/ui/SectionHeader";

/**
 * Continue Watching rail (design spec §10): landscape backdrop-first cards that
 * are larger than ordinary library cards. Episode cards resume the EPISODE on
 * ▶ (quickPlay keeps the episode id/position) and open the SERIES page on a
 * whole-card click so context + the episode list are visible.
 */
export function ContinueWatchingRow({
  items,
  onQuickPlay,
  onOpenDetail,
}: {
  items: MediaItem[];
  onQuickPlay: (item: MediaItem) => void;
  onOpenDetail: (item: MediaItem) => void;
}) {
  const watch = (items ?? []).filter(isContinueWatching);
  if (watch.length === 0) return null;
  const openDetailFor = (item: MediaItem) =>
    onOpenDetail(seriesTargetForEpisode(item) ?? item);
  return (
    <section aria-label="Continue watching">
      <SectionHeader title="Continue Watching" />
      <div className="no-scrollbar snap-rail flex gap-3.5 overflow-x-auto pb-1.5">
        {watch.map((item) => (
          <ContinueWatchingCard
            key={item.item_id}
            item={item}
            onQuickPlay={onQuickPlay}
            onOpenDetail={openDetailFor}
          />
        ))}
      </div>
    </section>
  );
}
