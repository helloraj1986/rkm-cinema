import { useEffect, useRef, useState } from "react";
import { api, type ProgressPayload } from "../../lib/api/client";
import { nextEpisode, type QueueEntry } from "./lib";

export interface PlayTarget {
  item_id: string;
  title: string;
}

/**
 * In-app player, at legacy `openPlayer` parity:
 * - streams the same-origin `/api/jellyfin/stream/{id}` (token stays server-side)
 * - seeks to the saved resume point once duration is known
 * - reports position back to `/api/jellyfin/progress` (start / throttled 5s
 *   timeupdate / stopped) WITHOUT clobbering the resume spot — a fresh stream
 *   sitting at 0s never POSTs a 0 that would wipe Jellyfin's saved position
 * - codec failure → friendly fallback note
 * - an episode ending offers "Up Next" from the loaded series queue
 */
export function Player({
  item,
  resume = 0,
  queue = [],
  onSwitch,
  onClose,
}: {
  item: PlayTarget;
  resume?: number;
  queue?: QueueEntry[];
  onSwitch?: (entry: QueueEntry) => void;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const resumeRef = useRef(Math.max(0, Number(resume) || 0));
  const lastReportRef = useRef(0);
  const queueRef = useRef(queue);
  useEffect(() => {
    queueRef.current = queue;
  }, [queue]);

  const [error, setError] = useState<string | null>(null);
  const [upNext, setUpNext] = useState<QueueEntry | null>(null);
  const src = api.streamUrl(item.item_id);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const report = (event: ProgressPayload["event"]) => {
      const pos = v.currentTime || 0;
      // Resume guard (legacy parity): don't report play/timeupdate until the
      // saved position is applied, else a fresh stream at 0 resets Jellyfin.
      if (resumeRef.current > 0 && pos < resumeRef.current - 1) return;
      const ticks = Math.round(pos * 1e7);
      void api.reportProgress({ item_id: item.item_id, position_ticks: ticks, is_paused: false, event }).catch(() => {});
    };
    const onLoaded = () => {
      if (resumeRef.current > 0 && v.duration && resumeRef.current < v.duration) {
        try {
          v.currentTime = resumeRef.current;
        } catch {
          /* ignore seek failure */
        }
      }
    };
    const onPlay = () => report("start");
    const onError = () => {
      report("stopped");
      setError("Couldn't play this file in the browser — the codec may not be supported.");
    };
    const onTime = () => {
      const now = Date.now();
      if (now - lastReportRef.current < 5000) return;
      lastReportRef.current = now;
      report("timeupdate");
    };
    const onEnded = () => {
      report("stopped");
      setUpNext(nextEpisode(queueRef.current, item.item_id));
    };
    const onPause = () => report("stopped");

    v.addEventListener("loadedmetadata", onLoaded);
    v.addEventListener("play", onPlay);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("pause", onPause);
    v.addEventListener("ended", onEnded);
    v.addEventListener("error", onError);
    return () => {
      v.removeEventListener("loadedmetadata", onLoaded);
      v.removeEventListener("play", onPlay);
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("pause", onPause);
      v.removeEventListener("ended", onEnded);
      v.removeEventListener("error", onError);
    };
  }, [item.item_id]);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/95"
      role="dialog"
      aria-modal="true"
      aria-label={`${item.title} player`}
    >
      <div className="flex items-center justify-between p-3">
        <div className="truncate text-sm font-medium text-zinc-200">{item.title}</div>
        <button
          onClick={onClose}
          className="rounded-full bg-zinc-800 px-3 py-1 text-sm text-zinc-200 hover:bg-zinc-700"
        >
          Close
        </button>
      </div>

      <div className="relative flex flex-1 items-center justify-center p-4">
        <video
          ref={videoRef}
          controls
          autoPlay
          playsInline
          src={src}
          className="max-h-full max-w-full"
        />
        {error && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/85 p-6 text-center">
            <div>
              <p className="text-sm text-zinc-100">⚠️ {error}</p>
              <p className="mt-1 text-xs text-zinc-500">Open it in Jellyfin directly instead.</p>
            </div>
          </div>
        )}
        {upNext && (
          <div className="absolute right-6 bottom-6 z-10 rounded-lg border border-zinc-700 bg-zinc-900/95 p-4 shadow-xl">
            <div className="text-[11px] font-medium tracking-wide text-zinc-400">UP NEXT</div>
            <div className="mt-1 text-sm font-medium text-white">{upNext.name}</div>
            <button
              onClick={() => onSwitch?.(upNext)}
              className="mt-3 w-full rounded-lg bg-amber-400 px-3 py-1.5 text-sm font-semibold text-black hover:bg-amber-300"
            >
              ▶ Play next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}