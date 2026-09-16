import { describe, expect, it } from "vitest";
import defaultTheme from "tailwindcss/defaultTheme";
import {
  DESKTOP_MIN_PX,
  MOBILE_MAX_PX,
  MOBILE_MEDIA_QUERY,
  layoutModeFor,
} from "./LayoutMode";

/**
 * The layout switch's RULE, and — more importantly — the PAIR it belongs to.
 *
 * ⚠ The interesting half of this file is the third block. "Is the rule right?" is easy to get
 * right once. The thing that rots is that the boundary exists in TWO places that no compiler
 * connects: the media query in JavaScript (which decides which component tree renders) and the
 * Tailwind breakpoint in the CSS classes (which decides which chrome is visible). Move one and
 * the app renders a mobile tree with a desktop sidebar — a state that looks like a styling bug
 * and is actually a one-line mistake in the other language.
 *
 * ⚠ `tailwindcss/defaultTheme` really is read here, not a copy of the value written into this
 * file. A test that asserts "1023 + 1 === 1024" proves nothing; a test that asserts our
 * constant equals Tailwind's own resolved breakpoint fails the day somebody overrides `lg` in
 * `tailwind.config.js`.
 */

describe("layoutModeFor — the rule, with no React and no matchMedia", () => {
  it("maps the viewport question to a mode, both ways", () => {
    expect(layoutModeFor(true)).toBe("mobile");
    expect(layoutModeFor(false)).toBe("desktop");
  });

  it("is total: a boolean always answers, and never anything else", () => {
    for (const input of [true, false]) {
      expect(["mobile", "desktop"]).toContain(layoutModeFor(input));
    }
  });
});

describe("the boundary constant", () => {
  it("partitions the integer pixel line with no gap and no overlap", () => {
    expect(MOBILE_MAX_PX).toBe(1023);
    expect(DESKTOP_MIN_PX).toBe(MOBILE_MAX_PX + 1);
    expect(DESKTOP_MIN_PX).toBe(1024);
  });

  it("builds the media query from the constant, never retyping the number", () => {
    expect(MOBILE_MEDIA_QUERY).toBe(`(max-width: ${MOBILE_MAX_PX}px)`);
    expect(MOBILE_MEDIA_QUERY).toBe("(max-width: 1023px)");
    // ⚠ `max-width` at 1023 and `min-width` at 1024 are complements only because the two
    // numbers are adjacent. A query that used `max-width: 1024px` would put 1024 in BOTH modes,
    // and the CSS (`lg`, a `min-width`) would disagree with the JS about that one width.
    expect(MOBILE_MEDIA_QUERY).not.toContain(`${DESKTOP_MIN_PX}px`);
  });
});

describe("⚠ the JS boundary and the CSS boundary are the SAME line", () => {
  const screens = defaultTheme.screens as Record<string, string>;

  it("Tailwind's lg is exactly where the JS says desktop begins", () => {
    expect(screens.lg).toBe(`${DESKTOP_MIN_PX}px`);
  });

  it("and md is NOT it — md is 768px, which is the boundary this phase REPLACES", () => {
    // ⚠ Named explicitly because it is the mistake a reader will make: the app shipped with the
    // mobile/desktop boundary at Tailwind's `md` (768px) for years. `md` remains a perfectly
    // good breakpoint for SIZING inside a shell; it must never again decide WHICH shell exists.
    expect(screens.md).toBe("768px");
    expect(screens.md).not.toBe(`${DESKTOP_MIN_PX}px`);
    expect(Number.parseInt(screens.md, 10)).toBeLessThan(DESKTOP_MIN_PX);
  });

  it("sm/md/lg are strictly increasing, so a mode can never be skipped", () => {
    const order = ["sm", "md", "lg"]
      .map((k) => Number.parseInt(screens[k], 10))
      .filter((n) => Number.isFinite(n));
    expect(order.length).toBe(3);
    for (let i = 1; i < order.length; i += 1) {
      expect(order[i]).toBeGreaterThan(order[i - 1]);
    }
  });
});
