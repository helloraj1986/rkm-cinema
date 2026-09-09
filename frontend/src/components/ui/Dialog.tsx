import { useCallback, useEffect, useRef, type ReactNode } from "react";

/**
 * Premium modal dialog shell (design spec §51).
 *
 * Chrome: backdrop `rgba(0,0,0,.65)` + 8px blur; panel = the elevated surface
 * (#1B1E24), 1px white/8 border, 16px radius, deep layered modal shadow.
 * Behaviour (phase-9 a11y pass):
 *  - body scroll lock while open
 *  - Escape closes
 *  - backdrop mousedown closes (clicks inside the panel never do)
 *  - focus moves to the panel on open and RETURNS to the previously focused
 *    element on close
 *  - Tab is trapped inside the panel (no focus leaks into the app behind)
 * The caller renders the panel content (hero, close button, body) as children.
 */
export function Dialog({
  labelledBy,
  onClose,
  children,
  panelClassName = "",
}: {
  /** id of the element that names this dialog (screen-reader title). */
  labelledBy?: string;
  onClose: () => void;
  children: ReactNode;
  panelClassName?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    restoreRef.current = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    if (panel) panel.focus();

    // Focus trap: keep Tab inside the dialog (spec §37/§56).
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
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

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = prevOverflow;
      // Return focus to whatever opened the dialog (phase-9 a11y).
      restoreRef.current?.focus?.();
    };
  }, [onClose]);

  const onBackdropMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  return (
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center bg-black/65 p-4 backdrop-blur-[8px]"
      onMouseDown={onBackdropMouseDown}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className={`relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/[.08] bg-surface-2 shadow-modal outline-none ${panelClassName}`}
      >
        {children}
      </div>
    </div>
  );
}
