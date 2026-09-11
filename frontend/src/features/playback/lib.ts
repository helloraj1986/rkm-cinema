/**
 * Pure helpers for the playback slice (Phase 3b), mirroring the legacy `app.js`
 * episode queue / season grouping / play-resume logic. Pure so they're
 * unit-testable without a DOM.
 */
import type { EpisodeShape, PlaybackInfo, PlaybackTrack, PreferredSubtitle } from "../../lib/api/client";
import type { HlsConfig } from "hls.js";

/** Ordered "Up Next" queue entry derived from an episode list. */
export interface QueueEntry {
  id: string;
  name: string;
  position: number;
  /** Episode runtime in seconds (API metadata) — lets the player show a
   *  correct total even before the browser resolves stream duration. */
  runtime?: number;
  /** Series position facts (when the entry is an episode) — the player shows
   *  "S1E4" context and prev/next episode controls from them. */
  season?: number;
  episode?: number;
}

/** Episode poster thumbnail proxy URL (keeps the token server-side). */
export function episodeThumbUrl(episodeId: string, width = 140): string | null {
  return episodeId ? `/api/jellyfin/poster?id=${encodeURIComponent(episodeId)}&width=${width}` : null;
}

/** Playback speeds offered by the speed control (0.5–2×). */
export const PLAYBACK_RATES = [0.5, 1, 1.25, 1.5, 2] as const;

export type PlaybackRate = (typeof PLAYBACK_RATES)[number];

/** Quality options: label -> MaxStreamingBitrate (bps); null = original/unthrottled. */
export interface QualityOption {
  label: string;
  bitrate: number | null;
}
export const QUALITY_OPTIONS: QualityOption[] = [
  { label: "Original", bitrate: null },
  { label: "1080p", bitrate: 8_000_000 },
  { label: "720p", bitrate: 5_000_000 },
  { label: "480p", bitrate: 2_500_000 },
];

/** Resolution for a labelled quality (null for "Original"). */
export function qualityFor(label: string): number | null {
  return QUALITY_OPTIONS.find((q) => q.label === label)?.bitrate ?? null;
}

/** Seconds to hold the autoplay-next countdown before advancing. */
export const AUTOPLAY_DELAY_MS = 8000;

/** Audio codecs major browsers decode natively in a <video> element. */
const BROWSER_SAFE_AUDIO = new Set([
  "aac", "mp3", "opus", "vorbis", "flac",
  "pcm_s16le", "pcm_s24le", "pcm_mulaw", "alac",
]);

/**
 * True when a codec (EAC3/AC3/DTS/TrueHD…) must be transcoded for the browser.
 * Unknown/missing codec -> false (assume direct play is fine; don't over-transcode).
 */
export function audioCodecNeedsTranscode(codec?: string | null): boolean {
  if (!codec) return false;
  return !BROWSER_SAFE_AUDIO.has(codec.toLowerCase());
}

/** Format seconds as m:ss (or h:mm:ss past an hour). Null/NaN/negative → "0:00". */
export function fmtTime(totalSeconds: number | null | undefined): string {
  const s = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const ss = String(sec).padStart(2, "0");
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${ss}`;
  return `${m}:${ss}`;
}

/** True only for a finite positive duration (Infinity/NaN = unknown stream). */
export function isFiniteDuration(d: number | null | undefined): d is number {
  return typeof d === "number" && Number.isFinite(d) && d > 0;
}

/**
 * The player bar's authoritative total (seconds).
 * Prefer the resolved stream duration once finite; until then fall back to the
 * API runtime hint (Jellyfin scan metadata) so the bar + total are correct from
 * the very first frame — even for containers the browser can't index up-front.
 */
export function barTotal(streamDuration: number | null | undefined, runtimeHint?: number | null): number {
  return isFiniteDuration(streamDuration) ? streamDuration : Math.max(0, Math.floor(Number(runtimeHint) || 0));
}

/** Clamp a seek target into [0, total] (total 0 → step forward only). */
export function clampSeek(target: number, total: number): number {
  if (total > 0) return Math.min(Math.max(0, target), total);
  return Math.max(0, target);
}

/**
 * Stream routing — how Jellyfin should serve this item:
 * - "direct": Static file, HTTP-range seekable (browser-safe MP4 family)
 * - "remux": copy/copy into MP4 (MKV etc. the browser can't index up-front)
 * - "transcode_audio": video copied, audio → AAC (EAC3/AC3/DTS/TrueHD)
 * - "transcode": H.264 + AAC (browser-unsafe video codec, or lower bitrate)
 */
export type StreamMode = "direct" | "remux" | "transcode_audio" | "transcode";

/** Video facts from playback-info (drives the transcode decision). */
export interface PlaybackVideoFacts {
  codec?: string | null;
  profile?: string | null;
  bit_depth?: number;
  width?: number;
  height?: number;
  bit_rate?: number;
}

/** Containers the browser indexes up-front (duration + byte-range seeking). */
const DIRECT_CONTAINERS = new Set(["mp4", "m4v", "mov", "webm"]);

/** Video codecs major browsers decode natively (8-bit H.264 + modern codecs). */
const SAFE_VIDEO_CODECS = new Set(["h264", "avc1", "vp9", "av01", "vp8", "theora"]);

/**
 * True when a video stream must be transcoded for the browser: unknown/absent
 * facts -> false (attempt play; the error-ladder escalates on failure).
 */
export function videoNeedsTranscode(video?: PlaybackVideoFacts | null): boolean {
  if (!video) return false;
  const codec = String(video.codec || "").toLowerCase();
  if (codec && !SAFE_VIDEO_CODECS.has(codec)) return true; // hevc/vc1/mpeg2/…
  if (codec === "h264" || codec === "avc1") {
    if ((video.bit_depth || 0) >= 10) return true; // High-10 / 4:2:2 10 undecodable
    const prof = String(video.profile || "").toLowerCase();
    if (prof.includes("10")) return true; // conservative: "high 10" etc.
  }
  return false;
}

/**
 * Pick the cheapest mode that will actually play in the browser.
 * Honest routing (verified live): Jellyfin IGNORES AudioStreamIndex /
 * MaxStreamingBitrate under Static=true, so any track/quality request forces
 * a non-direct mode; MKV-type containers need a remux to resolve duration.
 */
export function pickStreamMode(facts: {
  quality: string;
  container?: string | null;
  video?: PlaybackVideoFacts | null;
  activeAudioCodec?: string | null;
  /** True when a specific audio track was chosen (Static can't honour it). */
  forceNonDirect?: boolean;
}): StreamMode {
  if (facts.quality !== "Original") return "transcode"; // re-encode for bitrate
  if (videoNeedsTranscode(facts.video)) return "transcode";
  if (audioCodecNeedsTranscode(facts.activeAudioCodec)) return "transcode_audio";
  const c = String(facts.container || "").toLowerCase();
  if (facts.forceNonDirect || (c !== "" && !DIRECT_CONTAINERS.has(c))) return "remux";
  return "direct";
}

/** Short label for the player's playback-mode chip. */
export function streamModeLabel(mode: StreamMode): string {
  switch (mode) {
    case "direct": return "Direct play";
    case "remux": return "Remux";
    case "transcode_audio": return "Transcode (audio)";
    default: return "Transcode";
  }
}

/** Jellyfin Sessions PlayMethod reported with progress for a given mode. */
export function playMethodForMode(mode: StreamMode): "DirectPlay" | "DirectStream" | "Transcode" {
  if (mode === "direct") return "DirectPlay";
  if (mode === "remux") return "DirectStream";
  return "Transcode";
}

// ------------------------------------------------------------------ HLS (MSE)
/** Modes that ride the HLS/MSE transport (everything non-direct). */
export type HlsMode = Exclude<StreamMode, "direct">;

/** True when a mode is played via HLS (hls.js / native HLS) rather than the
 *  progressive <video> path. Direct MP4 (range-seekable) stays native. */
export function usesHls(mode: StreamMode): mode is HlsMode {
  return mode !== "direct";
}

/** Order HLS attempts escalate in on fatal errors (audio-aware: EAC3 etc.
 *  titles start at transcode_audio because copy-copy HLS keeps `ec-3`, which
 *  Chrome MSE can't decode — Phase 0 finding). */
export const HLS_LADDER: HlsMode[] = ["remux", "transcode_audio", "transcode"];

/** The next HLS mode to try after *mode* (null = give up). */
export function nextHlsMode(mode: StreamMode): HlsMode | null {
  if (mode === "direct") return HLS_LADDER[0] ?? null;
  const i = HLS_LADDER.indexOf(mode as HlsMode);
  return i >= 0 && i < HLS_LADDER.length - 1 ? HLS_LADDER[i + 1] : null;
}

/** HLS playback engine for the current browser: hls.js (MSE — Chrome/Firefox/
 *  Edge), "native" (Safari/iOS play mpegurl without hls.js), or "none". */
export type HlsEngine = "hlsjs" | "native" | "none";

/** Detect the engine. `canPlayMpegurl` is `video.canPlayType('application/
 *  vnd.apple.mpegurl')` and `isAppleMobile` is an iPhone/iPad UA check —
 *  injectable so the decision is unit-testable.
 *
 *  Native HLS is used ONLY on Apple mobile (Safari/iOS), where it is the
 *  robust, intended path. Desktop Chrome/Firefox/Edge ride hls.js even when a
 *  recent Chromium advertises canPlayType("maybe") — those native TS demuxers
 *  proved unreliable for Jellyfin segments, while hls.js transmuxes TS→fMP4
 *  that MSE decodes cleanly (verified in the headless harness). */
export function hlsEngineFor(
  canPlayMpegurl: () => string,
  hlsSupported = false,
  isAppleMobile = false,
): HlsEngine {
  const ct = (canPlayMpegurl() || "").toLowerCase();
  if (isAppleMobile && ct && ct !== "no") return "native"; // Safari/iOS
  return hlsSupported ? "hlsjs" : "none";
}

/** Label for the mode chip when riding HLS ("Remux"/"Transcode (audio)"/"Transcode"). */
export function hlsModeLabel(mode: StreamMode): string {
  if (mode === "direct") return "Direct play";
  if (mode === "transcode_audio") return "Transcode (audio)";
  if (mode === "transcode") return "Transcode";
  return "Remux (HLS)";
}

// ------------------------------------------------------------------ HLS tuning
/** Seconds of media hls.js keeps buffered ahead of the playhead (LAN-friendly;
 *  the hls.js default of 30 s is on the low side for fast local links). */
export const HLS_MAX_BUFFER_SEC = 60;
/** Hard ceiling the buffer can grow to on very fast links. */
export const HLS_MAX_MAX_BUFFER_SEC = 180;
/** Initial ABR bandwidth estimate (bps). hls.js defaults to ~500 kbps, so the
 *  first seconds of a transcode open blurry and only sharpen once real samples
 *  arrive — on a LAN we seed the estimator high enough to start at a sane level
 *  while still letting the ABR controller adapt downwards if it must. */
export const HLS_ABR_DEFAULT_ESTIMATE_BPS = 5_000_000;
/** ABR up-switch eagerness: switch up when estimate * factor > next level
 *  bitrate (hls.js default 0.7 → waits for a 1.4× cushion). 1.2 climbs the
 *  ladder sooner on a LAN without thrashing. */
export const HLS_ABR_BANDWIDTH_UP_FACTOR = 1.2;
/** ABR down-switch responsiveness (`abrBandWidthFactor`; hls.js default 0.95).
 *  0.85 still drops a level promptly when bandwidth genuinely falls while
 *  smoothing jitter. */
export const HLS_ABR_BANDWIDTH_DOWN_FACTOR = 0.85;

/**
 * hls.js config for one playback build — the buffer + ABR policy lives here in
 * one place. Quality caps ride the master URL (`max_bitrate`); hls.js adapts
 * WITHIN the ladder by measured bandwidth. Never caps to the element size.
 */
export function hlsConfigFor(opts: { startPosition?: number } = {}): Partial<HlsConfig> {
  return {
    ...(opts.startPosition && opts.startPosition > 0 ? { startPosition: opts.startPosition } : {}),
    maxBufferLength: HLS_MAX_BUFFER_SEC,
    maxMaxBufferLength: HLS_MAX_MAX_BUFFER_SEC,
    abrEwmaDefaultEstimate: HLS_ABR_DEFAULT_ESTIMATE_BPS,
    abrBandWidthUpFactor: HLS_ABR_BANDWIDTH_UP_FACTOR,
    abrBandWidthFactor: HLS_ABR_BANDWIDTH_DOWN_FACTOR,
    capLevelToPlayerSize: false,
  };
}

/** Facts about the live ABR level (from hls.js `LEVEL_SWITCHED`). */
export interface AbrLevelFacts {
  height?: number;
  bitrate?: number;
}

/** Coarse resolution label for a live ABR level (informational badge only). */
export function resolutionLabel(height: number | null | undefined): string {
  if (!height || height <= 0) return "Auto";
  if (height >= 2100) return "4K";
  if (height >= 1000) return "1080p";
  if (height >= 700) return "720p";
  if (height >= 400) return "480p";
  return `${Math.round(height)}p`;
}

/** Passive "Auto · 1080p" badge text — shown only while a live level exists. */
export function abrBadgeLabel(level: AbrLevelFacts | null | undefined): string {
  if (!level || !level.height) return "Auto";
  return `Auto · ${resolutionLabel(level.height)}`;
}

/** One parsed subtitle cue (item-time seconds). */
export interface VttCue {
  start: number;
  end: number;
  text: string;
}

const VTT_TIME = /^(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{1,3})$/;

/** Parse a WebVTT/`hh:mm:ss.mmm` (or `mm:ss.mmm`) timestamp to seconds. */
export function parseVttTime(raw: string): number {
  const m = String(raw).trim().match(VTT_TIME);
  if (!m) return 0;
  const h = Number(m[1] || 0);
  const min = Number(m[2]);
  const s = Number(m[3]);
  const frac = Number(m[4].padEnd(3, "0"));
  return h * 3600 + min * 60 + s + frac / 1000;
}

/**
 * Minimal WebVTT parser — enough for Jellyfin's `format=vtt` subtitle stream:
 * timing lines (`start --> end [settings]`) plus multi-line text until a blank
 * line; NOTE/STYLE/REGION blocks and inline tags are skipped/stripped.
 */
export function parseVtt(vtt: string): VttCue[] {
  const cues: VttCue[] = [];
  const lines = String(vtt || "").split(/\r?\n/);
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (line.includes("-->")) {
      const [startTok, rest] = line.split("-->", 2);
      const endTok = String(rest || "").trim().split(/\s+/)[0];
      const text: string[] = [];
      i += 1;
      while (i < lines.length && lines[i].trim() !== "") {
        text.push(lines[i]);
        i += 1;
      }
      const clean = text.join("\n").replace(/<[^>]*>/g, "").trim();
      if (clean) {
        cues.push({ start: parseVttTime(startTok), end: parseVttTime(endTok), text: clean });
      }
    } else {
      i += 1;
    }
  }
  return cues;
}

/** Text of the cue active at `position` seconds (start ≤ pos < end), or null. */
export function activeCueText(cues: VttCue[], position: number): string | null {
  for (const c of cues) {
    if (position >= c.start && position < c.end) return c.text;
  }
  return null;
}

/** Group episodes by season number, seasons ascending. */
export function groupBySeason(episodes: EpisodeShape[]): { season: number; episodes: EpisodeShape[] }[] {
  const map = new Map<number, EpisodeShape[]>();
  for (const e of episodes) {
    const s = e.season ?? 0;
    const list = map.get(s) ?? [];
    list.push(e);
    map.set(s, list);
  }
  return [...map.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([season, list]) => ({ season, episodes: list }));
}

/** Build the ordered queue (id/name/position/runtime/S-E) used for "Up Next"
 *  and prev/next episode navigation. */
export function episodeQueue(episodes: EpisodeShape[]): QueueEntry[] {
  return episodes.map((e) => ({
    id: e.id, name: e.name, position: e.playback_position || 0,
    runtime: e.runtime || 0,
    season: e.season, episode: e.episode,
  }));
}

/** The next episode after *curId*, or ``null`` at the end of the queue (legacy nextEpisode). */
export function nextEpisode(queue: QueueEntry[], curId: string): QueueEntry | null {
  const i = queue.findIndex((x) => x.id === curId);
  return i >= 0 && i + 1 < queue.length ? queue[i + 1] : null;
}

/** The episode before *curId*, or ``null`` at the start of the queue. */
export function prevEpisode(queue: QueueEntry[], curId: string): QueueEntry | null {
  const i = queue.findIndex((x) => x.id === curId);
  return i > 0 ? queue[i - 1] : null;
}

/** "S1E4" code for a queue entry ("" when it isn't an episode). */
export function queueEntryCode(entry: QueueEntry | null | undefined): string {
  if (!entry) return "";
  if (typeof entry.season !== "number" || typeof entry.episode !== "number") return "";
  return `S${entry.season}E${entry.episode}`;
}

/** Legacy play/resume/replay label + start position for an episode row. */
export function playLabel(ep: EpisodeShape): string {
  if (ep.played) return "Replay";
  return ep.playback_position > 0 ? "Resume" : "Play";
}

export function startPosition(ep: EpisodeShape): number {
  return ep.played ? 0 : ep.playback_position || 0;
}

/**
 * The episode a Plex-style series preplay "Play" should start on: the first
 * in-progress (resume) episode, else the first unwatched, else null when the
 * whole series is watched (UI then offers a replay of S1E1).
 */
export function nextPlayableEpisode(episodes: EpisodeShape[]): EpisodeShape | null {
  const sorted = [...episodes].sort(
    (a, b) => (a.season - b.season) || (a.episode - b.episode),
  );
  return (
    sorted.find((e) => !e.played && (e.playback_position || 0) > 0) ??
    sorted.find((e) => !e.played) ??
    null
  );
}

/** "S1E4" code for an episode row/preplay label. */
export function episodeCode(ep: Pick<EpisodeShape, "season" | "episode">): string {
  return `S${ep.season}E${ep.episode}`;
}

// ------------------------------------------------------------------ chrome auto-hide
/** Idle time (ms) before the player chrome auto-hides while playing. */
export const CHROME_HIDE_MS = 2800;

/**
 * True when the cinema chrome should hide: actively playing (not loading, in an
 * error, or showing Up Next), the pointer isn't resting on the chrome, and the
 * user has been idle past CHROME_HIDE_MS. Subtitles never hide — this governs
 * only the top bar, the bottom control bar and the cursor.
 */
export function shouldAutoHideChrome(f: {
  playing: boolean;
  switching: boolean;
  error: boolean;
  upNext: boolean;
  hoverChrome: boolean;
  idleMs: number;
}): boolean {
  if (!f.playing || f.switching || f.error || f.upNext || f.hoverChrome) return false;
  return f.idleMs >= CHROME_HIDE_MS;
}

// ------------------------------------------------------------------ layout policy
/**
 * How the fullscreen button should behave in THIS browser.
 *
 * `element` — the whole player shell goes fullscreen (Chrome/Edge/Firefox/Safari on
 * desktop and iPadOS): the dock, subtitles and top chrome come with it.
 * `video` — iPhone Safari has no `Element.requestFullscreen` at all, so the only
 * fullscreen that exists there is the `<video>`'s own `webkitEnterFullscreen`
 * (the native iOS player takes over, custom chrome included). Without this branch
 * the button is a silent no-op on an iPhone.
 * `none` — no path: the button must not be rendered rather than do nothing.
 */
export type FullscreenPlan = "element" | "video" | "none";

export function fullscreenPlan(facts: {
  /** `document.fullscreenEnabled` — the Element Fullscreen API is available. */
  elementFullscreen: boolean;
  /** The media element exposes `webkitEnterFullscreen` (iOS Safari). */
  videoFullscreen: boolean;
}): FullscreenPlan {
  if (facts.elementFullscreen) return "element";
  if (facts.videoFullscreen) return "video";
  return "none";
}

/** iOS Safari's non-standard video fullscreen surface (type-only, DOM lib can't
 *  know about it). */
export interface WebkitFullscreenVideo extends HTMLVideoElement {
  webkitEnterFullscreen?: () => void;
  webkitExitFullscreen?: () => void;
  webkitDisplayingFullscreen?: boolean;
}

/**
 * Chrome policy for the current viewport. A SHORT viewport (landscape phone, or a
 * short desktop window) has to spend its pixels on picture, so the top chrome
 * collapses to one row: the way out and the title stay, the "S1E2 · 3 of 10"
 * context line goes. Never hide the close button — a player you cannot leave is
 * not a player.
 */
export function playerChromeFor(facts: { vw: number; vh: number }): { compactHeader: boolean } {
  return { compactHeader: facts.vh > 0 && facts.vh <= 480 };
}

// ------------------------------------------------------------------ warm-start
/** One warm-cache slot: the in-flight (or resolved) playback-info fetch for an
 *  item, plus an optional HLS master pre-warm. `at` is the stamp used for TTL +
 *  LRU eviction. */
export interface WarmEntry {
  info: Promise<PlaybackInfo | null>;
  at: number;
}

/** How long a warm entry is trusted before it is refetched. */
export const WARM_TTL_MS = 10 * 60_000;
/** Cap on warm entries (a season queue only needs a handful). */
export const WARM_MAX_ITEMS = 8;
/** Seconds before the end of an item at which the next queue entry warms. */
export const WARM_AHEAD_SEC = 45;

const WARM_STORE = new Map<string, WarmEntry>();

function pruneWarm(now: number): void {
  for (const [id, e] of WARM_STORE) {
    if (now - e.at > WARM_TTL_MS) WARM_STORE.delete(id);
  }
}

/** A live warm entry for *id*, or null (expired entries are dropped on read). */
export function warmGet(id: string, now = Date.now()): WarmEntry | null {
  const e = WARM_STORE.get(id);
  if (!e) return null;
  if (now - e.at > WARM_TTL_MS) {
    WARM_STORE.delete(id);
    return null;
  }
  return e;
}

/** Store/replace a warm entry, evicting the oldest when over the cap. */
export function warmPut(id: string, entry: WarmEntry, now = Date.now()): void {
  pruneWarm(now);
  if (WARM_STORE.size >= WARM_MAX_ITEMS && !WARM_STORE.has(id)) {
    let oldestId: string | null = null;
    let oldestAt = Number.POSITIVE_INFINITY;
    for (const [k, v] of WARM_STORE) {
      if (v.at < oldestAt) {
        oldestAt = v.at;
        oldestId = k;
      }
    }
    if (oldestId) WARM_STORE.delete(oldestId);
  }
  WARM_STORE.set(id, entry);
}

/** Drop a warm entry (after a Player consumes it). */
export function warmDelete(id: string): void {
  WARM_STORE.delete(id);
}

/** Test/teardown helper. */
export function warmClear(): void {
  WARM_STORE.clear();
}

// ------------------------------------------------------------------ preferences
/** Persisted player preferences — global (not per-item): volume/mute, speed and
 *  the quality cap. Resume position and audio/subtitle tracks stay server/per-
 *  item and are deliberately NOT persisted here. */
export interface PlayerPrefs {
  volume: number; // 0..1
  muted: boolean;
  rate: number;
  quality: string; // a QUALITY_OPTIONS label
}

export const PLAYER_PREFS_KEY = "rkm.playerPrefs.v1";

/** Load preferences through an injected getter (localStorage in the browser,
 *  a fake in tests). Corrupt/partial JSON falls back per-field to defaults. */
export function loadPlayerPrefs(get: (key: string) => string | null): PlayerPrefs {
  const dflt: PlayerPrefs = {
    volume: 1,
    muted: false,
    rate: 1,
    quality: QUALITY_OPTIONS[0].label,
  };
  try {
    const raw = get(PLAYER_PREFS_KEY);
    if (!raw) return dflt;
    const p = JSON.parse(raw) as Partial<PlayerPrefs>;
    const rates = PLAYBACK_RATES as readonly number[];
    return {
      volume: typeof p.volume === "number" && p.volume >= 0 && p.volume <= 1 ? p.volume : dflt.volume,
      muted: typeof p.muted === "boolean" ? p.muted : dflt.muted,
      rate: typeof p.rate === "number" && rates.includes(p.rate) ? p.rate : dflt.rate,
      quality: QUALITY_OPTIONS.some((q) => q.label === p.quality) ? String(p.quality) : dflt.quality,
    };
  } catch {
    return dflt;
  }
}

/** Persist preferences through an injected setter; never throws. */
export function savePlayerPrefs(prefs: PlayerPrefs, set: (key: string, value: string) => void): void {
  try {
    set(PLAYER_PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* storage unavailable (private mode etc.) — prefs just don't persist */
  }
}

// ---------------------------------------------------------------- subtitles
/** ISO 639-2/B codes whose first two letters do NOT give the 639-1 code, which is
 *  what the subtitle APIs use (German is `ger`, not `ge`). Everything else maps by
 *  its two-letter prefix (`eng` → `en`, `hin` → `hi`). */
const LANG_639_2_EXCEPTIONS: Record<string, string> = {
  ger: "de", deu: "de", fre: "fr", fra: "fr", dut: "nl", nld: "nl", cze: "cs",
  ces: "cs", gre: "el", ell: "el", rum: "ro", ron: "ro", slo: "sk", slk: "sk",
  chi: "zh", zho: "zh", may: "ms", msa: "ms", per: "fa", fas: "fa", alb: "sq",
  sqi: "sq", arm: "hy", hye: "hy", geo: "ka", kat: "ka", ice: "is", isl: "is",
  mac: "mk", mkd: "mk", mao: "mi", mri: "mi", wel: "cy", cym: "cy", bur: "my",
  mya: "my", tib: "bo", bod: "bo", scc: "sr", srp: "sr", swe: "sv",
};

/** A comparable two-letter language key: `eng`/`EN` → `en`, `pt-BR` → `pt`, `ger` → `de`.
 *  Needed because the store holds the subtitle API's `en` while a track reports
 *  ffprobe's `eng` — a literal comparison would never match, so auto-apply would
 *  silently do nothing. */
export function languageKey(value: string | null | undefined): string {
  let text = String(value ?? "").trim().toLowerCase();
  if (!text) return "";
  if (text.includes("-") || text.includes("_")) text = text.replace(/_/g, "-").split("-")[0];
  if (text.length === 3) return LANG_639_2_EXCEPTIONS[text] ?? text.slice(0, 2);
  if (text.length > 3) return LANG_639_2_EXCEPTIONS[text.slice(0, 3)] ?? text.slice(0, 2);
  return text;
}

/** "Used 24 times" / "Used once" / "" — ours, never the provider's download count. */
export function usedCountLabel(count: number | null | undefined): string {
  const n = Number(count ?? 0);
  if (!Number.isFinite(n) || n < 1) return "";
  return n === 1 ? "Used once" : `Used ${n} times`;
}

/** The one-line label for a subtitle row: language · provider · usage · HI. */
export function subtitleRowLabel(row: {
  language?: string; provider?: string; display_title?: string;
  used_count?: number; hearing_impaired?: boolean; download_count?: number;
}): string {
  const parts = [
    String(row.display_title ?? "").trim() || "Subtitle",
    row.language ? String(row.language).toUpperCase() : "",
    row.provider && row.provider !== "local" ? "OpenSubtitles" : "on disk",
    usedCountLabel(row.used_count),
    // "SDH", not "HI": the language code for Hindi IS "HI", so a bare "HI" marker
    // reads as a language on a Hindi subtitle. SDH is also the term users know.
    row.hearing_impaired ? "SDH" : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

/**
 * Order the picker: local tracks first (unchanged behaviour — they are what the
 * item already has), then OpenSubtitles results by OUR usage count, then by the
 * provider's popularity. Mirrors the server's ranking so the UI cannot disagree
 * with the API about which subtitle is "best".
 */
export function rankSubtitleRows<T extends { local?: boolean; used_count?: number; download_count?: number; subtitle_id?: string }>(
  rows: T[],
): T[] {
  return [...(rows ?? [])].sort((a, b) => {
    const localDiff = Number(Boolean(b.local)) - Number(Boolean(a.local));
    if (localDiff !== 0) return localDiff;
    const usedDiff = Number(b.used_count ?? 0) - Number(a.used_count ?? 0);
    if (usedDiff !== 0) return usedDiff;
    const dlDiff = Number(b.download_count ?? 0) - Number(a.download_count ?? 0);
    if (dlDiff !== 0) return dlDiff;
    return String(a.subtitle_id ?? "").localeCompare(String(b.subtitle_id ?? ""));
  });
}

/**
 * Resolve a STORED subtitle choice to a stream index in the CURRENT track list.
 *
 * Stream indices are positional: adding or removing any track (which our own
 * download does) shifts every index after it, so we store the identity and resolve
 * it here at load time. Exact release-title match wins; otherwise the first track in
 * the same language; otherwise `null` — apply NOTHING and let the picker open.
 * **Never** substitute a different subtitle for the one that was chosen.
 */
export function resolveActiveSubtitle(
  tracks: PlaybackTrack[],
  preferred: PreferredSubtitle | null | undefined,
): number | null {
  if (!preferred || !tracks?.length) return null;
  const want = String(preferred.display_title ?? "").trim().toLowerCase();
  if (want) {
    const exact = tracks.find((t) => String(t.name ?? "").trim().toLowerCase() === want);
    if (exact) return exact.index;
  }
  const lang = languageKey(preferred.language);
  if (lang) {
    const sameLang = tracks.find((t) => languageKey(t.language) === lang);
    if (sameLang) return sameLang.index;
  }
  return null;
}
