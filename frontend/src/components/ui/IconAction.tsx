import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

/**
 * A secondary action as an ICON TILE — the icon over a small label, in one tap-sized box.
 *
 * ⚠ **Why a tile, and why the label is kept.** A row of bare icons makes a person guess (is ↓ download
 * or delete? is ✓ watched or watched-list?), and a row of full-text buttons makes every secondary
 * action shout as loudly as the primary one. The tile is the pattern iOS itself uses on a detail
 * screen — one dominant button with TEXT for the verb that matters, then icons-with-labels for the
 * rest — which is the answer to his question ("should be icons or text": the primary gets both, a
 * secondary gets an icon and a word).
 *
 * ⚠ The box is 56px tall and 60px wide MINIMUM, over the 44px thumb floor: the phone's card actions
 * had to live at 28px, where this control is actually used, and a tile that misses the floor is a tile
 * a thumb misses.
 *
 * `ICON_ACTION_CLASS` is exported because a control that opens a MENU is not this component
 * (`PopupMenu` owns its own trigger) — it needs to wear the identical box, and two copies of a class
 * string is two boxes that drift.
 */
export const ICON_ACTION_CLASS =
  "inline-flex h-14 w-[68px] flex-col items-center justify-center gap-1 rounded-[10px] border border-white/10 bg-white/[.07] px-1 text-[10px] font-semibold leading-none text-zinc-200 transition hover:bg-white/[.12] disabled:opacity-50";

export function IconAction({
  icon,
  label,
  onClick,
  disabled = false,
  active = false,
  danger = false,
  title,
  children,
}: {
  /** The glyph. Omit it and pass `children` instead when the box shows something richer (a ring). */
  icon?: IconName;
  /** The word under the icon. Required — that is the whole point of the tile. */
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  /** On = the state is already true (watched), so the tile reads as a state, not an invitation. */
  active?: boolean;
  danger?: boolean;
  title?: string;
  children?: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title ?? label}
      aria-label={label}
      aria-pressed={active || undefined}
      className={`${ICON_ACTION_CLASS} ${
        active
          ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-300"
          : danger
            ? "text-red-400 hover:bg-red-500/10"
            : ""
      }`}
    >
      {children ?? (icon ? <Icon name={icon} size={19} /> : null)}
      <span className="max-w-16 truncate">{label}</span>
    </button>
  );
}
