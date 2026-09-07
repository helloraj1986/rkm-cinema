import { useEffect, useRef } from "react";
import type { SuggestResult } from "../../lib/api/client";
import { useSuggestDetail } from "../watchlist/api";
import { fmtRating, fmtRuntimeMin } from "../watchlist/lib";

/**
 * Suggest detail modal (legacy `openSuggestDetail` parity): fetches full
 * TMDB + IMDb metadata on demand (/api/suggest/detail), shows backdrop hero,
 * chips, IMDb/TMDB scores, synopsis, director/cast/votes facts, and the
 * Add-to-Watchlist + Download actions (shared with the grid card).
 */
export function SuggestDetailModal({
  item,
  busy,
  onClose,
  onAdd,
  onDownload,
}: {
  item: SuggestResult;
  busy: boolean;
  onClose: () => void;
  onAdd: () => void;
  onDownload: () => void;
}) {
  const { data: d, isFetching, isError } = useSuggestDetail(item.tmdb_id, item.media_type);
  const ref = useRef<HTMLDivElement>(null);

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

  const title = d?.title || item.title;
  const typeLabel = d?.media_type === "tv" ? "TV Series" : "Movie";
  const meta = [d?.year ?? item.year, d?.cert, d?.runtime ? fmtRuntimeMin(d.runtime) : "", typeLabel]
    .filter(Boolean)
    .map(String);
  const genres = (d?.genres || item.genres || []).slice(0, 4);
  const scores: string[] = [];
  if (d && d.imdb_rating > 0) scores.push(`★ ${fmtRating(d.imdb_rating)} IMDb`);
  else if (d?.imdb_id) scores.push("IMDb unavailable");
  if (d && d.tmdb_score > 0) scores.push(`★ ${fmtRating(d.tmdb_score)} TMDB`);
  const facts: [string, string][] = [];
  if (d?.director) facts.push(["Director", d.director]);
  if (d?.cast?.length) facts.push(["Starring", d.cast.slice(0, 5).join(" · ")]);
  if (d?.vote_count) facts.push(["Votes", Number(d.vote_count).toLocaleString()]);
  const bg = d?.backdrop || d?.poster || item.backdrop || item.poster || "";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`${title} details`}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl outline-none"
      >
        <div className="relative h-52 w-full overflow-hidden sm:h-60">
          {bg ? (
            <img src={bg} alt="" referrerPolicy="no-referrer" className="h-full w-full object-cover" />
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

        <div className="px-6 pb-6 pt-4">
          {isFetching ? (
            <div className="py-10 text-center text-sm text-zinc-500">Fetching details…</div>
          ) : isError || (d && d.ok === false) ? (
            <div className="py-10 text-center text-sm text-zinc-500">
              Couldn't load details for {item.title}. The grid card still shows the basics below.
            </div>
          ) : null}

          <h2 className="text-2xl font-bold text-white">{title}</h2>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {[...meta, ...genres].map((m) => (
              <span key={m} className="rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300">
                {m}
              </span>
            ))}
          </div>

          {scores.length ? (
            <div className="mt-3 flex flex-wrap gap-3 text-sm font-semibold text-amber-300">
              {scores.map((s) => (
                <span key={s}>{s}</span>
              ))}
            </div>
          ) : null}

          <p className="mt-3 text-sm leading-relaxed text-zinc-300">
            {d?.overview || item.overview || "No synopsis available yet."}
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

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onAdd}
              disabled={busy || item.in_watchlist}
              className="rounded-full bg-zinc-800 px-4 py-2 text-sm font-bold text-zinc-100 ring-1 ring-zinc-600 hover:bg-zinc-700 disabled:opacity-60"
            >
              {busy ? "Adding…" : item.in_watchlist ? "✓ Added to Watchlist" : "＋ Add to Watchlist"}
            </button>
            <button
              type="button"
              onClick={onDownload}
              disabled={busy}
              className="rounded-full bg-amber-400 px-4 py-2 text-sm font-bold text-black hover:bg-amber-300 disabled:opacity-60"
            >
              ↓ Download
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
