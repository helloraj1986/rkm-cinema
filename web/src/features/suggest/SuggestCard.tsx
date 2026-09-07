import type { SuggestResult } from "../../lib/api/client";

/**
 * One suggest result card (legacy `suggestCardMarkup` parity): score + type
 * badges, On-Watchlist / In-Library flags, Add-to-Watchlist + Download hover
 * actions, and whole-card click → the full detail modal.
 */
export function SuggestCard({
  item,
  busy,
  onAdd,
  onDownload,
  onOpen,
}: {
  item: SuggestResult;
  busy: boolean;
  onAdd: () => void;
  onDownload: () => void;
  onOpen: () => void;
}) {
  const tv = item.media_type === "tv";
  return (
    <div
      className="group relative w-40 shrink-0 cursor-pointer rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400"
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
      <div className="pointer-events-none relative aspect-[2/3] w-full overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 transition duration-300 group-hover:-translate-y-1 group-hover:border-zinc-600 group-hover:shadow-xl group-hover:shadow-black/50">
        {item.poster ? (
          <img
            src={item.poster}
            loading="lazy"
            referrerPolicy="no-referrer"
            className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-105"
            alt={item.title}
            onError={(e) => ((e.currentTarget as HTMLImageElement).style.display = "none")}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-3xl" aria-hidden="true">
            🎬
          </div>
        )}
        <div className="absolute inset-0 bg-black/0 transition duration-300 group-hover:bg-black/45" />
        <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/80 to-transparent opacity-0 transition duration-300 group-hover:opacity-100" />

        {/* badges */}
        <div className="absolute left-2 top-2 flex flex-col items-start gap-1">
          {item.tmdb_score ? (
            <span className="rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">
              ★ {item.tmdb_score.toFixed(1)}
            </span>
          ) : null}
          <span className="rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-zinc-200">
            {tv ? "TV" : "MOVIE"}
          </span>
        </div>
        <div className="absolute right-2 top-2 flex flex-col items-end gap-1">
          {item.in_watchlist ? (
            <span className="rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-bold text-amber-300">On Watchlist</span>
          ) : null}
          {item.in_library ? (
            <span className="rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-bold text-emerald-400">In Library</span>
          ) : null}
        </div>

        {/* hover actions */}
        <div className="absolute inset-x-2 bottom-2 z-[2] flex flex-col items-stretch gap-1.5 opacity-0 transition group-hover:opacity-100">
          <button
            type="button"
            onClick={onAdd}
            disabled={busy || item.in_watchlist}
            className="rounded-full bg-zinc-200/90 px-3 py-1.5 text-center text-xs font-bold text-black hover:bg-white disabled:opacity-70"
          >
            {busy ? "Adding…" : item.in_watchlist ? "✓ Added" : "＋ Add to Watchlist"}
          </button>
          <button
            type="button"
            onClick={onDownload}
            disabled={busy}
            className="rounded-full bg-amber-400 px-3 py-1.5 text-center text-xs font-bold text-black hover:bg-amber-300 disabled:opacity-60"
          >
            {busy ? "Working…" : "↓ Download"}
          </button>
        </div>
      </div>

      <div className="pointer-events-none px-0.5 pt-1.5">
        <div className="truncate text-sm font-medium text-zinc-100 group-hover:text-white">{item.title}</div>
        <div className="flex items-center justify-between text-xs text-zinc-500">
          <span>{item.year || ""}</span>
          {item.genres?.[0] ? <span className="truncate pl-2">{item.genres[0]}</span> : null}
        </div>
      </div>
    </div>
  );
}
