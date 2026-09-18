/**
 * A title with the query's matched span emphasised (SEARCH_IMPROVEMENT_PLAN
 * Phase 4).
 *
 * ⚠ **One component, two surfaces.** The desktop palette (`features/search/`)
 * and the phone's search screen (`layouts/mobile/`) render the same rows, and
 * highlighting is exactly the kind of rule that quietly forks when each screen
 * writes its own `<mark>`. `layouts/mobile/**` is barred from `fetch` and from
 * re-derived rules (`layouts/imports.test.ts`), so the phone imports this rather
 * than restating it.
 *
 * ⚠ **The span comes from the server** (`row.ranges`, [start, end) into the
 * title it was computed against) — the client does not search the title again.
 * For a fuzzy match like "the dark knght" → *The Dark Knight* there is no
 * substring to find, so a client-side search would silently highlight nothing
 * while claiming the row matched.
 *
 * Renders a `<span>` so it can sit inside the truncated title element either
 * screen already uses; the caller passes that element's own class.
 */
import { highlightParts } from "./lib";

export function HighlightedTitle({
  text,
  ranges,
  className,
  highlightClassName = "bg-transparent text-accent",
}: {
  text: string;
  /** `[start, end)` offsets into `text`, from the API row. Absent → nothing highlighted. */
  ranges?: readonly (readonly number[])[] | null;
  className?: string;
  highlightClassName?: string;
}) {
  const parts = highlightParts(text, ranges);
  if (parts.length === 0) return null;
  return (
    <span className={className} data-testid="hl-title">
      {parts.map((part, i) =>
        part.hit ? (
          // `<mark>` because that is what it means; its UA background is cleared so
          // the theme decides the emphasis, and a screen reader still announces it.
          <mark key={i} className={highlightClassName}>
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </span>
  );
}
