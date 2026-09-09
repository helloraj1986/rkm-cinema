import { useLocation } from "react-router-dom";
import { GlobalSearch } from "../../features/search/GlobalSearch";

/**
 * Top bar (design spec §7): 64px, visually disappears into the content, holds
 * the global search + avatar. Since GLOBAL_SEARCH_PLAN, the search IS the
 * command palette (library-first, state-aware actions, TMDB discovery only
 * when there is no strong owned match); `/` or ⌘K focuses it. The breadcrumb
 * shows only where it adds context — Home stays clean for the hero.
 */
const CONTEXT: { re: RegExp; label: string }[] = [
  { re: /^\/library\/movies/, label: "Movies" },
  { re: /^\/library\/shows/, label: "TV Shows" },
  { re: /^\/library\/item\//, label: "Title" },
  { re: /^\/watchlist/, label: "Watchlist" },
  { re: /^\/discover/, label: "Discover" },
  { re: /^\/suggest/, label: "Suggest" },
  { re: /^\/settings/, label: "Settings" },
];

function contextFor(pathname: string): string | null {
  if (/^\/library\/home/.test(pathname)) return null; // hero owns the Home chrome
  for (const c of CONTEXT) if (c.re.test(pathname)) return c.label;
  return null;
}

export function Header() {
  const location = useLocation();
  const crumb = contextFor(location.pathname);

  return (
    <header className="sticky top-0 z-[var(--z-header)] flex h-16 shrink-0 items-center gap-4 border-b border-white/[.06] bg-canvas/85 px-4 backdrop-blur-xl sm:px-6 xl:px-8">
      <div className="hidden w-36 shrink-0 truncate text-[13px] text-zinc-500 md:block" aria-hidden="true">
        {crumb ?? ""}
      </div>

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
