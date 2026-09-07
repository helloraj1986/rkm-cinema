import type { WatchlistEntry } from "../../lib/api/client";
import {
  cardPrimaryAction,
  fmtRating,
  jellyfinMarker,
  type CardAction,
  type ResolvedState,
} from "./lib";

/**
 * State-aware card for watchlist entries (legacy `cardMarkup` parity in the
 * Tailwind design system). Whole card opens the detail modal; hover reveals
 * the ONE state-driven primary action + Trailer. Full action set lives in the
 * detail modal (multiple providers, trailer embed, state strip).
 */
export function WatchCard({
  entry,
  state,
  onOpen,
  onDownload,
  onPlayInRkm,
  onWatchLink,
  onTrailer,
}: {
  entry: WatchlistEntry;
  state: ResolvedState;
  onOpen: (entry: WatchlistEntry, trailer?: boolean) => void;
  /** Request the download (only offered when the resource says can_download). */
  onDownload: (entry: WatchlistEntry) => void;
  /** In-app play / episodes — routes to the item's page (/library/item/:id). */
  onPlayInRkm: (entry: WatchlistEntry, itemId: string) => void;
  /** Open an external watch link (Plex/Emby/Jellyfin web). */
  onWatchLink: (entry: WatchlistEntry, url: string) => void;
  onTrailer: (entry: WatchlistEntry) => void;
}) {
  const action: CardAction = cardPrimaryAction(entry, state);
  const marker = jellyfinMarker(state.watch.jellyfin);
  const inLibrary = state.state === "available" || state.state === "downloaded";
  const showWatchedTick = marker.kind === "watched" && !inLibrary;
  const badges: string[] = [];
  if (entry.imdb) badges.push(`★ ${fmtRating(entry.imdb)}`);
  if (entry.rt) badges.push(`${entry.rt}%`);

  return (
    <div
      className="group relative w-40 shrink-0 cursor-pointer rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400"
      data-testid="watch-card"
      role="button"
      tabIndex={0}
      aria-label={`Open details for ${entry.title} (${entry.year})`}
      onClick={(e) => {
        // Action buttons/link clicks handle themselves — never open the detail.
        if ((e.target as HTMLElement).closest("button, a")) return;
        onOpen(entry);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          if ((e.target as HTMLElement).closest("button, a")) return;
          e.preventDefault();
          onOpen(entry);
        }
      }}
    >
      <div className="pointer-events-none relative aspect-[2/3] w-full overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 transition duration-300 group-hover:-translate-y-1 group-hover:border-zinc-600 group-hover:shadow-xl group-hover:shadow-black/50">
        {entry.poster ? (
          <img
            src={entry.poster}
            loading="lazy"
            referrerPolicy="no-referrer"
            className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-105"
            alt={entry.title}
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        ) : null}
        <div className="absolute inset-0 bg-black/0 transition duration-300 group-hover:bg-black/45" />
        <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/80 to-transparent opacity-0 transition duration-300 group-hover:opacity-100" />

        {/* badges (top-left) */}
        <div className="absolute left-2 top-2 flex flex-col items-start gap-1">
          {badges.map((b) => (
            <span key={b} className="rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">
              {b}
            </span>
          ))}
          <span className="rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-zinc-200">
            {entry.type === "tv" ? "TV" : "MOVIE"}
          </span>
        </div>

        {/* in-library tick (top-right) or watched tick when not in a library */}
        {(inLibrary || showWatchedTick) && (
          <span
            role="img"
            aria-label={inLibrary ? "Available in library" : "Watched"}
            title={inLibrary ? "Available in library" : "Watched"}
            className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-[11px] font-bold text-black shadow"
          >
            ✓
          </span>
        )}

        {/* amber resume bar from the Jellyfin watch link */}
        {marker.kind === "resume" && (
          <div className="absolute inset-x-0 bottom-0">
            <div className="h-1 w-full bg-zinc-700">
              <div className="h-full bg-amber-400" style={{ width: `${marker.percent}%` }} />
            </div>
            <span className="absolute bottom-1.5 right-2 rounded bg-black/70 px-1 text-[10px] font-medium text-amber-300">
              {marker.percent}%
            </span>
          </div>
        )}

        {/* busy progress strip */}
        {action.type === "downloading" && (
          <div className="absolute inset-x-0 bottom-0">
            <div className="h-1 w-full bg-zinc-700">
              <div className="h-full bg-sky-400" style={{ width: `${action.progress}%` }} />
            </div>
          </div>
        )}

        {/* hover actions — pointer-events-auto: the poster wrapper is
            pointer-events-none, so without this clicks fall through to the
            card and open the detail instead of pressing the button. */}
        <div className="pointer-events-auto absolute inset-x-2 bottom-2 z-[2] flex flex-col items-stretch gap-1.5 opacity-0 transition group-hover:opacity-100">
          {action.type === "play-rkm" && (
            <button
              type="button"
              onClick={() => onPlayInRkm(entry, action.itemId)}
              className="rounded-full bg-amber-400 px-3 py-1.5 text-center text-xs font-bold text-black hover:bg-amber-300"
            >
              ▶ {action.label}
            </button>
          )}
          {action.type === "watch-link" && (
            <button
              type="button"
              onClick={() => onWatchLink(entry, action.url)}
              className="rounded-full bg-violet-500 px-3 py-1.5 text-center text-xs font-bold text-white hover:bg-violet-400"
            >
              ▶ {action.label}
            </button>
          )}
          {action.type === "download" && (
            <button
              type="button"
              onClick={() => onDownload(entry)}
              className="rounded-full bg-amber-400 px-3 py-1.5 text-center text-xs font-bold text-black hover:bg-amber-300"
            >
              ↓ Download
            </button>
          )}
          {action.type === "requested" && (
            <button type="button" disabled className="rounded-full bg-sky-600/80 px-3 py-1.5 text-center text-xs font-bold text-white">
              ✓ Requested
            </button>
          )}
          {action.type === "downloading" && (
            <button type="button" disabled className="rounded-full bg-sky-600/80 px-3 py-1.5 text-center text-xs font-bold text-white">
              ↓ Downloading {action.progress}%
            </button>
          )}
          {action.type === "available" && (
            <button type="button" disabled className="rounded-full bg-emerald-600/80 px-3 py-1.5 text-center text-xs font-bold text-white">
              ✓ Available
            </button>
          )}
          {action.type === "unavailable" && (
            <button type="button" disabled className="rounded-full bg-zinc-700/80 px-3 py-1.5 text-center text-xs font-bold text-zinc-400">
              Unavailable
            </button>
          )}
          <button
            type="button"
            onClick={() => onTrailer(entry)}
            className="rounded-full bg-black/70 px-3 py-1 text-center text-[11px] font-semibold text-zinc-200 ring-1 ring-zinc-600 hover:bg-black/90 hover:text-white"
          >
            ▶ Trailer
          </button>
        </div>
      </div>

      <div className="pointer-events-none px-0.5 pt-1.5">
        <div className="truncate text-sm font-medium text-zinc-100 group-hover:text-white">{entry.title}</div>
        <div className="flex items-center justify-between text-xs text-zinc-500">
          <span>{entry.year || ""}</span>
          {entry.genres?.[0] ? <span className="truncate pl-2">{entry.genres[0]}</span> : null}
        </div>
      </div>
    </div>
  );
}
