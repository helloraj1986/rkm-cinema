/**
 * Typed client for the FROZEN /api contract (docs/api/openapi.v1.json, ADR-0001).
 *
 * `types.ts` is the machine-generated source of truth (`npm run generate:types`,
 * openapi-typescript over the snapshot). This file hand-authors the narrow,
 * stable endpoints the Phase-2 shell needs (config/health) and mirrors the
 * served shapes; the full typed surface expands in Phase 3 per feature slice.
 *
 * Everything hits the same-origin `/api/*` (nginx proxies to FastAPI, which owns
 * the server-side secrets) — the browser never talks to a backend directly.
 */

export interface ServiceMap {
  radarr: boolean;
  sonarr: boolean;
  tmdb: boolean;
  plex: boolean;
  jellyfin: boolean;
  emby: boolean;
}

export interface ConfigShape {
  updated: string;
  heroMode: string;
  rotation: string[];
  services: ServiceMap;
}

export interface ServiceDetail {
  [name: string]: {
    configured: boolean;
    ok: boolean;
    detail?: string;
    error?: string;
  };
}

export interface HealthShape {
  ok: boolean;
  updated: string;
  titleCount: number;
  services: ServiceMap;
  degraded: boolean;
  serviceDetail: ServiceDetail;
}

export interface MediaItem {
  title: string;
  year?: number | null;
  type?: string; // "tv" | "movie" | "show" | "episode"
  thumb?: string | null;
  item_id: string;
  jellyfin_url?: string;
  played?: boolean;
  playback_position?: number; // seconds
  runtime?: number; // seconds
  play_count?: number;
  last_played?: string | null;
  /** Genre names (roadmap item 4 — discovery filters). */
  genres?: string[];
  /** DateCreated ISO string (roadmap item 4 — "recently added" sort). */
  added?: string | null;
  /** Continue-watching facet (CONTINUE_WATCHING_EPISODES_PLAN Option A):
   *  "movie" | "show" | "episode" — present on /library/continue-watching
   *  rows; episode rows carry the episode facet below. */
  kind?: "movie" | "show" | "episode";
  /** Series context for episode-kind Continue-Watching rows. */
  episode?: {
    number: number;
    season: number;
    series_id: string;
    series_name: string;
  };
}

export interface LibraryItemsShape {
  provider: string | null;
  items: MediaItem[];
}

/**
 * GET /api/library — the legacy library read (PLEX_VIEWS_PLAN Home view).
 * `recent` = recently-added titles (limit 8), the same `_item_public` shape
 * as items above. Frozen endpoint; additive client surface only.
 */
export interface LibraryRecentShape {
  provider: string | null;
  available: boolean;
  counts: Record<string, number>;
  recent: MediaItem[];
  server?: string | null;
  urls?: Record<string, string> | null;
}

export interface EpisodeShape {
  id: string;
  name: string;
  season: number;
  episode: number;
  played: boolean;
  playback_position: number;
  runtime: number;
  thumb?: string | null;
}

export interface EpisodesShape {
  provider: string | null;
  episodes: EpisodeShape[];
}

export interface ScanResult {
  ok?: boolean;
  jellyfin?: boolean;
  scanned?: number;
  status?: string;
  [key: string]: unknown;
}

/** Result of POST /api/library/{id}/state (mark watched/unwatched). */
export interface ItemStateResult {
  played: boolean;
  play_count: number;
}

/** One cast/credit person in the detail payload (people group entry). */
export interface DetailPerson {
  id: string;
  name: string;
  /** Character (actors) or credit role. */
  role: string;
  /** Jellyfin reports a headshot (people without one 404 on the proxy). */
  has_image: boolean;
}

export interface DetailPeople {
  actors: DetailPerson[];
  directors: DetailPerson[];
  writers: DetailPerson[];
}

/** Play state in the detail payload (ticks + ergonomic seconds). */
export interface DetailPlay {
  played: boolean;
  resume_ticks: number;
  /** Resume position in seconds (ticks / 1e7). */
  resume: number;
  play_count: number;
}

/** Series context carried by Episode-type detail items. */
export interface DetailSeriesContext {
  id: string;
  name: string;
}

/**
 * GET /api/jellyfin/detail — the Plex-style preplay payload
 * (docs/PLEX_UI_PLAN.md): synopsis/genres/ratings/studios/cast/backdrop facts.
 */
export interface ItemDetail {
  type: "movie" | "tv" | "episode";
  item_id: string;
  name: string;
  year?: number | null;
  /** Runtime in seconds (0 for Series records — episodes carry their own). */
  runtime?: number;
  runtime_ticks?: number;
  overview?: string;
  genres?: string[];
  /** Jellyfin community rating on a 0–10 scale (e.g. 7.473). */
  community_rating?: number | null;
  /** Content rating (e.g. "AU-MA 15+"). */
  official_rating?: string | null;
  studios?: string[];
  people?: DetailPeople;
  has_backdrop?: boolean;
  /** Poster aspect ratio (2:3 posters ≈ 0.667). */
  primary_aspect?: number | null;
  play: DetailPlay;
  /** Present when the detail item is an Episode. */
  series?: DetailSeriesContext;
  season_id?: string;
  season?: number;
  episode?: number;
}

/** One TMDB-similar row from GET /api/jellyfin/similar ("Because you watched").
 *  The id is a TMDB id — the title may NOT be in the library (posters are
 *  public TMDB CDN URLs, so no proxy is needed for row art). */
export interface SimilarItem {
  id: number;
  title: string;
  year?: number | null;
  kind: "movie" | "show";
  /** TMDB vote average (0 when absent — display hides sub-1 scores). */
  score: number;
  poster?: string | null;
  backdrop?: string | null;
}

/** GET /api/jellyfin/similar?id=&limit= response. */
export interface SimilarShape {
  similar: SimilarItem[];
}

/**
 * One audio/subtitle track from GET /api/jellyfin/playback-info. */
export interface PlaybackTrack {
  index: number;
  name: string;
  language: string;
  /** Audio codec (e.g. "aac", "eac3") — drives the audio-transcode decision. */
  codec?: string;
}

/** Video facts from playback-info (drives the direct/remux/transcode routing). */
export interface PlaybackVideo {
  codec?: string;
  profile?: string;
  width?: number;
  height?: number;
  bit_depth?: number;
  bit_rate?: number;
}

/** Tracks + media-source for the player's audio/subtitle pickers. */
export interface PlaybackInfo {
  media_source_id: string;
  /** Original container (e.g. "mkv", "mp4") — remux needed when not mp4-family. */
  container?: string;
  /** First video stream's codec facts (null for audio-only sources). */
  video?: PlaybackVideo | null;
  audio: PlaybackTrack[];
  subtitles: PlaybackTrack[];
}

/**
 * How Jellyfin serves the stream: direct = Static file (range-seekable);
 * remux = copy/copy to MP4; transcode_audio = video copy + AAC;
 * transcode = H.264 + AAC (honours max_bitrate).
 */
export type StreamMode = "direct" | "remux" | "transcode_audio" | "transcode";

/** Optional overrides for the stream URL (item 3 + honest routing). */
export interface StreamOptions {
  audio_stream_index?: number;
  max_bitrate?: number;
  /** Transcode audio to AAC (video copied) — legacy bool alias for mode. */
  transcode_audio?: boolean;
  /** Stream-routing mode (direct default). */
  mode?: StreamMode;
  /** Start the non-direct stream at this offset (restart-seek); ticks = s × 1e7. */
  start_time_ticks?: number;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------- legacy parity
// Rich watchlist-entry surface used by Discover/Watchlist/Search/Suggest.
// `GET /api/watchlist/entries` returns these (live; same mapper as the legacy
// dashboard generator) and `GET /api/watchlist` returns the thin §18 resources
// below — the React port keeps the legacy DATA + RES split (LEGACY_PARITY_PLAN).
// ----------------------------------------------------------------------------

/** One rich watchlist entry (WatchlistEntryResponse shape — camelCase). */
export interface WatchlistEntry {
  imdbId: string;
  tmdbId: number | null;
  tvdbId: number | null;
  title: string;
  year: number;
  type: "movie" | "tv";
  category: string;
  genres: string[];
  lang: string;
  cert: string;
  rt: number | null;
  imdb: number | null;
  tmdbScore: number | null;
  overview: string;
  cast: string[];
  director: string;
  runtime: number | null;
  poster: string;
  backdrop: string;
  trailerId: string;
  trailerTitle: string;
  trailerUrl: string;
  added: string;
  source: string;
  state?: string | null;
  detail?: string | null;
  progress?: number | null;
}

/** GET /api/watchlist/entries — the live rich-entry parity source. */
export interface WatchlistEntriesShape {
  updated: string;
  entries: WatchlistEntry[];
}

/** One provider watch link inside a MediaResource (spec §18 watch.<provider>). */
export interface WatchLink {
  available: boolean;
  url?: string | null;
  error?: string | null;
  /** Provider-native item id for in-app playback via /api/jellyfin/stream. */
  item_id?: string | null;
  played?: boolean | null;
  playback_position?: number | null;
  runtime?: number | null;
}

/** Thin §18 media resource (GET /api/watchlist) — per-title state facts. */
export interface MediaResource {
  id: string;
  title: string;
  year?: number | null;
  type: string;
  status: string;
  capabilities: { can_download: boolean; can_watch: boolean };
  watch: Record<string, WatchLink>;
  acquisition?: { provider?: string | null; status?: string | null } | null;
  detail?: string | null;
  progress?: number | null;
  speed?: number | null;
  eta?: number | null;
  qbitState?: string | null;
  qbitName?: string | null;
}

/** GET /api/watchlist — every entry as a resource. */
export interface WatchlistResourcesShape {
  entries: MediaResource[];
  indexerIssue?: string | null;
}

/** One hit from GET /api/search (watchlist match or live TMDB result). */
export interface SearchHit {
  title: string;
  year?: number | null;
  type: string;
  imdbId: string;
  tmdbId?: number | null;
  poster: string;
  inWatchlist: boolean;
  director: string;
  cast: string[];
  snippet: string;
  voteAverage?: number | null;
}

/** GET /api/search?q= response. */
export interface SearchShape {
  watchlist: SearchHit[];
  tmdb: SearchHit[];
  tmdbKey: boolean;
  servicesDown: boolean;
}

// -------------------------------------------------------------- global search
/** Target for a series "Continue / Play" primary action. */
export interface GlobalNextEpisode {
  id: string;
  season: number;
  episode: number;
  name: string;
  position: number;
  remaining: number;
  kind: "play" | "continue";
}

/** One owned playable result from GET /api/search/global. */
export interface GlobalOwnedRow {
  id: string;
  kind: "movie" | "show" | "episode";
  title: string;
  year?: number | null;
  genres: string[];
  rating?: number | null;
  played: boolean;
  playback_position: number;
  runtime: number;
  play_count: number;
  series_id?: string | null;
  series_name?: string | null;
  season?: number | null;
  episode?: number | null;
  /** Primary action: watch | resume | watch_again | next_episode. */
  state: string;
  remaining?: number | null;
  next_episode?: GlobalNextEpisode | null;
}

/** Intent hint (Person / Genre / BoxSet collection). */
export interface GlobalHint {
  id: string;
  name: string;
  kind: "person" | "genre" | "collection";
  year?: number | null;
}

/** TMDB discovery row — present only when no strong owned match exists. */
export interface GlobalDiscoveryRow {
  tmdb_id: number;
  media_type: "movie" | "tv";
  title: string;
  year?: number | null;
  poster: string;
  overview: string;
}

/** GET /api/search/global?q= response. */
export interface GlobalSearchShape {
  query: string;
  provider: string | null;
  tmdb_key: boolean;
  strong_match: boolean;
  items: GlobalOwnedRow[];
  people: GlobalHint[];
  person_titles: GlobalOwnedRow[];
  genres: GlobalHint[];
  collections: GlobalHint[];
  discovery: GlobalDiscoveryRow[];
}

/** POST /api/suggest filter payload (legacy suggestState.filters). */
export interface SuggestFilters {
  media_type: "all" | "movie" | "tv";
  genres: string[];
  year_from: number | null;
  year_to: number | null;
  min_rating: number;
  sort_by: string;
  count: number;
}

/** One TMDB-discovered title (POST /api/suggest result). */
export interface SuggestResult {
  tmdb_id: number;
  title: string;
  year?: number | null;
  media_type: "movie" | "tv";
  tmdb_score: number;
  vote_count: number;
  genres: string[];
  overview: string;
  poster: string;
  backdrop: string;
  in_watchlist: boolean;
  in_library: boolean;
}

/** POST /api/suggest response. */
export interface SuggestShape {
  results: SuggestResult[];
  total: number;
  filters: Record<string, unknown>;
  genres_available: string[];
}

/** GET /api/suggest/detail/{id} — full TMDB + IMDb detail for the modal. */
export interface SuggestDetail {
  ok: boolean;
  id: number;
  media_type: "movie" | "tv";
  title: string;
  year?: number | null;
  overview: string;
  genres: string[];
  runtime: number;
  cert: string;
  cast: string[];
  director: string;
  tmdb_score: number;
  vote_count: number;
  poster: string;
  backdrop: string;
  imdb_id: string;
  imdb_rating: number;
}

/** POST /api/suggest/add/{id} result — ok/already + the persisted entry
 *  (snake_case WatchlistEntry.to_dict shape — see persistedToEntry). */
export interface SuggestAddResult {
  ok: boolean;
  already?: boolean;
  message: string;
  title?: string;
  entry?: Record<string, unknown> | null;
}

/** POST /api/media/{id}/request result. */
export interface RequestMediaResult {
  ok: boolean;
  state: string;
  message: string;
  mediaId?: string;
  service?: string;
  candidates?: unknown[];
}

/** POST /api/jobs/add_watchlist/run result (manual recommendation refresh). */
export interface AddWatchlistJobResult {
  status?: string;
  error?: string;
  added?: number;
  [key: string]: unknown;
}

const BASE = "/api";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) {
    throw new ApiError(res.status, await errorDetail(res, `GET ${path}`));
  }
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) {
    throw new ApiError(res.status, await errorDetail(res, `POST ${path}`));
  }
  return (await res.json()) as T;
}

/** Best human message from a failed API response: FastAPI's `detail` (string
 *  or {message}) or `message`, else a `METHOD path -> status` fallback. */
async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const d = await res.json();
    if (d && typeof d.detail === "string" && d.detail) return d.detail;
    if (d && typeof d.detail?.message === "string" && d.detail.message) return d.detail.message;
    if (d && typeof d.message === "string" && d.message) return d.message;
  } catch {
    /* body not JSON — use the fallback */
  }
  return `${fallback} -> ${res.status}`;
}

/** Playback-progress payload for /api/jellyfin/progress (mirrors legacy reportProgress). */
export interface ProgressPayload {
  item_id: string;
  position_ticks: number;
  is_paused: boolean;
  event: "start" | "timeupdate" | "stopped";
  /** How the item is being played: DirectPlay | DirectStream | Transcode. */
  play_method?: string;
}

export const api = {
  getConfig: () => getJson<ConfigShape>("/config"),
  getHealth: () => getJson<HealthShape>("/health"),
  getLibraryItems: () => getJson<LibraryItemsShape>("/library/items"),
  /** GET /api/library — legacy read: counts + recently-added (Home view row). */
  getLibraryRecent: () => getJson<LibraryRecentShape>("/library"),
  getContinueWatching: () => getJson<LibraryItemsShape>("/library/continue-watching"),
  getEpisodes: (seriesId: string) => getJson<EpisodesShape>(`/library/series/${encodeURIComponent(seriesId)}/episodes`),
  scanLibrary: () => getJson<ScanResult>("/library/scan"),
  getRecentlyWatched: () => getJson<LibraryItemsShape>("/library/recently-watched"),
  /** Plex-style preplay metadata for one item (fetched on detail open). */
  getItemDetail: (itemId: string) =>
    getJson<ItemDetail>(`/jellyfin/detail?id=${encodeURIComponent(itemId)}`),
  /** "Because you watched" — TMDB similar titles for one library item. */
  getSimilar: (itemId: string, limit = 10) =>
    getJson<SimilarShape>(
      `/jellyfin/similar?id=${encodeURIComponent(itemId)}&limit=${limit}`,
    ),
  mutateItemState: (itemId: string, watched: boolean) =>
    postJson<ItemStateResult>(`/library/${encodeURIComponent(itemId)}/state`, { watched }),
  /** Fire-and-forget playback position report (soft no when backend absent). */
  reportProgress: (payload: ProgressPayload) => postJson<unknown>("/jellyfin/progress", payload),
  /** Same-origin stream URL for an item (token stays server-side). */
  streamUrl: (itemId: string, opts?: StreamOptions) => {
    const q = new URLSearchParams();
    if (opts?.mode && opts.mode !== "direct") q.set("mode", opts.mode);
    if (opts?.transcode_audio) q.set("transcode_audio", "true");
    if (opts?.audio_stream_index) q.set("audio_stream_index", String(opts.audio_stream_index));
    if (opts?.max_bitrate) q.set("max_bitrate", String(opts.max_bitrate));
    if (opts?.start_time_ticks) q.set("start_time_ticks", String(opts.start_time_ticks));
    const qs = q.toString();
    return `${BASE}/jellyfin/stream/${encodeURIComponent(itemId)}${qs ? `?${qs}` : ""}`;
  },
  /** Same-origin HLS master-playlist URL for an item (HLS plan Phases 1–2).
   *  The proxy strips the token and serves rewritten media/segment URIs. */
  hlsMasterUrl: (itemId: string, opts?: {
    mode: Exclude<StreamOptions["mode"], "direct" | undefined>;
    audio_stream_index?: number;
    max_bitrate?: number;
  }) => {
    const q = new URLSearchParams();
    if (opts?.mode) q.set("mode", opts.mode);
    if (opts?.audio_stream_index) q.set("audio_stream_index", String(opts.audio_stream_index));
    if (opts?.max_bitrate) q.set("max_bitrate", String(opts.max_bitrate));
    const qs = q.toString();
    return `${BASE}/jellyfin/hls/${encodeURIComponent(itemId)}/master.m3u8${qs ? `?${qs}` : ""}`;
  },
  /** Audio + text-subtitle track lists for the player pickers. */
  playbackInfo: (itemId: string) => getJson<PlaybackInfo>(`/jellyfin/playback-info?id=${encodeURIComponent(itemId)}`),
  /** Proxy URL for a text subtitle (WebVTT) stream. */
  subtitleUrl: (itemId: string, mediaSourceId: string, index: number) =>
    `${BASE}/jellyfin/subtitle?id=${encodeURIComponent(itemId)}&ms=${encodeURIComponent(mediaSourceId)}&index=${index}`,
  /** Proxy URL for an item's 16:9 backdrop (player keyart). */
  backdropUrl: (itemId: string, width = 1600) =>
    `${BASE}/jellyfin/backdrop?id=${encodeURIComponent(itemId)}&width=${width}`,

  // ------------------------------------------------- legacy-parity surface
  /** Live rich watchlist entries (Discover/Watchlist data — dashboard mapper). */
  getWatchlistEntries: () => getJson<WatchlistEntriesShape>("/watchlist/entries"),
  /** Thin §18 resources per watchlist entry (state/capabilities/watch links). */
  getWatchlistResources: () => getJson<WatchlistResourcesShape>("/watchlist"),
  /** Combined watchlist + TMDB search (legacy header combobox API). */
  search: (q: string) => getJson<SearchShape>(`/search?q=${encodeURIComponent(q)}`),
  /** Library-first global search (top-bar command palette). */
  searchGlobal: (q: string) => getJson<GlobalSearchShape>(`/search/global?q=${encodeURIComponent(q)}`),
  /** TMDB discover by taste filters. */
  suggest: (filters: SuggestFilters) => postJson<SuggestShape>("/suggest", filters),
  /** Full TMDB + IMDb detail for one suggested title (card-click modal). */
  suggestDetail: (tmdbId: number, mediaType: string) =>
    getJson<SuggestDetail>(`/suggest/detail/${tmdbId}?media_type=${encodeURIComponent(mediaType)}`),
  /** Add a TMDB title to the watchlist (pending entry). */
  suggestAdd: (tmdbId: number, mediaType: string) =>
    postJson<SuggestAddResult>(`/suggest/add/${tmdbId}?media_type=${encodeURIComponent(mediaType)}`, {}),
  /** Request a canonical media_id from the right *arr backend (§15/§17). */
  requestMedia: (mediaId: string) =>
    postJson<RequestMediaResult>(`/media/${encodeURIComponent(mediaId)}/request`, {}),
  /** Run the daily recommendation job on demand (refresh button). */
  runAddWatchlistJob: (count = 20) =>
    postJson<AddWatchlistJobResult>("/jobs/add_watchlist/run", { count }),
};