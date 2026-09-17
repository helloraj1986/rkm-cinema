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
 * ⚠ `sticky` on the action row rather than `fixed`: a fixed row would need its own clearance token,
 * and it would sit over the content it is filtering.
 */
export function MobileScreen({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  /** The thumb-zone controls (filters, view toggle). Sits under the title, above the content. */
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
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
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
