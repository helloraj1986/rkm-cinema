import { NavLink } from "react-router-dom";
import { Icon, type IconName } from "../../components/ui/Icon";
import { useLibraryFolders } from "../../features/library/api";
import { libraryIconFor } from "../../features/library/lib";
import { useAuth } from "../../features/auth/AuthProvider";
import { AccountMenu } from "../../features/auth/AccountMenu";

/**
 * Premium sidebar (design spec §5–6): brand lockup, grouped navigation,
 * selected-pill active state with the tiny yellow indicator, and a CSS-driven
 * collapse — full 240px on desktop (≥xl), icon rail on tablet (md–xl), hidden
 * below md where the MobileNav bottom bar takes over.
 *
 * Libraries group (MEDIA_LIBRARIES_PLAN): populated from /api/library/folders —
 * the configured MEDIA_LIBRARY_N_NAME values when any are set, otherwise the
 * media server's own folder names. Names come from the API, never hardcoded;
 * a configured library that failed to resolve shows a warning glyph instead of
 * a dead link.
 */
type NavItem = { to: string; label: string; icon: IconName; end?: boolean };

const BROWSE: { title: string; items: NavItem[] } = {
  title: "Browse",
  items: [{ to: "/library/home", label: "Home", icon: "home", end: true }],
};

const COLLECTIONS: { title: string; items: NavItem[] } = {
  title: "Collections",
  items: [
    { to: "/watchlist", label: "Watchlist", icon: "heart" },
    { to: "/discover", label: "Discover", icon: "compass" },
    { to: "/suggest", label: "Suggest", icon: "sparkles" },
  ],
};

function BrandLockup() {
  return (
    <div
      title="RKM Cinema"
      className="flex items-center gap-3 pb-6 pt-2 md:justify-center md:px-0 xl:justify-start xl:px-3"
    >
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-[10px] bg-gradient-to-br from-surface-2 to-surface-3 text-accent ring-1 ring-white/10">
        <Icon name="play" size={15} filled />
      </div>
      <div className="hidden min-w-0 leading-none xl:block">
        <div className="truncate text-[15px] font-extrabold tracking-tight text-zinc-100">RKM</div>
        <div className="text-[9.5px] font-bold uppercase tracking-[0.22em] text-accent">Cinema</div>
      </div>
    </div>
  );
}

function GroupHeading({ children }: { children: string }) {
  return (
    <div className="hidden px-3 pb-1.5 pt-5 text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-500 xl:block">
      {children}
    </div>
  );
}

function linkCls(isActive: boolean): string {
  const state = isActive
    ? "bg-white/[.08] text-zinc-50 ring-1 ring-white/[.04] hover:bg-white/[.09] hover:text-white"
    : "text-zinc-400 hover:bg-white/[.06] hover:text-zinc-100";
  return `relative flex items-center gap-3 rounded-[10px] py-2.5 text-[13.5px] font-medium transition-colors duration-150 md:justify-center md:px-0 xl:justify-start xl:px-3 ${state}`;
}

function NavIndicator({ active }: { active: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`absolute left-0 hidden h-[18px] w-[3px] rounded-r-full bg-accent transition-opacity xl:block ${
        active ? "opacity-100" : "opacity-0"
      }`}
    />
  );
}

function GroupNav({ title, items }: { title: string; items: NavItem[] }) {
  return (
    <div>
      <GroupHeading>{title}</GroupHeading>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          title={item.label}
          className={({ isActive }) => linkCls(isActive)}
        >
          {({ isActive }) => (
            <>
              <NavIndicator active={isActive} />
              <Icon name={item.icon} size={19} className="shrink-0" />
              <span className="hidden truncate xl:inline">{item.label}</span>
            </>
          )}
        </NavLink>
      ))}
    </div>
  );
}

export function Sidebar() {
  const { data } = useLibraryFolders();
  const libraries = data?.libraries ?? [];
  const { status, user } = useAuth();
  const signedIn = status === "signedIn" && !!user;

  return (
    <aside className="sticky top-0 hidden h-dvh w-[76px] shrink-0 flex-col self-start border-r border-white/[.06] bg-[#0B0C0F] py-5 md:flex xl:w-60">
      <BrandLockup />

      <nav aria-label="Primary" className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2.5">
        <GroupNav title={BROWSE.title} items={BROWSE.items} />

        {libraries.length > 0 && (
          <div>
            <GroupHeading>Libraries</GroupHeading>
            {libraries.map((lib) => {
              const icon = libraryIconFor(lib.collection_type);
              const href = lib.ok && lib.folder_id
                ? `/library/folder/${encodeURIComponent(lib.folder_id)}`
                : null;
              if (!href) {
                return (
                  <div
                    key={lib.name}
                    title={lib.warning || "Library unavailable"}
                    aria-label={`${lib.name} — unavailable`}
                    className="flex cursor-not-allowed items-center gap-3 rounded-[10px] py-2.5 pl-3 text-[13.5px] font-medium text-zinc-600 opacity-70"
                  >
                    <Icon name={icon} size={19} className="shrink-0" />
                    <span className="hidden truncate xl:inline">{lib.name}</span>
                    <span className="ml-auto hidden h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500 xl:block" />
                  </div>
                );
              }
              return (
                <NavLink
                  key={href}
                  to={href}
                  title={lib.name}
                  className={({ isActive }) => linkCls(isActive)}
                >
                  {({ isActive }) => (
                    <>
                      <NavIndicator active={isActive} />
                      <Icon name={icon} size={19} className="shrink-0" />
                      <span className="hidden truncate xl:inline">{lib.name}</span>
                    </>
                  )}
                </NavLink>
              );
            })}
          </div>
        )}

        <GroupNav title={COLLECTIONS.title} items={COLLECTIONS.items} />
      </nav>

      <div className="px-2.5 pt-2">
        <NavLink to="/settings" end title="Settings" className={({ isActive }) => linkCls(isActive)}>
          {({ isActive }) => (
            <>
              <NavIndicator active={isActive} />
              <Icon name="settings" size={19} className="shrink-0" />
              <span className="hidden truncate xl:inline">Settings</span>
            </>
          )}
        </NavLink>
        {/* Household (administrators only) and My password used to sit HERE. They are account
            destinations, not navigation, so they now live in the account menu behind the avatar —
            one place, both surfaces, one gate (his request, 2026-09-13: "consolidate the ui
            elements"). The server still refuses those routes; `mayManageHousehold` decides only
            what the app OFFERS. */}
      </div>

      <div className="mt-3 border-t border-white/[.06] px-2.5 pt-3">
        {signedIn ? (
          // The account conventionally lives at the bottom of the sidebar on desktop. This card
          // used to be decorative — it named you and offered nothing; now it IS the account menu
          // trigger (`AccountMenu variant="wide"`), sharing every rule with the header avatar.
          <AccountMenu variant="wide" />
        ) : (
          <div className="hidden items-center gap-2.5 px-3 py-2 xl:flex">
            <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-3 text-[11px] font-bold text-accent ring-1 ring-white/10">
              R
            </div>
            <div className="min-w-0 text-xs">
              {/* AUTH_MULTIUSER_PLAN Phase 1: this card used to be a hardcoded name. With real
                  sessions that would be a lie the moment somebody else signs in — so it says
                  plainly when there is no session. */}
              <div className="truncate font-semibold text-zinc-200">RKM Cinema</div>
              <div className="truncate text-[10.5px] text-zinc-500">Not signed in</div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
