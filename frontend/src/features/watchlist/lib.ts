/**
 * Pure helpers for the watchlist feature slice (LEGACY_PARITY_PLAN.md),
 * mirroring legacy `app.js`/`api.js` logic exactly so the React port is at
 * 1:1 parity: identity (`mediaIdOf`), state resolution (`resolveState`),
 * Discover rows (`pickHero`/`buildWatchlistRows`), Watchlist filter/sort,
 * Suggest history/filters, and the add-flow entry mappers. Kept pure so they
 * unit-test without a DOM (vitest node env).
 */
import type {
  MediaResource,
  SearchHit,
  SuggestFilters,
  SuggestResult,
  WatchlistEntry,
  WatchLink,
} from "../../lib/api/client";

// ---------------------------------------------------------------- formatting
/** Legacy fmtRating: numbers → one decimal, strings/unknown pass through. */
export function fmtRating(n: unknown): string {
  return typeof n === "number" ? n.toFixed(1) : String(n ?? "");
}

/** Legacy fmtRuntime(minutes): 136 → "2h 16m", 44 → "44m", 0 → "". */
export function fmtRuntimeMin(min: number | null | undefined): string {
  const m = Number(min) || 0;
  if (m <= 0) return "";
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return h ? `${h}h ${mm}m` : `${m}m`;
}

/** Legacy fmtEta(seconds): <90s → "45s", <90m → "45m", else "2h 5m"/"1d 2h". */
export function fmtEta(sec: number | null | undefined): string {
  if (sec == null || sec < 0 || !Number.isFinite(sec)) return "";
  if (sec < 90) return `${Math.round(sec)}s`;
  const m = Math.round(sec / 60);
  if (m < 90) return `${m}m`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return h >= 24 ? `${Math.floor(h / 24)}d ${h % 24}h` : `${h}h ${mm}m`;
}

/** Legacy timeAgo(iso) for the "Updated …" status line. */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  const d = Math.floor(h / 24);
  return d === 1 ? "yesterday" : `${d} days ago`;
}

// ---------------------------------------------------------------- identity
export interface EntryIdentity {
  type?: string;
  isSeries?: boolean;
  tmdbId?: number | string | null;
  imdbId?: string | null;
  tvdbId?: number | string | null;
}

/**
 * Canonical media_id for an entry, mirroring the backend identity rule
 * (domain/identity.txt): type:tmdb:{id} > type:imdb:{id} > type:tvdb:{id}.
 * This is how a watchlist entry maps onto a §18 resource's `id`.
 */
export function mediaIdOf(e: EntryIdentity): string {
  const t = e.type === "tv" || e.isSeries ? "tv" : "movie";
  if (e.tmdbId) return `${t}:tmdb:${e.tmdbId}`;
  if (e.imdbId) {
    const im = String(e.imdbId);
    return `${t}:imdb:${im.toLowerCase().startsWith("tt") ? im : `tt${im}`}`;
  }
  if (e.tvdbId) return `${t}:tvdb:${e.tvdbId}`;
  return `${t}:imdb:${e.imdbId ?? ""}`;
}

// ---------------------------------------------------------------- state
/** Capabilities + watch facts for one entry (mirrors legacy st() output). */
export interface ResolvedState {
  state: string;
  service: string;
  detail: string;
  progress?: number;
  speed?: number;
  eta?: number;
  qbitState?: string;
  qbitName?: string;
  capabilities: { can_download: boolean; can_watch: boolean };
  watch: Record<string, WatchLink>;
  plexUrl: string;
  embyUrl: string;
  jellyfinUrl: string;
  jellyfinItemId: string;
  acquisition?: MediaResource["acquisition"];
}

const NOT_ADDED: ResolvedState = {
  state: "not_added",
  service: "radarr",
  detail: "",
  capabilities: { can_download: true, can_watch: false },
  watch: {},
  plexUrl: "",
  embyUrl: "",
  jellyfinUrl: "",
  jellyfinItemId: "",
};

/**
 * Legacy `st()` parity: resolve the §18 resource for an entry; when the API is
 * reachable but the resource is missing, default to an actionable `not_added`
 * (never "unavailable") so the user can still request the download.
 */
export function resolveState(
  entry: EntryIdentity & { type?: string },
  resource: MediaResource | null | undefined,
  servicesHealthy: boolean,
): ResolvedState {
  if (resource) {
    const watch = resource.watch ?? {};
    return {
      state: resource.status ?? "not_added",
      service: resource.acquisition?.provider ?? (entry.type === "tv" ? "sonarr" : "radarr"),
      detail: resource.detail ?? "",
      progress: resource.progress ?? undefined,
      speed: resource.speed ?? undefined,
      eta: resource.eta ?? undefined,
      qbitState: resource.qbitState ?? "",
      qbitName: resource.qbitName ?? "",
      capabilities: resource.capabilities ?? { can_download: false, can_watch: false },
      watch,
      plexUrl: (watch.plex as WatchLink | undefined)?.url ?? "",
      embyUrl: (watch.emby as WatchLink | undefined)?.url ?? "",
      jellyfinUrl: (watch.jellyfin as WatchLink | undefined)?.url ?? "",
      jellyfinItemId: (watch.jellyfin as WatchLink | undefined)?.item_id ?? "",
      acquisition: resource.acquisition,
    };
  }
  // No resource: keep an actionable default (legacy st() when SERVICES healthy
  // or empty). `servicesHealthy=false` is not represented differently in
  // legacy — the fall-through is identical not_added.
  const svc = entry.type === "tv" ? "sonarr" : "radarr";
  return { ...NOT_ADDED, service: svc, capabilities: { can_download: true, can_watch: false } };
}

export function canDownload(st: ResolvedState): boolean {
  return st.state === "not_added" && Boolean(st.capabilities.can_download);
}

export function isDownloaded(st: ResolvedState): boolean {
  return Boolean(st.capabilities.can_watch) || st.state === "downloaded" || st.state === "available";
}

export function isBusy(st: ResolvedState): boolean {
  return st.state === "requested" || st.state === "downloading";
}

export const STATE_LABEL: Record<string, string> = {
  not_added: "Not added",
  requested: "Requested",
  downloading: "Downloading",
  downloaded: "Available",
  available: "Available",
  unavailable: "Unavailable",
  unknown: "Unknown",
};

/** Available watch links in display order: Plex, Emby, Jellyfin. */
export function availableWatchLinks(st: ResolvedState): { provider: "plex" | "emby" | "jellyfin"; url: string; itemId: string }[] {
  const out: { provider: "plex" | "emby" | "jellyfin"; url: string; itemId: string }[] = [];
  const plex = (st.watch.plex as WatchLink | undefined);
  const emby = (st.watch.emby as WatchLink | undefined);
  const jf = (st.watch.jellyfin as WatchLink | undefined);
  if (plex?.available && plex.url) out.push({ provider: "plex", url: plex.url, itemId: plex.item_id ?? "" });
  if (emby?.available && emby.url) out.push({ provider: "emby", url: emby.url, itemId: emby.item_id ?? "" });
  if (jf?.available && jf.url) out.push({ provider: "jellyfin", url: jf.url, itemId: jf.item_id ?? "" });
  return out;
}

/** The one main card action (legacy cardMarkup/downloadButton ordering). */
export type CardAction =
  | { type: "play-rkm"; itemId: string; label: "Play in RKM" | "Episodes" }
  | { type: "watch-link"; provider: "plex" | "emby" | "jellyfin"; url: string; label: string }
  | { type: "available" }
  | { type: "requested" }
  | { type: "downloading"; progress: number }
  | { type: "download" }
  | { type: "unavailable" };

export function cardPrimaryAction(entry: Pick<WatchlistEntry, "type">, st: ResolvedState): CardAction {
  const isTv = entry.type === "tv";
  if (st.capabilities.can_watch) {
    const links = availableWatchLinks(st);
    const jf = st.watch.jellyfin as WatchLink | undefined;
    if (jf?.available && jf.item_id) {
      return { type: "play-rkm", itemId: jf.item_id, label: isTv ? "Episodes" : "Play in RKM" };
    }
    const first = links[0];
    if (first) {
      return {
        type: "watch-link",
        provider: first.provider,
        url: first.url,
        label: first.provider === "plex" ? "Watch on Plex" : first.provider === "emby" ? "Watch on Emby" : "Watch on Jellyfin",
      };
    }
    return { type: "available" };
  }
  if (st.state === "downloaded") return { type: "available" };
  if (st.state === "requested") return { type: "requested" };
  if (st.state === "downloading") return { type: "downloading", progress: Math.min(99, st.progress || 0) };
  if (st.capabilities.can_download) return { type: "download" };
  return { type: "unavailable" };
}

/** Watched/resume marker facts from a Jellyfin watch link (if any). */
export function jellyfinMarker(
  jf: WatchLink | null | undefined,
): { kind: "watched" } | { kind: "resume"; percent: number } | { kind: "none" } {
  if (!jf) return { kind: "none" };
  if (jf.played) return { kind: "watched" };
  const pos = Number(jf.playback_position || 0);
  const runtime = Number(jf.runtime || 0);
  if (runtime > 0 && pos > 0) {
    return { kind: "resume", percent: Math.min(100, Math.round((pos / runtime) * 100)) };
  }
  return { kind: "none" };
}

// ---------------------------------------------------------------- discover rows
const LCG_A = 1664525;
const LCG_C = 1013904223;
const LCG_M = 4294967296;

/** Legacy seededShuffle — deterministic Fisher–Yates from a numeric seed. */
export function seededShuffle<T>(arr: readonly T[], seed: number): T[] {
  const a = [...arr];
  let s = seed >>> 0;
  const rnd = () => {
    s = (s * LCG_A + LCG_C) >>> 0;
    return s / LCG_M;
  };
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/** Legacy daySeed — one seed per UTC-ish calendar day (YYYYMMDD). */
export function daySeed(d = new Date()): number {
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
}

export type HeroMode = "auto" | "newest" | "random";

/** Legacy pickHero: auto = highest IMDb; newest = latest added; random (daily). */
export function pickHero(entries: WatchlistEntry[], mode: HeroMode = "auto"): WatchlistEntry | null {
  if (!entries?.length) return null;
  if (mode === "newest") return [...entries].sort((a, b) => String(b.added || "").localeCompare(String(a.added || "")))[0];
  if (mode === "random") return seededShuffle(entries, daySeed())[0];
  return [...entries].sort((a, b) => Number(b.imdb || 0) - Number(a.imdb || 0))[0];
}

export type WatchlistRow = {
  id: string;
  title: string;
  /** Category/director filter payload for "See all" (legacy row.filter). */
  filter?: { type: "all"; category: string };
  items: WatchlistEntry[];
};

/**
 * Legacy buildRows parity: Tonight's Picks (seeded, hero excluded) → New to
 * Your Watchlist → Highly Rated (≥2) → Hidden Gems (≥2) → Critically
 * Acclaimed (≥2) → top 3 categories by count (≥2) → "Because You Like
 * <director>" (2+ titles); max 8 rows.
 */
export function buildWatchlistRows(entries: WatchlistEntry[]): WatchlistRow[] {
  if (!entries?.length) return [];
  const hero = pickHero(entries);
  const heroId = hero?.imdbId;
  const rest = entries.filter((e) => e.imdbId !== heroId);
  const rows: WatchlistRow[] = [];

  rows.push({
    id: "tonight",
    title: "Tonight’s Picks",
    items: seededShuffle(rest.length ? rest : entries, daySeed()),
  });

  rows.push({
    id: "new",
    title: "New to Your Watchlist",
    items: [...entries].sort((a, b) => String(b.added || "").localeCompare(String(a.added || ""))),
  });

  const top = entries.filter((e) => (e.imdb && e.imdb >= 7.8) || (e.rt && e.rt >= 88));
  if (top.length >= 2) rows.push({ id: "top", title: "Highly Rated", items: top });

  const gems = entries.filter((e) => e.rt && e.rt >= 85 && (!e.imdb || e.imdb <= 8.3));
  if (gems.length >= 2) rows.push({ id: "gems", title: "Hidden Gems", items: gems });

  const praised = entries.filter((e) => e.imdb && e.imdb >= 8.0 && e.rt && e.rt >= 88);
  if (praised.length >= 2) rows.push({ id: "acclaim", title: "Critically Acclaimed", items: praised });

  const cats: Record<string, WatchlistEntry[]> = {};
  for (const e of entries) {
    const c = e.category || "Other";
    (cats[c] = cats[c] || []).push(e);
  }
  const sortedCats = Object.entries(cats).sort((a, b) => b[1].length - a[1].length);
  for (const [cat, items] of sortedCats.slice(0, 3)) {
    if (items.length >= 2) {
      rows.push({ id: `cat-${cat}`, title: cat, items, filter: { type: "all", category: cat } });
    }
  }

  const dirs: Record<string, WatchlistEntry[]> = {};
  for (const e of entries) {
    if (e.director) (dirs[e.director] = dirs[e.director] || []).push(e);
  }
  for (const [dir, items] of Object.entries(dirs)) {
    if (items.length >= 2) rows.push({ id: `dir-${dir}`, title: `Because You Like ${dir}`, items });
  }

  return rows.slice(0, 8);
}

// ---------------------------------------------------------------- watchlist grid
export type WatchlistChip = "all" | "movie" | "tv" | "downloaded" | "not";
export type WatchlistSort = "recent" | "rating" | "release" | "title";

export const WATCHLIST_CHIPS: { key: WatchlistChip; label: string }[] = [
  { key: "all", label: "All" },
  { key: "movie", label: "Movies" },
  { key: "tv", label: "TV Shows" },
  { key: "downloaded", label: "Downloaded" },
  { key: "not", label: "Not Downloaded" },
];

export const WATCHLIST_SORTS: { key: WatchlistSort; label: string }[] = [
  { key: "recent", label: "Sort: Recently Added" },
  { key: "rating", label: "Sort: Rating" },
  { key: "release", label: "Sort: Release Date" },
  { key: "title", label: "Sort: Title" },
];

function cmpRecentDesc(a: WatchlistEntry, b: WatchlistEntry): number {
  return String(b.added || "").localeCompare(String(a.added || ""));
}

/**
 * Legacy renderWatchlist parity: chip filter + sort over the rich entries.
 * Downloaded/Not Downloaded use the resolved state (isDownloaded/isBusy).
 */
export function filterWatchlist(
  entries: WatchlistEntry[],
  stateFor: (e: WatchlistEntry) => ResolvedState,
  f: { type?: WatchlistChip; sort?: WatchlistSort } = {},
): WatchlistEntry[] {
  const type = f.type ?? "all";
  const sort = f.sort ?? "recent";
  const list = (entries ?? []).filter((e) => {
    if (type === "movie" && e.type !== "movie") return false;
    if (type === "tv" && e.type !== "tv") return false;
    const st = stateFor(e);
    if (type === "downloaded" && !isDownloaded(st) && !isBusy(st)) return false;
    if (type === "not" && (isDownloaded(st) || isBusy(st))) return false;
    return true;
  });
  if (sort === "rating") return [...list].sort((a, b) => Number(b.imdb || 0) - Number(a.imdb || 0));
  if (sort === "release") return [...list].sort((a, b) => Number(b.year || 0) - Number(a.year || 0));
  if (sort === "title") return [...list].sort((a, b) => a.title.localeCompare(b.title));
  return [...list].sort(cmpRecentDesc);
}

/** Build a media_id → resource map for O(1) lookups. */
export function resourceMap(resources: MediaResource[] | null | undefined): Record<string, MediaResource> {
  const out: Record<string, MediaResource> = {};
  for (const r of resources ?? []) out[r.id] = r;
  return out;
}

// ---------------------------------------------------------------- search / add-flow
/** Find the rich entry backing a search hit (legacy entryById semantics:
 *  imdbId first, then tmdbId). Returns null for live (non-watchlist) hits. */
export function entryForHit(entries: WatchlistEntry[], hit: SearchHit): WatchlistEntry | null {
  if (!entries?.length) return null;
  const byImdb = entries.find((e) => e.imdbId === hit.imdbId);
  if (byImdb) return byImdb;
  const tmdbNum = Number(hit.tmdbId);
  if (!Number.isNaN(tmdbNum) && tmdbNum > 0) return entries.find((e) => Number(e.tmdbId) === tmdbNum) ?? null;
  return null;
}

/** Legacy entryFromSuggestItem: a display stub from a TMDB suggest item so a
 *  freshly-added title renders immediately (poster/genres/score/category). */
export function suggestItemToEntry(item: SuggestResult): WatchlistEntry {
  const tv = item.media_type === "tv";
  return {
    imdbId: "",
    tmdbId: item.tmdb_id,
    tvdbId: null,
    title: item.title,
    year: Number(item.year || 0),
    type: tv ? "tv" : "movie",
    category: (item.genres && item.genres[0]) || "Other",
    genres: item.genres || [],
    lang: "",
    cert: "",
    rt: null,
    imdb: null,
    tmdbScore: item.tmdb_score || null,
    overview: item.overview || "",
    cast: [],
    director: "",
    runtime: null,
    poster: item.poster || "",
    backdrop: item.backdrop || "",
    trailerId: "",
    trailerTitle: "",
    trailerUrl: "",
    added: new Date().toISOString().slice(0, 10),
    source: "user",
  };
}

/**
 * Legacy entryFromWatchlistEntry: map the persisted snake_case entry the
 * backend returns from /api/suggest/add (WatchlistEntry.to_dict) onto the rich
 * display shape so a freshly-added title renders a FULL card (poster, trailer,
 * director, scores) — same normalisation rebuild_dashboard applies.
 */
export function persistedToEntry(w: Record<string, unknown>): WatchlistEntry | null {
  if (!w) return null;
  const isSeries = Boolean(w.isSeries);
  const overview = String(w.overview || w.snippet || w.tmdb_overview || "");
  const tmdbScore = Number(w.tmdbScore || w.tmdb_score || 0);
  return {
    imdbId: String(w.imdbId || ""),
    tmdbId: w.tmdbId ? Number(w.tmdbId) : null,
    tvdbId: w.tvdbId ? Number(w.tvdbId) : null,
    title: String(w.title || ""),
    year: Number(w.year || 0),
    type: isSeries ? "tv" : "movie",
    category: String(w.category || "Other"),
    genres: Array.isArray(w.genres) ? (w.genres as string[]) : [],
    lang: String(w.lang || ""),
    cert: String(w.cert || ""),
    rt: w.rt ? Number(w.rt) : null,
    imdb: w.imdb ? Number(w.imdb) : null,
    tmdbScore: tmdbScore || null,
    overview,
    cast: Array.isArray(w.cast) ? (w.cast as string[]) : [],
    director: String(w.director || ""),
    runtime: w.runtime ? Number(w.runtime) : null,
    poster: String(w.poster || ""),
    backdrop: String(w.backdrop || ""),
    trailerId: String(w.trailerId || ""),
    trailerTitle: String(w.trailerTitle || ""),
    trailerUrl: String(w.trailerUrl || ""),
    added: String(w.added || new Date().toISOString().slice(0, 10)),
    source: String(w.source || "user"),
    state: w.state ? String(w.state) : "pending",
  };
}

// ---------------------------------------------------------------- suggest
export const SUGGEST_GENRES = [
  "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary", "Drama",
  "Family", "Fantasy", "History", "Horror", "Music", "Mystery", "Romance", "Sci-Fi",
  "Thriller", "War", "Western", "Kids", "Reality", "Talk", "War & Politics",
];

export function defaultSuggestFilters(): SuggestFilters {
  return {
    media_type: "all",
    genres: [],
    year_from: null,
    year_to: null,
    min_rating: 6.0,
    sort_by: "popularity.desc",
    count: 20,
  };
}

/** Legacy suggestHistoryPush — dedupe (by JSON) + most-recent-first, max 10. */
export function suggestHistoryPush(list: SuggestFilters[], filters: SuggestFilters): SuggestFilters[] {
  const snap = JSON.stringify(filters);
  return [filters, ...(list || []).filter((h) => JSON.stringify(h) !== snap)].slice(0, 10);
}

/** Legacy suggestHistoryLabel — human chip text for a saved filter set. */
export function suggestHistoryLabel(f: SuggestFilters): string {
  const parts: string[] = [];
  if (f.media_type === "movie") parts.push("Movies");
  else if (f.media_type === "tv") parts.push("TV");
  else parts.push("All");
  if (f.genres?.length) parts.push(f.genres.slice(0, 2).join(", ") + (f.genres.length > 2 ? " +" : ""));
  if (f.year_from || f.year_to) parts.push(`${f.year_from || "…"}–${f.year_to || "…"}`);
  if (f.min_rating) parts.push(`${f.min_rating}★`);
  parts.push(f.count ? `${f.count} results` : "");
  return parts.filter(Boolean).join(" · ");
}

// Re-export the entry type so consumers import it from the feature module.
export type { WatchlistEntry };

