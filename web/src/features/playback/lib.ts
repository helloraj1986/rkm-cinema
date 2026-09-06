/**
 * Pure helpers for the playback slice (Phase 3b), mirroring the legacy `app.js`
 * episode queue / season grouping / play-resume logic. Pure so they're
 * unit-testable without a DOM.
 */
import type { EpisodeShape } from "../../lib/api/client";

/** Ordered "Up Next" queue entry derived from an episode list. */
export interface QueueEntry {
  id: string;
  name: string;
  position: number;
  /** Episode runtime in seconds (API metadata) — lets the player show a
   *  correct total even before the browser resolves stream duration. */
  runtime?: number;
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

/** Build the ordered queue (id/name/position/runtime) used for "Up Next". */
export function episodeQueue(episodes: EpisodeShape[]): QueueEntry[] {
  return episodes.map((e) => ({
    id: e.id, name: e.name, position: e.playback_position || 0,
    runtime: e.runtime || 0,
  }));
}

/** The next episode after *curId*, or ``null`` at the end of the queue (legacy nextEpisode). */
export function nextEpisode(queue: QueueEntry[], curId: string): QueueEntry | null {
  const i = queue.findIndex((x) => x.id === curId);
  return i >= 0 && i + 1 < queue.length ? queue[i + 1] : null;
}

/** Legacy play/resume/replay label + start position for an episode row. */
export function playLabel(ep: EpisodeShape): string {
  if (ep.played) return "Replay";
  return ep.playback_position > 0 ? "Resume" : "Play";
}

export function startPosition(ep: EpisodeShape): number {
  return ep.played ? 0 : ep.playback_position || 0;
}