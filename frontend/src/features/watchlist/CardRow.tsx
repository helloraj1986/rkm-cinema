import type { ReactNode } from "react";

/**
 * Horizontal card row with a heading (legacy `rowMarkup` parity): section-style
 * title + optional "See all" door on the right + overflow-x scroll body.
 * Used by Discover (watchlist rows) and any surface that shows a card strip.
 */
export function CardRow({
  title,
  icon,
  count,
  onSeeAll,
  children,
}: {
  title: string;
  icon?: string;
  count?: string;
  onSeeAll?: () => void;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2" data-testid="card-row">
      <div className="mb-1 flex items-end justify-between gap-3 pr-1">
        <h2 className="flex items-center gap-2 text-[20px] font-semibold tracking-[-0.02em] text-zinc-100">
          {icon ? <span aria-hidden="true">{icon}</span> : null}
          {title}
          {count ? <span className="text-xs font-normal text-zinc-500">{count}</span> : null}
        </h2>
        {onSeeAll ? (
          <button
            type="button"
            onClick={onSeeAll}
            className="flex shrink-0 items-center gap-1 text-xs font-medium text-zinc-500 transition-colors hover:text-accent"
            aria-label={`See all in ${title}`}
          >
            See all
            <span aria-hidden="true" className="translate-y-[-1px]">
              →
            </span>
          </button>
        ) : null}
      </div>
      <div className="no-scrollbar snap-rail flex gap-3.5 overflow-x-auto pb-1.5">{children}</div>
    </section>
  );
}

/** Shared empty-state block (legacy emptyState parity, NEW_UX §33 copy rules). */
export function EmptyState({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-white/[.08] px-6 py-14 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-2xl bg-surface-2 text-zinc-500">
        <span className="text-xl" aria-hidden="true">
          🎞️
        </span>
      </div>
      <h3 className="mt-1 font-semibold text-zinc-200">{title}</h3>
      <p className="mx-auto max-w-md text-sm leading-relaxed text-zinc-500">{sub}</p>
    </div>
  );
}
