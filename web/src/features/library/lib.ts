/**
 * Pure helpers for the library feature slice, mirroring the legacy `app.js`
 * markup logic (playbackMarkup / libraryCard / continueWatchingRowMarkup) so the
 * React port is at 1:1 parity. Kept as pure functions so they're unit-testable
 * without a DOM (vitest node env).
 */
import type { MediaItem } from "../../lib/api/client";

/** Poster proxy URL for a library item (Jellyfin id first, Plex thumb fallback). */
export function posterUrl(item: Pick<MediaItem, "item_id" | "thumb">): string | null {
  if (item.item_id) {
    return `/api/jellyfin/poster?id=${encodeURIComponent(item.item_id)}&width=500`;
  }
  if (item.thumb) {
    return `/api/plex/thumb?path=${encodeURIComponent(item.thumb)}&width=500`;
  }
  return null;
}

export type Marker = { kind: "watched" } | { kind: "resume"; percent: number } | { kind: "none" };

/** Mirrors legacy playbackMarkup: watched → tick; pos>0 && runtime>0 → amber % bar. */
export function playbackMarker(info: MediaItem): Marker {
  if (!info) return { kind: "none" };
  if (info.played) return { kind: "watched" };
  const pos = info.playback_position || 0;
  const runtime = info.runtime || 0;
  if (runtime > 0 && pos > 0) {
    return { kind: "resume", percent: Math.min(100, Math.round((pos / runtime) * 100)) };
  }
  return { kind: "none" };
}

/** Mirrors legacy continueWatchingRowMarkup filter: has an id AND (in-progress OR watched). */
export function isContinueWatching(item: MediaItem): boolean {
  const pos = Number(item.playback_position || 0);
  return Boolean(item.item_id) && (pos > 0 || Boolean(item.played));
}

/** Is this a show/series (drives Play vs Episodes primary action). */
export function isSeries(item: MediaItem): boolean {
  return item.type === "tv" || item.type === "show" || item.type === "series";
}

/** Row heading used by both Continue Watching and Full Library. */
export function rowHead(title: string, subtitle?: string): string {
  return subtitle ? `${title} · ${subtitle}` : title;
}