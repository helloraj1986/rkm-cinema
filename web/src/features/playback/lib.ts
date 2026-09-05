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