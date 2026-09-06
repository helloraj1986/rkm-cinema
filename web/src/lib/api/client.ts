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
  type?: string; // "tv" | "movie" | "show"
  thumb?: string | null;
  item_id: string;
  jellyfin_url?: string;
  played?: boolean;
  playback_position?: number; // seconds
  runtime?: number; // seconds
  play_count?: number;
  last_played?: string | null;
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

/** One audio/subtitle track from GET /api/jellyfin/playback-info. */
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

const BASE = "/api";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) {
    throw new ApiError(res.status, `GET ${path} -> ${res.status}`);
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
    throw new ApiError(res.status, `POST ${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
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
};