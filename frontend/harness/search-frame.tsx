/**
 * Harness: the REAL global-search overlay, over a stubbed `/api/search/global`.
 *
 * `tools/check_search_fallback.py` uses this to pin his third report (2026-09-13): searching
 * **"sholay"** returned one unrelated library row and **no external section at all**.
 *
 * ⚠ Two independent gates hid the external rows, and this frame exists because the SECOND one is a
 * pure UI rule that no backend test can reach: `GlobalSearch` used to render the section only when
 * `!data.strong_match`, duplicating the server's own decision. With the backend relaxed, that copy
 * would still have hidden everything — which is why `?strong=1` below sends `strong_match: true`
 * AND discovery rows: the server says "an exact owned title exists" while still offering the external
 * half, and the UI must render what it is given.
 *
 * Query params:
 *   ?strong=1  (default) the server's answer for a containment match: the owned row PLUS external
 *              rows, with `strong_match` true (an exact match of a DIFFERENT owned title).
 *   ?tmdbkey=0 the capability is off: no key ⇒ the server sends no discovery rows at all, and the
 *              footer must say why instead of showing an empty section.
 */
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { GlobalSearch } from "../src/features/search/GlobalSearch";
import { Toaster } from "../src/features/watchlist/Toaster";
// The app's REAL stylesheet (see nav-frame.tsx): this check reads RENDERED content, and an unstyled
// frame would not show what he sees.
import "../src/styles/index.css";

const params = new URLSearchParams(location.search);
const TMDB_KEY = params.get("tmdbkey") !== "0";

/** The library's single, unrelated match for "sholay" — the row his report shows. */
const OWNED = {
  id: "ep-shso",
  kind: "episode",
  title: "Sholay — Special Ops",
  year: 2025,
  played: false,
  playback_position: 120,
  runtime: 3600,
  play_count: 1,
  series_id: "s-shso",
  series_name: "Sholay — Special Ops",
  season: 1,
  episode: 8,
  state: "resume",
  remaining: 3480,
  next_episode: null,
};

/** The real film, as TMDB ranks it (probe: result #0 of 13 for this query). */
const DISCOVERY = [
  { tmdb_id: 12259, media_type: "movie", title: "Sholay", year: 1975,
    poster: "", overview: "Two friends, their village, and a bandit.", in_watchlist: false },
  { tmdb_id: 586776, media_type: "movie", title: "The Sholay Girl", year: 2019,
    poster: "", overview: "", in_watchlist: true },
];

const calls: { url: string; method: string }[] = [];

window.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const raw = typeof input === "string" ? input : String((input as Request).url ?? input);
  const path = raw.slice(raw.indexOf("/api"));
  calls.push({ url: path, method: String(init.method || "GET").toUpperCase() });
  const send = (payload: unknown) =>
    new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });

  if (path.startsWith("/api/search/global")) {
    return send({
      query: new URLSearchParams(path.split("?")[1] ?? "").get("q") ?? "",
      provider: "jellyfin",
      tmdb_key: TMDB_KEY,
      // ⚠ true: an exact owned title matched — and the external rows are sent ANYWAY.
      strong_match: true,
      items: [OWNED],
      people: [],
      person_titles: [],
      genres: [],
      collections: [],
      discovery: TMDB_KEY ? DISCOVERY : [],
    });
  }
  if (path.startsWith("/api/suggest/detail/")) {
    return send({
      ok: true, id: 12259, media_type: "movie", title: "Sholay", year: 1975,
      overview: "Two friends, their village, and a bandit.", genres: ["Action", "Drama"],
      runtime: 204, cert: "PG", cast: ["Dharmendra", "Amitabh Bachchan"], director: "Ramesh Sippy",
      tmdb_score: 7.4, vote_count: 1200, poster: "", backdrop: "", imdb_id: "tt0073707",
      imdb_rating: 8.1,
    });
  }
  if (path === "/api/auth/me" || path === "/api/auth/profiles") {
    return send({ detail: "Sign in to use this app" });
  }
  return send({});
}) as typeof fetch;

(window as unknown as { __probe: () => unknown }).__probe = () => {
  const rows = [...document.querySelectorAll('[role="option"]')];
  const rowText = (r: Element) => (r.textContent || "").trim();
  const groupLabels = [...document.querySelectorAll("#global-search-results div")].map((d) => (d.textContent || "").trim()).filter((t) => t === "In your library" || t.startsWith("Discover"));
  return {
    calls: [...calls],
    searchCalls: calls.filter((c) => c.url.startsWith("/api/search/global")),
    detailCalls: calls.filter((c) => c.url.startsWith("/api/suggest/detail/")),
    rowCount: rows.length,
    rows: rows.map((r) => ({
      text: rowText(r),
      hasOwnedActions: [...r.querySelectorAll("button")].some((b) => /Resume|Watch|Continue|Play/i.test(b.textContent || "")),
      actionLabels: [...r.querySelectorAll("button")].map((b) => (b.textContent || "").trim()),
    })),
    groupLabels,
    body: document.body.textContent ?? "",
    dialog: document.querySelector('[role="dialog"]')
      ? { text: (document.querySelector('[role="dialog"]')!.textContent || "").trim().slice(0, 200) }
      : null,
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
          <section data-section="search" className="w-[720px]">
            <GlobalSearch />
          </section>
          <Toaster />
        </div>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
