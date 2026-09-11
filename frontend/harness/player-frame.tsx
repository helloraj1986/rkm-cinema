/**
 * Player LAYOUT harness entry — mounts the REAL <Player> with a stubbed API.
 *
 * Not part of the shipped bundle (`vite build` only builds `/index.html`).
 * Run with: `cd frontend && npx vite` then open `/harness/player-layout.html`.
 * See docs/PLAYER_LAYOUT_PLAN.md ("headless layout verification").
 */
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "../src/styles/index.css";
import { Player } from "../src/features/playback/Player";
import type { QueueEntry } from "../src/features/playback/lib";


/**
 * A stubbed API for the DATA-DRIVEN parts of the player.
 *
 * The layout measurement needs the track pickers (and the subtitle rows added in the
 * subtitle plan's Phase 4) to actually RENDER — without this, playback-info fails,
 * `info` stays null, and every panel section is skipped, so the probe would be
 * measuring an empty shell and would pass no matter how badly those rows laid out.
 * Anything that isn't one of our API paths falls through to the real fetch (the
 * sample media must still load).
 */
const HARNESS_PLAYBACK_INFO = {
  media_source_id: "harness-ms",
  container: "mkv",
  video: { codec: "h264", profile: "High", width: 1920, height: 1080, bit_depth: 8, bit_rate: 5_000_000 },
  audio: [
    { index: 1, name: "English AAC 5.1", language: "eng", codec: "aac" },
    { index: 2, name: "Hindi AAC 2.0", language: "hin", codec: "aac" },
  ],
  // The item's OWN track — plus the track our download delivered, which the server
  // names generically (live 2026-09-12: "English - SUBRIP - External", never the
  // release name). This pair is what made the reported bug invisible in the harness:
  // the tick MUST land on the result row below, not on this one.
  subtitles: [
    { index: 3, name: "English - SUBRIP - External", language: "eng", external: true },
    { index: 2, name: "English", language: "eng" },
  ],
  preferred_subtitle: {
    subtitle_id: "os:111", provider: "opensubtitles", language: "en",
    display_title: "Harness.Release.1080p", index: 3, used_count: 4,
  },
};

const HARNESS_SUBTITLE_SEARCH = {
  item_id: "harness-ep-2",
  enabled: true,
  language: "en",
  languages: ["en"],
  local_count: 1,
  remote_count: 3,
  preferred_subtitle: HARNESS_PLAYBACK_INFO.preferred_subtitle,
  disabled: false,
  remaining_downloads: 4,
  warning: "",
  results: [
    { subtitle_id: "", file_id: null, provider: "local", language: "eng",
      display_title: "English", index: 3, used_count: 0, last_used: "",
      download_count: 0, hearing_impaired: false, format: "", vendor_format: "",
      year: null, active: true, local: true },
    { subtitle_id: "os:111", file_id: 111, provider: "opensubtitles", language: "en",
      display_title: "Harness.Release.1080p", index: null, used_count: 4, last_used: "",
      download_count: 451_847, hearing_impaired: false, format: "srt",
      vendor_format: "eng-full", year: 2019, active: true, local: false },
    { subtitle_id: "os:222", file_id: 222, provider: "opensubtitles", language: "en",
      display_title: "Harness.Release.BDRip-ARiGOLD", index: null, used_count: 0,
      last_used: "", download_count: 217_018, hearing_impaired: true, format: "srt",
      vendor_format: "eng-sdh", year: 2019, active: false, local: false },
    { subtitle_id: "os:333", file_id: 333, provider: "opensubtitles", language: "hi",
      display_title: "Harness.Release.Hindi", index: null, used_count: 1, last_used: "",
      download_count: 1_204, hearing_impaired: false, format: "srt",
      vendor_format: "hi", year: 2019, active: false, local: false },
  ],
};

const realFetch = window.fetch.bind(window);
//: Counted so a check can PROVE the picker fetches only when asked — opening the
//: panel must never spend a download (the whole point of the on-demand search).
declare global {
  interface Window { __subtitleSearchCalls?: number }
}
window.__subtitleSearchCalls = 0;
window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
  if (url.includes("subtitle-search")) {
    window.__subtitleSearchCalls = (window.__subtitleSearchCalls ?? 0) + 1;
  }
  const json = url.includes("subtitle-search")
    ? HARNESS_SUBTITLE_SEARCH
    : url.includes("playback-info")
      ? HARNESS_PLAYBACK_INFO
      : null;
  if (json === null) return realFetch(input as RequestInfo, init);
  return new Response(JSON.stringify(json), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}) as typeof window.fetch;

const params = new URLSearchParams(location.search);
const kind = params.get("kind") ?? "series";

const SERIES_QUEUE: QueueEntry[] = [
  { id: "harness-ep-1", name: "S01E01 — Pilot", position: 0, runtime: 3600, season: 1, episode: 1 },
  { id: "harness-ep-2", name: "S01E02 — Second", position: 120, runtime: 3480, season: 1, episode: 2 },
  { id: "harness-ep-3", name: "S01E03 — Third", position: 0, runtime: 3540, season: 1, episode: 3 },
];

const queue = kind === "movie" ? [] : SERIES_QUEUE;
const item =
  kind === "movie"
    ? { item_id: "harness-movie", title: "Harness Movie — Very Long Title To Force Truncation Behaviour" }
    : { item_id: "harness-ep-2", title: "S01E02 — Second (harness episode title)" };

// The Player invalidates the library queries when it closes, so the harness must
// provide a client — without one `useQueryClient()` throws and the layout
// measurement tool renders nothing. A bare client is enough (nothing is fetched).
const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={queryClient}>
    <Player item={item} resume={120} runtime={3480} queue={queue} onClose={() => {}} />
  </QueryClientProvider>,
);
