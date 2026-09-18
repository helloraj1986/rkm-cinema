import type { SuggestResult } from "../../lib/api/client";
import type { AmbiguousMatch } from "../watchlist/actions";
import { useSuggestDetail } from "../watchlist/api";
import { Icon } from "../../components/ui/Icon";
import { AmbiguousMatches } from "./AmbiguousMatches";
import { suggestDetailView } from "./detail";

/**
 * The suggest-detail CONTENT — the facts, the hero, and the two actions.
 *
 * ⚠ Extracted from `SuggestDetailModal` (2026-09-18) the moment a SECOND shell
 * needed it. A title that is not in the library has no `/library/item/:itemId`
 * page, so its details come from `/api/suggest/detail`; the desktop renders them
 * in a `Dialog`, and the phone renders the SAME thing in a `Sheet` because a
 * centred 90vh dialog is the wrong composition on a 390px screen. Two shells,
 * ONE renderer, ONE fetch (`useSuggestDetail`) — a second copy is how the two
 * surfaces come to disagree about a film's runtime.
 *
 * The shell owns the chrome (Dialog's trap, Sheet's drag handle and backdrop);
 * this owns what is inside it. Nothing here is viewport-aware.
 */
export function SuggestDetailBody({
  item,
  busyAdd,
  busyDownload,
  ambiguous,
  onClose,
  onAdd,
  onDownload,
}: {
  item: SuggestResult;
  busyAdd: boolean;
  busyDownload: boolean;
  /**
   * The server's "which one did you mean?" answer for THIS title's download, when there is one.
   *
   * ⚠ The shell owns this state (it is the shell that catches the mutation's error), but the
   * RENDERING lives here so the desktop dialog and the phone sheet cannot describe the same 409
   * differently. `null`/omitted renders nothing — verbatim today's behaviour.
   */
  ambiguous?: AmbiguousMatch | null;
  onClose: () => void;
  onAdd: () => void;
  onDownload: () => void;
}) {
  const { data: d, isFetching, isError } = useSuggestDetail(item.tmdb_id, item.media_type);
  const view = suggestDetailView(item, d, isError);

  return (
    <>
      <div className="relative h-52 w-full overflow-hidden sm:h-60">
        <div aria-hidden="true" className={`absolute inset-0 art-${view.tone}`} />
        {view.backdrop ? (
          <img
            src={view.backdrop}
            alt=""
            referrerPolicy="no-referrer"
            className="h-full w-full object-cover"
          />
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
        ) : view.failed ? (
          <p className="py-4 text-sm leading-relaxed text-zinc-400">
            Couldn't load full details for {item.title} — the card below still shows the basics.
          </p>
        ) : null}

        <h2 id="suggest-detail-title" className="text-2xl font-bold tracking-[-0.01em] text-white">
          {view.title}
        </h2>
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {view.chips.map((m) => (
            <span
              key={m}
              className="rounded-full border border-white/[.08] bg-white/[.06] px-2.5 py-0.5 text-xs font-medium text-zinc-300"
            >
              {m}
            </span>
          ))}
        </div>

        {view.scores.length ? (
          <div className="mt-3 flex flex-wrap gap-3 text-sm font-semibold text-accent">
            {view.scores.map((s) => (
              <span key={s} className="flex items-center gap-1">
                <Icon name="star" size={13} filled className="text-accent" />
                {s.replace("★ ", "")}
              </span>
            ))}
          </div>
        ) : null}

        <p className="mt-3 text-sm leading-relaxed text-zinc-300">{view.overview}</p>

        {view.facts.length ? (
          <dl className="mt-4 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
            {view.facts.map(([k, v]) => (
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

        {/* ⚠ BELOW the actions, not above them: the person pressed Download, so the answer to that
            press belongs next to where they pressed. It is also the one failure with structure
            behind it (a 409's candidate list) — a toast could only ever carry the sentence. */}
        {ambiguous ? <AmbiguousMatches match={ambiguous} /> : null}
      </div>
    </>
  );
}
