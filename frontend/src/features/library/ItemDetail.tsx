import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import {
  api,
  type DetailPeople,
  type DetailPerson,
  type EpisodeShape,
  type ItemDetail as ItemDetailShape,
  type MediaItem,
} from "../../lib/api/client";
import { useItemDetail, useLibraryItems } from "./api";
import { SimilarRow } from "./SimilarRow";
import { useEpisodes } from "../playback/api";
import {
  episodeCode,
  episodeQueue,
  episodeThumbUrl,
  groupBySeason,
  nextPlayableEpisode,
  playLabel,
  type QueueEntry,
} from "../playback/lib";
import {
  artTone,
  detailInProgress,
  detailPrimaryLabel,
  detailResumePercent,
  fmtRuntime,
  isSeries,
  personHeadshotUrl,
  posterUrl,
  ratingText,
} from "./lib";
import { Icon } from "../../components/ui/Icon";
import { PopupMenu } from "../../components/ui/PopupMenu";

function EpisodeRow({
  ep,
  queue,
  onPlay,
}: {
  ep: EpisodeShape;
  queue: QueueEntry[];
  onPlay: (ep: EpisodeShape, queue: QueueEntry[]) => void;
}) {
  const percent =
    ep.runtime > 0 ? Math.min(100, Math.round(((ep.playback_position || 0) / ep.runtime) * 100)) : 0;
  const inProgress = !ep.played && ep.playback_position > 0;
  return (
    <div
      className={`flex items-center gap-4 rounded-xl border p-2.5 pr-3 transition-colors ${
        inProgress
          ? "border-accent/20 bg-accent/[.04] shadow-[inset_3px_0_0_0_var(--accent)]"
          : "border-transparent bg-surface-2/50 hover:bg-surface-2"
      }`}
    >
      <div className="relative h-[54px] w-24 shrink-0 overflow-hidden rounded-lg bg-surface-2">
        {episodeThumbUrl(ep.id) ? (
          <img
            src={episodeThumbUrl(ep.id) as string}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        ) : null}
        {!ep.played && percent > 0 && (
          <div className="absolute inset-x-0 bottom-0 h-[3px] bg-white/15">
            <div className="h-full bg-accent" style={{ width: `${percent}%` }} />
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2.5">
          <span className="shrink-0 text-[11px] font-bold uppercase tracking-[0.08em] text-accent/90">
            {episodeCode(ep)}
          </span>
          <span className="truncate text-sm font-medium text-zinc-100">{ep.name}</span>
        </div>
        {ep.played ? (
          <span className="mt-0.5 flex items-center gap-1 text-xs text-emerald-400">
            <Icon name="check" size={12} strokeWidth={2.5} /> Watched
          </span>
        ) : inProgress ? (
          <span className="mt-0.5 text-xs text-zinc-400">
            {percent}% watched · {fmtRuntime(Math.max(1, ep.runtime - (ep.playback_position || 0)))} left
          </span>
        ) : (
          <span className="mt-0.5 text-xs text-zinc-500">{fmtRuntime(ep.runtime) || "Not watched"}</span>
        )}
      </div>
      <button
        onClick={() => onPlay(ep, queue)}
        className="flex shrink-0 items-center gap-1.5 rounded-[10px] bg-accent px-3.5 py-2 text-xs font-bold text-black transition hover:bg-accent-hover"
      >
        <Icon name="play" size={12} filled />
        {playLabel(ep)}
      </button>
    </div>
  );
}

function PersonHead({
  person,
  fallbackName,
}: {
  person: DetailPerson;
  fallbackName?: string;
}) {
  const [errored, setErrored] = useState(false);
  const src = person.has_image && !errored ? personHeadshotUrl(person.id) : null;
  const initials = (person.name || fallbackName || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();
  return (
    <div className="flex w-[72px] shrink-0 flex-col items-center gap-1.5 text-center">
      <div className="grid h-[72px] w-[72px] place-items-center overflow-hidden rounded-full bg-surface-3 text-sm font-bold text-zinc-300 ring-1 ring-white/10">
        {src ? (
          <img
            src={src}
            alt={person.name}
            loading="lazy"
            className="h-full w-full object-cover"
            onError={() => setErrored(true)}
          />
        ) : (
          <span aria-hidden="true">{initials}</span>
        )}
      </div>
      <span className="line-clamp-1 w-full text-[11px] font-medium text-zinc-200" title={person.name}>
        {person.name}
      </span>
      {person.role && (
        <span className="line-clamp-1 w-full text-[10px] text-zinc-500" title={person.role}>
          {person.role}
        </span>
      )}
    </div>
  );
}

function creditsLine(people: DetailPeople | undefined, kind: "directors" | "writers"): string | null {
  const names = (people?.[kind] ?? []).map((p) => p.name).filter(Boolean);
  if (names.length === 0) return null;
  return `${kind === "directors" ? "Director" : "Writer"}${names.length > 1 ? "s" : ""}: ${names.join(", ")}`;
}

function ActionButton({
  children,
  onClick,
  variant = "secondary",
  className = "",
  ...rest
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost";
  className?: string;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  const base =
    "inline-flex h-10 items-center gap-2 rounded-[10px] px-4 text-sm font-bold transition disabled:opacity-60";
  const styles =
    variant === "primary"
      ? "bg-accent text-black shadow-lg shadow-accent/20 hover:bg-accent-hover"
      : variant === "secondary"
        ? "border border-white/10 bg-white/[.07] text-zinc-100 hover:bg-white/[.12]"
        : "px-3 text-zinc-400 hover:text-white";
  return (
    <button type="button" onClick={onClick} className={`${base} ${styles} ${className}`} {...rest}>
      {children}
    </button>
  );
}

/**
 * Premium item page (NEW_UX spec §23–§30): full-width cinematic backdrop hero,
 * overlapping poster, clear metadata hierarchy, one dominant Play action, cast,
 * and a rich season-grouped episode list. Driven by the URL id alone.
 */
export function ItemDetailContent({
  itemId,
  onBack,
  onPlayMovie,
  onPlayEpisode,
  onToggleWatched,
}: {
  itemId: string;
  onBack: () => void;
  /** Start a movie: (itemId, title, resumeSeconds, runtimeSeconds). */
  onPlayMovie: (itemId: string, title: string, resume: number, runtime: number) => void;
  /** Start an episode from the series list (queue rides along for Up Next). */
  onPlayEpisode: (episode: EpisodeShape, queue: QueueEntry[]) => void;
  onToggleWatched?: (item: MediaItem) => void;
}) {
  const { data: detail, isLoading, isError } = useItemDetail(itemId);
  // List lookup supplies type + fallback facts (undefined on a cold deep link
  // until the shared library query resolves — detail fetch is independent).
  const itemsQuery = useLibraryItems();
  const item = itemsQuery.data?.items.find((i) => i.item_id === itemId);

  const tv = (item ? isSeries(item) : false) || detail?.type === "tv";
  const epQuery = useEpisodes(tv ? itemId : null);

  const d: ItemDetailShape | undefined = detail;
  const title = d?.name ?? item?.title ?? "";
  const played = d?.play?.played ?? item?.played ?? false;
  const runtimeSec = Number(d?.runtime ?? (item?.runtime || 0));
  const resumeSec = Number(d?.play?.resume || 0);
  const genres = d?.genres ?? [];
  const studios = d?.studios ?? [];
  const episodes = epQuery.data?.episodes ?? [];
  const queue = episodeQueue(episodes);
  const groups = groupBySeason(episodes);
  const target = tv ? nextPlayableEpisode(episodes) : null;
  const firstEp = episodes[0];
  const seriesPlayEp = target ?? firstEp ?? null;
  const seriesLabel = target
    ? `${(target.playback_position || 0) > 0 ? "Resume" : "Play"} ${episodeCode(target)}`
    : firstEp
      ? `Replay ${episodeCode(firstEp)}`
      : "Play";

  const poster = posterUrl({ item_id: itemId });
  const backdrop = d?.has_backdrop ? api.backdropUrl(itemId, 1920) : null;
  const percent = detailResumePercent(d?.play, runtimeSec);
  const metaBits = [
    d?.year != null ? String(d.year) : item?.year != null ? String(item.year) : "",
    !tv ? fmtRuntime(runtimeSec) : groups.length > 0 ? `${groups.length} season${groups.length > 1 ? "s" : ""}` : "",
    d?.official_rating || "",
  ].filter(Boolean);
  const rating = ratingText(d?.community_rating);
  const people = d?.people;

  // Cold deep link to an unknown id: the detail probe 404s soft and the library
  // list has no match — render the grid-style fallback instead of a blank page.
  const notFound = !isLoading && isError && !item && !d;

  // Global-search deep link (?play=1[&episode={id}]): start playback as soon as
  // the data this item needs is ready, then clear the params so Back/refresh
  // don't replay it. Fires once per mount (remounts on item change via key).
  const [searchParams, setSearchParams] = useSearchParams();
  const autoPlayedRef = useRef(false);
  useEffect(() => {
    if (searchParams.get("play") !== "1" || autoPlayedRef.current) return;
    if (tv) {
      const epId = searchParams.get("episode");
      const targetEp = epId ? episodes.find((e) => e.id === epId) ?? null : seriesPlayEp;
      if (!targetEp) return; // wait for the episode list
      autoPlayedRef.current = true;
      onPlayEpisode(targetEp, queue);
    } else if (d) {
      autoPlayedRef.current = true;
      onPlayMovie(itemId, d.name ?? title, detailInProgress(d?.play) ? resumeSec : 0, runtimeSec);
    } else {
      return; // wait for the detail probe
    }
    const next = new URLSearchParams(searchParams);
    next.delete("play");
    next.delete("episode");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, tv, d, episodes, itemId, title, resumeSec, runtimeSec, seriesPlayEp]);

  if (isLoading && !d && !item) {
    return (
      <section aria-label="Loading title details" aria-busy="true">
        <div className="skeleton h-[300px] w-full rounded-2xl sm:h-[380px]" />
        <div className="flex gap-6 pt-6">
          <div className="skeleton hidden h-56 w-40 shrink-0 rounded-xl sm:block" />
          <div className="flex flex-1 flex-col gap-3 py-2">
            <div className="skeleton h-8 w-2/3 rounded-lg" />
            <div className="skeleton h-4 w-1/3 rounded" />
            <div className="skeleton h-4 w-1/2 rounded" />
            <div className="mt-4 flex gap-3">
              <div className="skeleton h-10 w-32 rounded-[10px]" />
              <div className="skeleton h-10 w-28 rounded-[10px]" />
            </div>
            <div className="skeleton mt-5 h-16 w-full rounded-lg" />
          </div>
        </div>
      </section>
    );
  }

  return (
    <section aria-label={`${title || "Item"} details`} className="pb-6">
      {notFound ? (
        <div className="flex flex-col items-center gap-5 rounded-2xl border border-dashed border-white/[.08] py-20 text-center">
          <div className="grid h-14 w-14 place-items-center rounded-2xl bg-surface-2 text-zinc-500">
            <Icon name="film" size={24} />
          </div>
          <div className="max-w-sm">
            <p className="text-[15px] font-semibold text-zinc-200">We couldn't find that title in the library.</p>
            <p className="mt-1 text-sm text-zinc-500">It may have been removed or the link is stale.</p>
          </div>
          <ActionButton variant="primary" onClick={onBack}>
            <Icon name="back" size={15} />
            Back to the library
          </ActionButton>
        </div>
      ) : (
        <>
          {/* Cinematic backdrop hero */}
          <div className="relative h-[300px] w-full overflow-hidden rounded-2xl sm:h-[400px]">
            <div aria-hidden="true" className={`absolute inset-0 art-${artTone(title)}`} />
            {backdrop && (
              <img
                src={backdrop}
                alt=""
                className="absolute inset-0 h-full w-full object-cover"
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = "none";
                }}
              />
            )}
            <div
              aria-hidden="true"
              className="absolute inset-0 bg-gradient-to-t from-canvas via-canvas/40 to-black/30"
            />
            <div
              aria-hidden="true"
              className="absolute inset-0 bg-gradient-to-r from-canvas/60 via-transparent to-transparent"
            />
            <button
              onClick={onBack}
              aria-label="Back"
              className="absolute left-4 top-4 inline-flex h-9 items-center gap-1.5 rounded-full border border-white/10 bg-black/40 px-3.5 text-[13px] font-semibold text-zinc-100 backdrop-blur-md transition hover:bg-black/70 hover:text-white"
            >
              <Icon name="back" size={15} />
              Back
            </button>
          </div>

          {/* Content block overlapping the hero */}
          <div className="relative px-0 pb-4 sm:px-2">
            <div className="-mt-28 flex flex-col gap-6 sm:-mt-32 sm:flex-row sm:items-end">
              {/* Poster */}
              <div className="mx-auto w-44 shrink-0 sm:mx-0 sm:w-48">
                {poster ? (
                  <img
                    src={poster}
                    alt={title}
                    className="aspect-[2/3] w-full rounded-[12px] border border-white/10 object-cover shadow-modal"
                  />
                ) : (
                  <div
                    aria-hidden="true"
                    className={`flex aspect-[2/3] w-full items-center justify-center rounded-[12px] border border-white/10 shadow-modal art-${artTone(title)}`}
                  >
                    <Icon name="film" size={40} className="text-white/30" />
                  </div>
                )}
              </div>

              {/* Title + hierarchy */}
              <div className="min-w-0 flex-1 pb-1 text-center sm:text-left">
                <div className="flex flex-wrap items-center justify-center gap-2.5 sm:justify-start">
                  <span className="rounded-md border border-accent/30 bg-accent/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-accent">
                    {tv ? "TV Series" : "Movie"}
                  </span>
                  {rating ? (
                    <span className="flex items-center gap-1 text-[15px] font-semibold text-zinc-100">
                      <Icon name="star" size={15} filled className="text-accent" />
                      {rating}
                      <span className="text-xs font-normal text-zinc-500">/ 10</span>
                    </span>
                  ) : null}
                </div>

                <h1 className="mt-2 text-3xl font-bold leading-[1.05] tracking-[-0.02em] text-white sm:text-5xl">
                  {title || "Loading…"}
                </h1>

                {metaBits.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap items-center justify-center gap-x-2.5 gap-y-1 text-[13px] font-medium text-zinc-400 sm:justify-start">
                    {metaBits.map((b, i) => (
                      <span key={b} className="flex items-center gap-2.5">
                        {i > 0 && <span aria-hidden="true" className="h-1 w-1 rounded-full bg-zinc-600" />}
                        {b}
                      </span>
                    ))}
                  </div>
                )}

                {d && genres.length > 0 && (
                  <div className="mt-3 flex flex-wrap justify-center gap-1.5 sm:justify-start">
                    {genres.map((g) => (
                      <span
                        key={g}
                        className="rounded-full border border-white/[.08] bg-white/[.06] px-2.5 py-1 text-[11px] font-medium text-zinc-300"
                      >
                        {g}
                      </span>
                    ))}
                  </div>
                )}

                {d && studios.length > 0 && (
                  <p className="mt-2.5 text-xs text-zinc-500">{studios.join(" · ")}</p>
                )}

                {isError && !d && !notFound && (
                  <p className="mt-2 text-xs text-red-400">Couldn't load full details — playing still works.</p>
                )}

                {/* Actions: ONE dominant Play (+ supporting secondary) */}
                <div className="mt-5 flex flex-wrap items-center justify-center gap-2.5 sm:justify-start">
                  {!tv && !isLoading ? (
                    <>
                      <ActionButton
                        variant="primary"
                        onClick={() =>
                          onPlayMovie(
                            itemId,
                            d?.name ?? item?.title ?? "Unknown",
                            detailInProgress(d?.play) ? resumeSec : 0,
                            runtimeSec,
                          )
                        }
                      >
                        <Icon name="play" size={15} filled />
                        {detailPrimaryLabel(d?.play)}
                        {percent > 0 ? ` (${percent}%)` : ""}
                      </ActionButton>
                      {detailInProgress(d?.play) && (
                        <ActionButton
                          variant="secondary"
                          onClick={() => onPlayMovie(itemId, d?.name ?? item?.title ?? "Unknown", 0, runtimeSec)}
                        >
                          Play from beginning
                        </ActionButton>
                      )}
                    </>
                  ) : null}
                  {tv && epQuery.isLoading ? (
                    <span className="text-sm text-zinc-400">Loading episodes…</span>
                  ) : null}
                  {tv && !epQuery.isLoading && seriesPlayEp ? (
                    <ActionButton
                      variant="primary"
                      onClick={() => onPlayEpisode(seriesPlayEp, queue)}
                    >
                      <Icon name="play" size={15} filled />
                      {seriesLabel}
                    </ActionButton>
                  ) : null}
                  {onToggleWatched && item ? (
                    <ActionButton
                      variant={played ? "secondary" : "ghost"}
                      onClick={() => onToggleWatched({ ...item, played })}
                      className={played ? "text-emerald-300 ring-1 ring-emerald-500/30" : ""}
                    >
                      <Icon name="check" size={15} strokeWidth={2.25} />
                      {played ? "Watched" : "Mark watched"}
                    </ActionButton>
                  ) : null}
                  <PopupMenu
                    label={`More actions for ${title}`}
                    triggerClassName="inline-flex h-10 w-10 items-center justify-center rounded-[10px] border border-white/10 bg-white/[.07] text-zinc-300 transition hover:bg-white/[.12] hover:text-white"
                    items={[
                      ...(onToggleWatched && item && item.played
                        ? [
                            {
                              key: "untoggle",
                              label: "Mark as unplayed",
                              icon: "check" as const,
                              onSelect: () => onToggleWatched({ ...item, played }),
                            },
                          ]
                        : []),
                      ...(item?.jellyfin_url
                        ? [
                            {
                              key: "jellyfin",
                              label: "Open in Jellyfin",
                              icon: "external" as const,
                              onSelect: () =>
                                window.open(item.jellyfin_url as string, "_blank", "noopener,noreferrer"),
                            },
                          ]
                        : []),
                    ]}
                  >
                    <Icon name="more" size={16} />
                  </PopupMenu>
                </div>

                {/* Resume progress under the actions when mid-play */}
                {!tv && detailInProgress(d?.play) && percent > 0 ? (
                  <div className="mt-4 flex max-w-sm items-center gap-3">
                    <div className="h-[3px] flex-1 rounded-full bg-white/10">
                      <div className="h-full rounded-full bg-accent" style={{ width: `${percent}%` }} />
                    </div>
                    <span className="text-[11px] font-semibold tabular-nums text-zinc-400">
                      {percent}% · {fmtRuntime(Math.max(1, runtimeSec - resumeSec))} left
                    </span>
                  </div>
                ) : null}
              </div>
            </div>

            {/* Synopsis */}
            {d?.overview && <p className="mt-6 max-w-3xl text-[14px] leading-relaxed text-zinc-300">{d.overview}</p>}

            {/* Cast */}
            {people && people.actors.length > 0 ? (
              <div className="mt-8">
                <h3 className="mb-3.5 text-sm font-semibold text-zinc-200">Cast</h3>
                <div className="no-scrollbar flex gap-5 overflow-x-auto pb-1">
                  {people.actors.slice(0, 10).map((p) => (
                    <PersonHead key={p.id || p.name} person={p} />
                  ))}
                </div>
              </div>
            ) : null}

            {/* Episodes (series only) — rich list, season-grouped */}
            {tv ? (
              <div className="mt-8">
                <h3 className="mb-3.5 text-sm font-semibold text-zinc-200">Episodes</h3>
                {epQuery.isLoading ? (
                  <p className="text-sm text-zinc-400">Loading episodes…</p>
                ) : epQuery.isError ? (
                  <p className="text-sm text-red-400">Couldn't load episodes.</p>
                ) : groups.length === 0 ? (
                  <p className="text-sm text-zinc-500">No episodes found.</p>
                ) : (
                  <div className="flex max-w-4xl flex-col gap-6">
                    {groups.map((group) => (
                      <div key={group.season}>
                        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                          Season {group.season}
                        </div>
                        <div className="flex flex-col gap-2">
                          {group.episodes.map((ep) => (
                            <EpisodeRow key={ep.id} ep={ep} queue={queue} onPlay={onPlayEpisode} />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : null}

            {/* Credits */}
            {(creditsLine(people, "directors") || creditsLine(people, "writers")) && (
              <p className="mt-6 text-xs text-zinc-500">
                {[creditsLine(people, "directors"), creditsLine(people, "writers")].filter(Boolean).join("  ·  ")}
              </p>
            )}

            {/* "Because you watched" — TMDB similar row (movie/tv pages only). */}
            {d && (d.type === "movie" || d.type === "tv") && title ? (
              <SimilarRow itemId={itemId} title={title} localItems={itemsQuery.data?.items ?? []} />
            ) : null}
          </div>
        </>
      )}
    </section>
  );
}
