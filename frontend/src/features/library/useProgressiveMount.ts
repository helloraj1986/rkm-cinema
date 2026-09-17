import { useEffect, useState } from "react";
import {
  FIRST_PAINT_CARDS,
  MOUNT_STEP,
  mountedCount,
  needsMoreRows,
  nextExtraCount,
} from "./lib";

/**
 * Run `work` in the NEXT macrotask, and return its canceller.
 *
 * ⚠ This was `requestIdleCallback`, and the production measurement is why it is not. Idle callbacks
 * are starved by exactly the work they are queueing: each step mounts a chunk of cards, those cards
 * begin loading posters, layout runs — so the main thread is rarely "idle", and every step then waits
 * out the `timeout` escape hatch. Measured on the real 714-title folder, a production build: the
 * DOM took **7.4 s** to hold the whole list, while the same list mounted in one commit took 1.9 s.
 * A first paint of 78 ms is worth little if the rest of the page is still filling seven seconds later.
 *
 * A macrotask per step keeps the commits SEPARATE (which is the whole point — no long task) while
 * letting them run back to back; the browser still paints between them, and a nested `setTimeout`
 * chain is clamped to a few ms, so the whole list lands in a few hundred ms rather than seconds.
 */
function onNextTask(work: () => void): () => void {
  const handle = setTimeout(work, 0);
  return () => clearTimeout(handle);
}

/**
 * Progressive mounting (M3) — how many of a long list are mounted RIGHT NOW.
 *
 * ⚠ The problem this solves, measured: `LibraryFolderView` mapped all 713 rows of the real Movies
 * folder in ONE commit, which held the main thread for 1.7–2.0 s on EVERY tap (CDP: Script 2.4 s,
 * `setAttribute` 814 ms — `tools/measure_library_latency.py`). Mounting a screenful first and
 * growing in idle steps removes that single long commit.
 *
 * ⚠ What it deliberately is NOT: virtualisation. Nothing is ever unmounted, so the page keeps its
 * exact height, every row stays reachable by ordinary scrolling, and no row's geometry changes.
 * That is what lets it be applied to the DESKTOP view without moving the layout the regression
 * argument (§10) protects — the bounded-DOM window belongs to the mobile grid, whose row geometry
 * this phase defines anyway.
 *
 * ⚠ `resetKey` is the LIST'S IDENTITY (folder + genre + sort), not its length: a 30-row filter over
 * a 713-row folder paints its own 30 rows immediately instead of inheriting a grown count, and
 * switching back to the full list starts short again rather than mounting 713 in one commit.
 */
export function useProgressiveMount(
  total: number,
  resetKey: string,
  first: number = FIRST_PAINT_CARDS,
  step: number = MOUNT_STEP,
): number {
  /** Rows mounted BEYOND the first paint — see `nextExtraCount` for why the state is the offset. */
  const [extra, setExtra] = useState(0);

  // A different list starts over: the first paint is short again.
  useEffect(() => {
    setExtra(0);
  }, [resetKey]);

  const shown = mountedCount(total, extra, first);

  useEffect(() => {
    if (!needsMoreRows(shown, total)) return;
    return onNextTask(() => setExtra((n) => nextExtraCount(n, total, first, step)));
  }, [shown, total, first, step]);

  return shown;
}
