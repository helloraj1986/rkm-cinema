import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useLibraryItems, useScanLibrary } from "./api";
import {
  filterLibraryItems,
  libraryFilterFromParams,
  libraryFilterToParams,
  libraryGenres,
  libraryItemsByType,
  libraryKindLabel,
  type LibraryFilter,
  type LibraryKind,
  type LibrarySort,
} from "./lib";
import { MediaCard } from "./MediaCard";
import { LibraryToolbar } from "./LibraryToolbar";
import { useLibraryOutlet } from "./LibraryLayout";
import { toast } from "../watchlist/toast";
import { Icon } from "../../components/ui/Icon";

/** How long after the user stops typing before the URL q= param updates. */
const QUERY_DEBOUNCE_MS = 220;

/**
 * /library/movies + /library/shows — the premium library folders (NEW_UX spec
 * §11–§19): a clean page header with human counts, a search + genre-pill +
 * sort toolbar, and a responsive auto-fill poster grid. Everything runs
 * client-side over the shared useLibraryItems cache — no extra fetches.
 *
 * URL state (§60/§63): q / genre / sort live in the URL
 * (/library/movies?q=…&genre=…&sort=…), so filters survive refresh, Back and
 * deep links, and the browser's scroll restoration returns to the same place.
 */
export function LibraryFolderView({ kind }: { kind: LibraryKind }) {
  const items = useLibraryItems();
  const scan = useScanLibrary();
  const { quickPlay, openItem, toggleWatched } = useLibraryOutlet();
  const [searchParams, setSearchParams] = useSearchParams();

  const parsed = libraryFilterFromParams(searchParams);
  // The search box mirrors the URL q (typing is instant); the URL is the
  // source of truth after the debounce.
  const [query, setQuery] = useState(parsed.q);
  const queryRef = useRef(parsed.q);
  queryRef.current = parsed.q;

  // External navigation (Back, deep link, header search) re-syncs the box.
  useEffect(() => {
    setQuery(parsed.q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parsed.q]);

  // Debounced write of the typed query back to the URL (replace — typing a
  // query shouldn't create a history entry per keystroke).
  useEffect(() => {
    const raw = query.trim();
    if (raw === queryRef.current) return;
    const t = window.setTimeout(() => {
      setSearchParams(libraryFilterToParams({ ...parsed, q: raw }), { replace: true });
    }, QUERY_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const apply = (patch: LibraryFilter) => {
    // Always carry the current box text — a genre/sort click while the query
    // is still inside its debounce must not drop it from the URL.
    const next = { ...parsed, q: query.trim(), ...patch };
    setSearchParams(libraryFilterToParams(next), { replace: true });
  };

  const label = libraryKindLabel(kind);
  const noun = label === "TV Shows" ? "show" : "movie";
  const kindItems = libraryItemsByType(items.data?.items ?? [], kind);
  const genres = libraryGenres(kindItems);
  const list = filterLibraryItems(kindItems, { q: query, genre: parsed.genre, sort: parsed.sort });
  const filtered = query.trim() !== "" || parsed.genre !== "";
  const provider = items.data?.provider ?? null;

  const nounLabel = (n: number) => `${n} ${noun}${n === 1 ? "" : "s"}`;

  const runScan = () => {
    scan.mutate(undefined, {
      onSuccess: () => toast("Library scan complete", "New titles will appear as they are discovered."),
      onError: () => toast("Scan failed", "Could not reach the scan job — check the backend.", "err"),
    });
  };

  const clear = () => {
    setQuery("");
    apply({ q: "", genre: "" });
  };

  return (
    <div className="flex flex-col gap-6 pb-8">
      {/* Page header (spec §12): title + human count, never provider jargon. */}
      <div className="pt-2">
        <h1 className="text-[32px] font-bold leading-none tracking-[-0.02em] text-zinc-50">
          {label}
        </h1>
        {provider ? (
          <p className="mt-2 text-[13px] text-zinc-500">{nounLabel(kindItems.length)}</p>
        ) : (
          <p className="mt-2 text-[13px] text-zinc-500">No media server connected</p>
        )}
      </div>

      {provider && kindItems.length > 0 && (
        <LibraryToolbar
          label={label}
          genres={genres}
          query={query}
          genre={parsed.genre}
          sort={parsed.sort}
          resultCount={list.length}
          totalCount={kindItems.length}
          onChange={({ q, genre: g, sort: s }) => {
            if (q !== undefined) setQuery(q);
            const patch: LibraryFilter = {};
            if (g !== undefined) patch.genre = g;
            if (s !== undefined) patch.sort = s as LibrarySort;
            if (g !== undefined || s !== undefined) apply(patch);
          }}
        />
      )}

      {items.isLoading ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-x-4 gap-y-7" aria-hidden="true">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="skeleton aspect-[2/3] rounded-[10px]" />
          ))}
        </div>
      ) : !provider ? (
        <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-white/[.08] py-16 text-center">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-surface-2 text-zinc-500">
            <Icon name={kind === "movies" ? "film" : "tv"} size={22} />
          </div>
          <div className="max-w-sm">
            <h2 className="font-semibold text-zinc-200">No media server connected</h2>
            <p className="mt-1 text-sm leading-relaxed text-zinc-500">
              Connect Jellyfin, Plex or Emby in the repo .env, then redeploy the stack.
            </p>
          </div>
        </div>
      ) : kindItems.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-white/[.08] py-16 text-center">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-surface-2 text-zinc-500">
            <Icon name={kind === "movies" ? "film" : "tv"} size={22} />
          </div>
          <div className="max-w-sm">
            <h2 className="font-semibold text-zinc-200">
              {label === "TV Shows" ? "No shows yet" : "No movies yet"}
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-zinc-500">
              Your media folders don't have any {label.toLowerCase()} yet — scan your library after adding some.
            </p>
          </div>
          <button
            type="button"
            onClick={runScan}
            disabled={scan.isPending}
            className="inline-flex items-center gap-2 rounded-[10px] bg-accent px-4 py-2 text-sm font-bold text-black transition hover:bg-accent-hover disabled:opacity-60"
          >
            <Icon name="scan" size={15} />
            {scan.isPending ? "Scanning…" : "Scan Library"}
          </button>
        </div>
      ) : list.length === 0 ? (
        <div className="flex flex-col items-start gap-3 rounded-2xl border border-dashed border-white/[.08] px-8 py-14">
          <h2 className="font-semibold text-zinc-200">
            No {label.toLowerCase()} match{query.trim() ? ` “${query.trim()}”` : ""}
            {parsed.genre ? ` in ${parsed.genre}` : ""}
          </h2>
          <p className="text-sm text-zinc-500">Try another title or genre.</p>
          <button
            type="button"
            onClick={clear}
            className="mt-1 rounded-[10px] border border-white/10 bg-white/[.06] px-4 py-2 text-sm font-semibold text-zinc-200 transition hover:bg-white/[.1]"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(158px,1fr))] gap-x-4 gap-y-7">
            {list.map((item) => (
              <MediaCard
                key={item.item_id}
                item={item}
                fluid
                onQuickPlay={quickPlay}
                onOpenDetail={openItem}
                onToggleWatched={toggleWatched}
              />
            ))}
          </div>
          {filtered && (
            <p className="text-xs text-zinc-500">
              Showing {nounLabel(list.length)} of {nounLabel(kindItems.length)} —{" "}
              <button
                type="button"
                onClick={clear}
                className="text-zinc-400 underline decoration-zinc-600 transition hover:text-accent"
              >
                clear filters
              </button>
            </p>
          )}
        </>
      )}
    </div>
  );
}
