import { Link } from "react-router-dom";

import { GlobalSearch } from "../../features/search/GlobalSearch";
import { useAuth } from "../../features/auth/AuthProvider";
import { AccountMenu } from "../../features/auth/AccountMenu";

/**
 * Top bar (design spec §7): 64px, visually disappears into the content, holds the global
 * search + the account menu. Since GLOBAL_SEARCH_PLAN, the search IS the command palette
 * (library-first, state-aware actions, TMDB discovery only when there is no strong owned
 * match); `/` or ⌘K focuses it. The page's own heading carries the "where you are"
 * context, so the bar stays clean.
 *
 * AUTH_MULTIUSER_PLAN Phase 1 + PLEX_PROFILE_AUTH_PLAN Phase B: the right-hand slot shows the
 * PROFILE — who is watching — because that is the identity media runs as, and a shared device is
 * the whole point of the feature.
 *
 * 2026-09-13 (his request): that slot is now ONE control. It used to be four — a name, an avatar
 * that was only an image, a "Switch profile" link and a "Sign out" button — with the profile
 * destinations ALSO duplicated in the sidebar and the mobile sheet. They all live in
 * `AccountMenu` now, opened from the avatar, on every breakpoint.
 *
 * Signed out, the slot offers Sign in, and nothing else: enforcement is off, the app is fully
 * usable signed out, and the bar must not pretend otherwise.
 */
export function Header() {
  const { status, user } = useAuth();
  const signedIn = status === "signedIn" && !!user;

  return (
    <header className="sticky top-0 z-[var(--z-header)] flex h-16 shrink-0 items-center gap-4 border-b border-white/[.06] bg-canvas/85 px-4 backdrop-blur-xl sm:px-6 xl:px-8">
      {/* The one global search (command palette). */}
      <div className="max-w-[430px] min-w-0 flex-1">
        <GlobalSearch />
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-2">
        {signedIn ? (
          <AccountMenu variant="chip" />
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
