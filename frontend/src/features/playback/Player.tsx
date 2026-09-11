import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import {
  api, type PlaybackInfo, type PlaybackTrack, type ProgressPayload, type SubtitleRow,
} from "../../lib/api/client";
import { useQueryClient } from "@tanstack/react-query";
import { Icon } from "../../components/ui/Icon";
import {
  nextEpisode, prevEpisode, queueEntryCode, qualityFor, AUTOPLAY_DELAY_MS,
  QUALITY_OPTIONS, PLAYBACK_RATES,
  fmtTime, isFiniteDuration, clampSeek, pickStreamMode, hlsModeLabel,
  playMethodForMode, usesHls, hlsEngineFor, nextHlsMode, hlsConfigFor,
  abrBadgeLabel, shouldAutoHideChrome, warmGet, warmPut, warmDelete,
  WARM_AHEAD_SEC, loadPlayerPrefs, savePlayerPrefs, PLAYER_PREFS_KEY,
  subtitleRowLabel, resolveActiveSubtitle, rankSubtitleRows,
  activeSubtitleRowKey, localSubtitleRowKey, subtitleRowKey,
  fullscreenPlan, playerChromeFor,
  type AbrLevelFacts, type HlsEngine, type PlayerPrefs, type FullscreenPlan,
  type WebkitFullscreenVideo,
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
/**
 * One selectable subtitle row (Off / a local track / an OpenSubtitles result).
 *
 * A radio, not a `<select>`: the panel now shows remote results with usage counts
 * and per-row download state, which a native select cannot express. `aria-pressed`
 * keeps the choice announced for screen readers.
 */
function SubtitleChoiceRow({
  label, active, busy, hint, onClick,
}: {
  label: string;
  active: boolean;
  busy?: boolean;
  hint?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      aria-pressed={active}
      className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[11px] transition ${
        active
          ? "bg-accent/15 text-accent ring-1 ring-accent/30"
          : "bg-white/[.04] text-zinc-300 hover:bg-white/[.09]"
      } disabled:opacity-70`}
    >
      <span
        className={`grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full border ${
          active ? "border-accent" : "border-white/25"
        }`}
        aria-hidden="true"
      >
        {active ? <span className="h-1.5 w-1.5 rounded-full bg-accent" /> : null}
      </span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {hint ? <span className="shrink-0 text-[10px] font-medium text-zinc-400">{hint}</span> : null}
    </button>
  );
}

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

const readStored = (key: string): string | null => {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
};
const writeStored = (key: string, value: string): void => {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* private mode / quota — prefs just don't persist */
  }
};

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

  // Viewport facts for the chrome policy (a SHORT viewport — landscape phone, or a
  // short desktop window — collapses the header to one row). Rotation, a mobile URL
  // bar sliding away and entering/leaving fullscreen all arrive as one of these
  // events, so a single re-measure keeps every band honest.
  const [viewport, setViewport] = useState(() => ({
    vw: typeof window === "undefined" ? 0 : window.innerWidth,
    vh: typeof window === "undefined" ? 0 : window.innerHeight,
  }));
  useEffect(() => {
    const measure = () => setViewport({ vw: window.innerWidth, vh: window.innerHeight });
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("orientationchange", measure);
    window.visualViewport?.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("orientationchange", measure);
      window.visualViewport?.removeEventListener("resize", measure);
    };
  }, []);
  const chromeLayout = playerChromeFor(viewport);

  // Lock the page behind the player (the pattern Dialog already uses): without it,
  // iOS rubber-band scrolling drags the document under the fixed shell, which reads
  // as the player itself being misaligned.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

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
  // Persisted prefs (volume/mute/speed/quality cap) — loaded once per mount.
  const prefsRef = useRef<PlayerPrefs>(loadPlayerPrefs(readStored));
  const [isPip, setIsPip] = useState(false);
  // Plex-style settings overlay (speed/quality/tracks) — extra controls live
  // here; only playback essentials stay on the transport bar.
  const [showSettings, setShowSettings] = useState(false);
  const showSettingsRef = useRef(false);

  // Custom control bar state.
  const [playing, setPlaying] = useState(false);
  const [cur, setCur] = useState(0); // display position = video.currentTime
  const [mediaDur, setMediaDur] = useState(0); // stream duration once finite
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(1);
  const [isFs, setIsFs] = useState(false);
  // iOS native video fullscreen (iPhone has no Element fullscreen at all): tracked so
  // the button flips to "exit" there instead of lying about the state.
  const [isVideoFs, setIsVideoFs] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const [scrub, setScrub] = useState<number | null>(null);
  const scrubbingRef = useRef(false);
  // Auto-play after the next engine (re)build — preserved through mode/quality
  // switches so a pause + change doesn't unexpectedly start playing.
  const autoPlayRef = useRef(true);
  // Subtitle overlay state (item-time cues — trivially aligned now the media
  // timeline IS the item timeline).
  const [subText, setSubText] = useState<string | null>(null);
  const subCuesRef = useRef<VttCue[]>([]);
  // Subtitle PICKER state (plan §3.7). Local tracks arrive with playback-info;
  // OpenSubtitles results are fetched ONLY when the user asks, so opening the panel
  // never spends a download. `subBusyId` drives a per-row spinner (several selects
  // are impossible at once anyway — one is enough to block the rest).
  const [subRows, setSubRows] = useState<SubtitleRow[] | null>(null);
  const [subBusyId, setSubBusyId] = useState<string | null>(null);
  const [subSearching, setSubSearching] = useState(false);
  const [subRemaining, setSubRemaining] = useState<number | null>(null);
  const [subEnabled, setSubEnabled] = useState<boolean | null>(null);
  const [subDisabled, setSubDisabled] = useState(false);
  // The OpenSubtitles result the user picked. Kept separately from `subIndex`, because
  // the tick belongs on the row they CLICKED while `subIndex` addresses the stream that
  // actually plays — see activeSubtitleRowKey().
  const [subChoiceId, setSubChoiceId] = useState<string | null>(null);
  const [subNotice, setSubNotice] = useState<{ text: string; kind: "error" | "warn" } | null>(null);
  const subNoticeTimer = useRef<number | null>(null);

  modeRef.current = mode;
  rateRef.current = rate;
  showSettingsRef.current = showSettings;

  // EXACTLY ONE row of the subtitle picker is ticked, and it is the row that REPRESENTS
  // the current choice — the result the user picked if the panel has it, otherwise the
  // local track actually playing. Computed once here so a local row and a remote row can
  // never both claim it (see activeSubtitleRowKey).
  const activeKey = activeSubtitleRowKey(
    subRows,
    { subtitle_id: subChoiceId, index: subIndex },
    info?.subtitles ?? null,
  );

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

  // Series context from the riding queue (movies ride an empty queue): the
  // current entry's S/E code + its position in the season + prev/next entries.
  const curIdx = queue.findIndex((q) => q.id === item.item_id);
  const curEntry = curIdx >= 0 ? queue[curIdx] : null;
  const prevEntry = curEntry ? prevEpisode(queue, item.item_id) : null;
  const nextEntry = curEntry ? nextEpisode(queue, item.item_id) : null;
  const curCode = queueEntryCode(curEntry);
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
    setQuality(prefsRef.current.quality); // persisted cap, not a hardcoded reset
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
        if (!alive) return;
        setInfo(d || null);
        // Auto-apply the user's stored subtitle choice (spec criteria 4–5). The
        // server resolves the identity to a CURRENT index (indices are positional);
        // re-resolving here against the same track list is a cheap guard that also
        // covers a stale warm-cache entry. No match → apply NOTHING (the picker
        // opens) rather than show a different subtitle than the one chosen.
        setSubIndex(resolveActiveSubtitle(d?.subtitles ?? [], d?.preferred_subtitle ?? null));
        setSubChoiceId(d?.preferred_subtitle?.subtitle_id ?? null);
        // A different item means different results: never carry the previous
        // title's OpenSubtitles list (or its notice) across.
        setSubRows(null);
        setSubNotice(null);
        setSubDisabled(false);
        setSubBusyId(null);
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

  // Apply persisted preferences once per Player mount (volume/mute/speed/
  // quality cap carry across episodes AND browser sessions).
  useEffect(() => {
    const p = prefsRef.current;
    const v = videoRef.current;
    setVolume(p.volume);
    setMuted(p.muted);
    setRate(p.rate);
    setQuality(p.quality);
    if (v) {
      v.volume = p.volume;
      v.muted = p.muted;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Picture-in-Picture: track enter/leave on the single <video> element.
  useEffect(() => {
    const v = videoRef.current;
    if (!v || typeof HTMLVideoElement === "undefined" || !("requestPictureInPicture" in HTMLVideoElement.prototype)) return;
    const onEnter = () => setIsPip(true);
    const onLeave = () => setIsPip(false);
    v.addEventListener("enterpictureinpicture", onEnter);
    v.addEventListener("leavepictureinpicture", onLeave);
    return () => {
      v.removeEventListener("enterpictureinpicture", onEnter);
      v.removeEventListener("leavepictureinpicture", onLeave);
    };
  }, []);

  // ---------------------------------------------------------------- subtitles
  /** Show a non-blocking notice (quota/rate-limit/format errors and warnings).
   *  The plan is explicit: a subtitle problem must NEVER block playback, so these
   *  are a transient pill rather than the blocking error card. */
  const showSubNotice = (text: string, kind: "error" | "warn" = "error") => {
    setSubNotice({ text, kind });
    if (subNoticeTimer.current) window.clearTimeout(subNoticeTimer.current);
    subNoticeTimer.current = window.setTimeout(() => setSubNotice(null), 7000);
  };

  useEffect(() => () => {
    if (subNoticeTimer.current) window.clearTimeout(subNoticeTimer.current);
  }, []);

  /** Fetch the picker's rows (local tracks + ranked OpenSubtitles results).
   *  Called on demand — opening the panel must not spend a download. */
  const loadSubtitleRows = async (): Promise<void> => {
    if (subSearching) return;
    setSubSearching(true);
    try {
      const data = await api.searchSubtitles(item.item_id);
      setSubRows(data.results ?? []);
      setSubEnabled(data.enabled);
      setSubDisabled(data.disabled);
      if (data.remaining_downloads != null) setSubRemaining(data.remaining_downloads);
      if (data.warning) showSubNotice(data.warning, "warn");
      // The server's own resolution wins: it knows which track carries our identity.
      const idx = data.preferred_subtitle?.index;
      if (idx != null) setSubIndex(idx);
      setSubChoiceId(data.preferred_subtitle?.subtitle_id ?? null);
    } catch (e) {
      showSubNotice((e as Error)?.message || "Could not search subtitles");
    } finally {
      setSubSearching(false);
    }
  };

  /** Choose a LOCAL track: applies for this session, exactly as before.
   *  (The store only persists OpenSubtitles choices — there is no download to
   *  remember, and the item already carries the file.) */
  const chooseLocalSubtitle = (index: number | null) => {
    setSubIndex(index);
    setSubChoiceId(null);
    setSubNotice(null);
  };

  /** Download + attach + remember one OpenSubtitles result. */
  const chooseRemoteSubtitle = async (row: SubtitleRow) => {
    if (subBusyId || row.file_id == null) return;
    setSubBusyId(row.subtitle_id);
    try {
      const res = await api.selectSubtitle({
        item_id: item.item_id,
        file_id: row.file_id,
        language: row.language,
        display_title: row.display_title,
      });
      const index = res.preferred_subtitle?.index
        ?? resolveActiveSubtitle(res.subtitles ?? [], res.preferred_subtitle ?? null);
      setSubIndex(index);
      setSubChoiceId(row.subtitle_id);
      setSubDisabled(false);
      if (res.remaining_downloads != null) setSubRemaining(res.remaining_downloads);
      showSubNotice(
        `Added "${row.display_title}"${res.reused ? " — already on disk" : ""}`, "warn");
      // Re-read the TRACK LIST too: the delivered subtitle becomes a NEW local track,
      // and until playback-info is refreshed that row does not exist in the panel at
      // all — which is exactly how a successful download came to look like nothing had
      // happened (live 2026-09-12).
      const fresh = await api.playbackInfo(item.item_id).catch(() => null);
      if (fresh) setInfo(fresh);
      // Refresh the rows so the active marker and the usage count are the server's
      // numbers, not our optimistic guess.
      setSubSearching(false);
      await loadSubtitleRows();
    } catch (e) {
      showSubNotice((e as Error)?.message || "Could not add that subtitle");
    } finally {
      setSubBusyId(null);
    }
  };

  /** Turn subtitles off — and REMEMBER it, so the next playback stays off. */
  const turnSubtitlesOff = () => {
    setSubIndex(null);
    setSubChoiceId(null);
    setSubNotice(null);
    // Only worth a round trip when a choice exists to disable.
    if (info?.preferred_subtitle || subRows?.some((r) => r.active)) {
      setSubDisabled(true);
      void api.disableSubtitle(item.item_id).catch((e) => {
        setSubDisabled(false);
        showSubNotice((e as Error)?.message || "Could not save the subtitle setting");
      });
    }
  };

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

  // Publish the transport dock's REAL height as --rkm-dock-h, so every overlay
  // (subtitles, Up-Next card, settings panel) clears it instead of guessing a
  // bottom offset — and so it stays correct when the dock reflows (tier change on
  // rotate, a wrapped transport row, safe-area insets appearing).
  useEffect(() => {
    const dock = dockRef.current;
    const root = rootRef.current;
    if (!dock || !root || typeof ResizeObserver === "undefined") return;
    let last = -1;
    const publish = () => {
      const h = Math.round(dock.getBoundingClientRect().height);
      if (h === last) return;
      last = h;
      root.style.setProperty("--rkm-dock-h", `${h}px`);
    };
    publish();
    const ro = new ResizeObserver(publish);
    ro.observe(dock);
    return () => ro.disconnect();
  }, []);

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
    persistPrefs({ muted: v.muted });
  };

  // Fullscreen capability for THIS browser: the whole shell goes fullscreen where the
  // Element API exists (so the dock, subtitles and chrome travel with it), the video's
  // own fullscreen is the iOS fallback, and when neither exists the button is hidden
  // rather than rendering as a no-op.
  const fsPlan: FullscreenPlan = fullscreenPlan({
    elementFullscreen: typeof document !== "undefined" && document.fullscreenEnabled === true,
    videoFullscreen:
      typeof HTMLVideoElement !== "undefined" &&
      typeof (HTMLVideoElement.prototype as WebkitFullscreenVideo).webkitEnterFullscreen === "function",
  });
  const fullscreenActive = isFs || isVideoFs;

  const toggleFullscreen = () => {
    if (fsPlan === "element") {
      const el = rootRef.current;
      if (!el) return;
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
      else void el.requestFullscreen().catch(() => {});
      return;
    }
    if (fsPlan === "video") {
      // iPhone Safari: the <video>'s own fullscreen is the only one that exists.
      const v = videoRef.current as WebkitFullscreenVideo | null;
      if (!v) return;
      if (v.webkitDisplayingFullscreen) v.webkitExitFullscreen?.();
      else v.webkitEnterFullscreen?.();
    }
  };

  // --- Persisted prefs + Picture-in-Picture --------------------------------
  const persistPrefs = (patch: Partial<PlayerPrefs>) => {
    prefsRef.current = { ...prefsRef.current, ...patch };
    savePlayerPrefs(prefsRef.current, writeStored);
  };
  const pipSupported =
    typeof document !== "undefined" && "pictureInPictureEnabled" in document && Boolean(document.pictureInPictureEnabled);
  const togglePip = () => {
    const v = videoRef.current;
    if (!v) return;
    if (document.pictureInPictureElement) void document.exitPictureInPicture().catch(() => {});
    else void v.requestPictureInPicture().catch(() => {});
  };

  const reportNow = (event: ProgressPayload["event"]) => {
    const pos = posNow();
    if (resumeRef.current > 0 && pos < resumeRef.current - 1) return;
    const ticks = Math.round(pos * 1e7);
    // Runtime lets the api treat a report near the end as "finished" (mark the
    // item watched) instead of storing a resume point at the credits.
    const runtime = Number(totalRef.current) || 0;
    void api
      .reportProgress({
        item_id: item.item_id,
        position_ticks: ticks,
        is_paused: false,
        event,
        play_method: playMethodForMode(modeRef.current),
        runtime_ticks: runtime > 0 ? Math.round(runtime * 1e7) : 0,
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
      // Keep the OS/PiP position state honest on the report cadence.
      try {
        const ms = navigator.mediaSession;
        const dur = totalRef.current;
        const pos = v.currentTime || 0;
        if (ms && typeof ms.setPositionState === "function" && dur > 0 && pos >= 0) {
          ms.setPositionState({ duration: dur, playbackRate: rateRef.current, position: Math.min(pos, dur) });
        }
      } catch {
        /* transient / unsupported */
      }
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
    // iOS reports its own native player fullscreen through non-standard events.
    const onWkFs = () => setIsVideoFs(true);
    const onWkFsEnd = () => setIsVideoFs(false);
    v.addEventListener("webkitbeginfullscreen", onWkFs);
    v.addEventListener("webkitendfullscreen", onWkFsEnd);
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
      v.removeEventListener("webkitbeginfullscreen", onWkFs);
      v.removeEventListener("webkitendfullscreen", onWkFsEnd);
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
          if (showSettingsRef.current) {
            setShowSettings(false);
            markActivity();
          } else if (!document.fullscreenElement) {
            onClose();
          }
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onClose]);

  // The rows BEHIND the player (Continue Watching, Recently played/watched, the
  // item's watched tick / resume point) do NOT remount when the player closes —
  // Home stays mounted underneath it — so with `staleTime: 30s` and
  // `refetchOnWindowFocus: false` nothing refetches them and they keep showing
  // the state from before playback. That is why a title you just watched "isn't
  // in Continue Watching" until a reload. Invalidate on unmount so the position
  // just reported is on screen the moment the user is back in the app.
  // (Invalidating an ACTIVE query refetches it immediately, so the row updates
  // as the player closes, not on the next navigation.)
  const queryClient = useQueryClient();
  useEffect(
    () => () => {
      void queryClient.invalidateQueries({ queryKey: ["library"] });
    },
    [queryClient],
  );

  // Cinema auto-hide timer: armed ONLY while actively playing with nothing
  // loading/error/up-next/settings open; hidden chrome is revealed by activity.
  useEffect(() => {
    const busy = !playing || switching || Boolean(error) || Boolean(upNext) || showSettings;
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
  }, [playing, switching, error, upNext, showSettings]);

  // Media Session: makes the PiP window + OS media keys control playback and
  // shows the item title. Best-effort; unsupported actions are skipped.
  useEffect(() => {
    if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    const ms = navigator.mediaSession;
    try {
      ms.metadata = new MediaMetadata({ title: item.title, artist: "RKM Cinema", album: item.title });
    } catch {
      /* metadata is optional */
    }
    const onPlay = () => {
      const v = videoRef.current;
      if (v?.paused) void v.play().catch(() => {});
    };
    const onPause = () => {
      videoRef.current?.pause();
    };
    const onSeekTo = (d: MediaSessionActionDetails) => {
      const v = videoRef.current;
      if (!v || typeof d.seekTime !== "number") return;
      const total = totalRef.current;
      const target = clampSeek(d.seekTime, total > 0 ? total : d.seekTime);
      try {
        v.currentTime = target;
        paint(target);
      } catch {
        /* not seekable yet */
      }
    };
    const onSeek = (delta: number) => () => {
      const v = videoRef.current;
      if (!v) return;
      const pos = (v.currentTime || 0) + delta;
      const total = totalRef.current;
      const target = clampSeek(pos, total > 0 ? total : pos);
      try {
        v.currentTime = target;
        paint(target);
      } catch {
        /* ignore */
      }
    };
    const onNext = () => {
      const next = nextEpisode(queueRef.current, item.item_id);
      if (next) onSwitchRef.current?.(next);
    };
    const handlers: [MediaSessionAction, MediaSessionActionHandler | null][] = [
      ["play", onPlay],
      ["pause", onPause],
      ["seekto", onSeekTo],
      ["seekforward", onSeek(SEEK_STEP)],
      ["seekbackward", onSeek(-SEEK_STEP)],
      ["nexttrack", onNext],
    ];
    for (const [action, handler] of handlers) {
      try {
        ms.setActionHandler(action, handler);
      } catch {
        /* action unsupported in this browser */
      }
    }
    return () => {
      for (const [action] of handlers) {
        try {
          ms.setActionHandler(action, null);
        } catch {
          /* ignore */
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.item_id, item.title]);

  const playNext = () => {
    clearAuto();
    if (upNext) onSwitchRef.current?.(upNext);
  };
  const cancelNext = () => {
    clearAuto();
    setUpNext(null);
  };

  /** Manual prev/next episode skip: report stopped, then switch the entry. */
  const skipToEntry = (entry: QueueEntry) => {
    clearAuto();
    reportNow("stopped");
    onSwitchRef.current?.(entry);
  };

  // Premium control chrome — one coherent scale across the whole player. Below
  // `sm` the dock drops a tier (36px targets + `touch-manipulation`, so a fast
  // double tap on play/pause is two taps and not a page zoom) which is what lets a
  // 320px phone fit the whole transport without hiding anything essential.
  const ctrlBtn =
    "grid h-9 w-9 shrink-0 touch-manipulation place-items-center rounded-full bg-white/10 text-zinc-50 ring-1 ring-white/10 backdrop-blur-sm transition hover:bg-white/20 sm:h-10 sm:w-10";
  const panelLabel = "text-[10px] font-bold uppercase tracking-[0.18em] text-zinc-500";
  const overlaySelect =
    "h-9 min-w-0 flex-1 rounded-[10px] border border-white/[.08] bg-black/30 px-2.5 text-xs font-medium text-zinc-100 outline-none transition hover:border-white/15 focus:border-accent/50";
  const chipBtn = (active: boolean) =>
    `inline-flex h-7 shrink-0 items-center justify-center rounded-lg px-2.5 text-[11px] font-semibold transition ${
      active
        ? "bg-accent text-black shadow-[0_0_18px_rgba(255,196,0,.22)]"
        : "bg-white/[.06] text-zinc-300 hover:bg-white/[.12]"
    }`;

  return (
    <div
      ref={rootRef}
      className="rkm-player z-[var(--z-player)]"
      role="dialog"
      aria-modal="true"
      aria-label={`${item.title} player`}
      onPointerMove={markActivity}
      onPointerDown={markActivity}
      style={{ cursor: chromeHidden ? "none" : undefined }}
    >
      {/* Keyart backdrop: visible while the stream prepares (and through the chrome
          scrims). The picture itself letterboxes inside the <video>'s own black, so
          the space around it is never a translucent poster frame. */}
      <div
        className="pointer-events-none absolute inset-0 opacity-40 blur-md"
        style={{
          backgroundImage: `url(${backdrop})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
        aria-hidden="true"
      />
      <div className="pointer-events-none absolute inset-0 bg-black/55" aria-hidden="true" />

      {/* STAGE — the whole shell. The transport dock and the top chrome overlay it
          from the SHELL's own edges (see .rkm-player__dock / __top), and the <video>
          is out of flow, so no intrinsic media size can push either band off the
          visible screen. This is what "fit to the screen" means here.
          NOTE: the stage deliberately carries NO z-index — an indexed stage would
          create a stacking context and trap the settings panel / Up-Next card (z-30)
          BELOW the top chrome (z-20), making their buttons unclickable wherever the
          two bands meet (measured: the settings ✕ in short viewports). */}
      <div className="absolute inset-0">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          onClick={togglePlay}
          className={`absolute inset-0 h-full w-full bg-black object-contain ${
            chromeHidden ? "cursor-none" : "cursor-pointer"
          }`}
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

        {/* Non-blocking subtitle notice (quota exhausted, rate limit, bad format).
            A pill, not a dialog: the plan forbids letting a subtitle problem block
            playback, and the user may still be watching happily without subtitles. */}
        {subNotice && (
          <div
            role="status"
            className={`pointer-events-none absolute left-1/2 top-[calc(env(safe-area-inset-top,0px)+4.25rem)] z-40 max-w-[min(92vw,32rem)] -translate-x-1/2 rounded-full px-3.5 py-2 text-center text-[11px] font-semibold shadow-modal backdrop-blur-md ${
              subNotice.kind === "error" ? "bg-red-500/85 text-white" : "bg-amber-400/90 text-black"
            }`}
          >
            {subNotice.text}
          </div>
        )}

        {error && (
          <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/85 p-6 text-center">
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

        {/* Up-Next card — anchored above the transport dock (--rkm-dock-h), never
            below the fold, and never wider than the viewport on a phone. */}
        {upNext && (
          <div className="absolute bottom-[calc(var(--rkm-dock-h)+12px)] right-3 z-30 w-[calc(100%-1.5rem)] max-w-72 overflow-hidden rounded-2xl border border-white/10 bg-surface-2/95 shadow-modal backdrop-blur-md sm:right-5">
            <div className="flex items-center gap-3 p-4">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent/15 text-accent">
                <Icon name="play" size={16} filled />
              </span>
              <div className="min-w-0">
                <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-zinc-500">
                  Up next {autoSecs > 0 ? `· auto in ${autoSecs}s` : ""}
                </div>
                <div className="mt-0.5 flex items-center gap-1.5">
                  {queueEntryCode(upNext) ? (
                    <span className="shrink-0 rounded bg-accent/15 px-1 py-px text-[10px] font-bold text-accent">
                      {queueEntryCode(upNext)}
                    </span>
                  ) : null}
                  <span className="truncate text-sm font-semibold text-white">{upNext.name}</span>
                </div>
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
            HLS/direct timeline IS the item timeline, so alignment is exact, and the
            cue sits above the transport dock rather than behind it. */}
        {subText && (
          <div className="pointer-events-none absolute inset-x-0 bottom-[calc(var(--rkm-dock-h)+10px)] z-[5] flex justify-center px-4 sm:px-6">
            <div className="max-w-[85%] whitespace-pre-line rounded-lg bg-black/70 px-3.5 py-1.5 text-center text-base text-white shadow-lg backdrop-blur-[2px] [text-shadow:0_1px_3px_rgba(0,0,0,0.95)]">
              {subText}
            </div>
          </div>
        )}

        {/* Settings overlay (Plex-style): click anywhere outside to dismiss;
            Esc / the ✕ close it too. The panel rides above the transport dock and
            is height-capped to the space actually available, so it can never be
            clipped by the shell or push its own controls off-screen. */}
        {showSettings && (
          <div
            className="absolute inset-0 z-[15]"
            onPointerDown={() => setShowSettings(false)}
            aria-hidden="true"
          />
        )}

        {showSettings && (
          <div
            role="dialog"
            aria-label="Player settings"
            onPointerDown={(e) => e.stopPropagation()}
            onPointerEnter={onChromeEnter}
            onPointerLeave={onChromeLeave}
            className="absolute bottom-[calc(var(--rkm-dock-h)+10px)] right-3 z-30 flex max-h-[calc(100dvh-var(--rkm-dock-h)-1.75rem)] w-[340px] max-w-[calc(100%-1.5rem)] flex-col overflow-hidden rounded-2xl border border-white/10 bg-surface-2/90 shadow-[0_24px_80px_rgba(0,0,0,0.6)] backdrop-blur-2xl sm:right-5"
          >
            <div className="flex items-center justify-between border-b border-white/[.06] px-4 py-3">
              <span className={panelLabel}>Player settings</span>
              <button
                type="button"
                onClick={() => setShowSettings(false)}
                aria-label="Close settings"
                className="grid h-7 w-7 place-items-center rounded-full text-zinc-400 transition hover:bg-white/10 hover:text-white"
              >
                <Icon name="close" size={14} />
              </button>
            </div>

            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
              <section className="space-y-2">
                <div className={panelLabel}>Speed</div>
                <div className="flex flex-wrap gap-1.5">
                  {PLAYBACK_RATES.map((r) => (
                    <button
                      key={r}
                      type="button"
                      aria-pressed={rate === r}
                      onClick={() => {
                        setRate(r);
                        persistPrefs({ rate: r });
                      }}
                      className={chipBtn(rate === r)}
                    >
                      {r}×
                    </button>
                  ))}
                </div>
              </section>

              <section className="space-y-2">
                <div className={panelLabel}>Quality</div>
                <div className="flex flex-wrap gap-1.5">
                  {QUALITY_OPTIONS.map((q) => (
                    <button
                      key={q.label}
                      type="button"
                      aria-pressed={quality === q.label}
                      onClick={() => {
                        setQuality(q.label);
                        persistPrefs({ quality: q.label });
                      }}
                      className={chipBtn(quality === q.label)}
                    >
                      {q.label}
                    </button>
                  ))}
                </div>
                {usesHls(mode) ? (
                  <p className="text-[10px] font-medium tabular-nums text-zinc-500">
                    Live: {abrBadgeLabel(lvl)}
                    {lvl?.bitrate ? ` · ${Math.round(lvl.bitrate / 1e6)} Mbps` : ""}
                  </p>
                ) : null}
              </section>

              {info && info.audio.length > 0 ? (
                <section className="space-y-1.5">
                  <div className={panelLabel}>Audio track</div>
                  <select
                    value={audioIndex}
                    onChange={(e) => setAudioIndex(Number(e.target.value))}
                    className={overlaySelect}
                  >
                    <option value={0}>Default</option>
                    {info.audio.map((a) => (
                      <option key={a.index} value={a.index}>
                        {a.name}
                        {a.language ? ` (${a.language})` : ""}
                      </option>
                    ))}
                  </select>
                </section>
              ) : null}

              {/* Subtitles (spec §4): Off / the item's own tracks / OpenSubtitles
                  results with our usage counts. The item's tracks behave exactly as
                  before; remote rows are fetched only when asked, and a failure here
                  never touches the picture — it becomes a notice pill. */}
              {info ? (
                <section className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className={panelLabel}>Subtitles</div>
                    {subRemaining != null ? (
                      <span className="text-[10px] font-medium tabular-nums text-zinc-500">
                        {subRemaining} download{subRemaining === 1 ? "" : "s"} left today
                      </span>
                    ) : null}
                  </div>

                  <SubtitleChoiceRow
                    label="Off"
                    active={activeKey === null && subIndex == null && !subChoiceId}
                    onClick={turnSubtitlesOff}
                  />
                  {subDisabled ? (
                    <p className="text-[10px] font-medium text-zinc-500">
                      Off for this title — pick one to turn subtitles back on.
                    </p>
                  ) : null}

                  {(info.subtitles ?? []).map((t: PlaybackTrack) => (
                    <SubtitleChoiceRow
                      key={localSubtitleRowKey(t.index)}
                      hint={activeKey === localSubtitleRowKey(t.index) && subChoiceId
                        ? "downloaded" : undefined}
                      label={`${t.name}${t.language ? ` (${t.language})` : ""}`}
                      active={activeKey === localSubtitleRowKey(t.index)}
                      onClick={() => chooseLocalSubtitle(t.index)}
                    />
                  ))}

                  {subRows === null ? (
                    <button
                      type="button"
                      onClick={() => void loadSubtitleRows()}
                      disabled={subSearching}
                      className="inline-flex h-8 w-full items-center justify-center rounded-lg border border-white/10 bg-white/[.06] text-[11px] font-semibold text-zinc-100 transition hover:bg-white/[.12] disabled:opacity-60"
                    >
                      {subSearching ? "Searching OpenSubtitles…" : "Search OpenSubtitles"}
                    </button>
                  ) : (
                    <>
                      {rankSubtitleRows(subRows.filter((r) => !r.local)).map((row) => (
                        <SubtitleChoiceRow
                          key={row.subtitle_id}
                          label={subtitleRowLabel(row)}
                          active={activeKey === subtitleRowKey(row)}
                          busy={subBusyId === row.subtitle_id}
                          hint={subBusyId === row.subtitle_id ? "Downloading…" : undefined}
                          onClick={() => void chooseRemoteSubtitle(row)}
                        />
                      ))}
                      {subRows.filter((r) => !r.local).length === 0 ? (
                        <p className="text-[10px] font-medium text-zinc-500">
                          No OpenSubtitles results for this title.
                        </p>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => void loadSubtitleRows()}
                        disabled={subSearching}
                        className="inline-flex h-8 w-full items-center justify-center rounded-lg border border-white/10 bg-white/[.06] text-[11px] font-semibold text-zinc-100 transition hover:bg-white/[.12] disabled:opacity-60"
                      >
                        {subSearching ? "Searching…" : "Search again"}
                      </button>
                    </>
                  )}

                  {subEnabled === false ? (
                    <p className="text-[10px] font-medium text-zinc-500">
                      OpenSubtitles is not configured — set OPENSUBTITLES_API_KEY in .env to
                      search online subtitles.
                    </p>
                  ) : null}
                </section>
              ) : null}
            </div>

            <div className="flex items-center justify-between border-t border-white/[.06] px-4 py-2.5">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                  mode !== "direct" ? "bg-accent/15 text-accent" : "bg-white/[.07] text-zinc-400"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${mode !== "direct" ? "bg-accent" : "bg-zinc-500"}`}
                  aria-hidden="true"
                />
                {desiredMode ? hlsModeLabel(mode) : "Loading…"}
              </span>
              <span className="text-[10px] font-medium text-zinc-500">
                {info ? `${info.audio.length} audio · ${info.subtitles.length} sub` : "no track info"}
              </span>
            </div>
          </div>
        )}

        {/* TRANSPORT DOCK — pinned to the SHELL's bottom edge (never to the stage's),
            so its position cannot depend on how tall the picture happens to be, and
            it can never sit below the visible screen. Safe-area padding for the home
            indicator / browser toolbar lives in .rkm-player__dock.
            Two rows on purpose: the clock rides WITH the seek bar and the transport
            row holds only buttons, which is what lets the whole transport fit a 320px
            phone. The row may wrap as a last resort — the dock is bottom-anchored, so
            wrapping grows it UPWARD over the picture instead of off-screen. */}
        <div
          ref={dockRef}
          className={`rkm-player__dock pointer-events-none absolute inset-x-0 bottom-0 z-20 bg-gradient-to-t from-black/95 via-black/70 to-transparent transition-opacity duration-300 ${
            chromeHidden ? "opacity-0" : "opacity-100"
          }`}
        >
          <div
            onPointerEnter={onChromeEnter}
            onPointerLeave={onChromeLeave}
            className={`${chromeHidden ? "pointer-events-none" : "pointer-events-auto"} flex items-center gap-2 sm:gap-3`}
          >
            <span className="shrink-0 tabular-nums text-[11px] font-semibold text-zinc-100 sm:text-[12px]">
              {fmtTime(cur)}
            </span>
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
              className={`${chromeHidden ? "pointer-events-none" : "pointer-events-auto"} group relative flex h-6 min-w-0 flex-1 cursor-pointer touch-none items-center outline-none sm:h-5 ${total <= 0 ? "opacity-40" : ""}`}
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
            <span className="shrink-0 tabular-nums text-[11px] font-medium text-zinc-500 sm:text-[12px]">
              {total > 0 ? fmtTime(total) : "--:--"}
            </span>
          </div>
          <div
            onPointerEnter={onChromeEnter}
            onPointerLeave={onChromeLeave}
            className={`${chromeHidden ? "pointer-events-none" : "pointer-events-auto"} mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-100 sm:gap-2.5`}
          >
            <button onClick={togglePlay} aria-label={playing ? "Pause" : "Play"} className={ctrlBtn}>
              <Icon name={playing ? "pause" : "play"} size={17} filled={!playing} />
            </button>
            <button
              onClick={() => seekTo(posNow() - SEEK_STEP)}
              aria-label={`Back ${SEEK_STEP} seconds`}
              title={`Back ${SEEK_STEP} seconds`}
              className={ctrlBtn}
            >
              <Icon name="skip-back-10" size={19} />
            </button>
            <button
              onClick={() => seekTo(posNow() + SEEK_STEP)}
              aria-label={`Forward ${SEEK_STEP} seconds`}
              title={`Forward ${SEEK_STEP} seconds`}
              className={ctrlBtn}
            >
              <Icon name="skip-forward-10" size={19} />
            </button>
            {prevEntry ? (
              <button
                onClick={() => skipToEntry(prevEntry)}
                aria-label={`Previous episode ${queueEntryCode(prevEntry)}`}
                title={`Previous episode — ${prevEntry.name}`}
                className={`${ctrlBtn} hidden sm:grid`}
              >
                <Icon name="chevron-left" size={18} />
              </button>
            ) : null}
            {nextEntry ? (
              <button
                onClick={() => skipToEntry(nextEntry)}
                aria-label={`Next episode ${queueEntryCode(nextEntry)}`}
                title={`Next episode — ${nextEntry.name}`}
                className={`${ctrlBtn} hidden sm:grid`}
              >
                <Icon name="chevron-right" size={18} />
              </button>
            ) : null}
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
                persistPrefs({ volume: val, muted: val === 0 });
              }}
              aria-label="Volume"
              className="hidden h-1 w-16 cursor-pointer accent-[var(--accent)] sm:block sm:w-20"
            />
            {desiredMode ? (
              <span
                className={`hidden rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide sm:inline ${
                  mode !== "direct" ? "bg-accent/15 text-accent" : "bg-white/[.07] text-zinc-400"
                }`}
              >
                {hlsModeLabel(mode)}
              </span>
            ) : null}
            <button
              onClick={() => setShowSettings((s) => !s)}
              aria-label={showSettings ? "Close settings" : "Settings"}
              aria-expanded={showSettings}
              title="Settings"
              className={`ml-auto ${ctrlBtn} ${showSettings ? "bg-white/20 ring-white/30" : ""}`}
            >
              <Icon name="settings" size={17} />
            </button>
            {pipSupported ? (
              <button
                onClick={() => void togglePip()}
                aria-label={isPip ? "Exit picture-in-picture" : "Picture in picture"}
                title={isPip ? "Exit picture-in-picture" : "Picture in picture"}
                className={`${ctrlBtn} hidden px-2.5 sm:grid sm:w-auto`}
              >
                <span className={`text-[10px] font-extrabold tracking-wider ${isPip ? "text-accent" : ""}`}>PIP</span>
              </button>
            ) : null}
            {fsPlan !== "none" ? (
              <button
                onClick={toggleFullscreen}
                aria-label={fullscreenActive ? "Exit fullscreen" : "Fullscreen"}
                className={ctrlBtn}
              >
                <Icon name={fullscreenActive ? "minimize" : "maximize"} size={17} />
              </button>
            ) : null}
          </div>
        </div>
      </div>

      {/* TOP CHROME — an overlay anchored to the SHELL's own top edge, so it cannot
          move with the video. The gradient band is click-through: only the title row
          takes pointer events, and hiding is opacity-only (never layout), so hiding
          mid-playback can never resize the picture. */}
      <div
        className={`rkm-player__top pointer-events-none absolute inset-x-0 top-0 z-20 bg-gradient-to-b from-black/85 via-black/35 to-transparent pb-8 transition-opacity duration-300 ${
          chromeHidden ? "opacity-0" : "opacity-100"
        }`}
      >
        <div
          onPointerEnter={onChromeEnter}
          onPointerLeave={onChromeLeave}
          className={`flex min-w-0 items-center gap-3 ${
            chromeHidden ? "pointer-events-none" : "pointer-events-auto"
          }`}
        >
          <button
            onClick={onClose}
            aria-label="Close player"
            className="grid h-10 w-10 shrink-0 touch-manipulation place-items-center rounded-full bg-black/50 text-zinc-100 ring-1 ring-white/15 backdrop-blur-sm transition hover:bg-black/80 hover:text-white"
          >
            <Icon name="back" size={18} />
          </button>
          <div className="min-w-0">
            <div className="truncate text-[15px] font-semibold leading-tight tracking-[-0.01em] text-zinc-50">
              {item.title}
            </div>
            {/* On a short viewport (landscape phone) the header gives its second line
                back to the picture — the close button and title always stay. */}
            {curEntry && !chromeLayout.compactHeader ? (
              <div className="mt-1 flex items-center gap-2">
                <span className="shrink-0 rounded-md bg-white/[.08] px-1.5 py-px text-[10px] font-bold uppercase tracking-[0.12em] text-zinc-300">
                  {curCode}
                </span>
                <span className="truncate text-[11px] font-medium text-zinc-500">
                  {curIdx + 1} of {queue.length}
                </span>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
