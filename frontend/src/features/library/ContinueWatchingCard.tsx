import type { MediaItem } from "../../lib/api/client";
import {
  artTone,
  episodeItemCode,
  fmtRuntime,
  isEpisodeItem,
  isSeries,
  posterUrl,
  resumePercent,
} from "./lib";
import { Icon } from "../../components/ui/Icon";

/**
 * Continue Watching card (design spec §10): landscape 16:9 backdrop-first —
 * larger than ordinary cards, title + episode/movie info + 3px progress on a
 * bottom gradient. Whole-card click opens the item/series page; the round ▶
 * resumes instantly (touch-friendly, never hover-only).
 */
export function ContinueWatchingCard({
  item,
  onQuickPlay,
  onOpenDetail,
}: {
  item: MediaItem;
  /** Hover/tap primary: resume now (episode rows resume the episode). */
  onQuickPlay: (item: MediaItem) => void;
  /** Whole-card click: open the item page (series page for episodes). */
  onOpenDetail: (item: MediaItem) => void;
}) {
  const src = posterUrl(item);
  const tone = artTone(item.title);
  const episode = isEpisodeItem(item);
  const epCode = episodeItemCode(item);
  const percent = resumePercent(item);
  const sub = episode
    ? [
        item.episode?.series_name || "",
        epCode ? `${epCode} · ${fmtRuntime(item.runtime)}` : "",
      ]
        .filter(Boolean)
        .join(" — ")
    : [item.year ? String(item.year) : "", fmtRuntime(item.runtime)].filter(Boolean).join(" · ");

  return (
    <article className="group relative w-[300px] shrink-0 snap-start sm:w-[340px]" data-testid="continue-card">
      <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-white/[.06] bg-surface-2 shadow-card transition-transform duration-200 ease-out group-hover:-translate-y-0.5 group-hover:scale-[1.015] group-hover:shadow-card-hover">
        {/* Seeded gradient art fallback — always under the image layer so a
            broken/failed poster degrades to art, never a blank card (§58). */}
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
            className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.04]"
          />
        ) : null}

        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-black/25" />

        {/* Type label */}
        <span className="absolute left-3 top-3 rounded-md border border-white/10 bg-black/45 px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-[0.14em] text-zinc-100 backdrop-blur-sm">
          {episode && epCode ? epCode : isSeries(item) ? "Series" : "Movie"}
        </span>

        {/* Whole-card click → the item's page (series page for episodes). */}
        <button
          type="button"
          aria-label={`Open details for ${item.title}`}
          onClick={() => onOpenDetail(item)}
          className="absolute inset-0 z-[1] cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        />

        {/* Title + facts on the gradient */}
        <div className="pointer-events-none absolute inset-x-3.5 bottom-2.5">
          <div className="line-clamp-1 pr-12 text-[16px] font-bold leading-tight text-white drop-shadow-[0_2px_10px_rgba(0,0,0,.8)]">
            {item.title}
          </div>
          <div className="mt-0.5 truncate text-[11px] font-medium text-zinc-300">{sub}</div>
        </div>

        {/* Resume — always reachable (spec §45: ▶ Resume 23:14). */}
        <button
          type="button"
          onClick={() => onQuickPlay(item)}
          aria-label={`Resume ${item.title}`}
          title={percent > 0 ? `Resume — ${percent}% watched` : "Play"}
          className="absolute bottom-2.5 right-3 z-[2] grid h-9 w-9 place-items-center rounded-full bg-accent text-black shadow-lg transition hover:scale-105 hover:bg-accent-hover"
        >
          <Icon name="play" size={16} filled className="ml-0.5" />
        </button>

        {/* 3px progress bar along the very bottom edge (§21). */}
        <div className="absolute inset-x-0 bottom-0 h-[3px] bg-white/10">
          <div
            className={`h-full ${item.played ? "bg-emerald-500" : "bg-accent"}`}
            style={{ width: item.played ? "100%" : `${percent}%` }}
          />
        </div>
      </div>
    </article>
  );
}
