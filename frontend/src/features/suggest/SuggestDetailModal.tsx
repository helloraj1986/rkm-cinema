import type { SuggestResult } from "../../lib/api/client";
import { useSuggestDetail } from "../watchlist/api";
import { fmtRating, fmtRuntimeMin } from "../watchlist/lib";
import { artTone } from "../library/lib";
import { Dialog } from "../../components/ui/Dialog";
import { Icon } from "../../components/ui/Icon";

/**
 * Suggest detail modal (legacy `openSuggestDetail` parity): fetches full
 * TMDB + IMDb metadata on demand (/api/suggest/detail), shows backdrop hero,
 * chips, IMDb/TMDB scores, synopsis, director/cast/votes facts, and the
 * Add-to-Watchlist + Download actions (shared with the grid card).
 *
 * Premium pass (2026-09): Dialog shell (§51 modal chrome + focus trap/restore),
 * §14 pill chips, §71 button hierarchy, seeded-art fallback (no emoji).
 */
export function SuggestDetailModal({
  item,
  busyAdd,
  busyDownload,
  onClose,
  onAdd,
  onDownload,
}: {
  item: SuggestResult;
  busyAdd: boolean;
  busyDownload: boolean;
  onClose: () => void;
  onAdd: () => void;
  onDownload: () => void;
}) {
  const { data: d, isFetching, isError } = useSuggestDetail(item.tmdb_id, item.media_type);

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
  const tone = artTone(title);

  return (
    <Dialog onClose={onClose} labelledBy="suggest-detail-title">
      <div className="relative h-52 w-full overflow-hidden sm:h-60">
        <div aria-hidden="true" className={`absolute inset-0 art-${tone}`} />
        {bg ? (
          <img src={bg} alt="" referrerPolicy="no-referrer" className="h-full w-full object-cover" />
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

      <div className="px-6 pb-6 pt-4">
        {isFetching ? (
          <div className="py-8" role="status">
            <div className="skeleton h-7 w-2/3 rounded-lg" />
            <div className="skeleton mt-3 h-4 w-1/2 rounded" />
            <div className="skeleton mt-5 h-16 w-full rounded-lg" />
          </div>
        ) : isError || (d && d.ok === false) ? (
          <p className="py-4 text-sm leading-relaxed text-zinc-400">
            Couldn't load full details for {item.title} — the card below still shows the basics.
          </p>
        ) : null}

        <h2 id="suggest-detail-title" className="text-2xl font-bold tracking-[-0.01em] text-white">
          {title}
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
              <span key={s} className="flex items-center gap-1">
                <Icon name="star" size={13} filled className="text-accent" />
                {s.replace("★ ", "")}
              </span>
            ))}
          </div>
        ) : null}

        <p className="mt-3 text-sm leading-relaxed text-zinc-300">
          {d?.overview || item.overview || "No synopsis available yet."}
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

        <div className="mt-5 flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={onAdd}
            disabled={busyAdd || item.in_watchlist}
            className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-white/10 bg-white/[.07] px-4 text-sm font-bold text-zinc-100 transition hover:bg-white/[.12] disabled:opacity-60"
          >
            <Icon name="plus" size={15} />
            {busyAdd ? "Adding…" : item.in_watchlist ? "✓ Added to Watchlist" : "Add to Watchlist"}
          </button>
          <button
            type="button"
            onClick={onDownload}
            disabled={busyDownload}
            className="inline-flex h-10 items-center gap-2 rounded-[10px] bg-accent px-4 text-sm font-bold text-black transition hover:bg-accent-hover disabled:opacity-60"
          >
            <Icon name="download" size={15} />
            {busyDownload ? "Starting download…" : "Download"}
          </button>
        </div>
      </div>
    </Dialog>
  );
}
