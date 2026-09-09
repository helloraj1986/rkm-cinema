/**
 * Section heading (design spec §32): name on the left, optional "See all →"
 * door on the right. The arrow only appears when a destination exists.
 */
export function SectionHeader({
  title,
  onSeeAll,
  seeAllLabel = "See all",
}: {
  title: string;
  onSeeAll?: () => void;
  seeAllLabel?: string;
}) {
  return (
    <div className="mb-3.5 flex items-end justify-between gap-3">
      <h2 className="text-[20px] font-semibold tracking-[-0.02em] text-zinc-100">{title}</h2>
      {onSeeAll ? (
        <button
          type="button"
          onClick={onSeeAll}
          className="flex shrink-0 items-center gap-0.5 text-xs font-medium text-zinc-500 transition-colors hover:text-accent"
        >
          {seeAllLabel}
          <span aria-hidden="true" className="translate-y-[-1px]">
            →
          </span>
        </button>
      ) : null}
    </div>
  );
}
