import { useEffect } from "react";
import type { EpisodeShape } from "../../lib/api/client";
import { useEpisodes } from "./api";
import { episodeQueue, episodeThumbUrl, groupBySeason, playLabel, type QueueEntry } from "./lib";

export function EpisodePicker({
  seriesId,
  title,
  onPlay,
  onClose,
}: {
  seriesId: string;
  title: string;
  onPlay: (episode: EpisodeShape, queue: QueueEntry[]) => void;
  onClose: () => void;
}) {
  const { data, isLoading, isError } = useEpisodes(seriesId);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const episodes = data?.episodes ?? [];
  const queue = episodeQueue(episodes);
  const groups = groupBySeason(episodes);

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-black/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`${title} episodes`}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="mx-auto mt-4 max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900">
        <div className="flex items-center justify-between border-b border-zinc-800 p-4">
          <h3 className="text-base font-semibold text-white">{title}</h3>
          <button
            onClick={onClose}
            className="rounded-full bg-zinc-800 px-3 py-1 text-sm text-zinc-200 hover:bg-zinc-700"
          >
            Close
          </button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto p-4">
          {isLoading && <p className="text-sm text-zinc-400">Loading episodes…</p>}
          {isError && <p className="text-sm text-red-400">Couldn't load episodes.</p>}
          {!isLoading && !isError && groups.length === 0 && (
            <p className="text-sm text-zinc-500">No episodes.</p>
          )}
          {groups.map((group) => (
            <div key={group.season} className="mb-4">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
                Season {group.season}
              </div>
              <div className="flex flex-col gap-2">
                {group.episodes.map((ep) => (
                  <div
                    key={ep.id}
                    className="flex items-center gap-3 rounded-lg bg-zinc-800/50 p-2"
                  >
                    {episodeThumbUrl(ep.id) && (
                      <img
                        src={episodeThumbUrl(ep.id) as string}
                        alt=""
                        className="h-12 w-20 shrink-0 rounded object-cover"
                        loading="lazy"
                        onError={(e) => {
                          (e.currentTarget as HTMLImageElement).style.display = "none";
                        }}
                      />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm text-zinc-100">
                        {ep.episode}. {ep.name}
                      </div>
                      {ep.played && <span className="text-xs text-emerald-400">✓ Watched</span>}
                    </div>
                    <button
                      onClick={() => onPlay(ep, queue)}
                      className="rounded-lg bg-amber-400 px-3 py-1.5 text-sm font-semibold text-black hover:bg-amber-300"
                    >
                      {playLabel(ep)}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}