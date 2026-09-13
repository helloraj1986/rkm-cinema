/**
 * Harness: the REAL card CTA and the REAL global-search result row, over a stubbed api.
 *
 * `tools/check_cta_alignment.py` uses this to pin two UI-polish defects he reported (2026-09-13):
 *
 *   Bug 1  the poster's "▶ Episodes" pill (`MediaCard`) laid the glyph and the label out as a
 *          **stack** — the pill was `grid place-items-center` with TWO children, so grid put the icon
 *          in row 1 and the text in row 2: the play triangle floated above the word.
 *   Bug 2  the search result row's **Resume** (primary) and **Details** (secondary) buttons were
 *          hand-rolled class strings that had drifted apart — the primary had a fixed `h-8` with no
 *          vertical padding, the secondary `py-1.5` with no height — so they rendered at different
 *          heights with different padding, as a pair that is meant to read as one action group.
 *
 * Why a browser, not a unit test: both defects are pure GEOMETRY (what a flex row does, what a
 * hand-tuned pair of class strings adds up to). A class-string assertion would have passed happily
 * while the rendered boxes disagreed — this repo has twice shipped a check that could not fail, so
 * these scenarios measure RECTS in a real engine over the real components.
 *
 * `?scene=card` mounts only the media cards, `?scene=search` only the search widget (the dropdown
 * overlays everything below it, so the check visits them separately). Default: both.
 *
 * The stub answers `/api/search/global` the way the SERVER does — an episode row mid-play (the
 * state machine's "Resume") and a movie row (`Watch Now`) — because the two labels come from the
 * backend's own state, and a stub that invented one would prove nothing about this screen.
 */
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import type { MediaItem } from "../src/lib/api/client";
import { MediaCard } from "../src/features/library/MediaCard";
import { GlobalSearch } from "../src/features/search/GlobalSearch";
import { Toaster } from "../src/features/watchlist/Toaster";
// The app's REAL stylesheet (see nav-frame.tsx / library-frame.tsx): without it a screenshot or a
// geometry measurement of this frame is unstyled and therefore not evidence of anything.
import "../src/styles/index.css";

const params = new URLSearchParams(location.search);
const SCENE = params.get("scene") ?? "both";
const SHOW_CARD = SCENE === "card" || SCENE === "both";
const SHOW_SEARCH = SCENE === "search" || SCENE === "both";

/** The reported card: a SERIES, so the poster CTA is the "▶ Episodes" pill. */
const SERIES: MediaItem = {
  item_id: "i-adolescence",
  title: "Adolescence",
  year: 2025,
  type: "tv",
  played: false,
  playback_position: 0,
  runtime: 0,
  play_count: 0,
};

/** The movie variant of the same CTA — a single centred ▶ in a circle. It must not regress. */
const MOVIE: MediaItem = {
  item_id: "i-matrix",
  title: "The Matrix",
  year: 1999,
  type: "movie",
  played: false,
  playback_position: 640,
  runtime: 8160,
  play_count: 1,
};

/** Two owned rows: the episode row's label comes back "Resume" (kind=episode, mid-play), the
 *  movie's "Watch Now". Facts copied from the schema in `lib/api/types.ts`. */
const OWNED_ROWS = [
  {
    id: "e-sholay-1",
    kind: "episode",
    title: "Sholay",
    year: 1975,
    played: false,
    playback_position: 4200,
    runtime: 12000,
    play_count: 1,
    series_id: "s-sholay",
    series_name: "Sholay",
    season: 1,
    episode: 1,
    state: "resume",
    remaining: 7800,
    next_episode: null,
  },
  {
    id: "m-ddlj",
    kind: "movie",
    title: "Dilwale Dulhania Le Jayenge",
    year: 1995,
    played: false,
    playback_position: 0,
    runtime: 11000,
    play_count: 2,
    state: "watch",
    remaining: null,
    next_episode: null,
  },
];

const calls: { url: string; method: string }[] = [];

window.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const raw = typeof input === "string" ? input : String((input as Request).url ?? input);
  const path = raw.slice(raw.indexOf("/api"));
  calls.push({ url: path, method: String(init.method || "GET").toUpperCase() });
  const send = (payload: unknown) =>
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "content-type": "application/json" },
    });

  if (path.startsWith("/api/search/global")) {
    return send({
      query: new URLSearchParams(path.split("?")[1] ?? "").get("q") ?? "",
      provider: "jellyfin",
      tmdb_key: false,
      strong_match: true,
      items: OWNED_ROWS,
      people: [],
      person_titles: [],
      genres: [],
      collections: [],
      discovery: [],
    });
  }
  if (path === "/api/auth/me" || path === "/api/auth/profiles") {
    return send({ detail: "Sign in to use this app" });
  }
  return send({});
}) as typeof fetch;

(window as unknown as { __probe: () => unknown }).__probe = () => {
  const buttons = [...document.querySelectorAll("button")];
  return {
    scene: SCENE,
    calls: [...calls],
    searchCalls: calls.filter((c) => c.url.startsWith("/api/search/global")),
    rows: document.querySelectorAll('[role="option"]').length,
    hasEpisodesCta: Boolean(document.querySelector('button[aria-label^="Episodes for"]')),
    hasPlayCta: Boolean(document.querySelector('button[aria-label^="Play "]')),
    labelled: buttons.map((b) => ({
      label: (b.getAttribute("aria-label") || b.textContent || "").trim().slice(0, 40),
      testid: b.getAttribute("data-testid") || "",
    })),
    body: document.body.textContent ?? "",
  };
};

function Frame() {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false } } }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <div className="min-h-dvh bg-canvas p-6 text-zinc-100">
          {SHOW_CARD ? (
            <section data-section="cards" className="flex items-start gap-6">
              <MediaCard item={SERIES} onQuickPlay={() => {}} onOpenDetail={() => {}} onToggleWatched={() => {}} />
              <MediaCard item={MOVIE} onQuickPlay={() => {}} onOpenDetail={() => {}} onToggleWatched={() => {}} />
            </section>
          ) : null}

          {SHOW_SEARCH ? (
            <section data-section="search" className="mt-8 w-[720px]">
              {/* The real top-bar widget, mounted as the header mounts it. */}
              <GlobalSearch />
            </section>
          ) : null}

          <Toaster />
        </div>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
