import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Icon, type IconName } from "../../components/ui/Icon";
import { useLibraryFolders } from "../../features/library/api";
import { libraryNavEntries, type LibraryNavEntry } from "../../features/library/lib";
import { librariesBehindMore, libraryTabsThatFit } from "./lib";
import { bridgeAvailable } from "../../features/offline/bridge";

/**
 * Mobile navigation (design spec §38/§59): the sidebar disappears below md and
 * a bottom bar takes over — Home · the profile's libraries · More.
 *
 * ⚠ **The tab count is MEASURED, not assumed (2026-09-14).** It used to be a hardcoded two
 * libraries with the rest behind More, and he reported the cost from his iPad: *"even though raj
 * profile have access to all three libraries..only two can be seen at the bottom...the ui needs a
 * bit of work to make sure all the libraries are accessible..specially for smaller devices like
 * ipad and ios"*. The arithmetic lives in `./lib.ts` (`libraryTabsThatFit`) because it is pure and
 * worth testing; this component only measures the bar and asks.
 *
 * ⚠ **The library list itself is no longer decided here.** `libraryNavEntries` is shared with the
 * sidebar, which used to apply a *different* rule — the sidebar kept an unresolved library and
 * warned about it, this bar dropped it. That divergence is what made a library vanish on a phone
 * while sitting there greyed out on the desktop. One rule, both surfaces.
 *
 * ⚠ The sheet is the **complete index**: every library that is not on the bar, every library the
 * server could not resolve (with its reason), then the destinations. It scrolls, because a library
 * that exists but cannot be reached is exactly the bug this file was fixed for.
 */
type Tab = { to: string; label: string; icon: IconName; end?: boolean };

/**
 * The sheet's destinations — NAVIGATION only.
 *
 * ⚠ Household and My password were listed here (2026-09-12, "it should be available on ui"). They
 * are ACCOUNT destinations, not places to browse, so they moved into the account menu behind the
 * header avatar — which is on screen at every breakpoint, so the phone reaches them too, with the
 * administrator gate applied in ONE place instead of two (his request, 2026-09-13: "consolidate the
 * ui elements"). A member's navigation therefore fires no `/api/admin/*` call at all.
 */
const MORE: { to: string; label: string; icon: IconName }[] = [
  { to: "/watchlist", label: "Watchlist", icon: "heart" },
  { to: "/discover", label: "Discover", icon: "compass" },
  { to: "/suggest", label: "Suggest", icon: "sparkles" },
  { to: "/settings", label: "Settings", icon: "settings" },
];

/** ⚠ The same rule as the sidebar's: shown only where it can work (B4, §4.5). */
const DOWNLOADS: Tab = { to: "/downloads", label: "Downloads", icon: "download" };

function tabCls(active: boolean) {
  // ⚠ `min-h-[var(--m-tap)]` — the 44px floor is a TOKEN, not a per-tab decision. A tab whose icon
  // or label changes must not silently drop below the size a thumb can reliably hit, and M0 already
  // decided what that size is (`--m-tap`, `styles/index.css`). The bar's own height follows.
  return `flex min-h-[var(--m-tap,44px)] min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-lg py-1.5 text-[10px] font-medium transition-colors ${
    active ? "text-accent" : "text-zinc-500 hover:text-zinc-200"
  }`;
}

const rowCls = (active: boolean) =>
  `flex min-h-[var(--m-tap,44px)] items-center gap-3 px-4 py-3 text-sm font-medium transition-colors ${
    active ? "bg-white/[.07] text-white" : "text-zinc-400 hover:bg-white/[.05] hover:text-zinc-100"
  }`;

const headingCls =
  "px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-[.12em] text-zinc-500";

function activeFor(pathname: string, to: string): boolean {
  return to === "/library/home"
    ? pathname === "/library/home" || pathname === "/"
    : pathname.startsWith(to);
}

export function MobileNav() {
  const location = useLocation();
  const { data } = useLibraryFolders();
  const [moreOpen, setMoreOpen] = useState(false);
  const sheetRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const [barWidth, setBarWidth] = useState(0);
  // ⚠ Downloads is offered only inside the app — see `DOWNLOADS` above, and the note in `Sidebar`
  // about asking the global directly rather than subscribing to the offline session.
  const destinations = bridgeAvailable() ? [...MORE, DOWNLOADS] : MORE;

  // Close the More sheet on navigation.
  useEffect(() => {
    setMoreOpen(false);
  }, [location.pathname]);

  // Esc closes the sheet; when it closes, focus returns to the More button.
  useEffect(() => {
    if (!moreOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setMoreOpen(false);
        buttonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [moreOpen]);

  /**
   * Measure the bar so the tab count is a fact rather than a guess.
   *
   * ⚠ `useLayoutEffect`, not `useEffect`: this runs AFTER the render that mounted the element but
   * BEFORE the browser paints it, so the measured width is applied in the same frame. With
   * `useEffect` the bar would paint once with zero tabs and then flick to three on every mount —
   * a visible flash, on the screen where the nav is the whole layout.
   *
   * ⚠ `ResizeObserver` covers the cases a `resize` listener does not: a rotation, a split-view
   * resize on iPad, and the bar's own max-width kicking in without the window changing at all.
   * The listener stays as the fallback for any engine without the observer.
   */
  useLayoutEffect(() => {
    const bar = barRef.current;
    if (!bar) return;
    const measure = () => setBarWidth(bar.getBoundingClientRect().width);
    measure();

    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(bar);
    return () => observer.disconnect();
  }, []);

  // ⚠ Every library the profile has. Loading or empty → Home + More only, never fabricated names.
  const entries = libraryNavEntries(data?.libraries ?? []);
  // ⚠ Only a RESOLVED library can be a tab: an unresolved one has no route to point at, and a tab
  // that leads nowhere is worse than a row that explains itself.
  const navigable = entries.filter((e) => e.to !== null);
  const unavailable = entries.filter((e) => e.to === null);

  const tabCount = libraryTabsThatFit(barWidth, navigable.length);
  const tabLibraries: LibraryNavEntry[] = navigable.slice(0, tabCount);
  const librariesBehind = librariesBehindMore(navigable, tabCount);
  const hiddenLibraryCount = librariesBehind.length + unavailable.length;

  const moreActive =
    destinations.some((m) => activeFor(location.pathname, m.to)) ||
    entries.some((e) => e.to !== null && activeFor(location.pathname, e.to));

  return (
    // ⚠ `lg:hidden` — the other half of the ONE decision (MOBILE_FIRST_UI_PLAN M1). The bar is the
    // navigation below Tailwind's `lg` (1024px), so the phone AND the tablet get it, and the sidebar
    // gets everything at or above it. The two classes must move together: a state where both are
    // visible is a styling bug that reads as a layout bug, and `tools/check_mobile_shell.py` asserts
    // it at every width.
    <nav
      aria-label="Mobile"
      className="fixed inset-x-0 bottom-0 z-[var(--z-drawer)] border-t border-white/[.07] bg-[#0B0C0F]/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
    >
      {moreOpen && (
        <div
          ref={sheetRef}
          aria-label="More destinations"
          className="absolute bottom-full left-0 right-0 mx-3 mb-2 max-h-[70vh] overflow-y-auto overscroll-contain rounded-2xl border border-white/10 bg-surface-3 shadow-modal"
        >
          {hiddenLibraryCount > 0 && (
            <>
              <p className={headingCls}>
                {hiddenLibraryCount === 1 ? "1 more library" : `${hiddenLibraryCount} more libraries`}
              </p>
              {librariesBehind.map((entry) => (
                <NavLink
                  key={entry.key}
                  to={entry.to as string}
                  title={entry.name}
                  className={({ isActive }) => rowCls(isActive)}
                >
                  <Icon name={entry.icon} size={18} />
                  <span className="truncate">{entry.name}</span>
                </NavLink>
              ))}
              {unavailable.map((entry) => (
                // ⚠ Rendered, not dropped — with the server's own reason. This is the half of the
                // bug the sidebar already got right, moved to the surface that did not.
                <div
                  key={entry.key}
                  title={entry.warning}
                  aria-label={`${entry.name} — unavailable`}
                  className="flex min-h-[var(--m-tap,44px)] cursor-not-allowed items-center gap-3 px-4 py-3 text-sm font-medium text-zinc-600 opacity-70"
                >
                  <Icon name={entry.icon} size={18} />
                  <span className="truncate">{entry.name}</span>
                  <span className="ml-auto h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                </div>
              ))}
            </>
          )}
          <p className={headingCls}>{hiddenLibraryCount > 0 ? "Go to" : "More"}</p>
          {destinations.map((m) => (
            <NavLink
              key={m.to}
              to={m.to}
              className={({ isActive }) => rowCls(isActive)}
            >
              <Icon name={m.icon} size={18} />
              {m.label}
            </NavLink>
          ))}
        </div>
      )}
      <div
        ref={barRef}
        /* ⚠ `h-[var(--m-nav-h)]`, NOT `h-16`: the row's height and the page's clearance must be the
           same number, and a token nobody reads is a comment. See `--m-nav-h` in styles/index.css and
           the derivation in AppShell. */
        className="mx-auto flex h-[var(--m-nav-h,64px)] max-w-lg items-center gap-1 px-3 sm:max-w-2xl"
      >
        <NavLink
          to="/library/home"
          end={tabLibraries.length === 0}
          className={() => tabCls(activeFor(location.pathname, "/library/home"))}
        >
          <Icon name="home" size={21} />
          <span className="truncate">Home</span>
        </NavLink>
        {tabLibraries.map((t) => (
          <NavLink
            key={t.key}
            to={t.to as string}
            title={t.name}
            className={() => tabCls(t.to !== null && activeFor(location.pathname, t.to))}
          >
            <Icon name={t.icon} size={21} />
            <span className="truncate">{t.name}</span>
          </NavLink>
        ))}
        <button
          ref={buttonRef}
          type="button"
          onClick={() => setMoreOpen((o) => !o)}
          aria-expanded={moreOpen}
          aria-label={moreOpen ? "Close more menu" : "More"}
          title={
            hiddenLibraryCount > 0
              ? `${hiddenLibraryCount} more ${hiddenLibraryCount === 1 ? "library" : "libraries"}`
              : undefined
          }
          className={`relative ${tabCls(moreActive)}`}
        >
          <Icon name="grid" size={21} />
          <span>More</span>
          {hiddenLibraryCount > 0 && (
            // ⚠ A signal, not decoration: he reported a library he could not find, and three words
            // in the bar gave no hint that anything was behind this button.
            <span
              aria-hidden="true"
              className="absolute right-[22%] top-0.5 h-1.5 w-1.5 rounded-full bg-accent"
            />
          )}
        </button>
      </div>
    </nav>
  );
}
