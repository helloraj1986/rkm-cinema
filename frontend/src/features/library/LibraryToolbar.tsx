import {
  LIBRARY_SORT_OPTIONS,
  type LibrarySort,
} from "./lib";
import { Icon } from "../../components/ui/Icon";

/**
 * Folder toolbar (roadmap item 4, NEW_UX §13–17): client-side search + genre
 * pill chips + sort for the Movies / TV Shows views. Presentational — state
 * lives in the folder view and everything runs over the shared library cache.
 * The count line is human copy ("6 movies"), never provider jargon.
 */
export function LibraryToolbar({
  label,
  genres,
  query,
  genre,
  sort,
  resultCount,
  totalCount,
  onChange,
}: {
  label: string;
  genres: string[];
  query: string;
  genre: string;
  sort: LibrarySort;
  resultCount: number;
  totalCount: number;
  onChange: (patch: { q?: string; genre?: string; sort?: LibrarySort }) => void;
}) {
  const pillOn = "bg-accent text-black hover:bg-accent-hover";
  const pillOff =
    "border border-white/[.08] bg-white/[.06] text-zinc-300 hover:bg-white/[.1] hover:text-white";
  const filtered = query.trim() !== "" || genre !== "";

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center gap-2.5">
        <div className="relative">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500">
            <Icon name="search" size={15} />
          </span>
          <input
            type="search"
            value={query}
            onChange={(e) => onChange({ q: e.target.value })}
            placeholder={`Search ${label.toLowerCase()}…`}
            aria-label={`Search ${label}`}
            className="w-64 rounded-[10px] border border-white/[.06] bg-surface-2 py-2 pl-9 pr-3 text-sm text-zinc-100 outline-none transition placeholder:text-zinc-500 focus:border-accent/50 focus:shadow-glow"
          />
        </div>

        <label className="flex items-center gap-2 text-xs text-zinc-500">
          <span className="sr-only">Sort by</span>
          <Icon name="clock" size={14} className="text-zinc-500" />
          <select
            value={sort}
            onChange={(e) => onChange({ sort: e.target.value as LibrarySort })}
            aria-label="Sort"
            className="rounded-[8px] border border-white/[.08] bg-surface-2 px-2.5 py-2 text-xs font-medium text-zinc-200 outline-none transition focus:border-accent/50"
          >
            {LIBRARY_SORT_OPTIONS.map((o) => (
              <option key={o.key} value={o.key}>{o.label}</option>
            ))}
          </select>
        </label>

        <span className="ml-auto text-xs font-medium text-zinc-500" aria-live="polite">
          {filtered
            ? `${resultCount} of ${totalCount} ${totalCount === 1 ? label.toLowerCase() : label === "TV Shows" ? "shows" : "movies"}`
            : `${totalCount} ${totalCount === 1 ? label.toLowerCase() : label === "TV Shows" ? "shows" : "movies"}`}
        </span>
      </div>

      {genres.length > 0 && (
        <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1 pb-0.5">
          <button
            type="button"
            onClick={() => onChange({ genre: "" })}
            aria-pressed={genre === ""}
            className={`shrink-0 rounded-full px-3.5 py-1.5 text-xs font-semibold transition ${genre === "" ? pillOn : pillOff}`}
          >
            All
          </button>
          {genres.map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => onChange({ genre: genre === g ? "" : g })}
              aria-pressed={genre === g}
              className={`shrink-0 rounded-full px-3.5 py-1.5 text-xs font-semibold transition ${genre === g ? pillOn : pillOff}`}
            >
              {g}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
