import type { WatchlistEntry } from "../../lib/api/client";
import {
  cardPrimaryAction,
  fmtRating,
  jellyfinMarker,
  type CardAction,
  type ResolvedState,
} from "./lib";
import { artTone } from "../library/lib";
import { Icon } from "../../components/ui/Icon";

/**
 * State-aware card for watchlist entries (legacy `cardMarkup` parity, NEW_UX
 * card system): poster-first with the same premium hover as MediaCard — whole
 * card opens the detail modal; hover reveals the ONE state-driven primary
 * action + Trailer. Full action set lives in the detail modal.
 */
export function WatchCard({
  entry,
  state,
  onOpen,
  onDownload,
  onPlayInRkm,
  onWatchLink,
  onTrailer,
  fluid = false,
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
  /** Fill the parent grid cell (folder/page grids) instead of the fixed rail width. */
  fluid?: boolean;
}) {
  const action: CardAction = cardPrimaryAction(entry, state);
  const marker = jellyfinMarker(state.watch.jellyfin);
  const inLibrary = state.state === "available" || state.state === "downloaded";
  const showWatchedTick = marker.kind === "watched" && !inLibrary;
  const tone = artTone(entry.title);
  const badges: string[] = [];
  if (entry.imdb) badges.push(`★ ${fmtRating(entry.imdb)}`);
  if (entry.rt) badges.push(`${entry.rt}%`);

  const primaryChip = () => {
    const chip =
      "w-full rounded-[8px] px-3 py-1.5 text-center text-xs font-bold transition";
    if (action.type === "play-rkm")
      return (
        <button
          type="button"
          onClick={() => onPlayInRkm(entry, action.itemId)}
          className={`${chip} bg-accent text-black hover:bg-accent-hover`}
        >
          ▶ {action.label}
        </button>
      );
    if (action.type === "watch-link")
      return (
        <button
          type="button"
          onClick={() => onWatchLink(entry, action.url)}
          className={`${chip} bg-[#7C5CFF] text-white hover:bg-[#8F74FF]`}
        >
          ▶ {action.label}
        </button>
      );
    if (action.type === "download")
      return (
        <button type="button" onClick={() => onDownload(entry)} className={`${chip} bg-accent text-black hover:bg-accent-hover`}>
          ↓ Download
        </button>
      );
    const disabledChip = {
      requested: "bg-sky-600/80 text-white",
      downloading: "bg-sky-600/80 text-white",
      available: "bg-emerald-600/80 text-white",
      unavailable: "bg-surface-3/80 text-zinc-400",
    }[action.type] ?? "bg-surface-3/80 text-zinc-400";
    const label =
      action.type === "requested"
        ? "✓ Requested"
        : action.type === "downloading"
          ? `↓ Downloading ${action.progress}%`
          : action.type === "available"
            ? "✓ Available"
            : "Unavailable";
    return (
      <button type="button" disabled className={`${chip} ${disabledChip}`}>
        {label}
      </button>
    );
  };

  return (
    <article
      className={`group relative rounded-[10px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
        fluid ? "w-full min-w-0" : "w-44 shrink-0"
      }`}
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
      <div className="pointer-events-none relative aspect-[2/3] w-full overflow-hidden rounded-[10px] border border-white/[.06] bg-surface-2 transition-[transform,box-shadow,border-color] duration-200 ease-out group-hover:-translate-y-1 group-hover:scale-[1.02] group-hover:border-white/10 group-hover:shadow-card-hover">
        {/* Seeded gradient art fallback (watchlist posters are remote TMDB art —
            a failed load degrades to art, never a broken-image icon). */}
        <div aria-hidden="true" className={`absolute inset-0 art-${tone}`} />
        {entry.poster ? (
          <img
            src={entry.poster}
            loading="lazy"
            referrerPolicy="no-referrer"
            className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.05]"
            alt={entry.title}
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        ) : null}

        {/* Hover darkening + bottom gradient */}
        <div className="absolute inset-0 bg-black/0 transition duration-300 group-hover:bg-black/45" />
        <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/85 to-transparent opacity-0 transition duration-300 group-hover:opacity-100" />

        {/* badges (top-left) + type glyph */}
        <div className="absolute left-2 top-2 flex flex-col items-start gap-1">
          {badges.length > 0 && (
            <span className="rounded-md bg-black/50 px-1.5 py-0.5 text-[10px] font-semibold text-accent backdrop-blur-sm">
              {badges.join(" · ")}
            </span>
          )}
          <span className="grid h-[22px] w-[22px] place-items-center rounded-md border border-white/10 bg-black/40 text-zinc-100 backdrop-blur-sm">
            <Icon name={entry.type === "tv" ? "tv" : "film"} size={13} />
          </span>
        </div>

        {/* in-library tick (top-right) or watched tick when not in a library */}
        {(inLibrary || showWatchedTick) && (
          <span
            role="img"
            aria-label={inLibrary ? "Available in library" : "Watched"}
            title={inLibrary ? "Available in library" : "Watched"}
            className="absolute right-2 top-2 grid h-5 w-5 place-items-center rounded-full bg-emerald-500 text-[11px] font-bold text-black shadow"
          >
            <Icon name="check" size={12} strokeWidth={3} />
          </span>
        )}

        {/* amber resume bar from the Jellyfin watch link */}
        {marker.kind === "resume" && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[3px] bg-black/30">
            <div className="h-full bg-accent" style={{ width: `${marker.percent}%` }} />
          </div>
        )}

        {/* busy progress strip */}
        {action.type === "downloading" && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[3px] bg-black/30">
            <div className="h-full bg-sky-400" style={{ width: `${action.progress}%` }} />
          </div>
        )}

        {/* hover actions — gated to the visible state so invisible chips can
            never intercept card taps; group-focus-within keeps them on
            keyboard/touch. */}
        <div className="pointer-events-none absolute inset-x-2 bottom-2 z-[2] flex flex-col items-stretch gap-1.5 opacity-0 transition group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100">
          {primaryChip()}
          <button
            type="button"
            onClick={() => onTrailer(entry)}
            className="w-full rounded-[8px] bg-black/60 px-3 py-1.5 text-center text-[11px] font-semibold text-zinc-200 ring-1 ring-white/15 backdrop-blur-sm transition hover:bg-black/80 hover:text-white"
          >
            ▶ Trailer
          </button>
        </div>
      </div>

      <div className="pointer-events-none px-0.5 pt-2">
        <div className="line-clamp-2 text-[13px] font-semibold leading-snug text-zinc-200 group-hover:text-white">
          {entry.title}
        </div>
        <div className="mt-0.5 truncate text-[11px] font-medium text-zinc-500">
          {[entry.year || "", entry.genres?.[0] || ""].filter(Boolean).join(" · ")}
        </div>
      </div>
    </article>
  );
}
