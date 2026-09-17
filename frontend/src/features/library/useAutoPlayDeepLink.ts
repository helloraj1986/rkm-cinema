import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";

import type { EpisodeShape, ItemDetail as ItemDetailShape } from "../../lib/api/client";
import { detailInProgress } from "./lib";
import type { QueueEntry } from "../playback/lib";

/**
 * The `?play=1[&episode={id}]` deep link — ONE rule for the desktop page and the phone's screen
 * (MOBILE_FIRST_UI_PLAN M4 · extraction E11).
 *
 * `GlobalSearch`'s rows, a Continue-Watching card and a watched/unwatched toggle all navigate by URL
 * — `playTarget(row)` builds `/library/item/:id?play=1`, with the episode id when there is one — and
 * whatever renders that route is responsible for acting on it. It is not a trivial one-liner: a
 * SERIES can arrive before its episode list exists (so the effect must wait, not fire), and the
 * params must be cleared afterwards or Back and refresh replay the film. That reasoning lived inside
 * `ItemDetailContent`; M4 gives the phone its own screen, and a second copy of "wait for the
 * episodes, then clear the params" is exactly the kind of rule that silently differs.
 *
 * ⚠ It fires ONCE per mount (`autoPlayedRef`), which is why both screens key the component by item
 * — a deep link to a second title is a new mount, not a second firing on the same one.
 */
export function useAutoPlayDeepLink({
  itemId,
  isSeries,
  detail,
  episodes,
  seriesPlayEp,
  queue,
  resumeSec,
  runtimeSec,
  title,
  onPlayMovie,
  onPlayEpisode,
}: {
  itemId: string;
  isSeries: boolean;
  /** The detail probe's answer — `undefined` until it lands. */
  detail: ItemDetailShape | undefined;
  episodes: EpisodeShape[];
  /** Where a series' Play goes when no episode was named (`nextPlayableEpisode ?? first`). */
  seriesPlayEp: EpisodeShape | null;
  queue: QueueEntry[];
  resumeSec: number;
  runtimeSec: number;
  /** The title as the SCREEN already resolved it (detail name, then the list row, then a fallback). */
  title: string;
  /** Start a movie: (itemId, title, resumeSeconds, runtimeSeconds). */
  onPlayMovie: (itemId: string, title: string, resume: number, runtime: number) => void;
  onPlayEpisode: (episode: EpisodeShape, queue: QueueEntry[]) => void;
}): void {
  const [searchParams, setSearchParams] = useSearchParams();
  const autoPlayedRef = useRef(false);

  useEffect(() => {
    if (searchParams.get("play") !== "1" || autoPlayedRef.current) return;

    if (isSeries) {
      const epId = searchParams.get("episode");
      const targetEp = epId ? episodes.find((e) => e.id === epId) ?? null : seriesPlayEp;
      if (!targetEp) return; // ⚠ wait for the episode list — do NOT fire and forget
      autoPlayedRef.current = true;
      onPlayEpisode(targetEp, queue);
    } else if (detail) {
      autoPlayedRef.current = true;
      onPlayMovie(itemId, title, detailInProgress(detail.play) ? resumeSec : 0, runtimeSec);
    } else {
      return; // ⚠ wait for the detail probe
    }

    const next = new URLSearchParams(searchParams);
    next.delete("play");
    next.delete("episode");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, isSeries, detail, episodes, itemId, resumeSec, runtimeSec, seriesPlayEp, title]);
}
