import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";

/**
 * Top bar (design spec §7): 64px, visually disappears into the content, holds
 * the global search + avatar. Search is first-class: `/` or ⌘K focuses it and
 * typing lands on the /search results page (spec §36–37). The breadcrumb shows
 * only where it adds context — Home stays clean for the hero.
 */
const CONTEXT: { re: RegExp; label: string }[] = [
  { re: /^\/library\/movies/, label: "Movies" },
  { re: /^\/library\/shows/, label: "TV Shows" },
  { re: /^\/library\/item\//, label: "Title" },
  { re: /^\/watchlist/, label: "Watchlist" },
  { re: /^\/discover/, label: "Discover" },
  { re: /^\/search/, label: "Search" },
  { re: /^\/suggest/, label: "Suggest" },
  { re: /^\/settings/, label: "Settings" },
];

const SEARCH_DEBOUNCE = 400;

function contextFor(pathname: string): string | null {
  if (/^\/library\/home/.test(pathname)) return null; // hero owns the Home chrome
  for (const c of CONTEXT) if (c.re.test(pathname)) return c.label;
  return null;
}

export function Header() {
  const navigate = useNavigate();
  const location = useLocation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");

  const qInUrl = () =>
    location.pathname === "/search" ? new URLSearchParams(location.search).get("q") ?? "" : "";

  // Keep the box in sync when landing on /search from elsewhere (Back etc.).
  useEffect(() => {
    const q = qInUrl();
    if (q !== text) setText(q);
    if (location.pathname !== "/search" && text !== "") setText("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, location.search]);

  // Typing navigates to the results page after a short idle (keeps the box
  // responsive; /search debounces its own live query).
  useEffect(() => {
    if (!text.trim() || qInUrl() === text) return;
    const t = setTimeout(() => {
      navigate(`/search?q=${encodeURIComponent(text.trim())}`);
    }, SEARCH_DEBOUNCE);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const focusSearch = () => inputRef.current?.focus();

  // Global shortcuts (spec §37): ⌘K / Ctrl+K or `/` focus search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing =
        target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        focusSearch();
      } else if (e.key === "/" && !typing) {
        e.preventDefault();
        focusSearch();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const crumb = contextFor(location.pathname);

  return (
    <header className="sticky top-0 z-[var(--z-header)] flex h-16 shrink-0 items-center gap-4 border-b border-white/[.06] bg-canvas/85 px-4 backdrop-blur-xl sm:px-6 xl:px-8">
      <div className="hidden w-36 shrink-0 truncate text-[13px] text-zinc-500 md:block" aria-hidden="true">
        {crumb ?? ""}
      </div>

      <div className="relative min-w-0 max-w-[430px] flex-1">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500">
          <Icon name="search" size={16} />
        </span>
        <input
          ref={inputRef}
          type="search"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Search your library…"
          autoComplete="off"
          aria-label="Search your library"
          className="w-full rounded-[10px] border border-white/[.06] bg-surface-2 py-2 pl-9 pr-14 text-[13px] text-zinc-100 outline-none transition placeholder:text-zinc-500 focus:border-accent/50 focus:shadow-glow"
        />
        <kbd className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 rounded border border-white/10 bg-white/[.04] px-1.5 py-0.5 text-[10.5px] font-medium text-zinc-500 sm:block">
          ⌘K
        </kbd>
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
