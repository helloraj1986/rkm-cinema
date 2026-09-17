import { useContinueWatching, useLibraryItems, useLibraryRecent, useRecentlyWatched } from "./api";
import { continueWatchingItems, pickHomeHero, recentlyAddedItems, withoutHero } from "./lib";
import type { MediaItem } from "../../lib/api/client";

/**
 * How many posters a Home rail shows. ⚠ These are the two numbers that were literals inside
 * the view (`.slice(0, 14)` / `.slice(0, 16)`), and they are named because a rail length is a
 * decision, not arithmetic: the "Recently Played" and "Recently Added" rails are deliberately
 * different lengths, and M3's mobile Home re-reads both.
 */
export const RECENTLY_PLAYED_ROW = 14;
export const RECENTLY_ADDED_ROW = 16;

/**
 * /library/home's view model (M3 · extraction E4) — the four queries the Home screen runs and
 * the rows derived from them, in one place:
 *
 *   * `cwItems`        — Continue Watching, filtered by the ONE rule (E3)
 *   * `hero`           — the cinematic hero pick, and whether it came from Continue Watching
 *   * `recentlyPlayed` — the rail, capped at RECENTLY_PLAYED_ROW
 *   * `recentlyAdded`  — the rail, capped at RECENTLY_ADDED_ROW
 *
 * ⚠ `items` is returned WHOLE rather than as a boolean, because the view's three branches —
 * skeleton, "no media server connected"/error, and the dashboard — are decided by the query's
 * own loading/error/data state, and flattening that into flags here would move those decisions
 * away from the JSX that renders them (and lose the server's `provider` field).
 *
 * The `has…` flags exist because "the section is empty" and "the query has not answered yet"
 * must render the same thing — nothing — without the view slicing an array twice to find out.
 */
export function useHomeRows(): {
  items: ReturnType<typeof useLibraryItems>;
  all: MediaItem[];
  cwItems: MediaItem[];
  hero: MediaItem | null;
  heroIsCw: boolean;
  /** The Continue-Watching rail (hero EXCLUDED, his rule) — empty means the rail does not render. */
  hasCwRail: boolean;
  recentlyPlayed: MediaItem[];
  hasRecentlyPlayed: boolean;
  recentlyAdded: MediaItem[];
  hasRecentlyAdded: boolean;
} {
  const items = useLibraryItems();
  const continueWatching = useContinueWatching();
  const recentlyWatched = useRecentlyWatched();
  const recent = useLibraryRecent();

  const all = items.data?.items ?? [];
  const cwAll = continueWatchingItems(continueWatching.data?.items);
  const recentlyAddedAll = recentlyAddedItems(recent.data?.recent);
  const recentlyPlayedAll = recentlyWatched.data?.items ?? [];
  const hero = pickHomeHero(cwAll, recentlyAddedAll, all);
  // ⚠ The hero is picked from the WHOLE Continue-Watching set and then REMOVED from the rail (his
  // decision, 2026-09-17 — see `withoutHero`): the same title appearing big at the top and as the
  // first card below reads as a de-duplication bug. Both Homes read `cwItems`, so both move together.
  const cwItems = withoutHero(cwAll, hero);

  return {
    items,
    all,
    cwItems,
    hero,
    heroIsCw: Boolean(hero && cwAll.some((i) => i.item_id === hero.item_id)),
    hasCwRail: cwItems.length > 0,
    recentlyPlayed: recentlyPlayedAll.slice(0, RECENTLY_PLAYED_ROW),
    hasRecentlyPlayed: recentlyPlayedAll.length > 0,
    recentlyAdded: recentlyAddedAll.slice(0, RECENTLY_ADDED_ROW),
    hasRecentlyAdded: recentlyAddedAll.length > 0,
  };
}
