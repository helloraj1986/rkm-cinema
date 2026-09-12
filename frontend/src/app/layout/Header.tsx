import { Link } from "react-router-dom";

import { GlobalSearch } from "../../features/search/GlobalSearch";
import { useAuth } from "../../features/auth/AuthProvider";
import { displayName, initials } from "../../features/auth/lib";

/**
 * Top bar (design spec §7): 64px, visually disappears into the content, holds the global
 * search + the session chip. Since GLOBAL_SEARCH_PLAN, the search IS the command palette
 * (library-first, state-aware actions, TMDB discovery only when there is no strong owned
 * match); `/` or ⌘K focuses it. The page's own heading carries the "where you are"
 * context, so the bar stays clean.
 *
 * AUTH_MULTIUSER_PLAN Phase 1: the avatar is now the SIGNED-IN user, with Sign out beside
 * it; signed out, the slot offers Sign in. Both states are visible because Phase 1
 * enforces nothing — the app is fully usable signed out, and the bar must not pretend
 * otherwise.
 */
export function Header() {
  const { status, user, signOut } = useAuth();
  const name = displayName(user);

  return (
    <header className="sticky top-0 z-[var(--z-header)] flex h-16 shrink-0 items-center gap-4 border-b border-white/[.06] bg-canvas/85 px-4 backdrop-blur-xl sm:px-6 xl:px-8">
      {/* The one global search (command palette). */}
      <div className="max-w-[430px] min-w-0 flex-1">
        <GlobalSearch />
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-2">
        {status === "signedIn" && user ? (
          <>
            <span className="hidden max-w-[10rem] truncate text-xs font-medium text-zinc-200 sm:inline">
              {name}
            </span>
            <span
              className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-surface-3 text-xs font-bold text-accent ring-1 ring-white/10"
              title={name}
              role="img"
              aria-label={`Signed in as ${name}`}
            >
              {initials(name)}
            </span>
            <button
              type="button"
              onClick={() => void signOut()}
              className="rounded-full border border-white/10 px-3 py-1.5 text-xs font-medium text-zinc-300 transition hover:border-accent hover:text-accent"
            >
              Sign out
            </button>
          </>
        ) : (
          <Link
            to="/login"
            className="rounded-full border border-white/10 px-3 py-1.5 text-xs font-medium text-zinc-200 transition hover:border-accent hover:text-accent"
          >
            Sign in
          </Link>
        )}
      </div>
    </header>
  );
}
