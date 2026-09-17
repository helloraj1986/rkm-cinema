import { Link, useLocation, useNavigate } from "react-router-dom";

import { GlobalSearch } from "../../features/search/GlobalSearch";
import { SEARCH_PLACEHOLDER } from "../../features/search/lib";
import { Icon } from "../../components/ui/Icon";
import { useAuth } from "../../features/auth/AuthProvider";
import { AccountMenu } from "../../features/auth/AccountMenu";
import { useLayoutMode } from "../../layouts/LayoutMode";

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
  const mobile = useLayoutMode() === "mobile";
  const navigate = useNavigate();
  const { pathname } = useLocation();
  // ⚠ On the phone the search SCREEN owns the field, so the bar must not offer a second one on that
  // route — two fields on one screen, both of which look like THE search box, is a question ("which
  // one do I type in?") that a header should never ask.
  const onSearchScreen = pathname === "/search";

  return (
    // ⚠ `pt-[env(safe-area-inset-top)]` + `min-h-16` (NOT `h-16`): the bar's BACKGROUND has to
    // fill the status-bar band while its CONTENT sits below it — with a fixed height the padding
    // would eat the row instead of adding to it, and a notched phone would leave ~5px for the
    // search field. The inset is 0px on a desktop browser and in any web view without
    // `viewport-fit=cover` (see index.html), so this is inert everywhere except where it matters.
    <header className="sticky top-0 z-[var(--z-header)] flex min-h-16 shrink-0 items-center gap-4 border-b border-white/[.06] bg-canvas/85 px-4 pt-[env(safe-area-inset-top)] backdrop-blur-xl sm:px-6 xl:px-8">
      {/* The one global search. ⚠ On a PHONE this is a BUTTON, not the palette (M3): the palette is a
          keyboard-first dropdown (⌘K, ↑↓, Enter) whose result rows carry two text buttons each —
          it cannot be driven by a thumb, so the phone is sent to `/search`, where the same data
          (`useGlobalSearch`) and the same rules (`features/search/lib.ts`) are laid out as a screen.
          Desktop is untouched: it keeps the palette, with its shortcut and its dropdown. */}
      {mobile ? (
        onSearchScreen ? (
          <span className="min-w-0 flex-1" aria-hidden="true" />
        ) : (
          <button
            type="button"
            onClick={() => navigate("/search")}
            aria-label="Search"
            className="flex h-11 min-w-0 flex-1 items-center gap-2 rounded-[10px] border border-white/[.06] bg-surface-2 px-3 text-left text-[13px] text-zinc-500 transition active:bg-white/[.08]"
          >
            <Icon name="search" size={16} />
            <span className="truncate">{SEARCH_PLACEHOLDER}</span>
          </button>
        )
      ) : (
        <div className="max-w-[430px] min-w-0 flex-1">
          <GlobalSearch />
        </div>
      )}

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
