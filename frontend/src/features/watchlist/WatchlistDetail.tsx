import { useEffect, useRef, useState } from "react";
import type { WatchlistEntry } from "../../lib/api/client";
import { artTone } from "../library/lib";
import {
  canDownload,
  fmtRating,
  fmtRuntimeMin,
  jellyfinMarker,
  STATE_LABEL,
  type ResolvedState,
} from "./lib";
import { Dialog } from "../../components/ui/Dialog";
import { Icon } from "../../components/ui/Icon";

const REDUCED_MOTION =
  typeof window !== "undefined" &&
  window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Detail modal for a watchlist entry (legacy `openModal` parity): backdrop
 * hero + floating poster, chips, scores, synopsis, director/cast/added facts,
 * and the state-driven action row (Play in RKM / Watch on Jellyfin /
 * Download with progress) + trailer embed. Esc / ✕ / backdrop-click close.
 *
 * Premium pass (2026-09): Dialog shell (§51 modal chrome + focus trap/restore),
 * §14 pill chips, seeded-art fallback, Icon close, reduced-motion-safe scroll.
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
  const trailerRef = useRef<HTMLDivElement>(null);

  // When a trailer is opened (button click, or the card's Trailer action opens
  // the modal with openTrailer=true), bring it into view — it sits below the
  // fold on long entries and users shouldn't have to scroll to find it.
  useEffect(() => {
    if (showTrailer) {
      const t = window.setTimeout(() => {
        trailerRef.current?.scrollIntoView({ behavior: REDUCED_MOTION ? "auto" : "smooth", block: "nearest" });
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
  const tone = artTone(entry.title);

  const actionBtn =
    "inline-flex h-10 items-center gap-2 rounded-[10px] px-4 text-sm font-bold transition disabled:opacity-60";
  const secondaryBtn = `${actionBtn} border border-white/10 bg-white/[.07] text-zinc-100 hover:bg-white/[.12]`;

  return (
    <Dialog onClose={onClose} labelledBy="watchlist-detail-title">
      {/* backdrop hero */}
      <div className="relative h-56 w-full overflow-hidden sm:h-64">
        <div aria-hidden="true" className={`absolute inset-0 art-${tone}`} />
        {background ? (
          <img src={background} alt="" referrerPolicy="no-referrer" className="h-full w-full object-cover" />
        ) : null}
        <div className="absolute inset-0 bg-gradient-to-t from-surface-2 via-surface-2/40 to-transparent" />
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-3 top-3 grid h-9 w-9 place-items-center rounded-full bg-black/60 text-zinc-100 ring-1 ring-white/15 backdrop-blur-sm transition hover:bg-black hover:text-white"
        >
          <Icon name="close" size={16} />
        </button>
      </div>

      <div className="relative px-6 pb-6">
        {/* floating poster */}
        <div className="pointer-events-none float-left -mt-12 mr-4 hidden w-28 overflow-hidden rounded-xl border border-white/10 shadow-modal sm:block">
          <div aria-hidden="true" className={`relative aspect-[2/3] w-full art-${tone}`}>
            {entry.poster ? (
              <img src={entry.poster} alt="" referrerPolicy="no-referrer" className="absolute inset-0 h-full w-full object-cover" />
            ) : null}
          </div>
        </div>

        <h2 id="watchlist-detail-title" className="text-2xl font-bold tracking-[-0.01em] text-white">
          {entry.title}
        </h2>
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {[...meta, ...genres].map((m) => (
            <span
              key={m}
              className="rounded-full border border-white/[.08] bg-white/[.06] px-2.5 py-0.5 text-xs font-medium text-zinc-300"
            >
              {m}
            </span>
          ))}
        </div>

        {scores.length ? (
          <div className="mt-3 flex flex-wrap gap-3 text-sm font-semibold text-accent">
            {scores.map((s) => (
              <span key={s}>{s.replace("★ ", "★ ")}</span>
            ))}
          </div>
        ) : null}

        <p className="mt-3 text-sm leading-relaxed text-zinc-300">
          {entry.overview || "No synopsis available yet."}
        </p>

        {facts.length ? (
          <dl className="mt-4 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
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
          <div className="mt-4 rounded-lg border border-white/[.06] bg-white/[.04] px-3 py-2 text-xs text-zinc-400">
            <span className="font-semibold uppercase tracking-wide text-zinc-500">Status · </span>
            {label}
            {state.detail ? ` — ${state.detail}` : ""}
            {downloading && state.progress != null ? ` (${Math.min(99, state.progress)}%)` : ""}
          </div>
        )}

        {/* actions */}
        <div className="mt-5 flex flex-wrap items-center gap-2.5">
          {state.capabilities.can_watch ? (
            <>
              {jf?.available && jf.item_id ? (
                <button
                  type="button"
                  onClick={() => onPlayInRkm(entry, String(jf.item_id))}
                  className={`${actionBtn} bg-accent text-black hover:bg-accent-hover`}
                >
                  <Icon name="play" size={14} filled />
                  {entry.type === "tv" ? "Episodes" : "Play in RKM"}
                </button>
              ) : null}
              {jf?.available && jf.url ? (
                <button type="button" onClick={() => onWatchLink(entry, String(jf.url))} className={`${actionBtn} bg-sky-600 text-white hover:bg-sky-500`}>
                  ▶ Watch on Jellyfin
                </button>
              ) : null}
              {!(jf?.available && jf.item_id) && !(jf?.available && jf.url) ? (
                <button type="button" disabled className={`${actionBtn} bg-emerald-600/70 text-white`}>
                  <Icon name="check" size={14} />
                  Available
                </button>
              ) : null}
            </>
          ) : canDownload(state) ? (
            <button type="button" onClick={() => onDownload(entry)} className={`${actionBtn} bg-accent text-black hover:bg-accent-hover`}>
              <Icon name="download" size={15} />
              Download
            </button>
          ) : downloading ? (
            <button type="button" disabled className={`${actionBtn} bg-sky-600/80 text-white`}>
              <Icon name="download" size={15} />
              Downloading {Math.min(99, state.progress || 0)}%
            </button>
          ) : (
            <button type="button" disabled className={`${actionBtn} bg-emerald-600/70 text-white`}>
              <Icon name="check" size={14} />
              {label}
            </button>
          )}

          {entry.trailerId ? (
            <button type="button" onClick={() => setShowTrailer((s) => !s)} className={secondaryBtn}>
              <Icon name="play" size={13} />
              {showTrailer ? "Hide Trailer" : "Watch Trailer"}
            </button>
          ) : (
            <a
              href={entry.trailerUrl || `https://www.youtube.com/results?search_query=${encodeURIComponent(`${entry.title} trailer`)}`}
              target="_blank"
              rel="noopener noreferrer"
              className={secondaryBtn}
            >
              <Icon name="external" size={14} />
              Search YouTube
            </a>
          )}
        </div>

        {showTrailer && entry.trailerId ? (
          <div
            ref={trailerRef}
            data-testid="trailer-embed"
            className="mt-4 aspect-video w-full overflow-hidden rounded-xl border border-white/[.08]"
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
          <div className="mt-3 h-1 w-full rounded bg-white/10">
            <div className="h-full rounded bg-accent" style={{ width: `${marker.percent}%` }} />
          </div>
        ) : null}
      </div>
    </Dialog>
  );
}
