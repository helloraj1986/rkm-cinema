import { useEffect, useRef, useState } from "react";
import { api, type PlaybackInfo, type ProgressPayload } from "../../lib/api/client";
import {
  nextEpisode, qualityFor, AUTOPLAY_DELAY_MS, QUALITY_OPTIONS, PLAYBACK_RATES,
  fmtTime, isFiniteDuration, clampSeek, pickStreamMode, streamModeLabel,
  playMethodForMode, type QueueEntry, type StreamMode,
} from "./lib";

export interface PlayTarget {
  item_id: string;
  title: string;
}

const SEEK_STEP = 10; // seconds for ← / → keys

/** Escalation ladder when a stream fails (each rung re-encodes more). */
const LADDER: StreamMode[] = ["direct", "remux", "transcode_audio", "transcode"];

/**
 * In-app player with HONEST stream routing:
 *
 * - **direct** (Static file, HTTP-range seekable) for browser-safe MP4;
 * - **remux** (copy/copy → MP4) for MKV-style containers the browser can't
 *   index up-front (solves duration=Infinity and gives a proper total);
 * - **transcode_audio** (video copy + AAC) for EAC3/AC3/DTS/TrueHD tracks;
 * - **transcode** (H.264 + AAC) for unsafe video codecs OR the quality picker.
 *
 * Static=true IGNORES AudioStreamIndex/MaxStreamingBitrate (verified live), so
 * any quality/track request forces a non-direct mode. Non-direct streams are
 * chunked MP4 (no byte ranges) — seeking RESTARTS the stream at
 * `start_time_ticks`, and the bar keeps an offset so position stays seamless.
 * On a media error the player escalates up the ladder before giving up.
 *
 * The control bar's total = the API runtime hint (scan metadata) until the
 * stream duration resolves — length + progress are correct from the start.
 */
export function Player({
  item,
  resume = 0,
  runtime = 0,
  queue = [],
  onSwitch,
  onClose,
}: {
  item: PlayTarget;
  resume?: number;
  /** Item runtime in seconds from the API (episode/movie scan metadata). */
  runtime?: number;
  queue?: QueueEntry[];
  onSwitch?: (entry: QueueEntry) => void;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const resumeRef = useRef(Math.max(0, Number(resume) || 0));
  // Seconds into the ITEM where the current stream begins (0 = direct from 0).
  const baseRef = useRef(0);
  // Direct-mode seek to apply once duration is known (resume / return-to-direct).
  const pendingSeekRef = useRef<number | null>(resumeRef.current > 0 ? resumeRef.current : null);
  const lastReportRef = useRef(0);
  const queueRef = useRef(queue);
  const autoTimerRef = useRef<number | null>(null);
  const autoTimeoutRef = useRef<number | null>(null);
  const onSwitchRef = useRef(onSwitch);
  const modeRef = useRef<StreamMode>("direct");
  const rateRef = useRef(1);
  const srcRef = useRef("");
  useEffect(() => {
    queueRef.current = queue;
    onSwitchRef.current = onSwitch;
  }, [queue, onSwitch]);

  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(true); // stream (re)loading
  const [upNext, setUpNext] = useState<QueueEntry | null>(null);
  const [autoSecs, setAutoSecs] = useState(0);
  const [info, setInfo] = useState<PlaybackInfo | null>(null);
  const [audioIndex, setAudioIndex] = useState(0); // 0 = default (no override)
  const [subIndex, setSubIndex] = useState<number | null>(null); // null = off
  const [quality, setQuality] = useState("Original");
  const [rate, setRate] = useState(1);
  // Stream session: how Jellyfin serves it + where it starts (restart-seek).
  const [mode, setMode] = useState<StreamMode>("direct");
  const [startAt, setStartAt] = useState(0);

  // Custom control bar state.
  const [playing, setPlaying] = useState(false);
  const [cur, setCur] = useState(0); // display position = offset + local time
  const [mediaDur, setMediaDur] = useState(0); // stream duration once finite
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(1);
  const [isFs, setIsFs] = useState(false);

  modeRef.current = mode;
  rateRef.current = rate;

  const activeAudioCodec =
    (audioIndex > 0
      ? info?.audio.find((a) => a.index === audioIndex)?.codec
      : info?.audio[0]?.codec) ?? null;

  // The mode the CURRENT facts call for (null until playback-info arrives).
  const desiredMode: StreamMode | null = info
    ? pickStreamMode({
        quality,
        container: info.container,
        video: info.video ?? null,
        activeAudioCodec,
        forceNonDirect: audioIndex > 0, // a chosen track can't work on Static
      })
    : null;

  const msId = info?.media_source_id || item.item_id;
  const bitrate = qualityFor(quality);
  const src = api.streamUrl(item.item_id, {
    ...(mode !== "direct" ? { mode, start_time_ticks: Math.round(startAt * 1e7) } : {}),
    ...(audioIndex > 0 ? { audio_stream_index: audioIndex } : {}),
    ...(bitrate && mode !== "direct" && mode !== "remux" ? { max_bitrate: bitrate } : {}),
  });
  const subSrc = subIndex != null && info ? api.subtitleUrl(item.item_id, msId, subIndex) : null;
  const backdrop = api.backdropUrl(item.item_id);
  // Display total: the API runtime (scan metadata) is authoritative; fall back
  // to the resolved stream duration (+offset for restart-seek streams).
  const total =
    runtime > 0
      ? runtime
      : isFiniteDuration(mediaDur)
        ? mediaDur + baseRef.current
        : 0;

  const posNow = () => baseRef.current + (videoRef.current ? videoRef.current.currentTime || 0 : 0);
  const seekBase = () => {
    const p = posNow();
    return p > 0 ? p : resumeRef.current;
  };

  // Apply a mode/position transition (info-driven auto-route, user quality or
  // audio changes, and the error-ladder escalations all land here).
  const transitionTo = (next: StreamMode, atSeconds?: number) => {
    const at = atSeconds ?? seekBase();
    pendingSeekRef.current = next === "direct" && at > 0 ? at : null;
    const nextBase = next === "direct" ? 0 : at;
    baseRef.current = nextBase;
    setStartAt(nextBase);
    setMode(next);
    setMediaDur(0);
    setError(null);
    setSwitching(true);
  };

  // Auto-route once playback-info resolves (or when quality/audio change).
  useEffect(() => {
    if (!desiredMode || desiredMode === mode) return;
    transitionTo(desiredMode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [desiredMode]);

  // Reload <video> whenever the stream URL changes (mode/quality/track/seek).
  useEffect(() => {
    const v = videoRef.current;
    if (!v || srcRef.current === src) return;
    srcRef.current = src;
    setCur(baseRef.current);
    try {
      v.load();
      void v.play().catch(() => {});
    } catch {
      /* playback resumes on user gesture if autoplay is blocked */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  // Load track info once per item (audio/subtitle pickers + routing facts).
  useEffect(() => {
    let alive = true;
    setInfo(null);
    setAudioIndex(0);
    setSubIndex(null);
    setQuality("Original");
    setMode("direct");
    setStartAt(0);
    baseRef.current = 0;
    pendingSeekRef.current = resumeRef.current > 0 ? resumeRef.current : null;
    api
      .playbackInfo(item.item_id)
      .then((d) => {
        if (alive) setInfo(d || null);
      })
      .catch(() => {
        /* stay direct; the error-ladder still rescues a bad direct attempt */
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.item_id]);

  // Speed: apply playbackRate whenever it changes.
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

  const seekTo = (seconds: number) => {
    const v = videoRef.current;
    if (!v) return;
    const target = clampSeek(seconds, total > 0 ? total : seconds);
    if (modeRef.current === "direct") {
      // Static file: HTTP-range seek straight on the media element.
      try {
        v.currentTime = target;
        setCur(target);
      } catch {
        /* not seekable yet */
      }
    } else {
      // Chunked remux/transcode: restart the stream at the target offset.
      if (Math.abs(posNow() - target) < 2) return;
      transitionTo(modeRef.current, target);
    }
  };

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) void v.play().catch(() => {});
    else v.pause();
  };

  const toggleMute = () => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setMuted(v.muted);
  };

  const toggleFullscreen = () => {
    const el = rootRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
    else void el.requestFullscreen().catch(() => {});
  };

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const report = (event: ProgressPayload["event"]) => {
      const pos = posNow();
      if (resumeRef.current > 0 && pos < resumeRef.current - 1) return;
      const ticks = Math.round(pos * 1e7);
      void api
        .reportProgress({
          item_id: item.item_id,
          position_ticks: ticks,
          is_paused: false,
          event,
          play_method: playMethodForMode(modeRef.current),
        })
        .catch(() => {});
    };

    const escalate = () => {
      const idx = LADDER.indexOf(modeRef.current);
      const next = idx >= 0 && idx < LADDER.length - 1 ? LADDER[idx + 1] : null;
      if (!next) {
        report("stopped");
        setError("Couldn't play this file in the browser — even transcoding failed. Open it in Jellyfin directly instead.");
        return;
      }
      transitionTo(next);
    };

    const onMeta = () => {
      if (isFiniteDuration(v.duration)) setMediaDur(v.duration);
      // Direct-mode resume / return: seek once duration is known.
      const pending = pendingSeekRef.current;
      if (pending != null && pending > 0) {
        const d = isFiniteDuration(v.duration) ? v.duration : Number.POSITIVE_INFINITY;
        if (pending < d) {
          try {
            v.currentTime = pending;
            setCur(pending);
          } catch {
            /* ignore seek failure — position stays visible via offset */
          }
        }
        pendingSeekRef.current = null;
      }
      setCur(baseRef.current);
    };
    const onDur = () => {
      if (isFiniteDuration(v.duration)) setMediaDur(v.duration);
    };
    const onPlay = () => {
      setPlaying(true);
      try {
        v.playbackRate = rateRef.current;
      } catch {
        /* ignore */
      }
      report("start");
    };
    const onPlaying = () => setSwitching(false);
    const onPause = () => {
      setPlaying(false);
      report("stopped");
    };
    const onError = () => {
      if (modeRef.current !== "transcode") {
        escalate(); // ladder: direct → remux → transcode_audio → transcode
      } else {
        report("stopped");
        setError("Couldn't play this file in the browser — the codec may not be supported. Open it in Jellyfin directly instead.");
      }
    };
    const onTime = () => {
      setCur(posNow());
      const now = Date.now();
      if (now - lastReportRef.current < 5000) return;
      lastReportRef.current = now;
      report("timeupdate");
    };
    const onWaiting = () => setSwitching(true);
    const onEnded = () => {
      report("stopped");
      const next = nextEpisode(queueRef.current, item.item_id);
      setUpNext(next);
      if (next) startAuto(next);
    };

    v.addEventListener("loadedmetadata", onMeta);
    v.addEventListener("durationchange", onDur);
    v.addEventListener("play", onPlay);
    v.addEventListener("playing", onPlaying);
    v.addEventListener("waiting", onWaiting);
    v.addEventListener("pause", onPause);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("ended", onEnded);
    v.addEventListener("error", onError);
    const onFs = () => setIsFs(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFs);
    return () => {
      v.removeEventListener("loadedmetadata", onMeta);
      v.removeEventListener("durationchange", onDur);
      v.removeEventListener("play", onPlay);
      v.removeEventListener("playing", onPlaying);
      v.removeEventListener("waiting", onWaiting);
      v.removeEventListener("pause", onPause);
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("ended", onEnded);
      v.removeEventListener("error", onError);
      document.removeEventListener("fullscreenchange", onFs);
      clearAuto();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.item_id]);

  // Keyboard: space play/pause, ←/→ ±10s, m mute, f fullscreen.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA")) return;
      const v = videoRef.current;
      switch (e.key) {
        case " ":
          e.preventDefault();
          togglePlay();
          break;
        case "ArrowRight":
          if (v) seekTo(posNow() + SEEK_STEP);
          break;
        case "ArrowLeft":
          if (v) seekTo(posNow() - SEEK_STEP);
          break;
        case "m":
        case "M":
          toggleMute();
          break;
        case "f":
        case "F":
          toggleFullscreen();
          break;
        case "Escape":
          if (!document.fullscreenElement) onClose();
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onClose]);

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
  const ctrlBtn =
    "flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-sm text-white hover:bg-white/20";

  return (
    <div
      ref={rootRef}
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

      <div className="relative z-10 flex items-center justify-between gap-3 p-3">
        <div className="min-w-0 truncate text-sm font-medium text-zinc-100">
          {item.title}
          {desiredMode && (
            <span className="ml-2 rounded bg-zinc-800/80 px-1.5 py-0.5 align-middle text-[10px] font-medium tracking-wide text-zinc-400">
              {streamModeLabel(mode)}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="shrink-0 rounded-full bg-zinc-800/90 px-3 py-1 text-sm text-zinc-100 hover:bg-zinc-700"
        >
          Close
        </button>
      </div>

      <div className="relative z-10 flex flex-1 flex-col p-4">
        <div className="relative flex flex-1 items-center justify-center">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            src={src}
            onClick={togglePlay}
            className="max-h-full max-w-full cursor-pointer rounded-lg bg-black shadow-2xl"
          >
            {subSrc && <track key={subSrc} kind="subtitles" src={subSrc} default />}
          </video>

          {switching && !error && (
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/30">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-600 border-t-amber-400" />
              <span className="text-[11px] text-zinc-300">Preparing stream…</span>
            </div>
          )}

          {!playing && !error && !switching && (
            <button
              onClick={togglePlay}
              aria-label="Play"
              className="pointer-events-auto absolute left-1/2 top-1/2 flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-3xl text-white hover:bg-black/70"
            >
              ▶
            </button>
          )}

          {error && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/85 p-6 text-center">
              <div>
                <p className="text-sm text-zinc-100">⚠️ {error}</p>
                <p className="mt-1 text-xs text-zinc-500">Open it in Jellyfin directly instead.</p>
              </div>
            </div>
          )}

          {upNext && (
            <div className="absolute bottom-24 right-6 z-10 rounded-lg border border-zinc-700 bg-zinc-900/95 p-4 shadow-xl">
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

          {/* Custom control bar — total from the API runtime until the stream
              duration resolves, so length + progress are always correct. */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 rounded-b-lg bg-gradient-to-t from-black/90 via-black/55 to-transparent px-3 pb-2 pt-10">
            <input
              type="range"
              min={0}
              max={total > 0 ? total : 0}
              step={1}
              value={Math.min(cur, total > 0 ? total : cur)}
              disabled={total <= 0}
              onChange={(e) => seekTo(Number(e.target.value))}
              aria-label="Seek"
              className="pointer-events-auto h-1.5 w-full cursor-pointer accent-amber-400 disabled:opacity-40"
            />
            <div className="pointer-events-auto mt-1.5 flex items-center gap-3 text-[11px] text-zinc-100">
              <button onClick={togglePlay} aria-label={playing ? "Pause" : "Play"} className={ctrlBtn}>
                {playing ? "❚❚" : "▶"}
              </button>
              <button onClick={toggleMute} aria-label={muted ? "Unmute" : "Mute"} className={ctrlBtn}>
                {muted || volume === 0 ? "🔇" : volume < 0.5 ? "🔉" : "🔊"}
              </button>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={muted ? 0 : volume}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  const v = videoRef.current;
                  if (!v) return;
                  v.volume = val;
                  v.muted = val === 0;
                  setVolume(val);
                  setMuted(val === 0);
                }}
                aria-label="Volume"
                className="h-1 w-20 cursor-pointer accent-amber-400"
              />
              <span className="tabular-nums">
                {fmtTime(cur)} / {total > 0 ? fmtTime(total) : "--:--"}
              </span>
              {mode !== "direct" && (
                <span className="rounded bg-amber-400/15 px-1.5 py-0.5 font-medium text-amber-300">
                  {streamModeLabel(mode)}
                </span>
              )}
              <button
                onClick={toggleFullscreen}
                aria-label={isFs ? "Exit fullscreen" : "Fullscreen"}
                className={`${ctrlBtn} ml-auto`}
              >
                {isFs ? "🗗" : "⛶"}
              </button>
            </div>
          </div>
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
            {mode === "transcode_audio" ? " · ⚠ audio transcoding" : ""}
          </span>
        </div>
      </div>
    </div>
  );
}
