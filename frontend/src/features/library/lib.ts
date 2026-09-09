/**
 * Pure helpers for the library feature slice, mirroring the legacy `app.js`
 * markup logic (playbackMarkup / libraryCard / continueWatchingRowMarkup) so the
 * React port is at 1:1 parity. Kept as pure functions so they're unit-testable
 * without a DOM (vitest node env).
 */
import type {
  DetailPlay,
  MediaItem,
  SimilarItem,
  SuggestResult,
} from "../../lib/api/client";

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

// ---------------------------------------------- Library & discovery (roadmap item 4)
/**
 * Sort options offered by the folder toolbar (NEW_UX §16). Every key maps to
 * a field the frozen /api/library payload truly carries (added/title/year/
 * last_played/position/runtime) — "Rating" is deliberately NOT offered here
 * because list items have no community rating (only the detail fetch does).
 */
export type LibrarySort =
  | "recent"
  | "title"
  | "title-desc"
  | "release"
  | "recently-played"
  | "progress"
  | "runtime"
  | "unwatched";

export const LIBRARY_SORT_OPTIONS: { key: LibrarySort; label: string }[] = [
  { key: "recent", label: "Recently added" },
  { key: "title", label: "Title (A–Z)" },
  { key: "title-desc", label: "Title (Z–A)" },
  { key: "release", label: "Release date" },
  { key: "recently-played", label: "Recently played" },
  { key: "progress", label: "Progress" },
  { key: "runtime", label: "Runtime" },
  { key: "unwatched", label: "Unwatched first" },
];

export const LIBRARY_SORT_KEYS: LibrarySort[] = LIBRARY_SORT_OPTIONS.map((o) => o.key);

/** Folder display mode (§17): poster grid (default) or compact list. */
export type LibraryViewMode = "grid" | "compact";

export const LIBRARY_VIEW_KEYS: LibraryViewMode[] = ["grid", "compact"];

/** Toolbar filter state (all optional; empty = no filtering). */
export interface LibraryFilter {
  q?: string;
  genre?: string;
  sort?: LibrarySort;
}

/**
 * Parse a folder's URLSearchParams into the toolbar state (NEW_UX §63 URL
 * state — /library/movies?q=…&genre=…&sort=… survives refresh/Back and is
 * shareable). Unknown/empty values fall back to the defaults; a sort key that
 * is not in LIBRARY_SORT_KEYS is never trusted (returns "recent").
 */
export function libraryFilterFromParams(
  params: URLSearchParams,
): Required<Omit<LibraryFilter, "q">> & { q: string } {
  // Free-text search was removed from the folders (GLOBAL_SEARCH_PLAN) — the
  // URL q= param is ignored so stale deep links don't silently filter.
  const q = "";
  const genre = (params.get("genre") ?? "").trim();
  const rawSort = (params.get("sort") ?? "").trim();
  const sort = (LIBRARY_SORT_KEYS as string[]).includes(rawSort) ? (rawSort as LibrarySort) : "recent";
  return { q, genre, sort };
}

/** Parse the view-mode param (§17/§60): compact when `view=compact`, else grid. */
export function libraryViewFromParams(params: URLSearchParams): LibraryViewMode {
  const raw = (params.get("view") ?? "").trim();
  return (LIBRARY_VIEW_KEYS as string[]).includes(raw) ? (raw as LibraryViewMode) : "grid";
}

/**
 * Build the query string for the folder toolbar state. Empty values are
 * dropped so a clean view yields no query string (shareable, minimal).
 */
export function libraryFilterToParams(f: LibraryFilter): URLSearchParams {
  const p = new URLSearchParams();
  // Free-text q= is never written (GLOBAL_SEARCH_PLAN — global search owns text).
  if (f.genre && f.genre.trim()) p.set("genre", f.genre.trim());
  if (f.sort && f.sort !== "recent") p.set("sort", f.sort);
  return p;
}

/**
 * Epoch millis for an item's `added` (Jellyfin DateCreated ISO). Jellyfin emits
 * 7-digit fractional seconds ("...0000000Z") which some engines' Date.parse
 * rejects — normalise to milliseconds first. Unknown/malformed -> null (never
 * a fabricated date; callers sort nulls last).
 */
export function addedTime(item: MediaItem): number | null {
  const iso = item?.added;
  if (!iso) return null;
  const norm = String(iso).replace(/\.(\d{3})\d+(Z|[+-]\d{2}:\d{2})$/i, ".$1$2");
  const t = Date.parse(norm);
  return Number.isFinite(t) ? t : null;
}

/** Genre names present in a (kind-split) list, alphabetical, unique. */
export function libraryGenres(items: MediaItem[]): string[] {
  const set = new Set<string>();
  for (const i of items ?? []) for (const g of i.genres ?? []) set.add(g);
  // Plain code-unit sort: deterministic across engines (localeCompare is not
  // for case-distinct names like "Drama" vs "drama").
  return [...set].sort();
}

function cmpRecentDesc(a: MediaItem, b: MediaItem): number {
  const ta = addedTime(a);
  const tb = addedTime(b);
  if (ta !== null && tb !== null) return tb - ta;
  if (ta !== null) return -1; // known dates before unknown
  if (tb !== null) return 1;
  return 0;
}

function cmpTitle(a: MediaItem, b: MediaItem): number {
  return String(a.title ?? "").toLowerCase().localeCompare(String(b.title ?? "").toLowerCase());
}

/** Release year desc (newest first); unknown years last, then recent. */
function cmpReleaseDesc(a: MediaItem, b: MediaItem): number {
  const ya = Number(a.year) || 0;
  const yb = Number(b.year) || 0;
  if (ya !== yb) return yb - ya;
  return cmpRecentDesc(a, b);
}

/** Recently played desc — sorts by UserData LastPlayedDate; never-played last. */
function cmpRecentlyPlayedDesc(a: MediaItem, b: MediaItem): number {
  const pa = a.played && a.last_played ? Date.parse(String(a.last_played)) : NaN;
  const pb = b.played && b.last_played ? Date.parse(String(b.last_played)) : NaN;
  const ha = Number.isFinite(pa);
  const hb = Number.isFinite(pb);
  if (ha !== hb) return ha ? -1 : 1; // played-with-date first
  if (ha && hb) return pb - pa;
  return cmpRecentDesc(a, b);
}

/** In-progress first, by resume fraction desc (highest % watched first). */
function cmpProgressDesc(a: MediaItem, b: MediaItem): number {
  const frac = (i: MediaItem) =>
    i.played || !i.runtime || i.runtime <= 0 ? 0 : (Number(i.playback_position) || 0) / i.runtime;
  const fa = frac(a);
  const fb = frac(b);
  if (fa !== fb) return fb - fa;
  return cmpRecentDesc(a, b);
}

/** Runtime desc (longest first); unknown runtime last, then recent. */
function cmpRuntimeDesc(a: MediaItem, b: MediaItem): number {
  const ra = Number(a.runtime) || 0;
  const rb = Number(b.runtime) || 0;
  if (ra !== rb) return rb - ra;
  return cmpRecentDesc(a, b);
}

function cmpUnwatched(a: MediaItem, b: MediaItem): number {
  if (Boolean(a.played) !== Boolean(b.played)) return a.played ? 1 : -1; // unwatched first
  return cmpRecentDesc(a, b);
}

const SORTERS: Record<LibrarySort, (a: MediaItem, b: MediaItem) => number> = {
  recent: cmpRecentDesc,
  title: cmpTitle,
  "title-desc": (a, b) => cmpTitle(b, a),
  release: cmpReleaseDesc,
  "recently-played": cmpRecentlyPlayedDesc,
  progress: cmpProgressDesc,
  runtime: cmpRuntimeDesc,
  unwatched: cmpUnwatched,
};

/**
 * Search + genre filter + sort over a folder's (kind-split) items. `q` is a
 * case-insensitive title match; `genre` requires membership in the item's
 * genre names; `sort` orders the survivors (default "recent"). Pure — the
 * folder views run this over the shared cache, so filtering needs no fetch.
 */
export function filterLibraryItems(items: MediaItem[], f: LibraryFilter = {}): MediaItem[] {
  const q = String(f.q ?? "").trim().toLowerCase();
  const genre = String(f.genre ?? "").trim();
  const sort = f.sort ?? "recent";
  const out = (items ?? []).filter((i) => {
    if (q && !String(i.title ?? "").toLowerCase().includes(q)) return false;
    if (genre && !(i.genres ?? []).includes(genre)) return false;
    return true;
  });
  const sorter = SORTERS[sort] ?? cmpRecentDesc;
  return [...out].sort(sorter);
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

// ---------------------------------------------- Similar titles (SIMILAR_TITLES_PLAN)
/**
 * Row → SuggestResult adapter so a "Because you watched" card reuses the
 * Suggest detail modal + Add/Download actions (Phase 2 decision: cards are
 * actionable, not decoration). vote_count/genres/overview are unknown for
 * similar rows — the detail modal refetches full metadata via
 * /api/suggest/detail, so the adapter stays light.
 */
export function similarItemToResult(item: SimilarItem): SuggestResult {
  return {
    tmdb_id: item.id,
    title: item.title,
    year: item.year ?? null,
    media_type: item.kind === "show" ? "tv" : "movie",
    tmdb_score: Number(item.score) || 0,
    vote_count: 0,
    genres: [],
    overview: "",
    poster: item.poster ?? "",
    backdrop: item.backdrop ?? "",
    in_watchlist: false,
    in_library: false,
  };
}

function normTitle(title: string | null | undefined): string {
  return String(title ?? "").trim().toLowerCase();
}

/**
 * True when a TMDB similar row already exists in the local library — exact
 * case-insensitive title AND years agree (both known+equal, or both unknown).
 * Conservative by design (SIMILAR_TITLES_PLAN: drop duplicates client-side,
 * never over-drop): a same-name different-year title (remake/reboot) survives.
 */
export function similarRowInLibrary(
  row: Pick<SimilarItem, "title" | "year">,
  items: MediaItem[],
): boolean {
  const t = normTitle(row.title);
  if (!t) return false;
  const ry = row.year ? Number(row.year) : null;
  return (items ?? []).some((i) => {
    if (normTitle(i.title) !== t) return false;
    const ly = i.year ? Number(i.year) : null;
    if (ry === null || ly === null) return ry === null && ly === null;
    return ry === ly;
  });
}

/** Drop similar rows that are already in the local library (client-side dedupe). */
export function filterLibraryRows(
  rows: SimilarItem[],
  items: MediaItem[],
): SimilarItem[] {
  return (rows ?? []).filter((r) => !similarRowInLibrary(r, items));
}

// ---------------------------------- Continue-Watching episodes (CW_EPISODES_PLAN)
/** True for an episode-kind Continue-Watching row (kind or type says episode). */
export function isEpisodeItem(item: MediaItem): boolean {
  return Boolean(item && (item.kind === "episode" || item.type === "episode"));
}

/** "S1E4"-style code for an episode-kind Continue-Watching row, or null. */
export function episodeItemCode(item: MediaItem): string | null {
  const f = isEpisodeItem(item) ? item.episode : null;
  if (!f) return null;
  return `S${f.season}E${f.number}`;
}

/**
 * The series page target for an episode Continue-Watching card: whole-card
 * click opens the SERIES (/library/item/:id on the series id) so context +
 * the episode list are visible (CW_EPISODES_PLAN Phase 2: hover ▶ resumes the
 * episode instantly; card click opens the series). Non-episode items pass
 * through untouched.
 */
export function seriesTargetForEpisode(item: MediaItem): MediaItem | null {
  if (!isEpisodeItem(item) || !item.episode?.series_id) return null;
  const rest: MediaItem = { ...item };
  delete rest.episode; // the series target never carries the episode facet
  return {
    ...rest,
    item_id: item.episode.series_id,
    title: item.episode.series_name || item.title,
    type: "tv",
    kind: "show",
    played: false,
    playback_position: 0,
    runtime: 0,
  };
}

// ---------------------------------------- Home hero & artwork tone (NEW_UX spec)
/**
 * Deterministic 0..5 tone index for an item title — picks one of the seeded
 * gradient palettes used as poster/landscape artwork fallback (never a broken
 * image state; spec §58). Stable across renders for the same title.
 */
export function artTone(title: string | null | undefined): number {
  const t = String(title ?? "");
  let h = 0;
  for (let i = 0; i < t.length; i += 1) h = (h * 31 + t.charCodeAt(i)) >>> 0;
  return h % 6;
}

/** Resume percent for a continue-watching item (0 when nothing to show). */
export function resumePercent(item: MediaItem): number {
  const pos = Number(item.playback_position || 0);
  const rt = Number(item.runtime || 0);
  if (pos <= 0 || rt <= 0) return 0;
  return Math.min(100, Math.round((pos / rt) * 100));
}

/**
 * The Home hero pick (NEW_UX spec §9/§64): prefer a continue-watching MOVIE
 * (clean "Resume" hero), then any in-progress item (episodes included), then
 * the most recently added title, then the first library item. Null when the
 * library is empty — the view renders an empty state instead of a hero.
 */
export function pickHomeHero(
  cw: MediaItem[],
  recent: MediaItem[],
  all: MediaItem[],
): MediaItem | null {
  // Resume candidates only — finished rows never take the hero's spotlight.
  const resume = (cw ?? []).filter(
    (i) => Boolean(i.item_id) && !i.played && Number(i.playback_position || 0) > 0,
  );
  const movie = resume.find((i) => !isSeries(i) && !isEpisodeItem(i));
  if (movie) return movie;
  if (resume[0]) return resume[0];
  const added = (recent ?? []).filter((i) => Boolean(i.item_id));
  if (added[0]) return added[0];
  const anyMovie = (all ?? []).find((i) => !isSeries(i));
  return anyMovie ?? (all ?? [])[0] ?? null;
}