import { useEffect, useState } from "react";
import type {
  MediaItem,
  SimilarItem,
  SuggestResult,
} from "../../lib/api/client";
import { Icon } from "../../components/ui/Icon";
import { useSimilar } from "./api";
import { filterLibraryRows, similarItemToResult } from "./lib";
import { useAddToWatchlist, useRequestMedia } from "../watchlist/api";
import { toast } from "../watchlist/toast";
import {
  acquisitionToast,
  ambiguousMatch,
  errorMessage,
  type AmbiguousMatch,
} from "../watchlist/actions";
import { SuggestCard } from "../suggest/SuggestCard";
import { SuggestDetailModal } from "../suggest/SuggestDetailModal";
import { SuggestDetailSheet } from "../suggest/SuggestDetailSheet";

/**
 * Which shell presents a similar title's details.
 *
 * ⚠ **A prop, not two rows.** The DATA (`useSimilar`), the dedupe rule and the three actions are
 * one implementation in this file; only the shell changes. The desktop's rail is a grid of
 * `SuggestCard`s whose tap opens a centred `Dialog`; on a 390px screen that dialog is the wrong
 * composition (M4's own argument), so the phone gets a list whose tap opens the shared `Sheet`.
 * Copying this file per platform is how the two would come to disagree about what Add and Download
 * mean — the drift `SuggestDetailBody` was extracted to prevent.
 */
export type SimilarDetailSurface = "modal" | "sheet";

/**
 * "Because you watched <title>" (SIMILAR_TITLES_PLAN Phase 2) — TMDB similar titles fetched
 * server-side. Rendered only on movie/tv pages; rows already in the local library are dropped
 * client-side against the shared library cache (zero extra fetches). Hidden silently while
 * loading / on empty / on error.
 *
 * ⚠ **The phone and the desktop differ in the RAIL, not in the actions.** `detailSurface="sheet"`
 * renders a thumb-reachable list of rows — the phone's own language (`SearchScreen`'s discovery
 * rows: a ≥44px body that opens the details, one ≥44px pill that Add/Downloads) — because the
 * desktop card's chips are ~26px and hover-revealed on a fine pointer, which is a mis-tap magnet on
 * a held device. Everything behind the two presentations is this one component.
 *
 * ⚠ **A 409 lands here too.** When the request matches several titles the server answers with the
 * candidates; this opens THAT title's details with the list in it (`AmbiguousMatches` renders inside
 * the body), rather than a toast that names titles the person cannot see.
 */
export function SimilarRow({
  itemId,
  title,
  localItems,
  detailSurface = "modal",
}: {
  itemId: string;
  /** The source title for the row heading ("Because you watched <title>"). */
  title: string;
  localItems: MediaItem[];
  /** `"modal"` (desktop `Dialog`) or `"sheet"` (phone `Sheet`, as a list of rows). */
  detailSurface?: SimilarDetailSurface;
}) {
  const query = useSimilar(itemId);
  const add = useAddToWatchlist();
  const request = useRequestMedia();

  const [results, setResults] = useState<SuggestResult[] | null>(null);
  const [busyAdd, setBusyAdd] = useState<number | null>(null);
  const [busyDownload, setBusyDownload] = useState<number | null>(null);
  const [detail, setDetail] = useState<SuggestResult | null>(null);
  /**
   * The server's ambiguous match for ONE title, kept with its tmdb id — so a different title's
   * details can never show another title's candidates.
   */
  const [ambiguous, setAmbiguous] = useState<{ tmdbId: number; match: AmbiguousMatch } | null>(null);

  // Reset local state when the routed item changes (component stays mounted
  // across /library/item/:id navigations).
  const [key, setKey] = useState(itemId);
  if (key !== itemId) {
    setKey(itemId);
    setResults(null);
    setDetail(null);
    setAmbiguous(null);
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

  const openDetail = (item: SuggestResult) => {
    setAmbiguous(null);
    setDetail(item);
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
    setAmbiguous(null);
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
            onError: (e) => {
              // ⚠ The candidates have no home on a rail of cards, so an ambiguous match OPENS the
              // title's details with the list inside it — the same answer the phone gives.
              const match = ambiguousMatch(e);
              if (match) {
                setDetail(item);
                setAmbiguous({ tmdbId: item.tmdb_id, match });
                return;
              }
              acquisitionToast(e, "Download failed");
            },
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

  const closeDetail = () => {
    setAmbiguous(null);
    setDetail(null);
  };

  const ambiguousFor =
    detail && ambiguous && ambiguous.tmdbId === detail.tmdb_id ? ambiguous.match : null;

  if (detailSurface === "sheet") {
    return (
      <section className="mt-6 flex flex-col gap-2" data-testid="similar-title-row">
        <h2 className="px-1 text-[11px] font-bold uppercase tracking-[0.16em] text-zinc-500">
          Because you watched {title}
        </h2>
        <ul className="flex flex-col gap-2">
          {rows.map((item) => (
            <li
              key={item.tmdb_id}
              data-testid="similar-item"
              className="flex items-center gap-3 rounded-xl border border-white/[.05] bg-surface/60 p-2.5"
            >
              <button
                type="button"
                onClick={() => openDetail(item)}
                data-testid="similar-open"
                aria-label={`Details for ${item.title}`}
                className="flex min-w-0 flex-1 items-center gap-3 text-left"
              >
                <SimilarArt item={item} />
                <span className="min-w-0 flex-1">
                  <span
                    data-testid="similar-title"
                    className="block truncate text-[14px] font-semibold text-zinc-100"
                  >
                    {item.title}
                  </span>
                  <span className="block truncate text-[12px] text-zinc-500">
                    {item.media_type === "tv" ? "TV Show" : "Movie"}
                    {item.year ? ` · ${item.year}` : ""}
                  </span>
                </span>
              </button>
              {/* ⚠ ONE action, and it tells the truth about where the title stands: "Add" until the
                  server knows about it, "Download" after that. Same two zones as the search screen's
                  discovery rows, so the phone teaches one pattern. */}
              {item.in_watchlist ? (
                <button
                  type="button"
                  onClick={() => handleDownload(item)}
                  disabled={busyDownload === item.tmdb_id}
                  data-testid="similar-action"
                  className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-[10px] bg-accent px-3.5 text-[13px] font-bold text-black transition active:bg-accent-hover disabled:opacity-60"
                >
                  <Icon name="download" size={13} />
                  {busyDownload === item.tmdb_id ? "Starting…" : "Download"}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => handleAdd(item)}
                  disabled={busyAdd === item.tmdb_id}
                  data-testid="similar-action"
                  className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-[10px] bg-accent px-3.5 text-[13px] font-bold text-black transition active:bg-accent-hover disabled:opacity-60"
                >
                  <Icon name="plus" size={13} />
                  {busyAdd === item.tmdb_id ? "Adding…" : "Add"}
                </button>
              )}
            </li>
          ))}
        </ul>
        {detail ? (
          <SuggestDetailSheet
            item={detail}
            busyAdd={busyAdd === detail.tmdb_id}
            busyDownload={busyDownload === detail.tmdb_id}
            ambiguous={ambiguousFor}
            onClose={closeDetail}
            onAdd={() => handleAdd(detail)}
            onDownload={() => handleDownload(detail)}
          />
        ) : null}
      </section>
    );
  }

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
            onOpen={() => openDetail(item)}
          />
        ))}
      </div>
      {detail ? (
        <SuggestDetailModal
          item={detail}
          busyAdd={busyAdd === detail.tmdb_id}
          busyDownload={busyDownload === detail.tmdb_id}
          ambiguous={ambiguousFor}
          onClose={closeDetail}
          onAdd={() => handleAdd(detail)}
          onDownload={() => handleDownload(detail)}
        />
      ) : null}
    </div>
  );
}

/**
 * A similar title's poster at row size. ⚠ It degrades to the app's seeded art + a type glyph, never
 * to a broken image (the same rule `SuggestCard` and the phone's discovery rows follow) — a similar
 * row's art comes from TMDB's CDN, and an offline phone is a real case here.
 */
function SimilarArt({ item }: { item: SuggestResult }) {
  const [failed, setFailed] = useState(false);
  if (item.poster && !failed) {
    return (
      <img
        src={item.poster}
        alt=""
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className="h-14 w-10 shrink-0 rounded-md bg-surface-3 object-cover ring-1 ring-white/[.06]"
      />
    );
  }
  return (
    <span className="grid h-14 w-10 shrink-0 place-items-center rounded-md bg-surface-3 text-zinc-500 ring-1 ring-white/[.06]">
      <Icon name={item.media_type === "tv" ? "tv" : "film"} size={14} />
    </span>
  );
}
