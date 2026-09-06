import { useEffect, useRef, useState } from "react";
import { api, type PlaybackInfo, type ProgressPayload } from "../../lib/api/client";
import {
  nextEpisode, qualityFor, AUTOPLAY_DELAY_MS, QUALITY_OPTIONS, PLAYBACK_RATES,
  type QueueEntry,
} from "./lib";

export interface PlayTarget {
  item_id: string;
  title: string;
}

/**
 * In-app player, at legacy `openPlayer` parity (item 3 adds the pickers):
 * - streams the same-origin `/api/jellyfin/stream/{id}` (token stays server-side)
 * - seeks to the saved resume point once duration is known
 * - reports position back to `/api/jellyfin/progress` (start / throttled 5s
 *   timeupdate / stopped) WITHOUT clobbering the resume spot
 * - codec failure → friendly fallback note
 * - an episode ending offers "Up Next" from the loaded series queue, with a
 *   cancellable autoplay-next countdown
 *
 * Item-3 controls: playback **speed**, **audio-track** + **subtitle-track**
 * pickers (from `/api/jellyfin/playback-info`), a **quality** picker
 * (MaxStreamingBitrate) and a 16:9 **backdrop** behind the player.
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
  const autoTimerRef = useRef<number | null>(null);
  const autoTimeoutRef = useRef<number | null>(null);
  const onSwitchRef = useRef(onSwitch);
  useEffect(() => {
    queueRef.current = queue;
    onSwitchRef.current = onSwitch;
  }, [queue, onSwitch]);

  const [error, setError] = useState<string | null>(null);
  const [upNext, setUpNext] = useState<QueueEntry | null>(null);
  const [autoSecs, setAutoSecs] = useState(0);
  const [info, setInfo] = useState<PlaybackInfo | null>(null);
  const [audioIndex, setAudioIndex] = useState(0); // 0 = default (no override)
  const [subIndex, setSubIndex] = useState<number | null>(null); // null = off
  const [quality, setQuality] = useState("Original");
  const [rate, setRate] = useState(1);

  const msId = info?.media_source_id || item.item_id;
  const bitrate = qualityFor(quality);
  const src = api.streamUrl(item.item_id, {
    ...(audioIndex ? { audio_stream_index: audioIndex } : {}),
    ...(bitrate ? { max_bitrate: bitrate } : {}),
  });
  const subSrc = subIndex != null && info ? api.subtitleUrl(item.item_id, msId, subIndex) : null;
  const backdrop = api.backdropUrl(item.item_id);

  // Load track info once per item (audio/subtitle pickers).
  useEffect(() => {
    let alive = true;
    setInfo(null);
    setAudioIndex(0);
    setSubIndex(null);
    setQuality("Original");
    api
      .playbackInfo(item.item_id)
      .then((d) => {
        if (alive) setInfo(d || null);
      })
      .catch(() => {
        /* track pickers stay hidden when the backend can't answer */
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.item_id]);

  // Speed: apply playbackRate whenever it changes (native controls don't expose it).
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.playbackRate = rate;
  }, [rate]);

  const clearAuto = () => {
    if (autoTimerRef.current != null) window.clearInterval(autoTimerRef.current);
    if (autoTimeoutRef.current != null) window.clearTimeout(autoTimeoutRef.current);
    autoTimerRef.current = null;
    autoTimeoutRef.current = null;
    setAutoSecs(0);
  };

  const startAuto = (next: QueueEntry) => {
    clearAuto();
    setAutoSecs(Math.round(AUTOPLAY_DELAY_MS / 1000));
    autoTimeoutRef.current = window.setTimeout(() => {
      clearAuto();
      onSwitchRef.current?.(next);
    }, AUTOPLAY_DELAY_MS);
    autoTimerRef.current = window.setInterval(() => {
      setAutoSecs((s) => (s > 0 ? s - 1 : 0));
    }, 1000);
  };

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const report = (event: ProgressPayload["event"]) => {
      const pos = v.currentTime || 0;
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
      clearAuto();
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
      const next = nextEpisode(queueRef.current, item.item_id);
      setUpNext(next);
      if (next) startAuto(next);
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
      clearAuto();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.item_id]);

  const playNext = () => {
    clearAuto();
    if (upNext) onSwitchRef.current?.(upNext);
  };
  const cancelNext = () => {
    clearAuto();
    setUpNext(null);
  };

  const selectCls =
    "rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200";

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black"
      role="dialog"
      aria-modal="true"
      aria-label={`${item.title} player`}
    >
      {/* 16:9 backdrop behind the player */}
      <div
        className="absolute inset-0 opacity-40 blur-md"
        style={{
          backgroundImage: `url(${backdrop})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
        aria-hidden="true"
      />
      <div className="pointer-events-none absolute inset-0 bg-black/55" aria-hidden="true" />

      <div className="relative z-10 flex items-center justify-between p-3">
        <div className="truncate text-sm font-medium text-zinc-100">{item.title}</div>
        <button
          onClick={onClose}
          className="rounded-full bg-zinc-800/90 px-3 py-1 text-sm text-zinc-100 hover:bg-zinc-700"
        >
          Close
        </button>
      </div>

      <div className="relative z-10 flex flex-1 flex-col p-4">
        <div className="relative flex flex-1 items-center justify-center">
          <video
            ref={videoRef}
            controls
            autoPlay
            playsInline
            src={src}
            className="max-h-full max-w-full rounded-lg bg-black shadow-2xl"
          >
            {subSrc && <track key={subSrc} kind="subtitles" src={subSrc} default />}
          </video>

          {error && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/85 p-6 text-center">
              <div>
                <p className="text-sm text-zinc-100">⚠️ {error}</p>
                <p className="mt-1 text-xs text-zinc-500">Open it in Jellyfin directly instead.</p>
              </div>
            </div>
          )}

          {upNext && (
            <div className="absolute -bottom-2 right-6 z-10 rounded-lg border border-zinc-700 bg-zinc-900/95 p-4 shadow-xl">
              <div className="text-[11px] font-medium tracking-wide text-zinc-400">
                UP NEXT {autoSecs > 0 ? `· auto in ${autoSecs}s` : ""}
              </div>
              <div className="mt-1 text-sm font-medium text-white">{upNext.name}</div>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={playNext}
                  className="rounded-lg bg-amber-400 px-3 py-1.5 text-sm font-semibold text-black hover:bg-amber-300"
                >
                  ▶ Play next
                </button>
                <button
                  onClick={cancelNext}
                  className="rounded-lg border border-zinc-600 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-800"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Item-3 player controls */}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-zinc-400">
            Speed
            <select value={rate} onChange={(e) => setRate(Number(e.target.value))} className={selectCls}>
              {PLAYBACK_RATES.map((r) => (
                <option key={r} value={r}>{r}×</option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-1.5 text-xs text-zinc-400">
            Quality
            <select value={quality} onChange={(e) => setQuality(e.target.value)} className={selectCls}>
              {QUALITY_OPTIONS.map((q) => (
                <option key={q.label} value={q.label}>{q.label}</option>
              ))}
            </select>
          </label>

          {info && info.audio.length > 0 && (
            <label className="flex items-center gap-1.5 text-xs text-zinc-400">
              Audio
              <select
                value={audioIndex}
                onChange={(e) => setAudioIndex(Number(e.target.value))}
                className={selectCls}
              >
                <option value={0}>Default</option>
                {info.audio.map((a) => (
                  <option key={a.index} value={a.index}>
                    {a.name} {a.language ? `(${a.language})` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}

          {info && info.subtitles.length > 0 && (
            <label className="flex items-center gap-1.5 text-xs text-zinc-400">
              Subs
              <select
                value={subIndex == null ? 0 : subIndex}
                onChange={(e) => setSubIndex(e.target.value ? Number(e.target.value) : null)}
                className={selectCls}
              >
                <option value={0}>Off</option>
                {info.subtitles.map((s) => (
                  <option key={s.index} value={s.index}>
                    {s.name} {s.language ? `(${s.language})` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}

          <span className="ml-auto text-[11px] text-zinc-500">
            {info ? `${info.audio.length} audio · ${info.subtitles.length} sub tracks` : "tracks unavailable"}
          </span>
        </div>
      </div>
    </div>
  );
}