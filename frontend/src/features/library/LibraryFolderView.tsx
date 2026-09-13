import { useParams, useSearchParams } from "react-router-dom";
import { useFolderItems, useLibraryFolders, useScanLibrary } from "./api";
import {
  filterLibraryItems,
  folderCountLabel,
  libraryByFolderId,
  libraryFilterFromParams,
  libraryFilterToParams,
  libraryGenres,
  libraryIconFor,
  libraryViewFromParams,
  scanFailure,
  type LibrarySort,
  type LibraryViewMode,
} from "./lib";
import { MediaCard } from "./MediaCard";
import { MediaListRow } from "./MediaListRow";
import { LibraryToolbar } from "./LibraryToolbar";
import { useLibraryOutlet } from "./LibraryLayout";
import { toast } from "../watchlist/toast";
import { Icon } from "../../components/ui/Icon";
import { mayScanLibrary } from "../auth/lib";
import { useCurrentProfile } from "../auth/useCurrentProfile";

/**
 * /library/folder/:folderId — ONE configured library folder (MEDIA_LIBRARIES_PLAN
 * §11–§19): a clean page header with the library's own name + human count, the
 * genre-pill + sort toolbar, and a responsive auto-fill poster grid. Everything
 * is folder-scoped server-side (GET /api/library/folders/{id}/items) — the old
 * client-side type split is gone, so arbitrary configured libraries (Movies,
 * My Anime, 4K Movies…) each show exactly their own folder's media.
 *
 * URL state (§60/§63): genre / sort live in the URL so filters survive
 * refresh, Back and deep links. Free-text search is deliberately NOT here —
 * global search is the one search surface, in the top bar (GLOBAL_SEARCH_PLAN).
 */
export function LibraryFolderView() {
  const { folderId = "" } = useParams();
  const foldersQ = useLibraryFolders();
  const items = useFolderItems(folderId || null);
  const scan = useScanLibrary();
  const { quickPlay, openItem, toggleWatched } = useLibraryOutlet();
  // Phase E: administrators-only on the server, and strict in every world — so the control is only
  // OFFERED to an administrator (a member, or a signed-out visitor, is not one).
  const mayScan = mayScanLibrary(useCurrentProfile()?.is_admin);
  const [searchParams, setSearchParams] = useSearchParams();

  const parsed = libraryFilterFromParams(searchParams);
  const view = libraryViewFromParams(searchParams);

  const apply = (patch: { genre?: string; sort?: LibrarySort }) => {
    setSearchParams(
      libraryFilterToParams({ genre: parsed.genre, sort: parsed.sort, ...patch }),
      { replace: true },
    );
  };

  const setView = (next: LibraryViewMode) => {
    const p = libraryFilterToParams({ genre: parsed.genre, sort: parsed.sort });
    if (next !== "grid") p.set("view", next);
    setSearchParams(p, { replace: true });
  };

  // The sidebar library that owns this folder (configured name when set, else
  // the server folder name) — heading + warning state come from HERE, never
  // from a hardcoded label.
  const libraries = foldersQ.data?.libraries ?? [];
  const lib = libraryByFolderId(libraries, folderId);
  const folderName =
    lib?.name ?? foldersQ.data?.folders.find((f) => f.id === folderId)?.name ?? "";
  const label = lib?.name || folderName || "Library";
  const icon = libraryIconFor(lib?.collection_type ?? "");
  const warning = lib && !lib.ok ? lib.warning : "";

  const folderItems = items.data?.items ?? [];
  const genres = libraryGenres(folderItems);
  const list = filterLibraryItems(folderItems, { genre: parsed.genre, sort: parsed.sort });
  const filtered = parsed.genre !== "";
  const provider = items.data?.provider ?? null;

  const runScan = () => {
    scan.mutate(undefined, {
      onSuccess: () => toast("Library scan complete", "New titles will appear as they are discovered."),
      onError: (e: unknown) => {
        const f = scanFailure(e);
        toast(f.title, f.sub, "err");
      },
    });
  };

  const clear = () => {
    apply({ genre: "" });
  };

  return (
    <div className="flex flex-col gap-6 pb-8">
      {/* Page header: the configured library name, never the env key. */}
      <div className="pt-2">
        <h1 className="text-[32px] font-bold leading-none tracking-[-0.02em] text-zinc-50">
          {label}
        </h1>
        {provider ? (
          <p className="mt-2 text-[13px] text-zinc-500">{folderCountLabel(folderItems.length)}</p>
        ) : (
          <p className="mt-2 text-[13px] text-zinc-500">No media server connected</p>
        )}
        {warning ? (
          <p className="mt-2 flex items-start gap-1.5 rounded-lg border border-amber-500/20 bg-amber-500/[.06] px-3 py-2 text-xs text-amber-300">
            <Icon name="clock" size={13} className="mt-0.5 shrink-0" />
            <span>{warning}</span>
          </p>
        ) : null}
      </div>

      {provider && folderItems.length > 0 && (
        <LibraryToolbar
          label={label}
          genres={genres}
          genre={parsed.genre}
          sort={parsed.sort}
          view={view}
          resultCount={list.length}
          totalCount={folderItems.length}
          countNoun="titles"
          onChange={({ genre: g, sort: s }) => {
            const patch: { genre?: string; sort?: LibrarySort } = {};
            if (g !== undefined) patch.genre = g;
            if (s !== undefined) patch.sort = s;
            if (g !== undefined || s !== undefined) apply(patch);
          }}
          onViewChange={setView}
        />
      )}

      {items.isLoading ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-x-4 gap-y-7" aria-hidden="true">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="skeleton aspect-[2/3] rounded-[10px]" />
          ))}
        </div>
      ) : !provider && !items.isLoading ? (
        <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-white/[.08] py-16 text-center">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-surface-2 text-zinc-500">
            <Icon name={icon} size={22} />
          </div>
          <div className="max-w-sm">
            <h2 className="font-semibold text-zinc-200">No media server connected</h2>
            <p className="mt-1 text-sm leading-relaxed text-zinc-500">
              Connect Jellyfin in the repo .env, then redeploy the stack.
            </p>
          </div>
        </div>
      ) : folderItems.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-white/[.08] py-16 text-center">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-surface-2 text-zinc-500">
            <Icon name={icon} size={22} />
          </div>
          <div className="max-w-sm">
            <h2 className="font-semibold text-zinc-200">No titles in {label} yet</h2>
            <p className="mt-1 text-sm leading-relaxed text-zinc-500">
              Your media folder doesn't have any titles yet — scan your library after adding some.
            </p>
          </div>
          {mayScan ? (
            <button
              type="button"
              onClick={runScan}
              disabled={scan.isPending}
              className="inline-flex items-center gap-2 rounded-[10px] bg-accent px-4 py-2 text-sm font-bold text-black transition hover:bg-accent-hover disabled:opacity-60"
            >
              <Icon name="scan" size={15} />
              {scan.isPending ? "Scanning…" : "Scan Library"}
            </button>
          ) : (
            // Never OFFER what the server refuses (the route is administrators-only, Phase E).
            <p className="max-w-sm text-xs leading-relaxed text-zinc-500">
              Scanning is an administrator action — sign in as the administrator to scan the
              library.
            </p>
          )}
        </div>
      ) : list.length === 0 ? (
        <div className="flex flex-col items-start gap-3 rounded-2xl border border-dashed border-white/[.08] px-8 py-14">
          <h2 className="font-semibold text-zinc-200">
            No {label.toLowerCase()} match{parsed.genre ? ` in ${parsed.genre}` : ""}
          </h2>
          <p className="text-sm text-zinc-500">Try another genre.</p>
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
          {view === "compact" ? (
            <div className="flex flex-col gap-1.5" data-testid="compact-list">
              {list.map((item) => (
                <MediaListRow
                  key={item.item_id}
                  item={item}
                  onQuickPlay={quickPlay}
                  onOpenDetail={openItem}
                />
              ))}
            </div>
          ) : (
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
          )}
          {filtered && (
            <p className="text-xs text-zinc-500">
              Showing {folderCountLabel(list.length)} of {folderCountLabel(folderItems.length)} —{" "}
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
