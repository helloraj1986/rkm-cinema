import { useState } from "react";
import { useLibraryItems } from "./api";
import {
  filterLibraryItems,
  libraryGenres,
  libraryItemsByType,
  libraryKindLabel,
  type LibraryKind,
  type LibrarySort,
} from "./lib";
import { MediaCard } from "./MediaCard";
import { LibraryToolbar } from "./LibraryToolbar";
import { useLibraryOutlet } from "./LibraryLayout";

/**
 * /library/movies + /library/shows — the Plex-style sidebar "folders". Each is
 * a type-filtered poster grid over the SHARED useLibraryItems cache (client-side
 * split via libraryItemsByType — no backend/contract change, no refetch).
 * Toolbar search/genre/sort (roadmap item 4) also runs client-side over that
 * same cache, so filtering is instant.
 */
export function LibraryFolderView({ kind }: { kind: LibraryKind }) {
  const items = useLibraryItems();
  const { quickPlay, openItem, toggleWatched } = useLibraryOutlet();

  const [query, setQuery] = useState("");
  const [genre, setGenre] = useState("");
  const [sort, setSort] = useState<LibrarySort>("recent");

  const label = libraryKindLabel(kind);
  const kindItems = libraryItemsByType(items.data?.items ?? [], kind);
  const genres = libraryGenres(kindItems);
  const list = filterLibraryItems(kindItems, { q: query, genre, sort });
  const filtered = query.trim() !== "" || genre !== "";
  const provider = items.data?.provider ?? null;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-lg font-semibold text-white">{label}</h2>
        <p className="text-xs text-zinc-500">
          {provider ? `${provider} · ${kindItems.length} title${kindItems.length === 1 ? "" : "s"}` : "No library backend connected."}
        </p>
      </div>

      {provider && kindItems.length > 0 && (
        <LibraryToolbar
          label={label}
          genres={genres}
          query={query}
          genre={genre}
          sort={sort}
          resultCount={list.length}
          totalCount={kindItems.length}
          onChange={({ q, genre: g, sort: s }) => {
            if (q !== undefined) setQuery(q);
            if (g !== undefined) setGenre(g);
            if (s !== undefined) setSort(s);
          }}
        />
      )}

      {items.isLoading ? (
        <p className="text-sm text-zinc-400">Loading library…</p>
      ) : kindItems.length === 0 ? (
        <p className="text-sm text-zinc-500">No {label.toLowerCase()} in the library yet.</p>
      ) : list.length === 0 ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-sm text-zinc-400">
            No {label.toLowerCase()} match{query.trim() ? ` “${query.trim()}”` : ""}
            {genre ? ` in ${genre}` : ""}.
          </p>
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setGenre("");
            }}
            className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap gap-3">
          {list.map((item) => (
            <MediaCard
              key={item.item_id}
              item={item}
              onQuickPlay={quickPlay}
              onOpenDetail={openItem}
              onToggleWatched={toggleWatched}
            />
          ))}
        </div>
      )}
      {filtered && list.length > 0 && (
        <p className="text-xs text-zinc-600">
          Showing {list.length} of {kindItems.length} —{" "}
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setGenre("");
            }}
            className="text-zinc-400 underline decoration-zinc-600 hover:text-zinc-200"
          >
            clear filters
          </button>
        </p>
      )}
    </div>
  );
}
