import { describe, expect, it } from "vitest";

import {
  DISMISS_FRACTION,
  DISMISS_VELOCITY,
  DRAG_ARM_PX,
  dragOffset,
  dragVelocity,
  shouldArmDrag,
  shouldDismiss,
} from "./sheetRules";

/**
 * The sheet's dismiss rules, falsified before they are trusted.
 *
 * ⚠ This file exists because the interesting failures are all SILENT. A sheet that dismisses on a
 * tap is annoying; a sheet that cannot be flicked away feels broken; a sheet that dismisses itself
 * mid-mount (height measured as 0) makes the feature unusable and looks like a data problem. None of
 * those throw, and none of them are visible in a diff — so they are pinned here.
 */
describe("dragOffset — the sheet moves DOWN, never up", () => {
  it("is the distance travelled downwards", () => {
    expect(dragOffset(100, 160)).toBe(60);
  });

  it("clamps an upward drag to 0", () => {
    expect(dragOffset(160, 100)).toBe(0);
    expect(dragOffset(160, 0)).toBe(0);
  });

  it("is 0 for no movement", () => {
    expect(dragOffset(120, 120)).toBe(0);
  });
});

describe("shouldDismiss — the three ways to mean it, and the ways to not", () => {
  const height = 600;

  it("dismisses a long drag past the fraction", () => {
    expect(DISMISS_FRACTION).toBe(0.3);
    expect(shouldDismiss({ dy: 180, elapsedMs: 900, height })).toBe(true); // exactly at the line
    expect(shouldDismiss({ dy: 400, elapsedMs: 1200, height })).toBe(true);
  });

  it("does NOT dismiss a long drag that stopped short, however slow", () => {
    expect(shouldDismiss({ dy: 179, elapsedMs: 3000, height })).toBe(false);
  });

  it("dismisses a short but FAST flick — the gesture a native sheet honours", () => {
    // 60px in 40ms = 1.5 px/ms, well past the threshold, and only 10% of the height.
    expect(dragVelocity(60, 40)).toBeGreaterThanOrEqual(DISMISS_VELOCITY);
    expect(shouldDismiss({ dy: 60, elapsedMs: 40, height })).toBe(true);
  });

  it("does NOT dismiss a short slow drag", () => {
    expect(shouldDismiss({ dy: 60, elapsedMs: 900, height })).toBe(false);
  });

  it("⚠ never dismisses an upward drag, at any speed", () => {
    expect(shouldDismiss({ dy: -400, elapsedMs: 5, height })).toBe(false);
    expect(shouldDismiss({ dy: 0, elapsedMs: 0, height })).toBe(false);
  });

  it("⚠ does NOT dismiss on an instant tap — velocity must not be divided by zero", () => {
    // The bug this pins: dy 0 / elapsedMs 0 is NaN (false, harmless), but a NON-zero dy with a zero
    // elapsed time would read as infinite velocity and dismiss on a tap that barely moved.
    expect(shouldDismiss({ dy: 5, elapsedMs: 0, height })).toBe(false);
    expect(dragVelocity(5, 0)).toBe(0);
    expect(Number.isFinite(dragVelocity(5, 0))).toBe(true);
  });

  it("⚠ does NOT dismiss a sheet whose height was measured as 0", () => {
    // A sheet mid-mount has no box yet. With `height = 0`, `dy >= height * 0.3` is true for ANY
    // positive dy — a sheet that closes itself as soon as it is touched.
    expect(shouldDismiss({ dy: 1, elapsedMs: 500, height: 0 })).toBe(false);
    expect(shouldDismiss({ dy: 300, elapsedMs: 500, height: 0 })).toBe(false);
    expect(shouldDismiss({ dy: 300, elapsedMs: 500, height: -1 })).toBe(false);
  });

  it("a flick and a drag that both clear a threshold agree", () => {
    // Both routes must be reachable and independent: the same dy, one fast and one slow.
    const fast = shouldDismiss({ dy: 200, elapsedMs: 100, height });
    const slow = shouldDismiss({ dy: 200, elapsedMs: 2000, height });
    expect(fast).toBe(true);
    expect(slow).toBe(true);
  });
});

/**
 * ⚠⚠ THE RULE THAT KEEPS EVERY BUTTON INSIDE A SHEET ALIVE — measured, not reasoned (2026-09-18).
 *
 * The panel's `pointerdown` handler sees gestures that START ON A BUTTON. Capturing the pointer
 * there retargets the gesture to the panel, so the browser dispatches `click` to the panel (the
 * nearest common ancestor of the captured down/up pair) and the button never hears it. In a real
 * browser that is a dead button: a real click on the suggest sheet's **Download** did nothing, while
 * `element.click()` from the console ran the handler exactly as written.
 *
 * So the gesture is armed — not captured — until it has travelled far enough to be a drag.
 */
describe("shouldArmDrag — a TAP must never be captured", () => {
  it("arms only once the gesture has clearly moved", () => {
    expect(DRAG_ARM_PX).toBeGreaterThan(0);
    expect(shouldArmDrag(DRAG_ARM_PX)).toBe(true);
    expect(shouldArmDrag(DRAG_ARM_PX + 40)).toBe(true);
  });

  it("does NOT arm for a tap, including the few px a thumb always drifts", () => {
    expect(shouldArmDrag(0)).toBe(false);
    expect(shouldArmDrag(1)).toBe(false);
    expect(shouldArmDrag(DRAG_ARM_PX - 1)).toBe(false);
  });

  it("does NOT arm an upward drag — that gesture dismisses nothing", () => {
    // `dragOffset` clamps upward movement to 0, so this is belt-and-braces: an upward gesture can
    // never arm, and so can never capture the pointer either.
    expect(shouldArmDrag(-50)).toBe(false);
  });

  it("⚠ the threshold is a fifth of the shortest tap target, not a gesture length", () => {
    // The rule that keeps these two numbers coupled: the arm threshold must be small enough that a
    // deliberate tap on a 44px control never crosses it, or this "fix" reintroduces the dead button
    // it exists to remove — intermittently, which is worse.
    expect(DRAG_ARM_PX).toBeLessThanOrEqual(44 / 5);
  });
});
