import { useLibraryItems } from "./api";
import { libraryItemsByType, libraryKindLabel, type LibraryKind } from "./lib";
import { MediaCard } from "./MediaCard";
import { useLibraryOutlet } from "./LibraryLayout";

/**
 * /library/movies + /library/shows — the Plex-style sidebar "folders". Each is
 * a type-filtered poster grid over the SHARED useLibraryItems cache (client-side
 * split via libraryItemsByType — no backend/contract change, no refetch).
 */
export function LibraryFolderView({ kind }: { kind: LibraryKind }) {
  const items = useLibraryItems();
  const { quickPlay, openItem, toggleWatched } = useLibraryOutlet();

  const list = libraryItemsByType(items.data?.items ?? [], kind);
  const label = libraryKindLabel(kind);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-lg font-semibold text-white">{label}</h2>
        <p className="text-xs text-zinc-500">
          {items.data?.provider
            ? `${items.data.provider} · ${list.length} title${list.length === 1 ? "" : "s"}`
            : "No library backend connected."}
        </p>
      </div>

      {items.isLoading ? (
        <p className="text-sm text-zinc-400">Loading library…</p>
      ) : list.length === 0 ? (
        <p className="text-sm text-zinc-500">No {label.toLowerCase()} in the library yet.</p>
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
    </div>
  );
}
