import { useEffect, useState } from "react";
import {
  api,
  type DetailPeople,
  type DetailPerson,
  type EpisodeShape,
  type ItemDetail as ItemDetailShape,
  type MediaItem,
} from "../../lib/api/client";
import { useItemDetail } from "./api";
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
  detailInProgress,
  detailPrimaryLabel,
  detailResumePercent,
  fmtRuntime,
  isSeries,
  personHeadshotUrl,
  posterUrl,
  ratingText,
} from "./lib";

function EpisodeRow({
  ep,
  queue,
  onPlay,
}: {
  ep: EpisodeShape;
  queue: QueueEntry[];
  onPlay: (ep: EpisodeShape, queue: QueueEntry[]) => void;
}) {
  const percent = ep.runtime > 0 ? Math.min(100, Math.round(((ep.playback_position || 0) / ep.runtime) * 100)) : 0;
  return (
    <div className="flex items-center gap-3 rounded-lg bg-zinc-800/40 p-2 hover:bg-zinc-800/70">
      <div className="relative h-14 w-24 shrink-0 overflow-hidden rounded bg-zinc-800">
        {episodeThumbUrl(ep.id) && (
          <img
            src={episodeThumbUrl(ep.id) as string}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        )}
        {!ep.played && percent > 0 && (
          <div className="absolute inset-x-0 bottom-0 h-0.5 bg-zinc-700">
            <div className="h-full bg-amber-400" style={{ width: `${percent}%` }} />
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-xs font-semibold text-amber-400/90">{episodeCode(ep)}</span>
          <span className="truncate text-sm text-zinc-100">{ep.name}</span>
        </div>
        {ep.played ? (
          <span className="text-xs text-emerald-400">✓ Watched</span>
        ) : ep.playback_position > 0 ? (
          <span className="text-xs text-amber-300">{percent}% watched</span>
        ) : (
          <span className="text-xs text-zinc-500">Not watched</span>
        )}
      </div>
      <button
        onClick={() => onPlay(ep, queue)}
        className="shrink-0 rounded-lg bg-amber-400 px-3 py-1.5 text-xs font-semibold text-black hover:bg-amber-300"
      >
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
    <div className="flex w-16 shrink-0 flex-col items-center gap-1 text-center">
      <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-full bg-zinc-700/80 text-sm font-bold text-zinc-300 ring-1 ring-zinc-600">
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
      <span className="line-clamp-1 w-full text-[10px] font-medium text-zinc-200" title={person.name}>
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

/**
 * Plex-style preplay overlay (PLEX_UI_PLAN.md §2): blurred backdrop hero,
 * poster, metadata (title/year/runtime/content rating/★/genres/studio), a big
 * Play/Resume button, synopsis, cast headshots, and — for series — the episode
 * list reusing the picker data path. Detail is fetched ONLY on open and cached
 * per item; Esc / backdrop / ✕ close.
 */
export function ItemDetail({
  item,
  onPlayMovie,
  onPlayEpisode,
  onToggleWatched,
  onClose,
}: {
  item: MediaItem;
  /** Start a movie: (itemId, title, resumeSeconds, runtimeSeconds). */
  onPlayMovie: (itemId: string, title: string, resume: number, runtime: number) => void;
  /** Start an episode from the series list (queue rides along for Up Next). */
  onPlayEpisode: (episode: EpisodeShape, queue: QueueEntry[]) => void;
  onToggleWatched?: (item: MediaItem) => void;
  onClose: () => void;
}) {
  const { data: detail, isLoading, isError } = useItemDetail(item.item_id);
  const tv = isSeries(item);
  const epQuery = useEpisodes(tv ? item.item_id : null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const d: ItemDetailShape | undefined = detail;
  const played = d?.play?.played ?? item.played;
  const runtimeSec = Number(d?.runtime ?? (item.runtime || 0));
  const resumeSec = Number(d?.play?.resume || 0);
  const genres = d?.genres ?? [];
  const studios = d?.studios ?? [];
  const episodes = epQuery.data?.episodes ?? [];
  const queue = episodeQueue(episodes);
  const groups = groupBySeason(episodes);
  const target = tv ? nextPlayableEpisode(episodes) : null;
  const firstEp = episodes[0];
  const seriesPlayEp = target ?? (!tv ? null : firstEp ?? null);
  const seriesLabel = target
    ? `${(target.playback_position || 0) > 0 ? "Resume" : "Play"} ${episodeCode(target)}`
    : firstEp
      ? `Replay ${episodeCode(firstEp)}`
      : "Play";

  const poster = posterUrl(item);
  const backdrop = d?.has_backdrop ? api.backdropUrl(item.item_id, 1920) : null;
  const percent = detailResumePercent(d?.play, runtimeSec);
  const metaBits = [
    d?.year != null ? String(d.year) : item.year != null ? String(item.year) : "",
    !tv ? fmtRuntime(runtimeSec) : groups.length > 0 ? `${groups.length} season${groups.length > 1 ? "s" : ""}` : "",
    d?.official_rating || "",
  ].filter(Boolean);
  const rating = ratingText(d?.community_rating);
  const people = d?.people;

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-black/85"
      role="dialog"
      aria-modal="true"
      aria-label={`${d?.name ?? item.title} details`}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="mx-auto my-6 w-full max-w-3xl overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl">
        {/* Backdrop hero */}
        <div className="relative h-64 w-full overflow-hidden bg-zinc-800">
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
          <div className="absolute inset-0 bg-gradient-to-t from-zinc-900 via-zinc-900/50 to-black/40" />
          <button
            onClick={onClose}
            aria-label="Close details"
            className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-black/60 text-zinc-200 hover:bg-black/80 hover:text-white"
          >
            ✕
          </button>
        </div>

        <div className="relative px-5 pb-6">
          {/* Poster overlapping the hero */}
          <div className="-mt-24 flex gap-5">
            <div className="hidden w-44 shrink-0 sm:block">
              {poster ? (
                <img
                  src={poster}
                  alt={d?.name ?? item.title}
                  className="aspect-[2/3] w-full rounded-lg border border-zinc-700/60 object-cover shadow-2xl"
                />
              ) : (
                <div className="flex aspect-[2/3] w-full items-center justify-center rounded-lg bg-zinc-800 text-4xl">🎬</div>
              )}
            </div>

            <div className="min-w-0 flex-1 pt-14">
              <h2 className="text-2xl font-bold leading-tight text-white">
                {tv && <span className="mr-2 align-middle text-xs font-semibold tracking-widest text-amber-400">TV</span>}
                {d?.name ?? item.title}
              </h2>
              {metaBits.length > 0 && (
                <p className="mt-1 text-sm text-zinc-400">{metaBits.join(" · ")}</p>
              )}
              {rating && (
                <p className="mt-1 text-sm text-zinc-300">
                  <span className="mr-0.5 text-amber-400">★</span>
                  {rating}
                  <span className="text-zinc-500"> / 10</span>
                </p>
              )}
              {d && genres.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {genres.map((g) => (
                    <span key={g} className="rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] font-medium text-zinc-300 ring-1 ring-zinc-700">
                      {g}
                    </span>
                  ))}
                </div>
              )}
              {d && studios.length > 0 && (
                <p className="mt-2 text-xs text-zinc-500">{studios.join(" · ")}</p>
              )}

              {isError && !d && (
                <p className="mt-2 text-xs text-red-400">Couldn't load full details — playing still works.</p>
              )}

              {/* Play actions */}
              <div className="mt-4 flex flex-wrap items-center gap-2">
                {!tv && !isLoading && (
                  <>
                    <button
                      onClick={() =>
                        onPlayMovie(
                          item.item_id,
                          d?.name ?? item.title,
                          detailInProgress(d?.play) ? resumeSec : 0,
                          runtimeSec,
                        )
                      }
                      className="flex items-center gap-2 rounded-lg bg-amber-400 px-4 py-2 text-sm font-bold text-black hover:bg-amber-300"
                    >
                      <span aria-hidden="true">▶</span>
                      {detailPrimaryLabel(d?.play)}
                      {percent > 0 ? ` (${percent}%)` : ""}
                    </button>
                    {detailInProgress(d?.play) && (
                      <button
                        onClick={() => onPlayMovie(item.item_id, d?.name ?? item.title, 0, runtimeSec)}
                        className="rounded-lg bg-zinc-800 px-3 py-2 text-sm font-medium text-zinc-200 ring-1 ring-zinc-700 hover:bg-zinc-700"
                      >
                        Play from beginning
                      </button>
                    )}
                  </>
                )}
                {tv && epQuery.isLoading && (
                  <span className="text-sm text-zinc-400">Loading episodes…</span>
                )}
                {tv && !epQuery.isLoading && seriesPlayEp && (
                  <button
                    onClick={() => onPlayEpisode(seriesPlayEp, queue)}
                    className="flex items-center gap-2 rounded-lg bg-amber-400 px-4 py-2 text-sm font-bold text-black hover:bg-amber-300"
                  >
                    <span aria-hidden="true">▶</span>
                    {seriesLabel}
                  </button>
                )}
                {onToggleWatched && (
                  <button
                    onClick={() => onToggleWatched({ ...item, played })}
                    className={`rounded-lg px-3 py-2 text-sm font-medium ring-1 ${
                      played
                        ? "bg-emerald-900/30 text-emerald-300 ring-emerald-700/70 hover:bg-emerald-800/40"
                        : "bg-zinc-800 text-zinc-300 ring-zinc-700 hover:bg-zinc-700"
                    }`}
                  >
                    {played ? "✓ Watched" : "Mark watched"}
                  </button>
                )}
                {item.jellyfin_url && (
                  <a
                    href={item.jellyfin_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded-lg bg-blue-600/20 px-3 py-2 text-sm font-medium text-blue-300 ring-1 ring-blue-700/60 hover:bg-blue-600/30"
                  >
                    Open in Jellyfin ↗
                  </a>
                )}
              </div>
            </div>
          </div>

          {/* Synopsis */}
          {d?.overview && <p className="mt-5 text-sm leading-relaxed text-zinc-300">{d.overview}</p>}

          {/* Cast */}
          {people && people.actors.length > 0 && (
            <div className="mt-6">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-zinc-500">Cast</h3>
              <div className="flex gap-4 overflow-x-auto pb-1">
                {people.actors.slice(0, 8).map((p) => (
                  <PersonHead key={p.id || p.name} person={p} />
                ))}
              </div>
            </div>
          )}

          {/* Episodes (series only) */}
          {tv && (
            <div className="mt-6">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-widest text-zinc-500">Episodes</h3>
              {epQuery.isLoading && <p className="text-sm text-zinc-400">Loading episodes…</p>}
              {epQuery.isError && <p className="text-sm text-red-400">Couldn't load episodes.</p>}
              {!epQuery.isLoading && !epQuery.isError && groups.length === 0 && (
                <p className="text-sm text-zinc-500">No episodes found.</p>
              )}
              <div className="mt-2 flex max-h-[45vh] flex-col gap-2 overflow-y-auto pr-1">
                {groups.map((group) => (
                  <div key={group.season}>
                    <div className="mb-1.5 mt-3 text-xs font-semibold uppercase tracking-wide text-zinc-400">
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
            </div>
          )}

          {/* Credits */}
          {(creditsLine(people, "directors") || creditsLine(people, "writers")) && (
            <p className="mt-6 text-xs text-zinc-500">
              {[creditsLine(people, "directors"), creditsLine(people, "writers")].filter(Boolean).join("  ·  ")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
