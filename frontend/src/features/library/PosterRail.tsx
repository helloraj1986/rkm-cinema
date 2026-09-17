import type { MediaItem } from "../../lib/api/client";
import { MediaCard } from "./MediaCard";

/**
 * The handlers every poster on Home takes. Exported with the rail because they travel together — a
 * rail of posters that cannot be played or opened is not a rail.
 */
export type CardHandlers = {
  onQuickPlay: (item: MediaItem) => void;
  onOpenDetail: (item: MediaItem) => void;
  onToggleWatched?: (item: MediaItem) => void;
};

/**
 * A horizontal rail of posters (M3 · extraction E9).
 *
 * ⚠ Extracted because the phone Home renders the SAME rails as the desktop one: the scroll behaviour
 * (`snap-rail` + hidden scrollbar), the gap and the card's own fixed width are one decision, and a
 * second copy of that class string is a second rail that drifts. The rail scrolls horizontally ON
 * PURPOSE — that is what a rail is — so it is the one place in the library where sideways movement is
 * correct, and it never moves the page itself.
 */
export function PosterRail({ items, handlers }: { items: MediaItem[]; handlers: CardHandlers }) {
  return (
    <div className="no-scrollbar snap-rail flex gap-3.5 overflow-x-auto pb-1.5">
      {items.map((item) => (
        <MediaCard key={item.item_id} item={item} {...handlers} />
      ))}
    </div>
  );
}
