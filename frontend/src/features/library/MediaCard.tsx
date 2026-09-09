import type { MediaItem } from "../../lib/api/client";
import {
  artTone,
  episodeItemCode,
  fmtRuntime,
  isEpisodeItem,
  isSeries,
  playbackMarker,
  posterUrl,
  resumePercent,
  type Marker,
} from "./lib";
import { Icon } from "../../components/ui/Icon";

/** Watched ✓ (success green) — top-right, small. */
function WatchedTick() {
  return (
    <span
      className="pointer-events-none absolute right-2 top-2 grid h-5 w-5 place-items-center rounded-full bg-emerald-500 text-[11px] font-bold text-black shadow"
      role="img"
      aria-label="Watched"
      title="Watched"
    >
      <Icon name="check" size={12} strokeWidth={3} />
    </span>
  );
}

/** 3px progress bar along the very bottom edge (spec §21). */
function ResumeBar({ percent }: { percent: number }) {
  if (percent <= 0) return null;
  return (
    <div
      className="pointer-events-none absolute inset-x-0 bottom-0 h-[3px] bg-black/30"
      role="img"
      aria-label={`${percent}% watched`}
      title={`${percent}% watched`}
    >
      <div className="h-full bg-accent" style={{ width: `${percent}%` }} />
    </div>
  );
}

function MarkerBadge({ marker }: { marker: Marker }) {
  if (marker.kind === "watched") return <WatchedTick />;
  return null;
}

/**
 * Premium media card (design spec §19–22): the poster owns the card — no heavy
 * borders, no clutter over the artwork. Whole card opens the item's page; the
 * hover overlay reveals a centered ▶ (movies play now / series open episodes)
 * and a compact watched toggle; a 3px amber progress bar sits on the poster's
 * bottom edge. `fluid` fills a CSS-grid track instead of the fixed rail width.
 */
export function MediaCard({
  item,
  onQuickPlay,
  onOpenDetail,
  onToggleWatched,
  fluid = false,
}: {
  item: MediaItem;
  /** Primary hover action — movies start playback; series open their page. */
  onQuickPlay: (item: MediaItem) => void;
  /** Whole-card click — navigates to the item's dedicated page. */
  onOpenDetail: (item: MediaItem) => void;
  onToggleWatched?: (item: MediaItem) => void;
  /** Fill the parent grid cell (folder pages) instead of the fixed rail width. */
  fluid?: boolean;
}) {
  const src = posterUrl(item);
  const tone = artTone(item.title);
  const marker = playbackMarker(item);
  const tv = isSeries(item);
  const episode = isEpisodeItem(item);
  const epCode = episodeItemCode(item);
  const percent = resumePercent(item);
  const sub = episode
    ? [epCode, item.episode?.series_name].filter(Boolean).join(" · ")
    : [
        item.year ? String(item.year) : "",
        tv ? "TV" : fmtRuntime(item.runtime),
        item.play_count && item.play_count > 1 ? `${item.play_count} plays` : "",
      ]
        .filter(Boolean)
        .join(" · ");

  return (
    <article
      className={`group relative rounded-[10px] ${fluid ? "w-full min-w-0" : "w-44 shrink-0"}`}
      data-testid="media-card"
    >
      {/* Transparent whole-card button — clicking anywhere opens the item page. */}
      <button
        type="button"
        aria-label={`Open details for ${item.title}`}
        onClick={() => onOpenDetail(item)}
        className="absolute inset-0 z-[1] cursor-pointer rounded-[10px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      />

      <div className="pointer-events-none relative aspect-[2/3] w-full overflow-hidden rounded-[10px] border border-white/[.06] bg-surface-2 transition-[transform,box-shadow,border-color] duration-200 ease-out group-hover:-translate-y-1 group-hover:scale-[1.02] group-hover:border-white/10 group-hover:shadow-card-hover">
        {/* Seeded gradient art fallback under the poster (§58). */}
        <div aria-hidden="true" className={`absolute inset-0 art-${tone}`} />
        {src ? (
          <img
            src={src}
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
            className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.05]"
            alt={item.title}
          />
        ) : null}

        {/* Hover darkening + bottom gradient so actions read over posters. */}
        <div className="absolute inset-0 bg-black/0 transition duration-300 group-hover:bg-black/45" />
        <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/85 to-transparent opacity-0 transition duration-300 group-hover:opacity-100" />

        {/* Type glyph (subtle, not a dashboard badge). */}
        <span className="absolute left-2 top-2 grid h-[22px] w-[22px] place-items-center rounded-md border border-white/10 bg-black/40 text-zinc-100 backdrop-blur-sm">
          {episode && epCode ? (
            <span className="px-0.5 text-[9px] font-bold tracking-tight">{epCode}</span>
          ) : (
            <Icon name={tv ? "tv" : "film"} size={13} />
          )}
        </span>

        <MarkerBadge marker={marker} />
        <ResumeBar percent={percent} />

        {/* Centered primary hover action: ▶ (movies) / Episodes (series).
            pointer-events-auto: the poster wrapper is pointer-events-none so
            without it these clicks fall through to the card's open button. */}
        <button
          type="button"
          onClick={() => onQuickPlay(item)}
          aria-label={tv ? `Episodes for ${item.title}` : `Play ${item.title}`}
          className="pointer-events-auto absolute left-1/2 top-[42%] z-[2] -translate-x-1/2 -translate-y-1/2 opacity-0 transition group-hover:opacity-100"
        >
          <span
            className={`grid place-items-center rounded-full bg-accent text-black shadow-lg transition hover:scale-105 hover:bg-accent-hover ${
              tv ? "h-9 min-w-24 gap-1.5 px-3.5 text-xs font-bold" : "h-12 w-12"
            }`}
          >
            <Icon name="play" size={tv ? 13 : 18} filled className="ml-0.5" />
            {tv ? "Episodes" : null}
          </span>
        </button>

        {/* Bottom hover row: watched toggle (+ Jellyfin deep link when present). */}
        <div className="pointer-events-auto absolute inset-x-2 bottom-2 z-[2] flex items-center justify-between opacity-0 transition group-hover:opacity-100">
          {onToggleWatched ? (
            <button
              type="button"
              onClick={() => onToggleWatched(item)}
              aria-label={item.played ? "Mark as unplayed" : "Mark as watched"}
              title={item.played ? "Mark as unplayed" : "Mark as watched"}
              className={`grid h-7 w-7 place-items-center rounded-full ring-1 transition ${
                item.played
                  ? "bg-emerald-500 text-black ring-emerald-400/60"
                  : "bg-black/60 text-zinc-200 ring-white/25 hover:bg-emerald-500 hover:text-black"
              }`}
            >
              <Icon name="check" size={13} strokeWidth={2.5} />
            </button>
          ) : (
            <span />
          )}
          {item.jellyfin_url ? (
            <a
              href={item.jellyfin_url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Open in Jellyfin"
              title="Open in Jellyfin"
              onClick={(e) => e.stopPropagation()}
              className="grid h-7 w-7 place-items-center rounded-full bg-black/60 text-zinc-200 ring-1 ring-white/25 transition hover:bg-surface-3 hover:text-white"
            >
              <Icon name="external" size={13} />
            </a>
          ) : null}
        </div>
      </div>

      {/* Card title + one meta line — 2-line clamp so titles never break the
          grid (spec §73). */}
      <div className="pointer-events-none px-0.5 pt-2">
        <div className="line-clamp-2 text-[13px] font-semibold leading-snug text-zinc-200 group-hover:text-white">
          {item.title}
        </div>
        <div className="mt-0.5 truncate text-[11px] font-medium text-zinc-500" title={sub}>
          {sub}
        </div>
      </div>
    </article>
  );
}
