import {
  LIBRARY_SORT_OPTIONS,
  type LibrarySort,
  type LibraryViewMode,
} from "./lib";
import { Icon } from "../../components/ui/Icon";

/**
 * Folder toolbar (roadmap item 4, NEW_UX §13–17): client-side search + genre
 * pill chips + sort + view-mode toggle for the Movies / TV Shows views.
 * Presentational — state lives in the folder view (URL-backed) and everything
 * runs over the shared library cache. The count line is human copy
 * ("6 movies"), never provider jargon.
 */
export function LibraryToolbar({
  label,
  genres,
  genre,
  sort,
  view,
  resultCount,
  totalCount,
  countNoun,
  onChange,
  onViewChange,
}: {
  label: string;
  genres: string[];
  genre: string;
  sort: LibrarySort;
  view: LibraryViewMode;
  resultCount: number;
  totalCount: number;
  /** Plural count noun (folder view passes "titles"); defaults to type nouns. */
  countNoun?: string;
  onChange: (patch: { genre?: string; sort?: LibrarySort }) => void;
  onViewChange: (view: LibraryViewMode) => void;
}) {
  const pillOn = "bg-accent text-black hover:bg-accent-hover";
  const pillOff =
    "border border-white/[.08] bg-white/[.06] text-zinc-300 hover:bg-white/[.1] hover:text-white";
  const filtered = genre !== "";
  const noun = countNoun ?? (label === "TV Shows" ? "shows" : "movies");

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center gap-2.5">
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

        {/* View mode (§17): poster grid / compact list. */}
        <div role="group" aria-label="View mode" className="flex items-center overflow-hidden rounded-[8px] border border-white/[.08] bg-surface-2">
          <button
            type="button"
            onClick={() => onViewChange("grid")}
            aria-pressed={view === "grid"}
            title="Grid view"
            className={`grid h-8 w-8 place-items-center transition ${view === "grid" ? "bg-white/[.1] text-white" : "text-zinc-500 hover:text-zinc-200"}`}
          >
            <Icon name="grid" size={15} />
          </button>
          <button
            type="button"
            onClick={() => onViewChange("compact")}
            aria-pressed={view === "compact"}
            title="Compact list"
            className={`grid h-8 w-8 place-items-center transition ${view === "compact" ? "bg-white/[.1] text-white" : "text-zinc-500 hover:text-zinc-200"}`}
          >
            <Icon name="list" size={15} />
          </button>
        </div>

        <span className="ml-auto text-xs font-medium text-zinc-500" aria-live="polite">
          {filtered
            ? `${resultCount} of ${totalCount} ${totalCount === 1 ? label.toLowerCase() : noun}`
            : `${totalCount} ${totalCount === 1 ? label.toLowerCase() : noun}`}
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
