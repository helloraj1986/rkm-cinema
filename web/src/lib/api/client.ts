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

/** One audio/subtitle track from GET /api/jellyfin/playback-info. */
export interface PlaybackTrack {
  index: number;
  name: string;
  language: string;
}

/** Tracks + media-source for the player's audio/subtitle pickers. */
export interface PlaybackInfo {
  media_source_id: string;
  audio: PlaybackTrack[];
  subtitles: PlaybackTrack[];
}

/** Optional overrides for the direct-play stream URL (item 3). */
export interface StreamOptions {
  audio_stream_index?: number;
  max_bitrate?: number;
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
}

export const api = {
  getConfig: () => getJson<ConfigShape>("/config"),
  getHealth: () => getJson<HealthShape>("/health"),
  getLibraryItems: () => getJson<LibraryItemsShape>("/library/items"),
  getContinueWatching: () => getJson<LibraryItemsShape>("/library/continue-watching"),
  getEpisodes: (seriesId: string) => getJson<EpisodesShape>(`/library/series/${encodeURIComponent(seriesId)}/episodes`),
  scanLibrary: () => getJson<ScanResult>("/library/scan"),
  getRecentlyWatched: () => getJson<LibraryItemsShape>("/library/recently-watched"),
  mutateItemState: (itemId: string, watched: boolean) =>
    postJson<ItemStateResult>(`/library/${encodeURIComponent(itemId)}/state`, { watched }),
  /** Fire-and-forget playback position report (soft no when backend absent). */
  reportProgress: (payload: ProgressPayload) => postJson<unknown>("/jellyfin/progress", payload),
  /** Same-origin direct-play stream URL for an item (token stays server-side). */
  streamUrl: (itemId: string, opts?: StreamOptions) => {
    const q = new URLSearchParams();
    if (opts?.audio_stream_index) q.set("audio_stream_index", String(opts.audio_stream_index));
    if (opts?.max_bitrate) q.set("max_bitrate", String(opts.max_bitrate));
    const qs = q.toString();
    return `${BASE}/jellyfin/stream/${encodeURIComponent(itemId)}${qs ? `?${qs}` : ""}`;
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