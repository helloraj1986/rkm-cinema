import { NavLink } from "react-router-dom";

const NAV: { to: string; label: string }[] = [
  { to: "/settings", label: "Settings" },
  { to: "/library", label: "Library" },
  { to: "/discover", label: "Discover" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/search", label: "Search" },
  { to: "/suggest", label: "Suggest" },
];

export function Sidebar() {
  return (
    <aside className="flex w-52 shrink-0 flex-col gap-1 border-r border-zinc-800 p-4">
      <div className="mb-4 text-lg font-semibold tracking-tight text-white">RKM Cinema</div>
      <nav className="flex flex-col gap-1">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/settings"}
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 text-sm transition ${
                isActive
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
              }`
            }
          >
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