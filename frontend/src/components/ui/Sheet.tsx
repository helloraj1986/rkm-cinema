import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { DISMISS_MS, dragOffset, shouldArmDrag, shouldDismiss } from "./sheetRules";

/**
 * The bottom sheet — the mobile answer to a centred dialog (MOBILE_FIRST_UI_PLAN §5.3, brief §6).
 *
 * ⚠ **A centred modal on a phone is a desktop habit.** It puts the content and the dismiss target in
 * the middle of the screen, which is the one place a thumb holding a phone cannot comfortably reach.
 * A sheet comes from the bottom edge, is dismissed by dragging it back, and keeps everything the
 * person is deciding between inside the bottom third of the display.
 *
 * ⚠ **It is NOT `Dialog` with different styling, and the two are deliberately separate.** `Dialog`
 * is tuned for a mouse: backdrop-click and Escape are its dismissals, it centres, and its scroll lock
 * is `overflow: hidden`. A sheet's dismissal is a GESTURE (see `sheet.ts`), its lock must survive
 * iOS — where `overflow: hidden` on the body does not actually stop the page scrolling — and it is
 * anchored to an edge that has a safe-area inset.
 *
 * ⚠ **Portalled to `<body>`, for the reason `Dialog` records at length**: a `fixed` element is laid
 * out against its nearest containing block, and an ancestor with `backdrop-filter`, `filter`,
 * `transform` or `contain: paint` becomes one. The top bar is `backdrop-blur-xl`, so a sheet mounted
 * from inside it would resolve against a 64px-tall box. Rendered from anywhere, it lands on the
 * viewport.
 *
 * What it shares with `Dialog`, on purpose: the focus trap, focus restore, and the `canEscapeClose`
 * escape hatch (a sheet layered over the full-screen player must not swallow Escape). Those are one
 * set of behaviours, implemented in both files because the two have different geometry — not two
 * policies.
 *
 * ⚠⚠ **A pointerdown inside this panel must NOT capture the pointer** (fixed 2026-09-18, see
 * `shouldArmDrag`). Capturing on `pointerdown` retargeted the whole gesture to the panel, so the
 * browser dispatched `click` to the PANEL and every button inside every sheet was inert to a real tap
 * — invisible in the source, and invisible to `element.click()`. The gesture is armed on movement
 * instead.
 */

export function Sheet({
  labelledBy,
  onClose,
  children,
  panelClassName = "",
  canEscapeClose,
  /** Set for a two-line sheet that should not be draggable (a keyboard-only prompt, say). */
  dismissible = true,
}: {
  /** id of the element that names this sheet (screen-reader title). */
  labelledBy?: string;
  onClose: () => void;
  children: ReactNode;
  panelClassName?: string;
  /** When this returns false, Escape is left ALONE — not stopped, not consumed. */
  canEscapeClose?: () => boolean;
  dismissible?: boolean;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);
  const canEscapeRef = useRef(canEscapeClose);
  canEscapeRef.current = canEscapeClose;

  // The drag, in a ref: a pointermove must not re-render the whole sheet tree per pixel.
  const dragRef = useRef<{
    startY: number;
    startTime: number;
    pointerId: number;
    /** Set once the gesture has travelled far enough to be a drag rather than a tap. */
    armed: boolean;
    /** The element the gesture is captured on — the panel, once `armed`. */
    el: HTMLElement | null;
  } | null>(null);
  const [dy, setDy] = useState(0);
  const [leaving, setLeaving] = useState(false);
  /**
   * ⚠ A STATE, not `dragRef.current`, decides whether the transform animates. A ref is not a render
   * input: reading one during render happens to work here only because `setDy` re-renders, and the
   * first frame of a drag would animate the sheet from 0 to its tiny first offset — which reads as
   * the sheet lagging your finger by one frame, on every drag.
   */
  const [dragging, setDragging] = useState(false);

  /**
   * ⚠ THE SCROLL LOCK, and why it is not `overflow: hidden`.
   *
   * On iOS a body with `overflow: hidden` still scrolls under the finger: the page behind a sheet
   * moves while the sheet is open, and it comes to rest somewhere else. The fix is to take the body
   * out of flow at a NEGATIVE top offset equal to the current scroll, and to put the scroll back on
   * unmount — so the page reappears exactly where it was, not at the top.
   */
  useEffect(() => {
    restoreRef.current = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    if (panel) panel.focus();

    const scrollY = window.scrollY;
    const body = document.body;
    const previous = {
      position: body.style.position,
      top: body.style.top,
      width: body.style.width,
      overflow: body.style.overflow,
    };
    body.style.position = "fixed";
    body.style.top = `-${scrollY}px`;
    body.style.width = "100%";
    body.style.overflow = "hidden";

    // Escape and the focus trap — the same contract as `Dialog`. Escape runs in the CAPTURE phase
    // and stops propagation, so a sheet that merely ignored it would swallow the key for whoever is
    // underneath (see `canEscapeClose`).
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (canEscapeRef.current && !canEscapeRef.current()) return;
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panel) return;
      const focusables = panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey, true);

    return () => {
      window.removeEventListener("keydown", onKey, true);
      body.style.position = previous.position;
      body.style.top = previous.top;
      body.style.width = previous.width;
      body.style.overflow = previous.overflow;
      // ⚠ Put the page back where it was, AFTER the styles are restored — scrolling while the body
      // is still `fixed` does nothing.
      window.scrollTo(0, scrollY);
      restoreRef.current?.focus?.();
    };
  }, [onClose]);

  const finish = useCallback(() => {
    setLeaving(true);
    // ⚠ The delay matches the CSS transition (`DISMISS_MS`). Closing immediately would unmount the
    // panel mid-flight, so the sheet would vanish instead of sliding away — and the next sheet would
    // flash on screen at full height for one frame.
    window.setTimeout(onClose, DISMISS_MS);
  }, [onClose]);

  const onPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (!dismissible || leaving) return;
      // ⚠ Only a drag that STARTS at the top dismisses. If the sheet's own content is scrolled down,
      // a downward drag is the person scrolling back up — dismissing there would throw away the
      // gesture the content needs.
      const scroller = panelRef.current;
      if (scroller && scroller.scrollTop > 0) return;
      // ⚠⚠ THE POINTER IS NOT CAPTURED HERE, AND THAT IS THE FIX (2026-09-18).
      //
      // This handler is on the PANEL, so it sees every pointerdown inside the sheet — including on a
      // button. Capturing immediately retargets the whole gesture to the panel, and the browser then
      // dispatches `click` to the panel (the nearest common ancestor of a captured down/up pair)
      // instead of to the control under the finger. Every control inside every sheet became inert to
      // a real tap: measured in Chromium, a real click on the suggest sheet's Download did nothing
      // while `element.click()` from the console worked — the signature of a swallowed gesture, not
      // of a broken handler. Nothing about it is visible in the source, only in the browser.
      //
      // The gesture is ARMED instead, and captured only once it has travelled far enough to be a
      // drag (`shouldArmDrag`): a tap never arms, so its `click` reaches the button; a drag arms and
      // then keeps following the finger even when it leaves the panel.
      dragRef.current = {
        startY: e.clientY,
        startTime: e.timeStamp,
        pointerId: e.pointerId,
        armed: false,
        el: e.currentTarget,
      };
    },
    [dismissible, leaving],
  );

  const onPointerMove = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const offset = dragOffset(drag.startY, e.clientY);
    if (!drag.armed) {
      if (!shouldArmDrag(offset)) return;
      drag.armed = true;
      setDragging(true);
      // Capture NOW, mid-gesture (a live pointer can be captured at any time): from here the sheet
      // follows the finger past the panel's own edges.
      drag.el?.setPointerCapture?.(drag.pointerId);
    }
    setDy(offset);
  }, []);

  const onPointerUp = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      const drag = dragRef.current;
      dragRef.current = null;
      if (!drag) return;
      // ⚠ A gesture that never armed is a TAP. It must not dismiss, and it must not "snap back"
      // either — there is nothing to snap back from. Without this the fast-flick rule would read a
      // 5px jiggle inside a tap as a dismissal.
      if (!drag.armed) return;
      setDragging(false);
      const offset = dragOffset(drag.startY, e.clientY);
      const height = panelRef.current?.getBoundingClientRect().height ?? 0;
      if (shouldDismiss({ dy: offset, elapsedMs: e.timeStamp - drag.startTime, height })) {
        finish();
        return;
      }
      // Snap back — 0 is the anchored position, and the CSS transition does the rest.
      setDy(0);
    },
    [finish],
  );

  return createPortal(
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex items-end justify-center bg-black/65 backdrop-blur-[8px]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) finish();
      }}
      data-testid="sheet-scrim"
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        data-testid="sheet-panel"
        // ⚠ `m-sheet` carries `overscroll-behavior: contain` from `styles/index.css`, so scrolling
        // the sheet's own content cannot chain out into the page behind it.
        //
        // ⚠ The bottom padding is the safe-area inset, so the last row of a sheet is never under the
        // home indicator. `var(--m-sheet-max, 92dvh)` — a `dvh` cap, never `vh`: with `vh` the sheet
        // extends under a browser's toolbar and its last row becomes unreachable.
        className={`m-sheet relative flex max-h-[var(--m-sheet-max,92dvh)] w-full max-w-[560px] flex-col overflow-y-auto overscroll-contain rounded-t-[var(--m-sheet-radius,20px)] border-t border-white/[.08] bg-surface-3 pb-[var(--rkm-safe-bottom,env(safe-area-inset-bottom))] shadow-modal outline-none ${panelClassName}`}
        style={{
          transform: `translateY(${leaving ? "100%" : `${dy}px`})`,
          transition: dragging ? "none" : `transform ${DISMISS_MS}ms cubic-bezier(.32,.72,0,1)`,
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        {/* The drag handle. ⚠ `touch-action: none` ONLY here: on the panel it would stop the sheet's
            own content scrolling, which is the other half of what a sheet does. */}
        <div
          className="flex shrink-0 cursor-grab touch-none justify-center pt-2.5 pb-1 active:cursor-grabbing"
          aria-hidden="true"
        >
          <span className="h-1 w-10 rounded-full bg-white/25" />
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
