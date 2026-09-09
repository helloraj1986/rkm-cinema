import { GlobalSearch } from "../../features/search/GlobalSearch";

/**
 * Top bar (design spec §7): 64px, visually disappears into the content, holds
 * the global search + avatar. Since GLOBAL_SEARCH_PLAN, the search IS the
 * command palette (library-first, state-aware actions, TMDB discovery only
 * when there is no strong owned match); `/` or ⌘K focuses it. The page's own
 * heading carries the "where you are" context, so the bar stays clean.
 */
export function Header() {
  return (
    <header className="sticky top-0 z-[var(--z-header)] flex h-16 shrink-0 items-center gap-4 border-b border-white/[.06] bg-canvas/85 px-4 backdrop-blur-xl sm:px-6 xl:px-8">
      {/* The one global search (command palette). */}
      <div className="max-w-[430px] flex-1">
        <GlobalSearch />
      </div>

      <div className="ml-auto shrink-0">
        <div
          className="grid h-9 w-9 place-items-center rounded-full bg-surface-3 text-xs font-bold text-accent ring-1 ring-white/10"
          title="RKM Cinema"
          role="img"
          aria-label="RKM Cinema"
        >
          R
        </div>
      </div>
    </header>
  );
}
