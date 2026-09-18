/**
 * Harness: the REAL phone detail SCREEN, over a stubbed api and a real outlet context.
 *
 * `MOBILE_FIRST_UI_PLAN` M4. It answers what a unit test cannot: that the screen MOUNTS with the
 * app's real stylesheet, that its action bar is reachable and ≥44px, that a series renders its
 * episode list with the shared progress rule, that ⋯ opens a SHEET (not a dialog) with only the
 * actions `moreActionsFor` allows, and that no element pokes outside a 320px viewport.
 *
 * ⚠ The outlet context is REAL (`LibraryOutletContext`'s shape), not a stub object: the screen's
 * play/watch handlers are what a tap actually calls, and the frame records those calls so the check
 * can prove a tap reached them.
 *
 * Query params:
 *   ?kind=series  a series with two seasons and a half-watched episode (default: a movie)
 *   ?nolink=1     no `jellyfin_url` — the ⋯ must then exist only if something else does
 *   ?fresh=1      untouched (nothing played, nothing in progress)
 */
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";

import { LayoutModeProvider } from "../src/layouts/LayoutMode";
import { DetailScreen } from "../src/layouts/mobile/DetailScreen";
import { Toaster } from "../src/features/watchlist/Toaster";
import type { LibraryOutletContext } from "../src/features/library/LibraryLayout";
import "../src/styles/index.css";

const PARAMS = new URLSearchParams(location.search);
const SERIES = PARAMS.get("kind") === "series";
const NO_LINK = PARAMS.get("nolink") === "1";
const FRESH = PARAMS.get("fresh") === "1";

const MOVIE_ID = "m-sholay";
const SERIES_ID = "s-shso";
const ID = SERIES ? SERIES_ID : MOVIE_ID;

const calls: { fn: string; args: unknown[] }[] = [];
(window as unknown as { __calls: typeof calls }).__calls = calls;

const movieItem = {
  item_id: MOVIE_ID,
  title: "Sholay",
  type: "movie",
  kind: "movie",
  year: 1975,
  played: FRESH ? false : true,
  playback_position: FRESH ? 0 : 0,
  runtime: 8640,
  genres: ["Action", "Adventure"],
  jellyfin_url: NO_LINK ? "" : "http://rkm-hp:8098/web/index.html#!/item?id=abc",
};

const seriesItem = {
  item_id: SERIES_ID,
  title: "Sholay — Special Ops",
  type: "tv",
  kind: "show",
  year: 2025,
  played: false,
  playback_position: 0,
  runtime: 0,
  genres: ["Drama"],
  jellyfin_url: NO_LINK ? "" : "http://rkm-hp:8098/web/index.html#!/item?id=def",
};

const episodes = [
  { id: "e1", name: "Pilot", season: 1, episode: 1, played: true, playback_position: 3600, runtime: 3600, thumb: null },
  { id: "e2", name: "Two", season: 1, episode: 2, played: false, playback_position: 1200, runtime: 3600, thumb: null },
  { id: "e3", name: "Three", season: 1, episode: 3, played: false, playback_position: 0, runtime: 3500, thumb: null },
  { id: "e4", name: "Another Country", season: 2, episode: 1, played: false, playback_position: 0, runtime: 3400, thumb: null },
];

window.fetch = (async (input: RequestInfo | URL) => {
  const raw = typeof input === "string" ? input : String((input as Request).url ?? input);
  const at = raw.indexOf("/api");
  const path = at >= 0 ? raw.slice(at) : raw;
  const send = (payload: unknown) =>
    new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });

  if (path.startsWith("/api/library/items")) {
    return send({ provider: "jellyfin", available: true, counts: { movies: 1, tvshows: 1 }, items: [movieItem, seriesItem] });
  }
  if (path.startsWith("/api/jellyfin/detail")) {
    const id = new URLSearchParams(path.split("?")[1] ?? "").get("id");
    const item = id === SERIES_ID ? seriesItem : movieItem;
    return send({
      id,
      name: item.title,
      type: SERIES ? "tv" : "movie",
      year: 1975,
      runtime: SERIES ? 0 : 8640,
      official_rating: "PG",
      community_rating: 8.1,
      genres: item.genres,
      studios: ["Sippy Films"],
      overview: "Two friends, their village, and a bandit.",
      has_backdrop: false,
      play: FRESH
        ? { played: false, resume: 0 }
        : // ⚠ Mid-play, NOT finished: this is the case the pinned bar must read "Resume" for, and the
          // only case where `moreActionsFor` offers "Play from beginning".
          { played: false, resume: SERIES ? 0 : 2400 },
      people: {
        actors: [{ id: "p1", name: "Amitabh Bachchan", has_image: false, role: "Jai" }],
        directors: [{ id: "d1", name: "Ramesh Sippy" }],
        writers: [],
      },
    });
  }
  if (path.startsWith("/api/library/series/")) {
    return send({ series_id: SERIES_ID, episodes: SERIES ? episodes : [] });
  }
  return send({});
}) as typeof fetch;

const ctx: LibraryOutletContext = {
  player: null,
  startMovie: (id, title, resume, runtime) => calls.push({ fn: "startMovie", args: [id, title, resume, runtime] }),
  startEpisode: (ep, queue) => calls.push({ fn: "startEpisode", args: [ep.id, queue.length] }),
  switchEntry: () => calls.push({ fn: "switchEntry", args: [] }),
  closePlayer: () => calls.push({ fn: "closePlayer", args: [] }),
  openItem: (item) => calls.push({ fn: "openItem", args: [item.item_id] }),
  quickPlay: (item) => calls.push({ fn: "quickPlay", args: [item.item_id] }),
  toggleWatched: (item) => calls.push({ fn: "toggleWatched", args: [item.item_id, item.played] }),
};

(window as unknown as { __probe: () => unknown }).__probe = () => {
  const px = (el: Element) => {
    const r = el.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top), bottom: Math.round(r.bottom) };
  };
  const primary = document.querySelector('[data-testid="detail-primary"]');
  // ⚠ The watched control's label is STATE-dependent: `Unwatched` while the item
  // is unplayed (the mid-play fixture) and `Watched` once it is played. The old
  // filter listed only `Watched`, so it silently dropped the tile it exists to
  // measure — the stale assertion the 2026-09-18 handoff flagged.
  const TILE_LABELS = ["Watched", "Unwatched", "More", "Download"];
  const tiles = [...document.querySelectorAll("button")].filter((b) =>
    TILE_LABELS.includes((b.textContent || "").trim()),
  );
  const poking = [...document.querySelectorAll("body *")].filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && (r.right > window.innerWidth + 1 || r.left < -1);
  });
  return {
    calls: [...calls],
    body: document.body.textContent ?? "",
    primary: primary ? { text: (primary.textContent || "").trim(), ...px(primary), opacity: getComputedStyle(primary).opacity } : null,
    tiles: tiles.map((t) => ({ text: (t.textContent || "").trim(), ...px(t) })),
    episodeRows: [...document.querySelectorAll("button")].filter((b) => /^(Play|Resume|Replay)( S\d+E\d+)?$/.test((b.textContent || "").trim())).map((b) => (b.textContent || "").trim()),
    headings: [...document.querySelectorAll("h2,h3")].map((h) => (h.textContent || "").trim()),
    sheet: document.querySelector('[role="dialog"]') ? (document.querySelector('[role="dialog"]')!.textContent || "").trim().slice(0, 160) : null,
    overflow: poking.length,
    overflowEls: poking.slice(0, 4).map((el) => `${el.tagName}.${String(el.className).slice(0, 50)}`),
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    viewportH: window.innerHeight,
  };
};

function Ctx() {
  return <Outlet context={ctx} />;
}

function Frame() {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/library/item/${ID}`]}>
        <LayoutModeProvider>
          <div className="min-h-dvh bg-canvas px-4 pt-4 text-zinc-100">
            <Routes>
              <Route element={<Ctx />}>
                <Route path="/library/item/:itemId" element={<DetailScreen />} />
              </Route>
            </Routes>
          </div>
          <Toaster />
        </LayoutModeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
