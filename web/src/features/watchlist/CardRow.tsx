import type { ReactNode } from "react";

/**
 * Horizontal card row with a heading (legacy `rowMarkup` parity): an optional
 * leading glyph, a "See all" door on the right, and an overflow-x scroll body.
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
      <div className="flex items-end justify-between pr-1">
        <h2 className="flex items-center gap-2 text-base font-semibold text-zinc-100">
          <span className="inline-block h-4 w-1 rounded-full bg-amber-400" aria-hidden="true" />
          {icon ? <span aria-hidden="true">{icon}</span> : null}
          {title}
          {count ? <span className="text-xs font-normal text-zinc-500">{count}</span> : null}
        </h2>
        {onSeeAll ? (
          <button
            type="button"
            onClick={onSeeAll}
            className="text-xs font-semibold text-zinc-400 hover:text-amber-300"
            aria-label={`See all in ${title}`}
          >
            See all ›
          </button>
        ) : null}
      </div>
      <div className="flex gap-3 overflow-x-auto pb-2" style={{ scrollbarWidth: "thin" }}>
        {children}
      </div>
    </section>
  );
}

/** Shared empty-state block (legacy emptyState parity copy). */
export function EmptyState({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="rounded-xl border border-dashed border-zinc-800 py-12 text-center">
      <div className="text-3xl" aria-hidden="true">
        🎞️
      </div>
      <h3 className="mt-2 font-semibold text-zinc-200">{title}</h3>
      <p className="mx-auto mt-1 max-w-md text-sm text-zinc-500">{sub}</p>
    </div>
  );
}
