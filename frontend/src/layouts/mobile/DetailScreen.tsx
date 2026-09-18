import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Icon } from "../../components/ui/Icon";
import { IconAction } from "../../components/ui/IconAction";
import { Sheet } from "../../components/ui/Sheet";
import { WatchedAction } from "../../features/library/WatchedAction";
import { useItemDetail, useLibraryItems } from "../../features/library/api";
import { useLibraryOutlet } from "../../features/library/LibraryLayout";
import {
  artTone,
  backdropUrl,
  DETAIL_NOT_FOUND_SUB,
  DETAIL_NOT_FOUND_TITLE,
  DETAIL_PARTIAL_WARNING,
  detailInProgress,
  detailMetaBits,
  detailPrimaryLabel,
  detailResumePercent,
  episodeProgress,
  fmtRuntime,
  isSeries,
  MORE_ACTION_COPY,
  moreActionsFor,
  personHeadshotUrl,
  posterUrl,
  ratingText,
  seriesPlayLabel,
  type EpisodeShape,
  type MoreActionKey,
} from "../../features/library/lib";
import { useAutoPlayDeepLink } from "../../features/library/useAutoPlayDeepLink";
import { SimilarRow } from "../../features/library/SimilarRow";
import { DownloadAction, DownloadNotice } from "../../features/offline/DownloadButton";
import { useEpisodes } from "../../features/playback/api";
import {
  episodeQueue,
  episodeThumbUrl,
  groupBySeason,
  nextPlayableEpisode,
  playLabel,
  type QueueEntry,
} from "../../features/playback/lib";
import { initials } from "../../features/auth/lib";

/**
 * `/library/item/:itemId` on a PHONE (MOBILE_FIRST_UI_PLAN §3.1, M4 — the §7.4 wireframe).
 *
 * ⚠ **What is new here, and what is not.** The desktop shows this title inside a centred `Dialog`
 * over an inert Home. On a phone that composition is wrong twice over: the modal is `90vh` of a
 * 390px-wide screen with a backdrop hero that eats a third of it, and the actions sit in the flow of
 * the page — so where "Play" lands depends on how long the synopsis is. This screen keeps the URL
 * (every entry point already navigates to it), keeps the DATA (`useItemDetail`, `useEpisodes`, the
 * library list) and keeps every RULE (`lib.ts`, `playback/lib.ts`) — and changes the composition:
 * a full-bleed 4:3 backdrop, the copy under it, the episodes as a list, and ONE action bar pinned in
 * the thumb zone.
 *
 * ⚠ **Every rule it reads already existed before this file did** — that is the whole point of M4's
 * extractions: `episodeProgress` (E6) for each row's percent and countdown, `initials` (E7) for a
 * person with no headshot, `moreActionsFor`/`MORE_ACTION_COPY` (E10) for what ⋯ offers,
 * `useAutoPlayDeepLink` (E11) for `?play=1`, `seriesPlayLabel`, `detailMetaBits` and the three
 * sentences. `layouts/importRule.ts` fails the build if this directory reaches for an HTTP client,
 * a formatter, a clock or the viewport, and `imports.test.ts` now scans these files for real.
 */
export function DetailScreen() {
  const { itemId = "" } = useParams();
  const navigate = useNavigate();
  const { startMovie, startEpisode, toggleWatched } = useLibraryOutlet();
  const detailQ = useItemDetail(itemId);
  const itemsQ = useLibraryItems();
  const [moreOpen, setMoreOpen] = useState(false);
  const [backdropFailed, setBackdropFailed] = useState(false);

  const d = detailQ.data;
  const item = itemsQ.data?.items.find((i) => i.item_id === itemId);
  const tv = (item ? isSeries(item) : false) || d?.type === "tv";
  const epQ = useEpisodes(tv ? itemId : null);

  const episodes = epQ.data?.episodes ?? [];
  const queue = episodeQueue(episodes);
  const groups = groupBySeason(episodes);
  const target = tv ? nextPlayableEpisode(episodes) : null;
  const firstEp = episodes[0] ?? null;
  const seriesPlayEp = target ?? firstEp;
  const title = d?.name ?? item?.title ?? "";
  const played = d?.play?.played ?? item?.played ?? false;
  const runtimeSec = Number(d?.runtime ?? (item?.runtime || 0));
  const resumeSec = Number(d?.play?.resume || 0);
  const percent = detailResumePercent(d?.play, runtimeSec);
  const inProgress = detailInProgress(d?.play);
  const notFound = !detailQ.isLoading && detailQ.isError && !item && !d;
  const poster = posterUrl({ item_id: itemId });
  const backdrop = d?.has_backdrop ? backdropUrl(itemId, 1200) : null;
  const metaBits = detailMetaBits({
    year: d?.year ?? item?.year,
    runtimeSec,
    isSeries: tv,
    seasonCount: groups.length,
    certification: d?.official_rating,
  });
  const rating = ratingText(d?.community_rating);
  const moreActions = moreActionsFor({
    isSeries: tv,
    inProgress,
    played,
    hasExternalLink: Boolean(item?.jellyfin_url),
  });
  const onPlayMovie = (id: string, name: string, resume: number, runtime: number) =>
    startMovie(id, name, resume, runtime);

  // ⚠ ONE implementation of the `?play=1` deep link (E11) — every search result and every poster
  // navigates by URL, and this screen is the one that has to act on it.
  useAutoPlayDeepLink({
    itemId,
    isSeries: tv,
    detail: d,
    episodes,
    seriesPlayEp,
    queue,
    resumeSec,
    runtimeSec,
    title: title || "Unknown",
    onPlayMovie,
    onPlayEpisode: startEpisode,
  });

  const runMoreAction = (key: MoreActionKey) => {
    setMoreOpen(false);
    if (key === "restart") {
      onPlayMovie(itemId, title || "Unknown", 0, runtimeSec);
    } else if (key === "untoggle") {
      if (item) toggleWatched({ ...item, played });
    } else if (item?.jellyfin_url) {
      window.open(item.jellyfin_url, "_blank", "noopener,noreferrer");
    }
  };

  if (detailQ.isLoading && !d && !item) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true">
        <div className="skeleton -mx-4 -mt-4 aspect-[4/3] rounded-b-2xl" />
        <div className="skeleton h-7 w-2/3 rounded-lg" />
        <div className="skeleton h-4 w-1/3 rounded" />
        <div className="skeleton h-12 w-full rounded-[10px]" />
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-2xl border border-dashed border-white/[.08] px-5 py-10">
        <Icon name="film" size={20} className="text-zinc-500" />
        <h1 className="text-[17px] font-bold text-zinc-100">{DETAIL_NOT_FOUND_TITLE}</h1>
        <p className="text-[13px] leading-relaxed text-zinc-400">{DETAIL_NOT_FOUND_SUB}</p>
        <button
          type="button"
          onClick={() => navigate("/library/home", { replace: true })}
          className="mt-1 inline-flex h-11 items-center gap-2 rounded-[10px] border border-white/10 bg-white/[.07] px-4 text-[14px] font-semibold text-zinc-100"
        >
          <Icon name="back" size={15} />
          Back to the library
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 pb-2">
      {/* Full-bleed backdrop. ⚠ 4:3, not the desktop's 21:10 letterbox: on a 390px screen a 21:10
          strip is a 186px band of mostly-empty art, and the copy that overlaps it on the desktop has
          nowhere to go. The phone puts the copy UNDER the art — the same composition as the phone's
          Home hero, so the two screens teach one layout. */}
      <div className="relative -mx-4 -mt-4 aspect-[4/3] w-[calc(100%+2rem)] overflow-hidden">
        <div aria-hidden="true" className={`absolute inset-0 art-${artTone(title)}`} />
        {backdrop && !backdropFailed ? (
          <img
            src={backdrop}
            alt=""
            referrerPolicy="no-referrer"
            onError={() => setBackdropFailed(true)}
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : poster ? (
          <img src={poster} alt="" className="absolute inset-0 h-full w-full object-cover object-[center_18%]" />
        ) : null}
        <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-t from-canvas via-canvas/50 to-black/30" />
        <button
          type="button"
          onClick={() => navigate(-1)}
          aria-label="Back"
          className="absolute left-3 top-3 inline-flex h-10 items-center gap-1.5 rounded-full border border-white/10 bg-black/45 px-3.5 text-[13px] font-semibold text-zinc-100 backdrop-blur-md transition active:bg-black/70"
        >
          <Icon name="back" size={15} />
          Back
        </button>
      </div>

      <section className="flex flex-col gap-2.5">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="rounded-md border border-accent/30 bg-accent/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-accent">
            {tv ? "TV Series" : "Movie"}
          </span>
          {rating ? (
            <span className="flex items-center gap-1 text-[14px] font-semibold text-zinc-100">
              <Icon name="star" size={14} filled className="text-accent" />
              {rating}
              <span className="text-[11px] font-normal text-zinc-500">/ 10</span>
            </span>
          ) : null}
        </div>

        <h1 className="text-[26px] font-bold leading-[1.08] tracking-[-0.02em] text-white">
          {title || "Loading…"}
        </h1>

        {metaBits.length > 0 ? (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] font-medium text-zinc-400">
            {metaBits.map((b, i) => (
              <span key={b} className="flex items-center gap-2">
                {i > 0 ? <span aria-hidden="true" className="h-1 w-1 rounded-full bg-zinc-600" /> : null}
                {b}
              </span>
            ))}
          </div>
        ) : null}

        {d && (d.genres ?? []).length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {(d.genres ?? []).map((g) => (
              <span
                key={g}
                className="rounded-full border border-white/[.08] bg-white/[.06] px-2.5 py-1 text-[11px] font-medium text-zinc-300"
              >
                {g}
              </span>
            ))}
          </div>
        ) : null}

        {d && (d.studios ?? []).length > 0 ? (
          <p className="text-[12px] text-zinc-500">{(d.studios ?? []).join(" · ")}</p>
        ) : null}

        {detailQ.isError && !d && !notFound ? (
          <p className="text-[12px] text-red-400">{DETAIL_PARTIAL_WARNING}</p>
        ) : null}

        {/* The progress readout, ABOVE the bar that acts on it — a person deciding whether to resume
            should see how much is left before they press the verb, not after. */}
        {!tv && inProgress && percent > 0 ? (
          <div className="flex items-center gap-3 pt-0.5">
            <div className="h-[3px] flex-1 rounded-full bg-white/10">
              <div className="h-full rounded-full bg-accent" style={{ width: `${percent}%` }} />
            </div>
            <span className="text-[11px] font-semibold tabular-nums text-zinc-400">
              {percent}% · {fmtRuntime(Math.max(1, runtimeSec - resumeSec))} left
            </span>
          </div>
        ) : null}
      </section>

      {d?.overview ? (
        <section className="flex flex-col gap-2">
          <p className="text-[14px] leading-relaxed text-zinc-300">{d.overview}</p>
        </section>
      ) : null}

      {/* Episodes (series only) — the reason a series' primary verb is not "Play". */}
      {tv ? (
        <section className="flex flex-col gap-3">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.16em] text-zinc-500">Episodes</h2>
          {epQ.isLoading ? (
            <div className="flex flex-col gap-2" aria-busy="true">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-16 w-full rounded-xl" />
              ))}
            </div>
          ) : epQ.isError ? (
            <p className="text-[13px] text-red-400">Couldn't load episodes.</p>
          ) : groups.length === 0 ? (
            <p className="text-[13px] text-zinc-500">No episodes found.</p>
          ) : (
            groups.map((group) => (
              <div key={group.season} className="flex flex-col gap-2">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                  Season {group.season}
                </h3>
                {group.episodes.map((ep) => (
                  <EpisodeRow key={ep.id} ep={ep} onPlay={() => startEpisode(ep, queue)} />
                ))}
              </div>
            ))
          )}
        </section>
      ) : null}

      {d && (d.people?.actors ?? []).length > 0 ? (
        <section className="flex flex-col gap-3">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.16em] text-zinc-500">Cast</h2>
          <div className="no-scrollbar flex gap-4 overflow-x-auto pb-1">
            {(d.people?.actors ?? []).slice(0, 10).map((p) => (
              <PersonTile key={p.id || p.name} person={p} />
            ))}
          </div>
        </section>
      ) : null}

      {(creditsLine(d?.people, "directors") || creditsLine(d?.people, "writers")) ? (
        <p className="text-[11px] text-zinc-500">
          {[creditsLine(d?.people, "directors"), creditsLine(d?.people, "writers")].filter(Boolean).join("  ·  ")}
        </p>
      ) : null}

      <DownloadNotice itemId={itemId} />

      {/* "Because you watched" — the SAME row the desktop renders, on the phone's own surface:
          `detailSurface="sheet"` swaps the desktop's card rail + centred dialog for a thumb-sized
          list + the shared suggest Sheet. ⚠ It was deliberately absent until M4's sheet existed —
          the desktop's tap opened a `Dialog`, and a row whose tap does nothing is the defect this
          project keeps re-finding. Sits ABOVE the pinned bar, which must stay the last thing in the
          flow for its sticky offset to be the bottom of the page. */}
      <SimilarRow
        itemId={itemId}
        title={title}
        localItems={itemsQ.data?.items ?? []}
        detailSurface="sheet"
      />

      {/* ⚠ THE ACTION BAR IS PINNED, and it is the ONLY primary on the screen. It sits in the thumb
          zone: `sticky bottom-<tab bar + inset + gap>` keeps it there while the page scrolls and puts
          it back in the flow at the end, without a `fixed` layer fighting the sheet or the bar. The
          clearance is DERIVED from the same tokens `AppShell` uses — a number here would be wrong on
          a notched phone, which is exactly the bug his 2026-09-16 report was about. */}
      <div className="sticky bottom-[calc(var(--m-nav-h,64px)_+_var(--rkm-safe-bottom,0px)_+_0.75rem)] z-20 -mx-4 flex items-center gap-2 border-t border-white/[.06] bg-canvas/95 px-4 py-2 backdrop-blur-xl">
        {tv && seriesPlayEp ? (
          <button
            type="button"
            onClick={() => startEpisode(seriesPlayEp, queue)}
            data-testid="detail-primary"
            className="inline-flex h-12 min-w-0 flex-1 items-center justify-center gap-2 rounded-[10px] bg-accent px-3 text-[15px] font-bold text-black transition active:bg-accent-hover"
          >
            <Icon name="play" size={16} filled />
            <span className="truncate">{seriesPlayLabel(seriesPlayEp, firstEp)}</span>
          </button>
        ) : (
          <button
            type="button"
            onClick={() =>
              onPlayMovie(itemId, title || "Unknown", inProgress ? resumeSec : 0, runtimeSec)
            }
            data-testid="detail-primary"
            className="inline-flex h-12 min-w-0 flex-1 items-center justify-center gap-2 rounded-[10px] bg-accent px-3 text-[15px] font-bold text-black transition active:bg-accent-hover"
          >
            <Icon name="play" size={16} filled />
            <span className="truncate">
              {detailPrimaryLabel(d?.play)}
              {percent > 0 ? ` (${percent}%)` : ""}
            </span>
          </button>
        )}

        {tv && epQ.isLoading ? <span className="text-[12px] text-zinc-400">Loading…</span> : null}

        {item ? <WatchedAction item={item} played={played} /> : null}

        {/* Renders NOTHING in a browser — the bridge only exists inside the iOS shell (B4). */}
        <DownloadAction itemId={itemId} title={title} />

        {/* ⚠ The ⋯ exists only when it has something to open: a control that cannot act is the defect
            M3-part-4 fixed, and `moreActionsFor` is the one rule that knows. */}
        {moreActions.length > 0 ? (
          <IconAction
            icon="more"
            label="More"
            onClick={() => setMoreOpen(true)}
            title={`More actions for ${title}`}
          />
        ) : null}
      </div>

      {moreOpen ? (
        <Sheet labelledBy="detail-more-title" onClose={() => setMoreOpen(false)}>
          <div className="mx-auto flex w-full max-w-lg flex-col gap-1 pb-2">
            <h2 id="detail-more-title" className="px-2 pb-2 text-base font-bold text-zinc-100">
              {title}
            </h2>
            {moreActions.map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => runMoreAction(key)}
                className="flex h-12 items-center gap-3 rounded-[10px] px-3 text-left text-[15px] font-medium text-zinc-200 transition active:bg-white/[.06]"
              >
                <Icon name={MORE_ACTION_COPY[key].icon} size={18} className="text-zinc-400" />
                {MORE_ACTION_COPY[key].label}
              </button>
            ))}
          </div>
        </Sheet>
      ) : null}
    </div>
  );
}

/**
 * One episode. ⚠ Its percent and countdown come from `episodeProgress` (E6) — the same function the
 * desktop row uses, which is the whole reason the extraction happened before this file existed.
 */
function EpisodeRow({ ep, onPlay }: { ep: EpisodeShape; onPlay: () => void }) {
  const { percent, inProgress, remainingLabel } = episodeProgress(ep);
  const thumb = episodeThumbUrl(ep.id);
  return (
    <div
      className={`flex items-center gap-3 rounded-xl border p-2.5 ${
        inProgress ? "border-accent/20 bg-accent/[.04]" : "border-white/[.05] bg-surface/60"
      }`}
    >
      <div className="relative h-14 w-24 shrink-0 overflow-hidden rounded-lg bg-surface-2">
        {thumb ? <img src={thumb} alt="" loading="lazy" className="h-full w-full object-cover" /> : null}
        {!ep.played && percent > 0 ? (
          <div className="absolute inset-x-0 bottom-0 h-[3px] bg-white/15">
            <div className="h-full bg-accent" style={{ width: `${percent}%` }} />
          </div>
        ) : null}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-accent/90">
          S{ep.season}E{ep.episode}
        </div>
        <div className="truncate text-[14px] font-semibold text-zinc-100">{ep.name}</div>
        <div className="mt-0.5 truncate text-[12px] text-zinc-500">
          {ep.played ? (
            <span className="flex items-center gap-1 text-emerald-400">
              <Icon name="check" size={12} strokeWidth={2.5} /> Watched
            </span>
          ) : inProgress ? (
            <span className="text-zinc-400">
              {percent}% watched{remainingLabel ? ` · ${remainingLabel}` : ""}
            </span>
          ) : (
            fmtRuntime(ep.runtime) || "Not watched"
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={onPlay}
        className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-[10px] bg-accent px-3.5 text-[13px] font-bold text-black transition active:bg-accent-hover"
      >
        <Icon name="play" size={12} filled />
        {playLabel(ep)}
      </button>
    </div>
  );
}

/**
 * A cast member. ⚠ The initials fallback is `auth/lib.ts::initials()` (E7) — the SAME function the
 * header chip uses, because two copies of that rule is how "Rajeev Kumar" comes to read differently
 * in two places.
 */
function PersonTile({ person }: { person: { id: string; name: string; has_image?: boolean; role?: string | null } }) {
  const [errored, setErrored] = useState(false);
  const src = person.has_image && !errored ? personHeadshotUrl(person.id) : null;
  return (
    <div className="flex w-16 shrink-0 flex-col items-center gap-1.5 text-center">
      <div className="grid h-16 w-16 place-items-center overflow-hidden rounded-full bg-surface-3 text-[13px] font-bold text-zinc-300 ring-1 ring-white/10">
        {src ? (
          <img
            src={src}
            alt={person.name}
            loading="lazy"
            className="h-full w-full object-cover"
            onError={() => setErrored(true)}
          />
        ) : (
          <span aria-hidden="true">{initials(person.name)}</span>
        )}
      </div>
      <span className="line-clamp-1 w-full text-[11px] font-medium text-zinc-200">{person.name}</span>
    </div>
  );
}

/** "Director: X" / "Writers: X, Y" — the same sentence the desktop page prints. */
function creditsLine(
  people: { directors?: { name: string }[]; writers?: { name: string }[] } | undefined,
  kind: "directors" | "writers",
): string | null {
  const names = (people?.[kind] ?? []).map((p) => p.name).filter(Boolean);
  if (names.length === 0) return null;
  return `${kind === "directors" ? "Director" : "Writer"}${names.length > 1 ? "s" : ""}: ${names.join(", ")}`;
}

/** Re-exported type so this file names the episode row it renders without reaching for the client. */
export type { EpisodeShape, MoreActionKey, QueueEntry };
