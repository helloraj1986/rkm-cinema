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

/** Build the ordered queue (id/name/position) used for "Up Next". */
export function episodeQueue(episodes: EpisodeShape[]): QueueEntry[] {
  return episodes.map((e) => ({ id: e.id, name: e.name, position: e.playback_position || 0 }));
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