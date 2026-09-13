import type { ButtonHTMLAttributes } from "react";

import { Icon, type IconName } from "./Icon";

/**
 * The app's ONE interactive-button geometry (2026-09-13).
 *
 * Why this exists: the global-search result row's primary ("Resume") and secondary ("Details")
 * buttons were two hand-rolled class strings, and they DRIFTED — the primary carried a fixed `h-8`
 * with no vertical padding, the secondary `py-1.5` with no height, so the pair rendered 32.00px next
 * to 30.50px with different padding while reading as one action group. Every size decision now lives
 * in `SIZE` below, shared by every variant: a variant may change FILL, TEXT COLOUR and WEIGHT (that
 * is hierarchy), never height, padding, radius or font-size.
 *
 * `tools/check_cta_alignment.py` measures the rendered result (the pair's rects in a real browser) —
 * this component is what makes the measurement hold across a restyle. `Button.test.ts` pins the one
 * shared token that would drift first.
 *
 * Sizing is deliberately compact (32px) because these buttons sit INSIDE a result row whose content
 * block (a 56px poster) they must not dominate; a taller control would push the row's own height.
 */

/** The geometry every variant shares. Nothing here may move into a variant. */
const SIZE =
  "inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-lg px-3 text-[11px] leading-none transition disabled:cursor-not-allowed disabled:opacity-60";

export type ButtonVariant = "primary" | "secondary" | "ghost";

const VARIANT: Record<ButtonVariant, string> = {
  /** The row's own action (Resume / Watch Now / Download / Add): filled accent. */
  primary: "bg-accent font-bold text-black hover:bg-accent-hover",
  /** The paired, quieter action (Details): outlined surface. */
  secondary: "border border-white/10 bg-white/[.06] font-semibold text-zinc-200 hover:bg-white/[.12]",
  /** An outlined action that is NOT paired with a filled one (discovery rows). */
  ghost: "border border-white/12 bg-white/[.06] font-bold text-zinc-100 hover:bg-white/[.12]",
};

/**
 * The class string for a variant, for the rare case where the geometry is needed outside a
 * `<button>` — e.g. the search rows' decorative "Browse" chip, which must line up with the
 * neighbouring "Details" button.
 */
export function buttonClass(variant: ButtonVariant, extra = ""): string {
  return [SIZE, VARIANT[variant], extra].filter(Boolean).join(" ");
}

export function Button({
  variant = "primary",
  icon,
  iconSize = 11,
  iconFilled = false,
  children,
  className = "",
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  /** Optional leading glyph, laid out inline and vertically centred with the label. */
  icon?: IconName;
  iconSize?: number;
  iconFilled?: boolean;
}) {
  return (
    <button type={type} className={buttonClass(variant, className)} {...rest}>
      {icon ? <Icon name={icon} size={iconSize} filled={iconFilled} /> : null}
      {children}
    </button>
  );
}
