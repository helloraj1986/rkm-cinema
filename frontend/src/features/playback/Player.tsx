import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import { api, type PlaybackInfo, type ProgressPayload } from "../../lib/api/client";
import { Icon } from "../../components/ui/Icon";
import {
  nextEpisode, qualityFor, AUTOPLAY_DELAY_MS, QUALITY_OPTIONS, PLAYBACK_RATES,
  fmtTime, isFiniteDuration, clampSeek, pickStreamMode, hlsModeLabel,
  playMethodForMode, usesHls, hlsEngineFor, nextHlsMode, hlsConfigFor,
  abrBadgeLabel, shouldAutoHideChrome, warmGet, warmPut, warmDelete,
  WARM_AHEAD_SEC, type AbrLevelFacts, type HlsEngine,
  parseVtt, activeCueText, type VttCue, type QueueEntry,
  type StreamMode,
} from "./lib";

export interface PlayTarget {
  item_id: string;
  title: string;
}

const SEEK_STEP = 10; // seconds for ← / → keys
const MPEGURL = "application/vnd.apple.mpegurl";

/** Pre-warm Jellyfin's pipe for an item that will play next: when the default
 *  route is HLS, fetch the master manifest once (no-store) so the transcode
 *  pipe + proxy are hot when the Player actually mounts. Best-effort only. */
function prefetchMasterFor(id: string, info: PlaybackInfo): void {
  const mode = pickStreamMode({
    quality: "Original",
    container: info.container,
    video: info.video ?? null,
    activeAudioCodec: info.audio?.[0]?.codec ?? null,
    forceNonDirect: false,
  });
  if (!usesHls(mode)) return;
  void fetch(api.hlsMasterUrl(id, { mode }), { cache: "no-store" }).catch(() => {});
}

/**
 * In-app player with Plex-style transport (HLS/MSE plan):
 *
 * - **direct** (Static file, HTTP-range seekable) for browser-safe MP4 — kept
 *   on the native <video> path with byte-range currentTime seeks.
 * - **remux / transcode_audio / transcode** ride **HLS** — hls.js on
 *   Chrome/Firefox/Edge over the same-origin proxy
 *   (`/api/jellyfin/hls/{id}/master.m3u8`), native HLS on Safari/iOS.
 *
 * Position = plain `video.currentTime` on the ITEM timeline for every mode
 * (the offset/restart-seek model is deleted): HLS seeks by asking the server
 * for the segment at the clicked time — a silent no-op seek is structurally
 * impossible. Audio/quality changes rebuild the master URL at the same
 * position; media errors escalate along the audio-aware HLS ladder
 * (remux → transcode_audio → transcode) before a friendly give-up.
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
  const engineStartRef = useRef(resumeRef.current); // where the NEXT engine begins
  const hasStartedRef = useRef(false); // any real playback yet? (resume vs live pos)
  // Position to seek once the media element has metadata (direct/native-HLS
  // resume + mid-play mode switches that plain-load a new URL).
  const pendingSeekRef = useRef<number | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const engineTypeRef = useRef<HlsEngine | null>(null);
  const lastReportRef = useRef(0);
  const queueRef = useRef(queue);
  const warmNextRef = useRef<(next: QueueEntry) => void>(() => {});
  const totalRef = useRef(0);
  const autoTimerRef = useRef<number | null>(null);
  const autoTimeoutRef = useRef<number | null>(null);
  const onSwitchRef = useRef(onSwitch);
  const modeRef = useRef<StreamMode>("direct");
  const rateRef = useRef(1);
  const srcKeyRef = useRef("");
  useEffect(() => {
    queueRef.current = queue;
    onSwitchRef.current = onSwitch;
  }, [queue, onSwitch]);

  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(true); // engine (re)loading
  const [upNext, setUpNext] = useState<QueueEntry | null>(null);
  const [autoSecs, setAutoSecs] = useState(0);
  const [info, setInfo] = useState<PlaybackInfo | null>(null);
  const [audioIndex, setAudioIndex] = useState(0); // 0 = default (no override)
  const [subIndex, setSubIndex] = useState<number | null>(null); // null = off
  const [quality, setQuality] = useState("Original");
  const [rate, setRate] = useState(1);
  // How Jellyfin serves it: direct (progressive) or an HLS mode (remux /
  // transcode_audio / transcode). The mode chip shows the label.
  const [mode, setMode] = useState<StreamMode>("direct");
  // Live ABR level from hls.js (LEVEL_SWITCHED) — powers the passive
  // "Auto · 1080p" badge. Null until an HLS level actually switches.
  const [lvl, setLvl] = useState<AbrLevelFacts | null>(null);
  // Cinema chrome auto-hide. Refs keep per-mousemove work off the render path;
  // the timer only ticks while actively playing.
  const [chromeHidden, setChromeHidden] = useState(false);
  const chromeHiddenRef = useRef(false);
  const lastActRef = useRef<number>(Date.now());
  const hoverChromeRef = useRef(false);
  const hideTimerRef = useRef<number | null>(null);

  // Custom control bar state.
  const [playing, setPlaying] = useState(false);
  const [cur, setCur] = useState(0); // display position = video.currentTime
  const [mediaDur, setMediaDur] = useState(0); // stream duration once finite
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(1);
  const [isFs, setIsFs] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);
  const [scrub, setScrub] = useState<number | null>(null);
  const scrubbingRef = useRef(false);
  // Auto-play after the next engine (re)build — preserved through mode/quality
  // switches so a pause + change doesn't unexpectedly start playing.
  const autoPlayRef = useRef(true);
  // Subtitle overlay state (item-time cues — trivially aligned now the media
  // timeline IS the item timeline).
  const [subText, setSubText] = useState<string | null>(null);
  const subCuesRef = useRef<VttCue[]>([]);

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

  const bitrate = qualityFor(quality);
  // Direct = progressive stream URL (browser byte-range seeks). HLS modes =
  // same-origin master URL built with the mode's codec pair.
  const directSrc = api.streamUrl(item.item_id, {
    ...(audioIndex > 0 ? { audio_stream_index: audioIndex } : {}),
  });
  const hlsSrc = usesHls(mode)
    ? api.hlsMasterUrl(item.item_id, {
        mode,
        ...(audioIndex > 0 ? { audio_stream_index: audioIndex } : {}),
        ...(bitrate && mode !== "remux" ? { max_bitrate: bitrate } : {}),
      })
    : "";
  const engineKey = usesHls(mode) ? hlsSrc : directSrc;
  const backdrop = api.backdropUrl(item.item_id);
  // Display total: the API runtime (scan metadata) is authoritative; fall back
  // to the resolved stream duration. HLS VOD durations resolve to ~runtime.
  const total =
    runtime > 0
      ? runtime
      : isFiniteDuration(mediaDur)
        ? mediaDur
        : 0;

  const posNow = () => (videoRef.current ? videoRef.current.currentTime || 0 : 0);
  totalRef.current = total;
  // Where the NEXT engine load should start: the live position once anything
  // has played, otherwise the mount resume point.
  const currentTarget = () => (hasStartedRef.current ? posNow() : resumeRef.current);
  // Paint a display position + the active subtitle cue (item-time based).
  const paint = (p: number) => {
    setCur(p);
    setSubText(activeCueText(subCuesRef.current, p));
  };

  // Switch the engine (mode / desired-route / quality / audio / escalation).
  // HLS rebuilds the master URL; the build effect restarts at `at` so the
  // switch is seamless. Direct keeps the plain <video> reload path.
  const switchModeTo = (next: StreamMode, at?: number) => {
    const v = videoRef.current;
    autoPlayRef.current = v ? !v.paused : autoPlayRef.current;
    engineStartRef.current = at ?? currentTarget();
    setMode(next);
    setMediaDur(0);
    setError(null);
    setSwitching(true);
    paint(engineStartRef.current);
  };

  // Auto-route once playback-info resolves (or when quality/audio change).
  useEffect(() => {
    if (!desiredMode || desiredMode === mode) return;
    switchModeTo(desiredMode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [desiredMode]);

  // (Re)build the playback engine when the source changes. Mode switches,
  // quality/audio changes and escalations all land here via engineKey.
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !engineKey || engineKey === srcKeyRef.current) return;
    srcKeyRef.current = engineKey;
    if (engineTypeRef.current === null) {
      const ua = navigator.userAgent || "";
      // iPadOS 13+ masquerades as a Macintosh UA — detect via touch support.
      const appleMobile =
        /iPhone|iPad|iPod/.test(ua) ||
        (/Macintosh/.test(ua) && typeof window !== "undefined" && "ontouchstart" in window && navigator.maxTouchPoints > 1);
      engineTypeRef.current = hlsEngineFor(
        () => v.canPlayType(MPEGURL),
        Hls.isSupported(),
        appleMobile,
      );
    }
    const engineType = engineTypeRef.current;
    const isHls = usesHls(modeRef.current);
    const start = engineStartRef.current;
    engineStartRef.current = 0; // consumed by this build
    setSwitching(true);

    const teardownHls = () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      setLvl(null);
      v.removeAttribute("src");
      try {
        v.load();
      } catch {
        /* element may be detached during unmount */
      }
    };
    teardownHls();

    if (!isHls) {
      // Native direct play (browser-safe MP4) — byte-range seek via currentTime.
      pendingSeekRef.current = start > 0 ? start : null;
      v.src = engineKey;
      try {
        v.load();
        if (autoPlayRef.current) void v.play().catch(() => {});
      } catch {
        /* playback resumes on user gesture if autoplay is blocked */
      }
      return;
    }

    if (engineType === "native") {
      // Safari/iOS native HLS — no hls.js needed; seek = currentTime set.
      pendingSeekRef.current = start > 0 ? start : null;
      v.src = engineKey;
      try {
        v.load();
        if (autoPlayRef.current) void v.play().catch(() => {});
      } catch {
        /* resume on gesture */
      }
      return;
    }

    if (engineType === "hlsjs") {
      const hls = new Hls(hlsConfigFor({ startPosition: start }));
      hlsRef.current = hls;
      hls.loadSource(engineKey);
      hls.attachMedia(v);
      // Track the live ABR level so the badge shows the REAL playing ladder
      // rung (informational only — the Quality select remains a cap).
      hls.on(Hls.Events.LEVEL_SWITCHED, (_evt, data) => {
        const level = hls.levels[data.level];
        setLvl(level ? { height: level.height, bitrate: level.bitrate } : null);
      });
      hls.on(Hls.Events.ERROR, (_evt, data) => {
        if (data.fatal) escalateHls();
      });
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (autoPlayRef.current) void v.play().catch(() => {});
      });
      return;
    }

    // engineType === "none": no MSE and no native HLS — can't play HLS.
    setError("Your browser can't play HLS streams (no MediaSource support).");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engineKey, item.item_id]);

  // Load track info once per item (audio/subtitle pickers + routing facts).
  useEffect(() => {
    let alive = true;
    setInfo(null);
    setAudioIndex(0);
    setSubIndex(null);
    setQuality("Original");
    setMode("direct");
    setMediaDur(0);
    srcKeyRef.current = "";
    engineTypeRef.current = null;
    engineStartRef.current = resumeRef.current;
    hasStartedRef.current = false;
    pendingSeekRef.current = resumeRef.current > 0 ? resumeRef.current : null;
    // Warm-start consume: when this item was prefetched as the "next", resolve
    // from the warm promise (no cold fetch, no spinner). Delete so a replay
    // refetches fresh even inside the TTL window.
    const warm = warmGet(item.item_id);
    const infoP = warm ? warm.info : api.playbackInfo(item.item_id);
    warmDelete(item.item_id);
    infoP
      .then((d) => {
        if (alive) setInfo(d || null);
      })
      .catch(() => {
        /* stay direct; the error-ladder still rescues a bad direct attempt */
      });
    return () => {
      alive = false;
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.item_id]);

  // Fetch + parse the selected subtitle stream as item-time cues. Native
  // <track> doesn't survive engine switches reliably, so the overlay renders
  // from these cues instead (aligned via currentTime — trivially correct on
  // the HLS timeline).
  useEffect(() => {
    let alive = true;
    subCuesRef.current = [];
    setSubText(null);
    if (subIndex == null || !info) return;
    const source = info.media_source_id || item.item_id;
    fetch(api.subtitleUrl(item.item_id, source, subIndex))
      .then((r) => (r.ok ? r.text() : ""))
      .then((t) => {
        if (alive) {
          subCuesRef.current = parseVtt(t);
          paint(posNow());
        }
      })
      .catch(() => {
        if (alive) subCuesRef.current = [];
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subIndex, item.item_id, info?.media_source_id]);

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

  // Plain currentTime seek for EVERY mode. Direct MP4 byte-range-seeks; HLS
  // (hls.js / native) fetches the segment at the target — the transport no
  // longer needs restart-at-StartTimeTicks or an offset model.
  const seekTo = (seconds: number) => {
    const v = videoRef.current;
    if (!v) return;
    const target = clampSeek(seconds, total > 0 ? total : seconds);
    try {
      v.currentTime = target;
      paint(target);
    } catch {
      /* not seekable yet — position stays visible via the bar */
    }
  };

  const escalateHls = () => {
    const v = videoRef.current;
    const wasPlaying = v ? !v.paused : false;
    autoPlayRef.current = wasPlaying;
    const next = nextHlsMode(modeRef.current);
    if (!next) {
      reportNow("stopped");
      setError(
        "Couldn't play this file in the browser — even HLS transcoding failed. Open it in Jellyfin directly instead.",
      );
      return;
    }
    switchModeTo(next);
  };

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) void v.play().catch(() => {});
    else v.pause();
  };

  // --- Cinema chrome auto-hide -------------------------------------------
  const revealChrome = () => {
    if (chromeHiddenRef.current) {
      chromeHiddenRef.current = false;
      setChromeHidden(false);
    }
  };
  const hideChrome = () => {
    if (!chromeHiddenRef.current) {
      chromeHiddenRef.current = true;
      setChromeHidden(true);
    }
  };
  // Any pointer/keyboard activity on the player resets the idle clock + reveals.
  const markActivity = () => {
    lastActRef.current = Date.now();
    revealChrome();
  };
  const onChromeEnter = () => {
    hoverChromeRef.current = true;
    revealChrome();
  };
  const onChromeLeave = () => {
    hoverChromeRef.current = false;
    lastActRef.current = Date.now(); // a fresh idle period starts on exit
  };

  // --- Warm-start: prefetch the next item so Play-next is instant -----------
  const warmNext = (next: QueueEntry) => {
    if (warmGet(next.id)) return; // already warming / warm
    const info = api
      .playbackInfo(next.id)
      .then((d) => {
        if (d) prefetchMasterFor(next.id, d); // hot transcode pipe for HLS routes
        return d;
      })
      .catch(() => null);
    warmPut(next.id, { info, at: Date.now() });
  };
  warmNextRef.current = warmNext;

  // --- Custom seek bar (div + pointer capture). A native <input type=range>
  // proved unreliable here: mouse events can miss its thin hit area and a
  // controlled range leaves the thumb visually at the click point when the
  // underlying position doesn't change — exactly the "bar moved, video didn't"
  // symptom. The div bar owns its fill/thumb, so UI can never desync.
  const barPosFromClientX = (clientX: number): number => {
    const el = barRef.current;
    if (!el || total <= 0) return 0;
    const rc = el.getBoundingClientRect();
    const frac = rc.width > 0 ? (clientX - rc.left) / rc.width : 0;
    return clampSeek(Math.round(frac * total), total);
  };
  const onBarPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    scrubbingRef.current = true;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    setScrub(barPosFromClientX(e.clientX));
  };
  const onBarPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!scrubbingRef.current) return;
    e.stopPropagation();
    setScrub(barPosFromClientX(e.clientX));
  };
  const onBarPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!scrubbingRef.current) return;
    e.stopPropagation();
    scrubbingRef.current = false;
    const target = scrub ?? barPosFromClientX(e.clientX);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    setScrub(null);
    if (target > 0) seekTo(target);
  };
  const onBarPointerCancel = () => {
    scrubbingRef.current = false;
    setScrub(null);
  };
  const onBarKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    let target: number | null = null;
    if (e.key === "ArrowRight") target = posNow() + SEEK_STEP;
    else if (e.key === "ArrowLeft") target = posNow() - SEEK_STEP;
    else if (e.key === "Home") target = 0;
    else if (e.key === "End") target = total > 0 ? total : posNow();
    if (target == null) return;
    e.preventDefault();
    e.stopPropagation();
    seekTo(target);
  };
  const barPos = scrub ?? Math.min(cur, total > 0 ? total : cur);
  const barPct = total > 0 ? Math.min(100, (barPos / total) * 100) : 0;

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

  const reportNow = (event: ProgressPayload["event"]) => {
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

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const report = (event: ProgressPayload["event"]) => reportNow(event);

    const onMeta = () => {
      if (isFiniteDuration(v.duration)) setMediaDur(v.duration);
      hasStartedRef.current = true;
      // Direct / native-HLS resume + mid-play reloads: seek once duration is
      // known (hls.js instead consumes startPosition at build time).
      const pending = pendingSeekRef.current;
      if (pending != null && pending > 0) {
        const d = isFiniteDuration(v.duration) ? v.duration : Number.POSITIVE_INFINITY;
        if (pending < d) {
          try {
            v.currentTime = pending;
          } catch {
            /* ignore seek failure — position stays visible via the bar */
          }
        }
        pendingSeekRef.current = null;
      }
      paint(v.currentTime || 0);
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
    const onPlaying = () => {
      hasStartedRef.current = true;
      setSwitching(false);
    };
    const onCanPlay = () => {
      // Autoplay may be blocked/paused: clear the "Preparing stream…" spinner.
      if (v.paused) setSwitching(false);
    };
    const onPause = () => {
      setPlaying(false);
      report("stopped");
    };
    const onError = () => {
      // hls.js reports its own fatal errors (escalateHls); don't double-fire.
      if (hlsRef.current) return;
      const next = nextHlsMode(modeRef.current);
      if (!next) {
        report("stopped");
        setError(
          "Couldn't play this file in the browser — the codec may not be supported. Open it in Jellyfin directly instead.",
        );
        return;
      }
      switchModeTo(next);
    };
    const onTime = () => {
      paint(posNow());
      // Warm the next queue entry as this item nears its end so Play-next and
      // auto-advance skip the cold start (deduped by the warm cache).
      const dur = isFiniteDuration(v.duration) ? v.duration : totalRef.current;
      const rem = dur > 0 ? dur - (v.currentTime || 0) : Number.POSITIVE_INFINITY;
      if (rem <= WARM_AHEAD_SEC) {
        const next = nextEpisode(queueRef.current, item.item_id);
        if (next) warmNextRef.current?.(next);
      }
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
      if (next) {
        warmNextRef.current?.(next); // instant Play-next once the card shows
        startAuto(next);
      }
    };

    v.addEventListener("loadedmetadata", onMeta);
    v.addEventListener("durationchange", onDur);
    v.addEventListener("play", onPlay);
    v.addEventListener("playing", onPlaying);
    v.addEventListener("canplay", onCanPlay);
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
      v.removeEventListener("canplay", onCanPlay);
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
      markActivity();
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

  // Cinema auto-hide timer: armed ONLY while actively playing with nothing
  // loading/error/up-next; hidden chrome is revealed by any activity above.
  useEffect(() => {
    const busy = !playing || switching || Boolean(error) || Boolean(upNext);
    if (busy) {
      if (hideTimerRef.current != null) window.clearInterval(hideTimerRef.current);
      hideTimerRef.current = null;
      revealChrome();
      return;
    }
    if (hideTimerRef.current == null) {
      hideTimerRef.current = window.setInterval(() => {
        if (
          shouldAutoHideChrome({
            playing: true,
            switching: false,
            error: false,
            upNext: false,
            hoverChrome: hoverChromeRef.current,
            idleMs: Date.now() - lastActRef.current,
          })
        ) {
          hideChrome();
        }
      }, 400);
    }
    return () => {
      if (hideTimerRef.current != null) window.clearInterval(hideTimerRef.current);
      hideTimerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, switching, error, upNext]);

  const playNext = () => {
    clearAuto();
    if (upNext) onSwitchRef.current?.(upNext);
  };
  const cancelNext = () => {
    clearAuto();
    setUpNext(null);
  };

  const selectCls =
    "rounded-[8px] border border-white/[.08] bg-surface-2/90 px-2.5 py-2 text-xs font-medium text-zinc-100 outline-none transition backdrop-blur-sm focus:border-accent/50";
  const ctrlBtn =
    "grid h-10 w-10 place-items-center rounded-full bg-white/10 text-zinc-50 ring-1 ring-white/10 backdrop-blur-sm transition hover:bg-white/20";

  return (
    <div
      ref={rootRef}
      className="fixed inset-0 z-[var(--z-player)] flex flex-col bg-black"
      role="dialog"
      aria-modal="true"
      aria-label={`${item.title} player`}
      onPointerMove={markActivity}
      onPointerDown={markActivity}
      style={{ cursor: chromeHidden ? "none" : undefined }}
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

      <div
        onPointerEnter={onChromeEnter}
        onPointerLeave={onChromeLeave}
        className={`relative z-10 flex items-center justify-between gap-3 bg-gradient-to-b from-black/80 to-transparent p-3 pr-4 transition-opacity duration-300 sm:p-4 sm:pr-5 ${
          chromeHidden ? "pointer-events-none opacity-0" : "opacity-100"
        }`}
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <button
            onClick={onClose}
            aria-label="Close player"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-black/50 text-zinc-100 ring-1 ring-white/15 backdrop-blur-sm transition hover:bg-black/80 hover:text-white"
          >
            <Icon name="back" size={17} />
          </button>
          <div className="min-w-0 truncate text-sm font-semibold text-zinc-50">{item.title}</div>
          {desiredMode && (
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide ${
                mode !== "direct" ? "bg-accent/15 text-accent" : "bg-white/10 text-zinc-300"
              }`}
            >
              {hlsModeLabel(mode)}
            </span>
          )}
        </div>
        <div className="shrink-0 text-right text-[11px] font-medium tabular-nums text-zinc-400">
          {fmtTime(cur)} / {total > 0 ? fmtTime(total) : "--:--"}
        </div>
      </div>

      <div className="relative z-10 flex flex-1 flex-col p-4">
        <div className="relative flex flex-1 items-center justify-center">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            onClick={togglePlay}
            className={`max-h-full max-w-full rounded-lg bg-black shadow-2xl ${chromeHidden ? "cursor-none" : "cursor-pointer"}`}
          />

          {switching && !error && (
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/30">
              <div className="h-9 w-9 animate-spin rounded-full border-2 border-white/15 border-t-accent" />
              <span className="text-[11px] font-medium tracking-wide text-zinc-300">Preparing stream…</span>
            </div>
          )}

          {!playing && !error && !switching && (
            <button
              onClick={togglePlay}
              aria-label="Play"
              className="pointer-events-auto absolute left-1/2 top-1/2 grid h-20 w-20 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-black/55 text-white ring-1 ring-white/20 backdrop-blur-md transition hover:bg-black/75 hover:ring-white/40"
            >
              <Icon name="play" size={34} filled />
            </button>
          )}

          {error && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/85 p-6 text-center">
              <div className="max-w-md rounded-2xl border border-white/10 bg-surface-2/90 p-6 shadow-modal">
                <p className="text-sm font-semibold text-zinc-100">{error}</p>
                <button
                  type="button"
                  onClick={onClose}
                  className="mt-4 inline-flex h-10 items-center justify-center rounded-[10px] border border-white/10 bg-white/[.07] px-4 text-sm font-bold text-zinc-100 transition hover:bg-white/[.12]"
                >
                  Close player
                </button>
              </div>
            </div>
          )}

          {upNext && (
            <div className="absolute bottom-28 right-6 z-10 w-72 overflow-hidden rounded-2xl border border-white/10 bg-surface-2/95 shadow-modal backdrop-blur-md">
              <div className="flex items-center gap-3 p-4">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent/15 text-accent">
                  <Icon name="play" size={16} filled />
                </span>
                <div className="min-w-0">
                  <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-zinc-500">
                    Up next {autoSecs > 0 ? `· auto in ${autoSecs}s` : ""}
                  </div>
                  <div className="truncate text-sm font-semibold text-white">{upNext.name}</div>
                </div>
              </div>
              <div className="flex gap-2 border-t border-white/[.06] px-4 py-3">
                <button
                  onClick={playNext}
                  className="inline-flex h-9 flex-1 items-center justify-center gap-1.5 rounded-[8px] bg-accent text-xs font-bold text-black transition hover:bg-accent-hover"
                >
                  <Icon name="play" size={12} filled />
                  Play next
                </button>
                <button
                  onClick={cancelNext}
                  className="inline-flex h-9 flex-1 items-center justify-center rounded-[8px] border border-white/10 bg-white/[.06] text-xs font-semibold text-zinc-200 transition hover:bg-white/[.12]"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Subtitle overlay — item-time cues parsed from the VTT proxy. The
              HLS/direct timeline IS the item timeline, so alignment is exact. */}
          {subText && (
            <div className="pointer-events-none absolute inset-x-0 bottom-24 z-[5] flex justify-center px-6">
              <div className="max-w-[85%] whitespace-pre-line rounded-lg bg-black/70 px-3.5 py-1.5 text-center text-base text-white shadow-lg backdrop-blur-[2px] [text-shadow:0_1px_3px_rgba(0,0,0,0.95)]">
                {subText}
              </div>
            </div>
          )}

          {/* Custom control bar — total from the API runtime until the stream
              duration resolves, so length + progress are always correct. */}
          <div
            onPointerEnter={onChromeEnter}
            onPointerLeave={onChromeLeave}
            className={`pointer-events-none absolute inset-x-0 bottom-0 rounded-b-lg bg-gradient-to-t from-black/90 via-black/60 to-transparent px-3 pb-2.5 pt-12 transition-opacity duration-300 sm:px-5 ${
              chromeHidden ? "opacity-0" : "opacity-100"
            }`}
          >
            <div
              ref={barRef}
              role="slider"
              tabIndex={0}
              aria-label="Seek"
              aria-valuemin={0}
              aria-valuemax={total > 0 ? Math.round(total) : 0}
              aria-valuenow={Math.round(barPos)}
              aria-disabled={total <= 0}
              onClick={(e) => e.stopPropagation()}
              onPointerDown={(e) => {
                markActivity();
                onBarPointerDown(e);
              }}
              onPointerMove={(e) => {
                markActivity();
                onBarPointerMove(e);
              }}
              onPointerUp={onBarPointerUp}
              onPointerCancel={onBarPointerCancel}
              onKeyDown={onBarKeyDown}
              onPointerEnter={onChromeEnter}
              onPointerLeave={onChromeLeave}
              className={`${chromeHidden ? "pointer-events-none" : "pointer-events-auto"} group relative flex h-5 w-full cursor-pointer touch-none items-center outline-none ${total <= 0 ? "opacity-40" : ""}`}
            >
              <div className="relative h-1 w-full overflow-visible rounded-full bg-white/20">
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-accent"
                  style={{ width: `${barPct}%` }}
                />
              </div>
              <div
                className="pointer-events-none absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent shadow-[0_0_0_4px_rgba(255,196,0,.25)] transition-opacity group-hover:shadow-[0_0_0_5px_rgba(255,196,0,.3)]"
                style={{ left: `${barPct}%` }}
              />
            </div>
            <div
              onPointerEnter={onChromeEnter}
              onPointerLeave={onChromeLeave}
              className={`${chromeHidden ? "pointer-events-none" : "pointer-events-auto"} mt-2 flex items-center gap-2.5 text-[11px] text-zinc-100 sm:gap-3`}
            >
              <button onClick={togglePlay} aria-label={playing ? "Pause" : "Play"} className={ctrlBtn}>
                <Icon name={playing ? "pause" : "play"} size={17} filled={!playing} />
              </button>
              <button
                onClick={toggleMute}
                aria-label={muted || volume === 0 ? "Unmute" : "Mute"}
                className={ctrlBtn}
              >
                <Icon name={muted || volume === 0 ? "volume-x" : "volume"} size={17} />
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
                className="h-1 w-16 cursor-pointer accent-[var(--accent)] sm:w-20"
              />
              {mode !== "direct" && (
                <span className="hidden rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-semibold text-accent sm:inline">
                  {hlsModeLabel(mode)}
                </span>
              )}
              <span className="ml-auto flex items-center gap-1 tabular-nums text-zinc-300">
                <Icon name="clock" size={12} className="text-zinc-500" />
                {fmtTime(cur)}
              </span>
              <button
                onClick={toggleFullscreen}
                aria-label={isFs ? "Exit fullscreen" : "Fullscreen"}
                className={ctrlBtn}
              >
                <Icon name={isFs ? "minimize" : "maximize"} size={17} />
              </button>
            </div>
          </div>
        </div>

        {/* Item-3 player controls */}
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2.5 rounded-2xl border border-white/[.06] bg-surface-2/70 px-4 py-3 backdrop-blur-sm">
          <label className="flex items-center gap-2 text-xs font-medium text-zinc-400">
            Speed
            <select value={rate} onChange={(e) => setRate(Number(e.target.value))} className={selectCls}>
              {PLAYBACK_RATES.map((r) => (
                <option key={r} value={r}>{r}×</option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 text-xs font-medium text-zinc-400">
            Quality
            <select value={quality} onChange={(e) => setQuality(e.target.value)} className={selectCls}>
              {QUALITY_OPTIONS.map((q) => (
                <option key={q.label} value={q.label}>{q.label}</option>
              ))}
            </select>
          </label>

          {usesHls(mode) && lvl ? (
            <span
              title={lvl.bitrate ? `${Math.round(lvl.bitrate / 1e6)} Mbps live` : "Live ABR level"}
              className="inline-flex items-center rounded-full bg-white/[.06] px-2 py-0.5 text-[10px] font-semibold tabular-nums text-zinc-300"
            >
              {abrBadgeLabel(lvl)}
            </span>
          ) : null}

          {info && info.audio.length > 0 && (
            <label className="flex items-center gap-2 text-xs font-medium text-zinc-400">
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
            <label className="flex items-center gap-2 text-xs font-medium text-zinc-400">
              Subs
              <select
                value={subIndex == null ? "" : String(subIndex)}
                onChange={(e) => setSubIndex(e.target.value === "" ? null : Number(e.target.value))}
                className={selectCls}
              >
                <option value="">Off</option>
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
