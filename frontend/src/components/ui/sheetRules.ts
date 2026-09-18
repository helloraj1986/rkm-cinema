/**
 * The bottom sheet's RULES — pure, so they can be tested without a browser (MOBILE_FIRST_UI_PLAN
 * §5.3, brief §6 "sheets, not dialogs").
 *
 * ⚠ Only the DECISIONS live here. The gesture plumbing (pointer capture, transforms, the lock) is in
 * `Sheet.tsx`, and it is plumbing: what a person can get wrong is not "how do I capture a pointer",
 * it is "how far is far enough to mean dismissed", and that is the question this file answers.
 */

/** How much of the sheet's height a drag must cover before releasing dismisses it. */
export const DISMISS_FRACTION = 0.3;

/** …or how fast it must be travelling, in px/ms. A flick dismisses without travelling far. */
export const DISMISS_VELOCITY = 0.5;

/** How long the exit transform takes. ⚠ Must match the CSS transition, or `onClose` fires while the
 *  sheet is still visibly on screen and the next frame flashes it back. */
export const DISMISS_MS = 180;

/**
 * The drag offset to render.
 *
 * ⚠ Clamped at 0: a sheet may be dragged DOWN and never up. An upward drag that moved the panel
 * would separate it from the bottom edge it is anchored to, which reads as a rendering bug.
 */
export function dragOffset(startY: number, currentY: number): number {
  return Math.max(0, currentY - startY);
}

/**
 * Did that release mean "close"?
 *
 * Three ways to be sure, and all three are needed:
 *   · a long drag past `DISMISS_FRACTION` of the height — the deliberate gesture;
 *   · a fast flick past `DISMISS_VELOCITY`, however short — the impatient one, and the one that
 *     makes a sheet feel native. ⚠ Without it, a quick flick down that covers 20% of the height
 *     snaps back, which on a phone reads as the app ignoring you;
 *   · and NEITHER fires for an upward drag, because `dragOffset` clamped it to 0 and a zero offset
 *     cannot clear either threshold.
 *
 * ⚠ `height <= 0` is not a dismissal. A sheet measured at zero height (mid-mount, or hidden) would
 * otherwise satisfy `dy >= 0` for a fraction of 0 — a sheet that closes itself on first touch.
 */
export function shouldDismiss(input: { dy: number; elapsedMs: number; height: number }): boolean {
  const { dy, elapsedMs, height } = input;
  if (!(height > 0)) return false;
  if (dy <= 0) return false;
  if (dy >= height * DISMISS_FRACTION) return true;
  // ⚠ Guard the division: an instant release (`elapsedMs` 0) would otherwise read as infinite
  // velocity and dismiss on a tap.
  if (elapsedMs <= 0) return false;
  return dy / elapsedMs >= DISMISS_VELOCITY;
}

/**
 * Velocity in px/ms — exported so a failure can say the number rather than just "not dismissed".
 */
export function dragVelocity(dy: number, elapsedMs: number): number {
  if (elapsedMs <= 0) return 0;
  return dy / elapsedMs;
}

/**
 * How far a finger must travel before a pointerdown becomes a DRAG rather than a tap.
 *
 * ⚠⚠ **This threshold exists because capturing the pointer on `pointerdown` breaks every control
 * inside the sheet** (measured 2026-09-18). The panel's handler sees the pointerdown that started on
 * a button; capturing it there retargets the gesture to the panel, so the browser dispatches the
 * `click` to the PANEL — the nearest common ancestor of the captured down/up pair — and the button
 * never hears it. On a real browser that is indistinguishable from a dead button: a real click did
 * nothing while `element.click()` from the console fired the handler exactly as written.
 *
 * So the gesture is armed, not captured, until it is clearly a drag. 8px is deliberately below the
 * ~10px a thumb moves during an ordinary tap on a 44px target, and far below the distance that
 * distinguishes a drag: anything smaller than this is not a gesture anybody meant.
 */
export const DRAG_ARM_PX = 8;

/** Is this much travel a DRAG (and so capturable), or still a TAP? */
export function shouldArmDrag(dy: number): boolean {
  return dy >= DRAG_ARM_PX;
}
