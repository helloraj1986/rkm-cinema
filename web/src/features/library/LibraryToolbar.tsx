import {
  LIBRARY_SORT_OPTIONS,
  type LibrarySort,
} from "./lib";

/**
 * Folder toolbar (roadmap item 4): client-side search + genre chips + sort for
 * the Movies / TV Shows views. Presentational — state lives in the folder view
 * and everything runs over the shared library cache (no fetches).
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
  const inputCls =
    "w-64 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-amber-400/70 focus:outline-none";
  const chipBase =
    "rounded-full px-3 py-1 text-xs font-medium ring-1 transition";
  const chipOn =
    "bg-amber-400 text-black ring-amber-300 hover:bg-amber-300";
  const chipOff =
    "bg-zinc-900 text-zinc-300 ring-zinc-700 hover:bg-zinc-800 hover:text-white";
  const filtered = query.trim() !== "" || genre !== "";

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={query}
          onChange={(e) => onChange({ q: e.target.value })}
          placeholder={`Search ${label.toLowerCase()}…`}
          aria-label={`Search ${label}`}
          className={inputCls}
        />
        <label className="flex items-center gap-1.5 text-xs text-zinc-400">
          Sort
          <select
            value={sort}
            onChange={(e) => onChange({ sort: e.target.value as LibrarySort })}
            aria-label="Sort"
            className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200"
          >
            {LIBRARY_SORT_OPTIONS.map((o) => (
              <option key={o.key} value={o.key}>{o.label}</option>
            ))}
          </select>
        </label>
        <span className="ml-auto text-xs text-zinc-500" aria-live="polite">
          {filtered
            ? `${resultCount} of ${totalCount} title${totalCount === 1 ? "" : "s"}`
            : `${totalCount} title${totalCount === 1 ? "" : "s"}`}
        </span>
      </div>

      {genres.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => onChange({ genre: "" })}
            aria-pressed={genre === ""}
            className={`${chipBase} ${genre === "" ? chipOn : chipOff}`}
          >
            All
          </button>
          {genres.map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => onChange({ genre: genre === g ? "" : g })}
              aria-pressed={genre === g}
              className={`${chipBase} ${genre === g ? chipOn : chipOff}`}
            >
              {g}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
