import { useEffect, useRef, useState } from "react";
import type { WatchlistEntry } from "../../lib/api/client";
import {
  canDownload,
  fmtRating,
  fmtRuntimeMin,
  jellyfinMarker,
  STATE_LABEL,
  type ResolvedState,
} from "./lib";

/**
 * Detail modal for a watchlist entry (legacy `openModal` parity): backdrop
 * hero + floating poster, chips, scores, synopsis, director/cast/added facts,
 * and the state-driven action row (Play in RKM / Watch on Plex·Emby·Jellyfin /
 * Download with progress) + trailer embed. Esc / ✕ / backdrop-click close.
 */
export function WatchlistDetail({
  entry,
  state,
  onClose,
  onDownload,
  onPlayInRkm,
  onWatchLink,
  openTrailer = false,
}: {
  entry: WatchlistEntry;
  state: ResolvedState;
  onClose: () => void;
  onDownload: (entry: WatchlistEntry) => void;
  onPlayInRkm: (entry: WatchlistEntry, itemId: string) => void;
  onWatchLink: (entry: WatchlistEntry, url: string) => void;
  openTrailer?: boolean;
}) {
  const [showTrailer, setShowTrailer] = useState(openTrailer);
  const ref = useRef<HTMLDivElement>(null);
  const trailerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    document.body.style.overflow = "hidden";
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  // When a trailer is opened (button click, or the card's Trailer action opens
  // the modal with openTrailer=true), bring it into view — it sits below the
  // fold on long entries and users shouldn't have to scroll to find it.
  useEffect(() => {
    if (showTrailer) {
      const t = window.setTimeout(() => {
        trailerRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 120);
      return () => window.clearTimeout(t);
    }
  }, [showTrailer]);

  const meta: string[] = [entry.year, entry.lang, entry.cert, entry.runtime ? fmtRuntimeMin(entry.runtime) : ""]
    .filter(Boolean)
    .map(String);
  const genres = (entry.genres || []).slice(0, 4);
  const facts: [string, string][] = [];
  if (entry.director) facts.push(["Director", entry.director]);
  if (entry.cast?.length) facts.push(["Starring", entry.cast.slice(0, 5).join(" · ")]);
  if (entry.type === "tv") facts.push(["Format", "TV Series"]);
  if (entry.added) facts.push(["Added", entry.added]);

  const scores: string[] = [];
  if (entry.imdb) scores.push(`★ ${fmtRating(entry.imdb)} IMDb`);
  if (entry.tmdbScore) scores.push(`${fmtRating(entry.tmdbScore * 10)}% TMDB`);
  if (entry.rt) scores.push(`${entry.rt}% Rotten Tomatoes`);

  const marker = jellyfinMarker(state.watch.jellyfin);
  const jf = state.watch.jellyfin;
  const downloading = state.state === "downloading";
  const label = STATE_LABEL[state.state] ?? state.state;
  const background = entry.backdrop || entry.poster || "";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`${entry.title} details`}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl outline-none"
      >
        {/* backdrop hero */}
        <div className="relative h-56 w-full overflow-hidden sm:h-64">
          {background ? (
            <img src={background} alt="" referrerPolicy="no-referrer" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full items-center justify-center bg-zinc-900 text-4xl">🎬</div>
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-zinc-950 via-zinc-950/40 to-transparent" />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-black/60 text-zinc-200 ring-1 ring-zinc-600 hover:bg-black hover:text-white"
          >
            ✕
          </button>
        </div>

        <div className="relative -mt-20 px-6 pb-6">
          {/* floating poster */}
          <div className="pointer-events-none float-left mr-4 hidden w-32 overflow-hidden rounded-lg border border-zinc-700 shadow-2xl sm:block">
            {entry.poster ? (
              <img src={entry.poster} alt="" referrerPolicy="no-referrer" className="aspect-[2/3] w-full object-cover" />
            ) : (
              <div className="flex aspect-[2/3] items-center justify-center bg-zinc-900 text-3xl">🎬</div>
            )}
          </div>

          <h2 className="text-2xl font-bold text-white">{entry.title}</h2>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {[...meta, ...genres].map((m) => (
              <span key={m} className="rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300">
                {m}
              </span>
            ))}
          </div>

          {scores.length ? (
            <div className="mt-3 flex flex-wrap gap-3 text-sm">
              {scores.map((s) => (
                <span key={s} className="font-semibold text-amber-300">
                  {s}
                </span>
              ))}
            </div>
          ) : null}

          <p className="mt-3 text-sm leading-relaxed text-zinc-300">
            {entry.overview || "No synopsis available yet."}
          </p>

          {facts.length ? (
            <dl className="mt-4 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
              {facts.map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <dt className="shrink-0 font-semibold uppercase tracking-wide text-zinc-500">{k}</dt>
                  <dd className="text-zinc-300">{v}</dd>
                </div>
              ))}
            </dl>
          ) : null}

          {/* state strip for in-flight titles */}
          {state.state !== "not_added" && (
            <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900/70 px-3 py-2 text-xs text-zinc-400">
              <span className="font-semibold uppercase tracking-wide text-zinc-500">Status · </span>
              {label}
              {state.detail ? ` — ${state.detail}` : ""}
              {downloading && state.progress != null ? ` (${Math.min(99, state.progress)}%)` : ""}
            </div>
          )}

          {/* actions */}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {state.capabilities.can_watch ? (
              <>
                {jf?.available && jf.item_id ? (
                  <button
                    type="button"
                    onClick={() => onPlayInRkm(entry, String(jf.item_id))}
                    className="rounded-full bg-amber-400 px-4 py-2 text-sm font-bold text-black hover:bg-amber-300"
                  >
                    ▶ {entry.type === "tv" ? "Episodes" : "Play in RKM"}
                  </button>
                ) : null}
                {jf?.available && jf.url ? (
                  <button
                    type="button"
                    onClick={() => onWatchLink(entry, String(jf.url))}
                    className="rounded-full bg-sky-600 px-4 py-2 text-sm font-bold text-white hover:bg-sky-500"
                  >
                    ▶ Watch on Jellyfin
                  </button>
                ) : null}
                {state.plexUrl ? (
                  <button
                    type="button"
                    onClick={() => onWatchLink(entry, state.plexUrl)}
                    className="rounded-full bg-violet-600 px-4 py-2 text-sm font-bold text-white hover:bg-violet-500"
                  >
                    ▶ Watch on Plex
                  </button>
                ) : null}
                {state.embyUrl ? (
                  <button
                    type="button"
                    onClick={() => onWatchLink(entry, state.embyUrl)}
                    className="rounded-full bg-fuchsia-700 px-4 py-2 text-sm font-bold text-white hover:bg-fuchsia-600"
                  >
                    ▶ Watch on Emby
                  </button>
                ) : null}
                {!(jf?.available && jf.item_id) && !state.plexUrl && !state.embyUrl && !(jf?.available && jf.url) ? (
                  <button type="button" disabled className="rounded-full bg-emerald-600/70 px-4 py-2 text-sm font-bold text-white">
                    ✓ Available
                  </button>
                ) : null}
              </>
            ) : canDownload(state) ? (
              <button
                type="button"
                onClick={() => onDownload(entry)}
                className="rounded-full bg-amber-400 px-4 py-2 text-sm font-bold text-black hover:bg-amber-300"
              >
                ↓ Download
              </button>
            ) : downloading ? (
              <button type="button" disabled className="rounded-full bg-sky-600/80 px-4 py-2 text-sm font-bold text-white">
                ↓ Downloading {Math.min(99, state.progress || 0)}%
              </button>
            ) : (
              <button type="button" disabled className="rounded-full bg-emerald-600/70 px-4 py-2 text-sm font-bold text-white">
                ✓ {label}
              </button>
            )}

            {entry.trailerId ? (
              <button
                type="button"
                onClick={() => setShowTrailer((s) => !s)}
                className="rounded-full bg-zinc-800 px-4 py-2 text-sm font-semibold text-zinc-200 ring-1 ring-zinc-600 hover:bg-zinc-700"
              >
                ▶ {showTrailer ? "Hide Trailer" : "Watch Trailer"}
              </button>
            ) : (
              <a
                href={entry.trailerUrl || `https://www.youtube.com/results?search_query=${encodeURIComponent(`${entry.title} trailer`)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-full bg-zinc-800 px-4 py-2 text-sm font-semibold text-zinc-200 ring-1 ring-zinc-600 hover:bg-zinc-700"
              >
                Search YouTube
              </a>
            )}
          </div>

          {showTrailer && entry.trailerId ? (
            <div
              ref={trailerRef}
              data-testid="trailer-embed"
              className="mt-4 aspect-video w-full overflow-hidden rounded-xl border border-zinc-800"
            >
              <iframe
                title={`${entry.title} trailer`}
                src={`https://www.youtube.com/embed/${entry.trailerId}?autoplay=1&rel=0&color=white`}
                allow="autoplay; encrypted-media; picture-in-picture"
                allowFullScreen
                className="h-full w-full"
              />
            </div>
          ) : null}
          {marker.kind === "resume" && !state.capabilities.can_watch ? (
            <div className="mt-2 h-1 w-full rounded bg-zinc-700">
              <div className="h-full rounded bg-amber-400" style={{ width: `${marker.percent}%` }} />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
