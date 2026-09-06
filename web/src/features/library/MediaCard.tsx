import type { MediaItem } from "../../lib/api/client";
import { posterUrl, playbackMarker, isSeries, type Marker } from "./lib";

function Marker({ marker }: { marker: Marker }) {
  if (marker.kind === "watched") {
    return (
      <span
        className="pointer-events-none absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-[11px] font-bold text-black shadow"
        role="img"
        aria-label="Watched"
        title="Watched"
      >
        ✓
      </span>
    );
  }
  if (marker.kind === "resume") {
    return (
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0"
        role="img"
        aria-label={`${marker.percent}% watched`}
        title={`${marker.percent}% watched`}
      >
        <div className="h-1 w-full bg-zinc-700">
          <div className="h-full bg-amber-400" style={{ width: `${marker.percent}%` }} />
        </div>
        <span className="absolute bottom-1.5 right-2 rounded bg-black/70 px-1 text-[10px] font-medium text-amber-300">
          {marker.percent}%
        </span>
      </div>
    );
  }
  return null;
}

/**
 * Plex-style card (PLEX_UI_PLAN.md §2 + PLEX_VIEWS_PLAN.md): the WHOLE card
 * navigates to the item's OWN page (/library/item/:id); hover reveals a
 * centred play action (movies) / an Episodes action (series) plus a watched
 * toggle and the Jellyfin deep link. Watched ✓ badge + amber resume bar stay
 * as-is; metadata stays clean — the item page holds the rest.
 */
export function MediaCard({
  item,
  onQuickPlay,
  onOpenDetail,
  onToggleWatched,
}: {
  item: MediaItem;
  /** Primary hover action — movies start playback; series open their page. */
  onQuickPlay: (item: MediaItem) => void;
  /** Whole-card click — navigates to the item's dedicated page. */
  onOpenDetail: (item: MediaItem) => void;
  onToggleWatched?: (item: MediaItem) => void;
}) {
  const src = posterUrl(item);
  const marker = playbackMarker(item);
  const tv = isSeries(item);
  return (
    <div className="group relative w-40 shrink-0 rounded-lg" data-testid="media-card">
      {/* Transparent whole-card button — clicking anywhere opens the detail view. */}
      <button
        type="button"
        aria-label={`Open details for ${item.title}`}
        onClick={() => onOpenDetail(item)}
        className="absolute inset-0 z-[1] cursor-pointer rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400"
      />
      <div className="pointer-events-none relative aspect-[2/3] w-full overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 transition duration-300 group-hover:-translate-y-1 group-hover:border-zinc-600 group-hover:shadow-xl group-hover:shadow-black/50">
        {src ? (
          <img
            src={src}
            loading="lazy"
            referrerPolicy="no-referrer"
            className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-105"
            alt={item.title}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-3xl" aria-hidden="true">
            🎬
          </div>
        )}
        {/* Hover darkening + bottom gradient so text/actions read over posters. */}
        <div className="absolute inset-0 bg-black/0 transition duration-300 group-hover:bg-black/45" />
        <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/80 to-transparent opacity-0 transition duration-300 group-hover:opacity-100" />
        <span className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-white">
          {tv ? "TV" : "MOVIE"}
        </span>
        <Marker marker={marker} />
      </div>

      {/* Hover primary action: ▶ play (movie) / Episodes (series). */}
      {tv ? (
        <button
          type="button"
          onClick={() => onQuickPlay(item)}
          aria-label={`Episodes for ${item.title}`}
          className="absolute left-1/2 top-[40%] z-[2] -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-full bg-amber-400 px-4 py-2 text-xs font-bold text-black opacity-0 shadow-lg transition hover:bg-amber-300 group-hover:opacity-100"
        >
          ▶ Episodes
        </button>
      ) : (
        <button
          type="button"
          onClick={() => onQuickPlay(item)}
          aria-label={`Play ${item.title}`}
          className="absolute left-1/2 top-[40%] z-[2] flex h-12 w-12 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-amber-400 pl-0.5 text-lg text-black opacity-0 shadow-lg transition hover:scale-105 hover:bg-amber-300 group-hover:opacity-100"
        >
          ▶
        </button>
      )}

      {/* Hover quick actions: watched toggle + Jellyfin deep link. */}
      <div className="absolute inset-x-2 bottom-2 z-[2] flex items-center justify-between opacity-0 transition group-hover:opacity-100">
        {onToggleWatched && (
          <button
            type="button"
            onClick={() => onToggleWatched(item)}
            aria-label={item.played ? "Mark as unplayed" : "Mark as watched"}
            title={item.played ? "Mark as unplayed" : "Mark as watched"}
            className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ring-1 ${
              item.played
                ? "bg-emerald-500 text-black ring-emerald-400"
                : "bg-black/60 text-zinc-200 ring-zinc-500 hover:bg-emerald-500 hover:text-black"
            }`}
          >
            ✓
          </button>
        )}
        {item.jellyfin_url && (
          <a
            href={item.jellyfin_url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Open in Jellyfin"
            title="Open in Jellyfin"
            onClick={(e) => e.stopPropagation()}
            className="flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-xs font-bold text-blue-300 ring-1 ring-zinc-500 hover:bg-blue-600/70 hover:text-white"
          >
            ↗
          </a>
        )}
      </div>

      <div className="pointer-events-none px-0.5 pt-1.5">
        <div className="truncate text-sm font-medium text-zinc-100 group-hover:text-white">{item.title}</div>
        <div className="flex items-center justify-between text-xs text-zinc-500">
          <span>{item.year || ""}</span>
          {item.play_count ? <span>{item.play_count}× plays</span> : null}
        </div>
      </div>
    </div>
  );
}
