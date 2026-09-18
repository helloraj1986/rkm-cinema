/**
 * Pure helpers for the global-search command palette (GLOBAL_SEARCH_PLAN
 * Phase 3). Owned rows carry backend-computed state (watch / resume /
 * watch_again / next_episode) — these helpers map each row to its premium
 * copy (action label, meta line) and its play/details navigation target.
 */
import type {
  GlobalDiscoveryRow,
  GlobalOwnedRow,
  SuggestResult,
  WatchlistEntry,
} from "../../lib/api/client";

/**
 * ⚠ Re-exported for the mobile views. `layouts/importRule.ts` bans `layouts/mobile/` from importing
 * the API client directly — the rule that keeps a second cache key and a second staleness policy
 * from appearing — and a mobile screen still has to be able to NAME the rows it renders. A type
 * carries no behaviour, so re-exporting it beside the hooks that produce it is the honest half of
 * that ban rather than an exception to it.
 */
export type { GlobalDiscoveryRow, GlobalHint, GlobalOwnedRow } from "../../lib/api/client";

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

// ---------------------------------------- The search screen's own rules (M3)
/**
 * ⚠ Everything below moved here from `GlobalSearch.tsx` the moment a SECOND search surface existed.
 * M3 gives the phone its own search screen, and a screen that re-words "No matches for X" or
 * re-derives the debounce is exactly the copy the architecture forbids — two surfaces, two answers to
 * the same question, and a diff that shows neither.
 */

/** How long the field waits after a keystroke before it asks the server. Fast enough to feel live,
 *  slow enough that typing a word is one request — and ONE value, for the palette and the screen. */
export const SEARCH_DEBOUNCE_MS = 200;

/** Placeholder on both fields (it names what can be searched, not where it searches). */
export const SEARCH_PLACEHOLDER = "Search movies, shows, people…";

export const SEARCH_FAILED = "Search failed — try again shortly.";

/** "No matches for “sholay”." — the query is echoed, so a typo is visible. */
export function noMatchesText(query: string): string {
  return `No matches for “${query}”.`;
}

// ---------------------------------------- Matched-span highlighting (M4 · Phase 4)
/**
 * ⚠ SEARCH_IMPROVEMENT_PLAN Phase 4. The SERVER decides which part of a title the
 * query matched (`ranges`, `[start, end)` into the displayed title) and sends the
 * spans with the row; the UI's only job is to emphasise them. A client that
 * re-found the substring itself would be a SECOND implementation of the scorer's
 * decision — and it would disagree the moment the match was fuzzy ("the dark
 * knght" has no substring to find in "The Dark Knight").
 *
 * ⚠ This parses numbers that arrived over the wire and are applied to a title that
 * came with them, so it is defensive by construction: anything that is not a
 * well-formed, in-bounds, non-empty span is dropped rather than trusted. A wrong
 * range does not merely fail to highlight — it bolds the wrong letters of a title.
 */
export interface HighlightPart {
  text: string;
  hit: boolean;
}

export function normaliseRanges(
  text: string,
  ranges?: readonly (readonly number[])[] | null,
): Array<[number, number]> {
  const length = String(text ?? "").length;
  if (!length || !Array.isArray(ranges)) return [];
  const clean: Array<[number, number]> = [];
  for (const raw of ranges) {
    if (!Array.isArray(raw) || raw.length < 2) continue;
    const start = Number(raw[0]);
    const end = Number(raw[1]);
    if (!Number.isInteger(start) || !Number.isInteger(end)) continue;
    const a = Math.max(0, start);
    const b = Math.min(length, end);
    if (b <= a) continue; // empty, reversed, or entirely out of bounds
    clean.push([a, b]);
  }
  // Sorted and merged, so two overlapping spans cannot produce a doubled or
  // reordered title — the segments are concatenated back together in order.
  clean.sort((x, y) => x[0] - y[0]);
  const merged: Array<[number, number]> = [];
  for (const span of clean) {
    const last = merged[merged.length - 1];
    if (last && span[0] <= last[1]) last[1] = Math.max(last[1], span[1]);
    else merged.push([...span] as [number, number]);
  }
  return merged;
}

/** Split a title into alternating plain/emphasised parts. Never loses a character. */
export function highlightParts(
  text: string,
  ranges?: readonly (readonly number[])[] | null,
): HighlightPart[] {
  const value = String(text ?? "");
  const spans = normaliseRanges(value, ranges);
  if (!spans.length) return value ? [{ text: value, hit: false }] : [];
  const out: HighlightPart[] = [];
  let cursor = 0;
  for (const [start, end] of spans) {
    if (start > cursor) out.push({ text: value.slice(cursor, start), hit: false });
    out.push({ text: value.slice(start, end), hit: true });
    cursor = end;
  }
  if (cursor < value.length) out.push({ text: value.slice(cursor), hit: false });
  return out;
}

// ---------------------------------------- Recent searches (M3 · the phone's RECENT row)
/** Where the phone's recent queries live. Versioned: a shape change is a new key, never a migration. */
export const RECENT_KEY = "rkm.recentSearches.v1";

/** How many the row keeps. Six fits two lines of chips on a 390px screen without a horizontal
 *  scroller that nobody discovers. */
export const RECENT_MAX = 6;

/**
 * Read a stored recent list, tolerantly. ⚠ This parses something a previous version of the app wrote,
 * so it must never throw and never trust the shape: anything that is not an array of non-empty
 * strings is dropped rather than rendered as "[object Object]" under a heading that reads RECENT.
 * Case-insensitive dedupe, most recent first, capped.
 */
export function parseRecent(raw: string | null | undefined): string[] {
  if (!raw) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return []; // corrupt storage is a reason to forget, not to crash the screen
  }
  if (!Array.isArray(parsed)) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const entry of parsed) {
    if (typeof entry !== "string") continue;
    const q = entry.trim();
    if (!q) continue;
    const key = q.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(q);
    if (out.length >= RECENT_MAX) break;
  }
  return out;
}

/**
 * The list with `query` at the top. `["a","b"]` + "B" → `["B","a"]` — a repeat moves the entry up and
 * keeps the person's latest SPELLING, which is the one they just typed. An empty query changes
 * nothing (a screen that stores its own blank state is a screen with a history of nothing).
 */
export function pushRecent(list: string[], query: string): string[] {
  const q = String(query ?? "").trim();
  if (!q) return parseRecent(JSON.stringify(list));
  return [q, ...list.filter((entry) => entry.toLowerCase() !== q.toLowerCase())].slice(0, RECENT_MAX);
}

// ---------------------------------------- Discovery rows → the shared action language
/**
 * ⚠ Also lifted out of `GlobalSearch.tsx` for M3. A discovery row has to become a `SuggestResult`
 * (the shape `SuggestDetailModal` and the suggest cards speak) and a `WatchlistEntry` stub (the shape
 * `useCardActions().download` requests the canonical media id from). Two adapters, one copy: the
 * phone's search screen and the palette must agree about what "Add" adds and what "Download" asks for.
 */
export function discoveryToSuggestItem(
  disc: GlobalDiscoveryRow,
  inWatchlist: boolean,
): SuggestResult {
  return {
    tmdb_id: disc.tmdb_id,
    media_type: disc.media_type,
    title: disc.title,
    year: disc.year ?? null,
    tmdb_score: 0,
    vote_count: 0,
    genres: [],
    overview: disc.overview,
    poster: disc.poster,
    backdrop: "",
    in_watchlist: inWatchlist,
    in_library: false,
  };
}

/** A `WatchlistEntry` stub so Download requests the canonical media id. */
export function discoveryEntryStub(disc: GlobalDiscoveryRow): WatchlistEntry {
  return {
    imdbId: "",
    tmdbId: disc.tmdb_id,
    tvdbId: null,
    title: disc.title,
    year: disc.year ?? 0,
    type: disc.media_type === "tv" ? "tv" : "movie",
    category: "Other",
    genres: [],
    lang: "",
    cert: "",
    rt: null,
    imdb: null,
    tmdbScore: null,
    overview: disc.overview,
    cast: [],
    director: "",
    runtime: null,
    poster: disc.poster,
    backdrop: "",
    trailerId: "",
    trailerTitle: "",
    trailerUrl: "",
    added: "",
    source: "search",
  };
}
