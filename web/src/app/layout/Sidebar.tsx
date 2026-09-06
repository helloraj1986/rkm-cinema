import { NavLink } from "react-router-dom";

const NAV: { to: string; label: string; end?: boolean }[] = [
  { to: "/settings", label: "Settings", end: true },
];

/** Plex-style library group — the sidebar "folders" (PLEX_VIEWS_PLAN Phase 0). */
const LIBRARY: { to: string; label: string; end?: boolean }[] = [
  { to: "/library/home", label: "Home", end: true },
  { to: "/library/movies", label: "Movies" },
  { to: "/library/shows", label: "TV Shows" },
];

const REST: { to: string; label: string }[] = [
  { to: "/discover", label: "Discover" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/search", label: "Search" },
  { to: "/suggest", label: "Suggest" },
];

function linkCls(isActive: boolean): string {
  return `rounded-md px-3 py-1.5 text-sm transition ${
    isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
  }`;
}

function FolderHeading({ children }: { children: string }) {
  return (
    <div className="px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-widest text-zinc-600">
      {children}
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="flex w-52 shrink-0 flex-col border-r border-zinc-800 p-4">
      <div className="mb-4 text-lg font-semibold tracking-tight text-white">RKM Cinema</div>
      <nav className="flex flex-col gap-0.5">
        {NAV.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => linkCls(isActive)}>
            {item.label}
          </NavLink>
        ))}

        <FolderHeading>Library</FolderHeading>
        {LIBRARY.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => linkCls(isActive)}>
            {item.label}
          </NavLink>
        ))}

        <FolderHeading>More</FolderHeading>
        {REST.map((item) => (
          <NavLink key={item.to} to={item.to} className={({ isActive }) => linkCls(isActive)}>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto border-t border-zinc-800 pt-3 text-[11px] leading-relaxed text-zinc-500">
        React shell (Phases 0–4). Ported views render here.
        <div className="mt-1.5">
          <a href="/legacy/" className="text-zinc-400 underline decoration-zinc-600 hover:text-zinc-200">
            Legacy app (/legacy)
          </a>
        </div>
      </div>
    </aside>
  );
}
