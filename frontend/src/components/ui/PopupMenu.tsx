import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon, type IconName } from "./Icon";

export interface PopupMenuItem {
  key: string;
  label: string;
  icon?: IconName;
  onSelect: () => void;
  /** Destructive actions are separated + tinted (§25: destructive separated). */
  danger?: boolean;
  disabled?: boolean;
}

/**
 * Lightweight popup menu for cards and detail rows (design spec §46 context
 * menus / §25 More actions). The trigger renders wherever the caller puts it
 * (poster hover rows, action bars); the open panel is PORTALLED to body so
 * overflow-hidden card art / rail clipping can never cut it off.
 *
 * Behaviour (phase-9 a11y): opens on click, closes on outside click, Esc,
 * scroll or resize; position is re-measured each open and clamps to the
 * viewport; each item is a real <button role="menuitem">.
 */
export function PopupMenu({
  label,
  items,
  align = "right",
  triggerClassName = "",
  triggerIcon = "more",
  header,
  triggerTestId,
  triggerLabel,
  children,
}: {
  /** aria-label for the trigger + the menu. */
  label: string;
  items: PopupMenuItem[];
  align?: "left" | "right";
  triggerClassName?: string;
  triggerIcon?: IconName;
  /**
   * Non-interactive content above the items — the account menu's "who is this" block. Kept out of
   * `items` on purpose: it is a description, not an action, so it must not be focusable or
   * selectable, and it must not look like something that navigates (2026-09-13).
   */
  header?: React.ReactNode;
  /**
   * Static test id for the trigger button (2026-09-13). The header's account affordance is a MENU
   * now, not a chip plus two buttons, so a probe needs a stable handle on it to open the menu.
   */
  triggerTestId?: string;
  /**
   * Accessible name for the TRIGGER, when it should differ from the menu's. The account menu needs
   * both: the trigger says WHO is watching ("Watching as Guest", the same wording the header chip
   * used, so a screen reader hears the identity first and `aria-haspopup` supplies the rest), while
   * the menu itself is named for what it is ("Account menu for Guest").
   */
  triggerLabel?: string;
  /** Custom trigger content; default is the ⋯ icon button. */
  children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const measure = useCallback(() => {
    const el = btnRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const menuW = 224;
    const menuH = Math.min(items.length * 40 + 12, 320);
    let left = align === "right" ? r.right - menuW : r.left;
    left = Math.max(8, Math.min(left, window.innerWidth - menuW - 8));
    let top = r.bottom + 6;
    if (top + menuH > window.innerHeight - 8) top = Math.max(8, r.top - menuH - 6);
    setPos({ top, left });
  }, [items.length, align]);

  useLayoutEffect(() => {
    if (open) measure();
  }, [open, measure]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
        btnRef.current?.focus();
      }
    };
    const onDown = (e: MouseEvent | TouchEvent) => {
      const t = e.target as Node;
      if (menuRef.current?.contains(t) || btnRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onScroll = () => setOpen(false);
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("touchstart", onDown);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("touchstart", onDown);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open]);

  const onSelect = (item: PopupMenuItem) => {
    setOpen(false);
    item.onSelect();
  };

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        aria-label={triggerLabel ?? label}
        aria-haspopup="menu"
        aria-expanded={open}
        data-testid={triggerTestId}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        className={triggerClassName}
      >
        {children ?? <Icon name={triggerIcon} size={16} />}
      </button>
      {open && pos
        ? createPortal(
            <div
              ref={menuRef}
              role="menu"
              aria-label={label}
              className="fixed z-[var(--z-popover)] w-56 overflow-hidden rounded-xl border border-white/10 bg-surface-3 p-1.5 shadow-modal"
              style={{ top: pos.top, left: pos.left }}
            >
              {header ? (
                <>
                  <div className="px-1 pb-1 pt-1.5">{header}</div>
                  <div className="mx-1 mb-1 h-px bg-white/[.07]" />
                </>
              ) : null}
              {items.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  role="menuitem"
                  disabled={item.disabled}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect(item);
                  }}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium transition disabled:opacity-50 ${
                    item.danger
                      ? "text-red-400 hover:bg-red-500/10"
                      : "text-zinc-200 hover:bg-white/[.07] hover:text-white"
                  }`}
                >
                  {item.icon ? <Icon name={item.icon} size={15} className="shrink-0 text-zinc-500" /> : null}
                  <span className="truncate">{item.label}</span>
                </button>
              ))}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
