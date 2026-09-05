import type { MediaItem } from "../../lib/api/client";
import { posterUrl, playbackMarker, isSeries, type Marker } from "./lib";

function Marker({ marker }: { marker: Marker }) {
  if (marker.kind === "watched") {
    return (
      <span
        className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-[11px] font-bold text-black shadow"
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
        className="absolute inset-x-0 bottom-0"
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

export function MediaCard({
  item,
  onPlay,
  onToggleWatched,
}: {
  item: MediaItem;
  onPlay: (item: MediaItem) => void;
  onToggleWatched?: (item: MediaItem) => void;
}) {
  const src = posterUrl(item);
  const marker = playbackMarker(item);
  const tv = isSeries(item);
  return (
    <div className="group relative w-40 shrink-0 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 transition hover:border-zinc-600" data-testid="media-card">
      <div className="relative aspect-[2/3] w-full overflow-hidden bg-zinc-800/60">
        {src ? (
          <img
            src={src}
            loading="lazy"
            referrerPolicy="no-referrer"
            className="absolute inset-0 h-full w-full object-cover"
            alt={item.title}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-3xl" aria-hidden="true">
            🎬
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent" />
        <span className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-white">
          {tv ? "TV" : "MOVIE"}
        </span>
        <Marker marker={marker} />
        <button
          onClick={() => onPlay(item)}
          className="absolute bottom-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-amber-400 px-3 py-1 text-[11px] font-semibold text-black opacity-0 shadow transition group-hover:opacity-100"
        >
          {tv ? "Episodes" : "Play in RKM"}
        </button>
        {item.jellyfin_url && (
          <a
            href={item.jellyfin_url}
            target="_blank"
            rel="noopener noreferrer"
            className="absolute right-2 bottom-3 rounded-full bg-blue-600/80 px-2 py-0.5 text-[10px] font-medium text-white opacity-0 transition group-hover:opacity-100"
          >
            Jellyfin
          </a>
        )}
      </div>
      <div className="p-2">
        <div className="truncate text-sm font-medium text-zinc-100">{item.title}</div>
        <div className="flex items-center justify-between text-xs text-zinc-500">
          <span>{item.year || ""}</span>
          {item.play_count ? <span>{item.play_count}× plays</span> : null}
        </div>
        {onToggleWatched && (
          <button
            onClick={() => onToggleWatched(item)}
            className={`mt-1.5 w-full rounded-md px-2 py-1 text-xs font-medium ring-1 ${
              item.played
                ? "bg-emerald-900/40 text-emerald-300 ring-emerald-700 hover:bg-emerald-800/50"
                : "bg-zinc-800 text-zinc-300 ring-zinc-700 hover:bg-zinc-700"
            }`}
          >
            {item.played ? "✓ Marked watched" : "Mark watched"}
          </button>
        )}
      </div>
    </div>
  );
}