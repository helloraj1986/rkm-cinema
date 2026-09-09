import type { SuggestResult } from "../../lib/api/client";
import { artTone } from "../library/lib";
import { Icon } from "../../components/ui/Icon";

/**
 * One suggest result card (legacy `suggestCardMarkup` parity): score + type
 * badges, On-Watchlist / In-Library flags, Add-to-Watchlist + Download hover
 * actions, and whole-card click → the full detail modal.
 *
 * Premium pass (2026-09): matches the WatchCard/MediaCard card language —
 * seeded-art fallback (§58, never an emoji), layered hover lift, §71 pill
 * hierarchy (accent primary + glass secondary), focus-visible ring.
 */
export function SuggestCard({
  item,
  busyAdd,
  busyDownload,
  onAdd,
  onDownload,
  onOpen,
}: {
  item: SuggestResult;
  busyAdd: boolean;
  busyDownload: boolean;
  onAdd: () => void;
  onDownload: () => void;
  onOpen: () => void;
}) {
  const tv = item.media_type === "tv";
  const tone = artTone(item.title);
  const chip =
    "w-full rounded-[8px] px-3 py-1.5 text-center text-xs font-bold transition disabled:opacity-70";

  return (
    <div
      className="group relative w-40 shrink-0 cursor-pointer rounded-[10px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      data-testid="suggest-card"
      role="button"
      tabIndex={0}
      aria-label={`${item.title} (${item.year || ""})`}
      onClick={(e) => {
        // Add/Download buttons handle themselves — a card click opens detail.
        if ((e.target as HTMLElement).closest("button, a")) return;
        onOpen();
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          if ((e.target as HTMLElement).closest("button, a")) return;
          e.preventDefault();
          onOpen();
        }
      }}
    >
      <div className="pointer-events-none relative aspect-[2/3] w-full overflow-hidden rounded-[10px] border border-white/[.06] bg-surface-2 transition-[transform,box-shadow,border-color] duration-200 ease-out group-hover:-translate-y-1 group-hover:scale-[1.02] group-hover:border-white/10 group-hover:shadow-card-hover">
        {/* Seeded gradient art fallback under the poster (§58) — if the poster
            urns or is missing the card degrades to art, never a broken icon. */}
        <div aria-hidden="true" className={`absolute inset-0 art-${tone}`} />
        {item.poster ? (
          <img
            src={item.poster}
            loading="lazy"
            referrerPolicy="no-referrer"
            className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.05]"
            alt={item.title}
            onError={(e) => ((e.currentTarget as HTMLImageElement).style.display = "none")}
          />
        ) : null}
        <div className="absolute inset-0 bg-black/0 transition duration-300 group-hover:bg-black/45" />
        <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/85 to-transparent opacity-0 transition duration-300 group-hover:opacity-100" />

        {/* badges */}
        <div className="absolute left-2 top-2 flex flex-col items-start gap-1">
          {item.tmdb_score ? (
            <span className="rounded-md bg-black/50 px-1.5 py-0.5 text-[10px] font-semibold text-accent backdrop-blur-sm">
              ★ {item.tmdb_score.toFixed(1)}
            </span>
          ) : null}
          <span className="grid h-[22px] w-[22px] place-items-center rounded-md border border-white/10 bg-black/40 text-zinc-100 backdrop-blur-sm">
            <Icon name={tv ? "tv" : "film"} size={13} />
          </span>
        </div>
        <div className="absolute right-2 top-2 flex flex-col items-end gap-1">
          {item.in_watchlist ? (
            <span className="flex items-center gap-1 rounded-md bg-black/60 px-1.5 py-0.5 text-[10px] font-bold text-accent backdrop-blur-sm">
              <Icon name="check" size={10} strokeWidth={3} /> Watchlist
            </span>
          ) : null}
          {item.in_library ? (
            <span className="flex items-center gap-1 rounded-md bg-black/60 px-1.5 py-0.5 text-[10px] font-bold text-emerald-400 backdrop-blur-sm">
              <Icon name="check" size={10} strokeWidth={3} /> Library
            </span>
          ) : null}
        </div>

        {/* hover actions — pointer-events-auto: the poster wrapper is
            pointer-events-none, so without this clicks fall through to the
            card and open the detail instead of pressing the button. */}
        <div className="pointer-events-auto absolute inset-x-2 bottom-2 z-[2] flex flex-col items-stretch gap-1.5 opacity-0 transition group-hover:opacity-100">
          <button
            type="button"
            onClick={onAdd}
            disabled={busyAdd || item.in_watchlist}
            className={`${chip} ${item.in_watchlist ? "bg-black/60 text-accent ring-1 ring-white/15" : "bg-accent text-black hover:bg-accent-hover"}`}
          >
            {busyAdd ? "Adding…" : item.in_watchlist ? "✓ Added" : "＋ Add to Watchlist"}
          </button>
          <button
            type="button"
            onClick={onDownload}
            disabled={busyDownload}
            className={`${chip} bg-black/60 text-zinc-100 ring-1 ring-white/15 backdrop-blur-sm hover:bg-black/80 hover:text-white`}
          >
            {busyDownload ? "Starting download…" : "↓ Download"}
          </button>
        </div>
      </div>

      <div className="pointer-events-none px-0.5 pt-2">
        <div className="line-clamp-2 text-[13px] font-semibold leading-snug text-zinc-200 group-hover:text-white">
          {item.title}
        </div>
        <div className="mt-0.5 flex items-center justify-between gap-2 text-[11px] font-medium text-zinc-500">
          <span className="shrink-0">{item.year || ""}</span>
          {item.genres?.[0] ? <span className="truncate">{item.genres[0]}</span> : null}
        </div>
      </div>
    </div>
  );
}
