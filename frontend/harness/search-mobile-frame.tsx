/**
 * Harness: the REAL phone search SCREEN, over a stubbed `/api/search/global`.
 *
 * `MOBILE_FIRST_UI_PLAN` M3, §8.3 — one frame per screen, a fresh page per scenario. It answers what
 * a unit test cannot: that the screen MOUNTS with the app's real stylesheet, that the field issues ONE
 * request per word rather than one per keystroke, that every action is visible and ≥44px WITHOUT a
 * hover, and that nothing overflows at 320px.
 *
 * ⚠ The stub reports the shape the SERVER reports. `strong_match: true` AND discovery rows together is
 * the case his 2026-09-13 report was about (an exact owned match used to hide the external half), and a
 * stub that "helpfully" sent `strong_match: false` would hide the very bug the sibling search frame
 * exists for.
 *
 * ⚠ `?fail=1` makes `/api/search/global` answer 500 — the degradation path, which must surface as the
 * shared sentence and never as a blank screen or a stack. `?empty=1` answers a real empty result set.
 *
 * Query params:
 *   ?fail=1   the search route fails (500)
 *   ?slow=1   the answer takes 900ms (the loading state)
 *   ?empty=1  no owned rows, no hints, no discovery — the "no matches" case
 */
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { LayoutModeProvider } from "../src/layouts/LayoutMode";
import { SearchScreen } from "../src/layouts/mobile/SearchScreen";
import { Toaster } from "../src/features/watchlist/Toaster";
// The app's REAL stylesheet: `[data-layout="mobile"]` rules are scoped to it, and an unstyled frame
// would measure a screen nobody sees.
import "../src/styles/index.css";

const PARAMS = new URLSearchParams(location.search);
const FAIL = PARAMS.get("fail") === "1";
const SLOW = PARAMS.get("slow") === "1";
const EMPTY = PARAMS.get("empty") === "1";

/** His own library row for "sholay" — the episode his report showed. */
const OWNED = {
  id: "ep-shso",
  kind: "episode",
  title: "Sholay — Special Ops",
  year: 2025,
  genres: ["Drama"],
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

const DISCOVERY = [
  {
    tmdb_id: 12259, media_type: "movie", title: "Sholay", year: 1975,
    poster: "", overview: "Two friends, their village, and a bandit.", in_watchlist: false,
  },
  {
    tmdb_id: 586776, media_type: "movie", title: "The Sholay Girl", year: 2019,
    poster: "", overview: "", in_watchlist: true,
  },
];

const calls: { url: string; method: string }[] = [];

window.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const raw = typeof input === "string" ? input : String((input as Request).url ?? input);
  const at = raw.indexOf("/api");
  const path = at >= 0 ? raw.slice(at) : raw;
  calls.push({ url: path, method: String(init.method || "GET").toUpperCase() });
  const send = (payload: unknown, status = 200) =>
    new Response(JSON.stringify(payload), {
      status,
      headers: { "content-type": "application/json" },
    });

  if (path.startsWith("/api/search/global")) {
    if (FAIL) return send({ detail: "search exploded" }, 500);
    if (SLOW) await new Promise((r) => setTimeout(r, 900));
    const q = new URLSearchParams(path.split("?")[1] ?? "").get("q") ?? "";
    return send({
      query: q,
      provider: "jellyfin",
      tmdb_key: true,
      strong_match: true,
      items: EMPTY ? [] : [OWNED],
      people: EMPTY ? [] : [{ id: "p1", name: "Amitabh Bachchan", kind: "person" }],
      person_titles: [],
      genres: EMPTY ? [] : [{ id: "g1", name: "Action", kind: "genre" }],
      collections: EMPTY ? [] : [{ id: "c1", name: "Sholay Collection", kind: "collection" }],
      discovery: EMPTY ? [] : DISCOVERY,
    });
  }
  if (path.startsWith("/api/suggest/add/")) return send({ ok: true, message: "Added" });
  if (path.startsWith("/api/media/")) return send({ ok: true, state: "requested", message: "Requested" });
  return send({});
}) as typeof fetch;

(window as unknown as { __probe: () => unknown }).__probe = () => {
  const px = (el: Element) => {
    const r = el.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top) };
  };
  const actions = [...document.querySelectorAll('[data-testid$="-action"], [data-testid="owned-action"]')];
  const poking = [...document.querySelectorAll("body *")].filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && (r.right > window.innerWidth + 1 || r.left < -1);
  });
  return {
    calls: [...calls],
    searchCalls: calls.filter((c) => c.url.startsWith("/api/search/global")).length,
    // ⚠ Read the COMPUTED opacity: an action that is visible only under `:hover` is invisible here,
    // and this screen must never depend on a hover (§7.3).
    actions: actions.map((a) => ({ text: (a.textContent || "").trim(), ...px(a), opacity: getComputedStyle(a).opacity })),
    headings: [...document.querySelectorAll("h2")].map((h) => (h.textContent || "").trim()),
    body: document.body.textContent ?? "",
    field: document.querySelector("input") ? px(document.querySelector("input") as Element) : null,
    // Horizontal overflow, measured at the narrowest width the brief names.
    overflow: poking.filter((el) => !el.className?.toString().includes("sr-only")).length,
    overflowEls: poking.slice(0, 5).map((el) => `${el.tagName}.${String(el.className).slice(0, 60)}`),
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    layout: document.documentElement.dataset.layout ?? null,
    recent: [...document.querySelectorAll('[data-testid="recent-chip"]')].map((c) => (c.textContent || "").trim()),
  };
};

function Frame() {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/search"]}>
        <LayoutModeProvider>
          <div className="min-h-dvh bg-canvas px-4 pt-4 text-zinc-100">
            <SearchScreen />
          </div>
          <Toaster />
        </LayoutModeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
