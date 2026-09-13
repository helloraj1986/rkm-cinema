/**
 * Pure helpers for the app shell's layout — the mobile bottom bar's arithmetic, kept out of the
 * component so it is unit-testable without a DOM (vitest node env), like every other `lib.ts`.
 *
 * ⚠ Why this exists (his report, 2026-09-14, on the iPad):
 *
 *     "even though raj profile have access to all three libraries..only two can be seen at the
 *      bottom...the ui needs a bit of work to make sure all the libraries are accessible..
 *      specially for smaller devices like ipad and ios"
 *
 * The bar showed a **hardcoded two** libraries, with the rest behind More. Two is a guess about
 * screen width, and it is wrong on every device: an iPad mini portrait has room for four or five
 * tabs, a phone has room for three or four, and only a narrow phone has room for two. So the count
 * is now **measured** — the bar's own width decides, never the device name, because a device name
 * is a worse guess than the pixels in front of us (the same reason the sidebar is CSS-driven).
 *
 * ⚠ The count is also **capped**. Past four library tabs the bar stops being a bar and becomes a row
 * of truncated words, and More is the better home for the tail: a tab is for what he opens daily,
 * the sheet is the complete index.
 */

/**
 * px a single tab needs to show its 21px icon and a readable label at the bar's 10px type size.
 *
 * ⚠ Measured against the longest library names in use — "Movies Kids" and "TV Shows" — not chosen
 * for the average, because a tab that is too narrow to read is the same as no tab at all.
 */
export const MIN_TAB_WIDTH = 66;

/** Home and More are always on the bar; libraries fill the space between them. */
export const FIXED_TAB_COUNT = 2;

/** The bar's own horizontal padding (`px-3` in the component) — 12px each side. */
export const BAR_PADDING_X = 24;

/** The gap between tabs (`gap-1`). */
export const TAB_GAP = 4;

/** Beyond this many library tabs the tail belongs in the sheet, however wide the screen is. */
export const MAX_LIBRARY_TABS = 4;

/**
 * How many library tabs fit in `width` px of bar, alongside Home and More.
 *
 * ⚠ **Monotonic by construction**: every extra tab needs the same minimum width *and* shrinks the
 * width left for all the others, so the first count that fails is the last one worth testing — hence
 * the `break` rather than a scan of every possibility.
 *
 * @param width        the bar's inner content width in CSS px (0 before measurement → 0 tabs).
 * @param libraryCount how many libraries the profile actually has.
 * @param maxLibraries the cap, overridable so a test can state it explicitly.
 */
export function libraryTabsThatFit(
  width: number,
  libraryCount: number,
  maxLibraries: number = MAX_LIBRARY_TABS,
): number {
  if (!Number.isFinite(width) || width <= 0) return 0;
  const ceiling = Math.max(0, Math.min(libraryCount, maxLibraries));

  let fitting = 0;
  for (let libraries = 0; libraries <= ceiling; libraries += 1) {
    const tabs = libraries + FIXED_TAB_COUNT;
    const usable = width - BAR_PADDING_X - TAB_GAP * (tabs - 1);
    if (usable / tabs >= MIN_TAB_WIDTH) fitting = libraries;
    else break;
  }
  return fitting;
}

/** The list of libraries that did NOT fit on the bar — these are what More must account for. */
export function librariesBehindMore<T>(entries: T[], tabsThatFit: number): T[] {
  return entries.slice(Math.max(0, Math.min(tabsThatFit, entries.length)));
}
