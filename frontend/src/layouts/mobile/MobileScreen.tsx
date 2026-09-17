import type { ReactNode } from "react";

/**
 * The standard phone screen frame (`MOBILE_FIRST_UI_PLAN` §3.1) — a title, an optional thumb-zone
 * action row, and the scrolling body.
 *
 * ⚠ It deliberately does NOT add bottom padding for the tab bar. That clearance is derived once, in
 * `AppShell`, from `--m-nav-h` + `--rkm-safe-bottom` — the fix his phone forced on 2026-09-16 when a
 * flat `pb-24` sat the last row under the bar on a notched device. A screen that padded itself again
 * would add a second, disagreeing source for the same number.
 *
 * ⚠ **The action row STICKS** (his report, 2026-09-17: *"when I scroll up the filters button hides"*).
 * The recommended pattern for a filter surface on a phone is a bar that stays put — the alternative, a
 * floating button, sits on top of the posters AND just above the tab bar, which is two thumb targets
 * fighting for the same 20mm of screen; and hiding the control means a person has to scroll back to
 * the top to change their mind. It sticks to the top of the window (the scroller here), bleeds to the
 * shell's gutter, and takes a translucent canvas + blur so content reads under it rather than through
 * it. ⚠ `z-20` keeps it under the sheet (which portals above everything) and above the cards.
 */
export function MobileScreen({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  /** The thumb-zone controls (filters, view toggle). Sticks under the top bar while scrolling. */
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4">
      <header className="pt-1">
        <h1 className="text-[26px] font-bold leading-none tracking-[-0.02em] text-zinc-50">
          {title}
        </h1>
        {subtitle ? <p className="mt-1.5 text-[13px] text-zinc-500">{subtitle}</p> : null}
      </header>
      {actions ? (
        <div className="sticky top-0 z-20 -mx-4 flex items-center gap-2 border-b border-white/[.05] bg-canvas/85 px-4 py-2 backdrop-blur-xl">
          {actions}
        </div>
      ) : null}
      {children}
    </div>
  );
}

/**
 * A thumb-sized control for the action row — 44px tall, because `--m-tap` is the floor M1 set and a
 * phone control that misses that floor is a control a thumb misses.
 */
export function MobileAction({
  onClick,
  active = false,
  children,
  label,
}: {
  onClick: () => void;
  active?: boolean;
  children: ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={`inline-flex h-11 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-semibold transition ${
        active
          ? "bg-accent text-black"
          : "border border-white/[.08] bg-white/[.06] text-zinc-300 active:bg-white/[.12]"
      }`}
    >
      {children}
    </button>
  );
}
