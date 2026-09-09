import type { MediaItem } from "../../lib/api/client";
import {
  artTone,
  fmtRuntime,
  isEpisodeItem,
  isSeries,
  playbackMarker,
  posterUrl,
  resumePercent,
  type Marker,
} from "./lib";
import { Icon } from "../../components/ui/Icon";

/**
 * Compact list row (NEW_UX §17) for the folder views: a table-like row that
 * shows many more titles per screen than the poster grid — thumbnail |
 * title | year | genre | runtime | status. Deliberately light on chrome;
 * whole-row click opens the item page, hover reveals a play affordance for
 * movies (series still open their page — episodes live there).
 *
 * Columns follow what the frozen list payload truly carries: rating is NOT a
 * column here (list items have no community rating; only the detail does).
 */
export function MediaListRow({
  item,
  onQuickPlay,
  onOpenDetail,
}: {
  item: MediaItem;
  onQuickPlay: (item: MediaItem) => void;
  onOpenDetail: (item: MediaItem) => void;
}) {
  const src = posterUrl(item);
  const tone = artTone(item.title);
  const marker: Marker = playbackMarker(item);
  const tv = isSeries(item);
  const episode = isEpisodeItem(item);
  const percent = resumePercent(item);
  const genres = (item.genres ?? []).slice(0, 2).join(" · ");
  const runtime = episode ? "" : tv ? "Series" : fmtRuntime(item.runtime);
  const statusText = marker.kind === "watched" ? "Watched" : marker.kind === "resume" ? `${percent}% watched` : "Not watched";

  return (
    <div
      className="group relative grid cursor-pointer grid-cols-[44px_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5 rounded-xl border border-transparent px-2 py-1.5 transition-colors hover:border-white/[.08] hover:bg-surface-2 sm:grid-cols-[44px_minmax(0,1fr)_96px_110px_72px_130px] sm:gap-x-4 sm:pr-4"
      data-testid="media-list-row"
      role="button"
      tabIndex={0}
      aria-label={`Open ${item.title}`}
      onClick={() => onOpenDetail(item)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpenDetail(item);
        }
      }}
    >
      {/* Thumbnail */}
      <div className="relative aspect-[2/3] h-12 w-[44px] shrink-0 overflow-hidden rounded-md ring-1 ring-white/[.06]">
        <div aria-hidden="true" className={`absolute inset-0 art-${tone}`} />
        {src ? (
          <img
            src={src}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : null}
        {marker.kind === "resume" && percent > 0 && (
          <div className="absolute inset-x-0 bottom-0 h-[3px] bg-white/15">
            <div className="h-full bg-accent" style={{ width: `${percent}%` }} />
          </div>
        )}
      </div>

      {/* Title */}
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold text-zinc-100 group-hover:text-white">
          {item.title}
          {episode ? (
            <span className="ml-2 rounded bg-white/[.06] px-1 py-0.5 align-middle text-[10px] font-bold text-accent">
              {item.episode ? `S${item.episode.season}E${item.episode.number}` : "EP"}
            </span>
          ) : null}
        </div>
        {/* Mobile meta line (desktop shows real columns instead). */}
        <div className="truncate text-xs text-zinc-500 sm:hidden">{genres || "—"}</div>
      </div>

      {/* Year */}
      <div className="hidden text-right text-xs tabular-nums text-zinc-400 sm:block">{item.year ?? "—"}</div>

      {/* Genre (desktop replaces the under-title line) */}
      <div className="hidden truncate text-xs text-zinc-500 sm:block" title={genres}>
        {genres || "—"}
      </div>

      {/* Runtime */}
      <div className="hidden text-xs text-zinc-400 sm:block">{runtime || "—"}</div>

      {/* Status */}
      <div className="hidden items-center justify-end gap-1.5 text-xs sm:flex">
        {marker.kind === "watched" ? (
          <span className="inline-flex items-center gap-1 font-semibold text-emerald-400">
            <Icon name="check" size={12} strokeWidth={2.5} />
            {statusText}
          </span>
        ) : marker.kind === "resume" ? (
          <span className="font-medium text-accent">{statusText}</span>
        ) : (
          <span className="text-zinc-600">{statusText}</span>
        )}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onQuickPlay(item);
          }}
          aria-label={tv ? `Episodes for ${item.title}` : `Play ${item.title}`}
          className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent text-black opacity-0 transition hover:bg-accent-hover group-hover:opacity-100 focus-visible:opacity-100"
        >
          <Icon name="play" size={13} filled />
        </button>
      </div>
    </div>
  );
}
