/**
 * Pure helpers for the global-search command palette (GLOBAL_SEARCH_PLAN
 * Phase 3). Owned rows carry backend-computed state (watch / resume /
 * watch_again / next_episode) — these helpers map each row to its premium
 * copy (action label, meta line) and its play/details navigation target.
 */
import type { GlobalOwnedRow } from "../../lib/api/client";

/** S/E code from season/episode numbers ("" when absent). */
export function codeOf(season?: number | null, episode?: number | null): string {
  if (typeof season !== "number" || typeof episode !== "number") return "";
  return `S${season}E${episode}`;
}

/** "Movie · 2024" / "TV Show · 2024 · 1 season-ish" label is backend-agnostic:
 *  the kind word is all we need next to the title. */
export function kindWord(row: GlobalOwnedRow): string {
  return row.kind === "show" ? "TV Show" : row.kind === "episode" ? "Episode" : "Movie";
}

/** Primary-action label for an owned row (the state machine's copy). */
export function actionLabel(row: GlobalOwnedRow): string {
  if (row.kind === "episode") return row.playback_position > 0 ? "Resume" : "Play";
  if (row.state === "watch_again") return "Watch Again";
  if (row.state === "next_episode" && row.next_episode) {
    return row.next_episode.kind === "continue" ? "Continue Watching" : "Play Next Episode";
  }
  if (row.state === "resume") return "Continue Watching";
  return "Watch Now";
}

/** Contextual meta line under the title (state-aware). */
export function metaLine(row: GlobalOwnedRow): string {
  const code = row.kind === "episode"
    ? codeOf(row.season, row.episode)
    : row.state === "next_episode" && row.next_episode
      ? codeOf(row.next_episode.season, row.next_episode.episode)
      : "";
  const bits: string[] = [];
  if (row.kind === "episode" && row.series_name) bits.push(row.series_name);
  if (code) bits.push(code);
  if (!bits.length) bits.push(kindWord(row));
  if (row.year) bits.push(String(row.year));
  const rem = row.remaining ?? row.next_episode?.remaining ?? null;
  if (rem && rem > 0 && (row.state === "resume" || row.state === "next_episode" || row.kind === "episode")) {
    bits.push(`${Math.max(1, Math.round(rem / 60))} min left`);
  }
  return bits.join(" · ");
}

/** Navigation for an owned row's primary action (play) — "" when n/a. */
export function playTarget(row: GlobalOwnedRow): string {
  const target = row.kind === "episode"
    ? row.series_id
    : row.state === "next_episode" && row.next_episode
      ? row.id
      : row.id;
  if (!target) return "";
  const epId = row.kind === "episode"
    ? row.id
    : row.state === "next_episode" && row.next_episode
      ? row.next_episode.id
      : "";
  const qs = new URLSearchParams();
  qs.set("play", "1");
  if (epId) qs.set("episode", epId);
  return `/library/item/${encodeURIComponent(target)}?${qs.toString()}`;
}

/** Navigation for the secondary "View Details" action. */
export function detailsTarget(row: GlobalOwnedRow): string {
  const target = row.kind === "episode" ? row.series_id : row.id;
  return target ? `/library/item/${encodeURIComponent(target)}` : "";
}

/** Poster/art proxy URL for an owned item id. */
export function artUrl(itemId: string, width = 92): string {
  return `/api/jellyfin/poster?id=${encodeURIComponent(itemId)}&width=${width}`;
}
