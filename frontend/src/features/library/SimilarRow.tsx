import { useEffect, useState } from "react";
import type {
  MediaItem,
  SimilarItem,
  SuggestResult,
} from "../../lib/api/client";
import { useSimilar } from "./api";
import { filterLibraryRows, similarItemToResult } from "./lib";
import { useAddToWatchlist, useRequestMedia } from "../watchlist/api";
import { toast } from "../watchlist/toast";
import { acquisitionToast, errorMessage } from "../watchlist/actions";
import { SuggestCard } from "../suggest/SuggestCard";
import { SuggestDetailModal } from "../suggest/SuggestDetailModal";

/**
 * "Because you watched <title>" row (SIMILAR_TITLES_PLAN Phase 2) on the item
 * page — TMDB similar titles fetched server-side. Rendered only on movie/tv
 * pages; cards are actionable (SIMILAR_TITLES_PLAN: reuse the Suggest detail
 * modal so Add/Download work) and rows already in the local library are
 * dropped client-side against the shared library cache (zero extra fetches).
 * Hidden silently while loading / on empty / on error.
 */
export function SimilarRow({
  itemId,
  title,
  localItems,
}: {
  itemId: string;
  /** The source title for the row heading ("Because you watched <title>"). */
  title: string;
  localItems: MediaItem[];
}) {
  const query = useSimilar(itemId);
  const add = useAddToWatchlist();
  const request = useRequestMedia();

  const [results, setResults] = useState<SuggestResult[] | null>(null);
  const [busyAdd, setBusyAdd] = useState<number | null>(null);
  const [busyDownload, setBusyDownload] = useState<number | null>(null);
  const [detail, setDetail] = useState<SuggestResult | null>(null);

  // Reset local state when the routed item changes (component stays mounted
  // across /library/item/:id navigations).
  const [key, setKey] = useState(itemId);
  if (key !== itemId) {
    setKey(itemId);
    setResults(null);
    setDetail(null);
  }

  // Adapt + dedupe once the query lands (drop titles already in the library).
  useEffect(() => {
    if (!query.data) return;
    setResults(
      filterLibraryRows(query.data.similar, localItems).map(similarItemToResult),
    );
  }, [query.data, localItems]);

  const rows = results ?? [];
  if (rows.length === 0) return null;

  const patchItem = (tmdbId: number, patch: Partial<SuggestResult>) => {
    setResults((rs) =>
      (rs ?? []).map((r) => (r.tmdb_id === tmdbId ? { ...r, ...patch } : r)),
    );
    // Keep the OPEN detail modal in sync so its Add button flips immediately.
    setDetail((d) => (d && d.tmdb_id === tmdbId ? { ...d, ...patch } : d));
  };

  const handleAdd = (item: SuggestResult) => {
    setBusyAdd(item.tmdb_id);
    add.mutate(
      { tmdbId: item.tmdb_id, mediaType: item.media_type },
      {
        onSuccess: (resp) => {
          if (resp.ok) {
            patchItem(item.tmdb_id, { in_watchlist: true });
            toast("Added to watchlist", resp.title || item.title || "");
          } else {
            toast("Add failed", resp.message || "unknown error", "err");
          }
        },
        onError: (e) => toast("Add failed", errorMessage(e), "err"),
        onSettled: () => setBusyAdd(null),
      },
    );
  };

  const handleDownload = (item: SuggestResult) => {
    setBusyDownload(item.tmdb_id);
    add.mutate(
      { tmdbId: item.tmdb_id, mediaType: item.media_type },
      {
        onSuccess: (addResp) => {
          if (!addResp.ok && !addResp.already) {
            toast("Download failed", addResp.message || "Failed to add to watchlist", "err");
            setBusyDownload(null);
            return;
          }
          patchItem(item.tmdb_id, { in_watchlist: true });
          const mediaId = (item.media_type === "tv" ? "tv" : "movie") + ":tmdb:" + item.tmdb_id;
          request.mutate(mediaId, {
            onSuccess: (r) => {
              if (r.ok) toast("Download started", item.title || "");
              else toast("Download failed", r.message || r.state, "err", 6000);
            },
            onError: (e) => acquisitionToast(e, "Download failed"),
            onSettled: () => setBusyDownload(null),
          });
        },
        onError: (e) => {
          toast("Download failed", errorMessage(e), "err");
          setBusyDownload(null);
        },
      },
    );
  };

  return (
    <div className="mt-6">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-zinc-500">
        Because you watched {title}
      </h3>
      <div className="flex gap-3 overflow-x-auto pb-1">
        {rows.map((item) => (
          <SuggestCard
            key={item.tmdb_id}
            item={item}
            busyAdd={busyAdd === item.tmdb_id}
            busyDownload={busyDownload === item.tmdb_id}
            onAdd={() => handleAdd(item)}
            onDownload={() => handleDownload(item)}
            onOpen={() => setDetail(item)}
          />
        ))}
      </div>
      {detail ? (
        <SuggestDetailModal
          item={detail}
          busyAdd={busyAdd === detail.tmdb_id}
          busyDownload={busyDownload === detail.tmdb_id}
          onClose={() => setDetail(null)}
          onAdd={() => handleAdd(detail)}
          onDownload={() => handleDownload(detail)}
        />
      ) : null}
    </div>
  );
}
