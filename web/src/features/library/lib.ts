/**
 * Pure helpers for the library feature slice, mirroring the legacy `app.js`
 * markup logic (playbackMarkup / libraryCard / continueWatchingRowMarkup) so the
 * React port is at 1:1 parity. Kept as pure functions so they're unit-testable
 * without a DOM (vitest node env).
 */
import type { DetailPlay, MediaItem } from "../../lib/api/client";

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

// ---------------------------------------------- Plex-style views (PLEX_VIEWS_PLAN)
/** Sidebar/library folder kinds — movies (Plex "Movies") and series ("TV Shows"). */
export type LibraryKind = "movies" | "shows";

/**
 * Split the cached library items into one Plex-style folder. Pure + shared by
 * the /library/movies and /library/shows folder views (client-side split of the
 * already-fetched `/api/library/items` response — zero backend/contract work).
 */
export function libraryItemsByType(items: MediaItem[], kind: LibraryKind): MediaItem[] {
  const wantSeries = kind === "shows";
  return (items ?? []).filter((i) => (wantSeries ? isSeries(i) : !isSeries(i)));
}

/** Folder heading label ("Movies" / "TV Shows") for the routed folder views. */
export function libraryKindLabel(kind: LibraryKind): string {
  return kind === "movies" ? "Movies" : "TV Shows";
}

// ---------------------------------------------- Plex-style detail (Phase 2)
/** Person-headshot proxy URL (token stays server-side). */
export function personHeadshotUrl(personId: string, width = 200): string | null {
  return personId ? `/api/jellyfin/person?id=${encodeURIComponent(personId)}&width=${width}` : null;
}

/** Plex-style runtime label: "2h 33m" / "44m" / "" (0 or unknown). */
export function fmtRuntime(totalSeconds: number | null | undefined): string {
  const s = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  if (s <= 0) return "";
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  if (h > 0) {
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
  }
  return `${Math.max(1, m)}m`;
}

/** One-decimal community rating for the ★ readout (7.473 → "7.5"). */
export function ratingText(rating: number | null | undefined): string {
  const n = Number(rating);
  if (!Number.isFinite(n) || n <= 0) return "";
  return n.toFixed(1).replace(/\.0$/, "");
}

/** Resume % for the detail overlay's bar (0 when nothing to resume). */
export function detailResumePercent(play: DetailPlay | undefined, runtimeSec: number | null | undefined): number {
  const pos = Number(play?.resume || 0);
  const rt = Number(runtimeSec || 0);
  if (play?.played || pos <= 0 || rt <= 0) return 0;
  return Math.min(100, Math.round((pos / rt) * 100));
}

/** True when the title is mid-play (resume applies) and not finished. */
export function detailInProgress(play: DetailPlay | undefined): boolean {
  return Boolean(!play?.played && Number(play?.resume || 0) > 0);
}

/** Primary preplay button label: "Resume" mid-play, else "Play". */
export function detailPrimaryLabel(play: DetailPlay | undefined): string {
  return detailInProgress(play) ? "Resume" : "Play";
}