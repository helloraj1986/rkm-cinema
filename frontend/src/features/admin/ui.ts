/**
 * The Household screen's own class strings (HOUSEHOLD_UX_PLAN.md Phase 1, 2026-09-13).
 *
 * One home for the look, because the page and its modals are two files now: the mockup's visual
 * hierarchy (bold header → secondary summary → tertiary cards → quietest in-card actions) is
 * carried by these, and a second copy of a button in the other file is exactly how the two layers
 * start disagreeing. Tailwind strings only — no behaviour.
 */

/** The page's one filled accent button (the mockup's "Add member"). */
export const PRIMARY_BUTTON =
  "inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-2 text-sm font-semibold text-canvas transition hover:brightness-[1.06] disabled:opacity-60";

/**
 * The filled in-card button, used for ONE case only: a member with no password yet.
 *
 * The mockup singles that row out on purpose — an account that anyone can sign into is the one
 * thing on this page worth a raised voice, so "Set password" is the only in-card action that gets
 * the accent rather than a quiet hover.
 */
export const PRIMARY_SMALL_BUTTON =
  "rounded-lg bg-accent px-2.5 py-1.5 text-xs font-semibold text-canvas transition hover:brightness-[1.06] disabled:opacity-60";

/** A modal's quiet counterpart — the mockup's `.btn.subtle`, and its Cancel. */
export const SUBTLE_BUTTON =
  "rounded-lg border border-white/[.10] px-3.5 py-2 text-sm font-medium text-zinc-300 transition hover:bg-white/[.06] hover:text-zinc-100 disabled:opacity-50";

/** The quietest layer: an in-card action. */
export const CARD_BUTTON =
  "rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-400 transition hover:bg-white/[.06] hover:text-zinc-100 disabled:opacity-50";

/** Removing an account is the one irreversible action on the page. */
export const DANGER_BUTTON =
  "rounded-lg bg-red-500/90 px-3.5 py-2 text-sm font-semibold text-white transition disabled:opacity-50";

export const INPUT =
  "w-full rounded-lg border border-white/10 bg-canvas px-3 py-2 text-sm outline-none focus:border-accent";

export const FIELD_LABEL = "block text-xs font-medium text-zinc-300";

/** The card surface the summary row and every profile card sits on. */
export const CARD_SURFACE = "rounded-xl border border-white/[.06] bg-surface-2/70";

/** The small uppercase heading above a group ("MEMBERS"). */
export const GROUP_LABEL = "text-[11px] font-semibold uppercase tracking-[.12em] text-zinc-500";
