/**
 * Player LAYOUT harness entry — mounts the REAL <Player> with a stubbed API.
 *
 * Not part of the shipped bundle (`vite build` only builds `/index.html`).
 * Run with: `cd frontend && npx vite` then open `/harness/player-layout.html`.
 * See docs/PLAYER_LAYOUT_PLAN.md ("headless layout verification").
 */
import { createRoot } from "react-dom/client";
import "../src/styles/index.css";
import { Player } from "../src/features/playback/Player";
import type { QueueEntry } from "../src/features/playback/lib";

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

createRoot(document.getElementById("root")!).render(
  <Player item={item} resume={120} runtime={3480} queue={queue} onClose={() => {}} />,
);
