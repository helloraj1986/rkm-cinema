import { describe, expect, it } from "vitest";
import {
  BAR_PADDING_X,
  FIXED_TAB_COUNT,
  MAX_LIBRARY_TABS,
  MIN_TAB_WIDTH,
  TAB_GAP,
  librariesBehindMore,
  libraryTabsThatFit,
} from "./lib";

/**
 * The widths that actually matter — the devices he holds, plus the bar's own ceilings.
 *
 * ⚠ The bar is only the navigation below `md` (768px): above that the sidebar takes over. So the
 * viewports worth stating are a phone and an iPad mini in portrait, and the measured width is the
 * INNER bar's — min(viewport, its max width) — which is what the component hands in.
 */
const IPAD_MINI_INNER = 744; // 744px viewport, capped by the bar's own max width
const BAR_MAX_WIDE = 672; // `sm:max-w-2xl` — what an iPad-sized viewport gets
const BAR_MAX_PHONE = 512; // `max-w-lg` — what a phone gets
const IPHONE_INNER = 390;
const NARROW_INNER = 320; // the smallest phone still in use

describe("libraryTabsThatFit", () => {
  it("shows ALL THREE of his libraries on the iPad he reported the problem from", () => {
    // The report: Raj's profile has three libraries, and the bar showed two of them.
    expect(libraryTabsThatFit(BAR_MAX_WIDE, 3)).toBe(3);
    expect(libraryTabsThatFit(IPAD_MINI_INNER, 3)).toBe(3);
  });

  it("shows all three on a phone as well — the third tab is what More used to hold", () => {
    expect(libraryTabsThatFit(IPHONE_INNER, 3)).toBe(3);
  });

  it("still prefers More over an unreadable tab on the narrowest screen", () => {
    // 320px cannot hold Home + 3 libraries + More at a legible width, so the third goes behind
    // More — which is why More has to be a complete index rather than a dumping ground.
    expect(libraryTabsThatFit(NARROW_INNER, 3)).toBe(2);
  });

  it("never exceeds the cap, however wide the screen gets", () => {
    expect(libraryTabsThatFit(1400, 9)).toBe(MAX_LIBRARY_TABS);
    expect(libraryTabsThatFit(1400, 9, 2)).toBe(2); // the cap is stated, not assumed
  });

  it("never invents libraries that are not there", () => {
    expect(libraryTabsThatFit(1400, 0)).toBe(0);
    expect(libraryTabsThatFit(1400, 2)).toBe(2);
  });

  it("returns nothing before the bar has been measured", () => {
    // The component measures in a layout effect, so the first value it can pass is 0. Rendering
    // tabs at an unknown width is how a bar overflows on the device it was never tried on.
    expect(libraryTabsThatFit(0, 3)).toBe(0);
    expect(libraryTabsThatFit(-1, 3)).toBe(0);
    expect(libraryTabsThatFit(Number.NaN, 3)).toBe(0);
  });

  it("HOLDS THE INVARIANT: every tab it promises is at least MIN_TAB_WIDTH wide", () => {
    // The property the whole module exists for — swept, because a single hand-picked width proves
    // nothing about the widths nobody thought of.
    for (let width = 240; width <= 1400; width += 1) {
      for (let count = 0; count <= 8; count += 1) {
        const fitting = libraryTabsThatFit(width, count);
        expect(fitting).toBeLessThanOrEqual(Math.min(count, MAX_LIBRARY_TABS));

        const tabs = fitting + FIXED_TAB_COUNT;
        const usable = width - BAR_PADDING_X - TAB_GAP * (tabs - 1);
        expect(usable / tabs).toBeGreaterThanOrEqual(MIN_TAB_WIDTH);
      }
    }
  });

  it("is monotonic in width: a wider bar never shows fewer libraries", () => {
    for (let count = 1; count <= 6; count += 1) {
      let previous = 0;
      for (let width = 240; width <= 1400; width += 7) {
        const fitting = libraryTabsThatFit(width, count);
        expect(fitting).toBeGreaterThanOrEqual(previous);
        previous = fitting;
      }
    }
  });
});

describe("librariesBehindMore", () => {
  const libs = ["Movies", "Movies Kids", "TV Shows", "Documentaries"];

  it("hands every library that did not fit to More — in order", () => {
    expect(librariesBehindMore(libs, 2)).toEqual(["TV Shows", "Documentaries"]);
  });

  it("hands over nothing when they all fit", () => {
    expect(librariesBehindMore(libs, 4)).toEqual([]);
  });

  it("never slices backwards from a stale or oversized fit count", () => {
    // Defensive on purpose: the count comes from a measurement, and a measurement can be stale for
    // one frame after a rotation. `slice(-3)` would silently return the LAST three libraries —
    // a library that disappears while a wrong one stays is worse than either.
    expect(librariesBehindMore(libs, 99)).toEqual([]);
    expect(librariesBehindMore(libs, -3)).toEqual(libs);
    expect(librariesBehindMore(libs, 0)).toEqual(libs);
  });
});
