import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Icon, type IconName } from "../../components/ui/Icon";
import { useLibraryFolders } from "../../features/library/api";
import { libraryIconFor } from "../../features/library/lib";

/**
 * Mobile navigation (design spec §38/§59): the sidebar disappears below md and
 * a bottom bar takes over — Home · first two libraries · More. More opens a
 * compact sheet above the bar with the remaining libraries + destinations.
 * Blurred, safe-area aware, z-indexed below the player/toasts. Library entries
 * come from the folders API (MEDIA_LIBRARIES_PLAN) — never hardcoded names.
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

function tabCls(active: boolean) {
  return `flex min-w-0 flex-1 flex-col items-center gap-1 rounded-lg py-1.5 text-[10px] font-medium transition-colors ${
    active ? "text-accent" : "text-zinc-500 hover:text-zinc-200"
  }`;
}

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
  const destinations = MORE;

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

  // Live libraries only (resolved to a server folder) become tabs / sheet
  // entries. Loading or empty → Home + More only, never fabricated names.
  const liveLibs = (data?.libraries ?? []).filter((l) => l.ok && l.folder_id);
  const tabLibraries: Tab[] = liveLibs.slice(0, 2).map((l) => ({
    to: `/library/folder/${encodeURIComponent(l.folder_id as string)}`,
    label: l.name,
    icon: libraryIconFor(l.collection_type),
  }));
  const moreLibraries: Tab[] = liveLibs.slice(2).map((l) => ({
    to: `/library/folder/${encodeURIComponent(l.folder_id as string)}`,
    label: l.name,
    icon: libraryIconFor(l.collection_type),
  }));

  const moreActive =
    MORE.some((m) => activeFor(location.pathname, m.to)) ||
    moreLibraries.some((m) => activeFor(location.pathname, m.to));

  return (
    <nav
      aria-label="Mobile"
      className="fixed inset-x-0 bottom-0 z-[var(--z-drawer)] border-t border-white/[.07] bg-[#0B0C0F]/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden"
    >
      {moreOpen && (
        <div
          ref={sheetRef}
          role="menu"
          aria-label="More destinations"
          className="absolute bottom-full left-0 right-0 mx-3 mb-2 overflow-hidden rounded-2xl border border-white/10 bg-surface-3 shadow-modal"
        >
          {moreLibraries.map((m) => (
            <NavLink
              key={m.to}
              to={m.to}
              role="menuitem"
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 text-sm font-medium transition-colors ${
                  isActive ? "bg-white/[.07] text-white" : "text-zinc-400 hover:bg-white/[.05] hover:text-zinc-100"
                }`
              }
            >
              <Icon name={m.icon} size={18} />
              {m.label}
            </NavLink>
          ))}
          {destinations.map((m) => (
            <NavLink
              key={m.to}
              to={m.to}
              role="menuitem"
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 text-sm font-medium transition-colors ${
                  isActive ? "bg-white/[.07] text-white" : "text-zinc-400 hover:bg-white/[.05] hover:text-zinc-100"
                }`
              }
            >
              <Icon name={m.icon} size={18} />
              {m.label}
            </NavLink>
          ))}
        </div>
      )}
      <div className="mx-auto flex h-16 max-w-lg items-center gap-1 px-3">
        <NavLink
          to="/library/home"
          end={tabLibraries.length === 0}
          className={() => tabCls(activeFor(location.pathname, "/library/home"))}
        >
          <Icon name="home" size={21} />
          <span className="truncate">Home</span>
        </NavLink>
        {tabLibraries.map((t) => (
          <NavLink key={t.to} to={t.to} className={() => tabCls(activeFor(location.pathname, t.to))}>
            <Icon name={t.icon} size={21} />
            <span className="truncate">{t.label}</span>
          </NavLink>
        ))}
        <button
          ref={buttonRef}
          type="button"
          onClick={() => setMoreOpen((o) => !o)}
          aria-expanded={moreOpen}
          aria-haspopup="menu"
          aria-label={moreOpen ? "Close more menu" : "More"}
          className={tabCls(moreActive)}
        >
          <Icon name="grid" size={21} />
          <span>More</span>
        </button>
      </div>
    </nav>
  );
}
