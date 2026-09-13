/**
 * Harness: the REAL app shell + library routes, so a report about "the detail overlay from a search
 * result" can be REPRODUCED and MEASURED instead of guessed at.
 *
 * Why this exists (his Bug 5, 2026-09-13): he describes a detail panel that opens from a click in the
 * search dropdown and has *no scrim, hard edges, ~60% width, the title flush against the top, and no
 * close button*. Every symptom points at a MODAL that lost its chrome — but this codebase has exactly
 * two detail presentations, and neither is a broken modal:
 *
 *   * the WATCHLIST card → `WatchlistDetail`, a real `<Dialog>` (scrim, centred, Esc, backdrop click);
 *   * a LIBRARY card or a search result → NAVIGATION to `/library/item/:itemId`, the item's own PAGE
 *     (PLEX_VIEWS_PLAN Phase 1): a URL, a hero with a Back button, and no scrim at all — because a page
 *     is not a modal.
 *
 * Which is why this frame mounts the REAL router shape (`AppShell` + `LibraryLayout` + the real views)
 * over a stubbed api: the question "is this a modal that broke, or a page that looks wrong?" is decided
 * by measuring the rendered result, not by reading JSX.
 *
 * `?route=` picks the entry point (default `/library/home`, so the search bar can be driven exactly as
 * he drove it: type "sholay", then click the result).
 */
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, Navigate, RouterProvider } from "react-router-dom";

import { AuthProvider } from "../src/features/auth/AuthProvider";
import { AppShell } from "../src/app/layout/AppShell";
import { ItemDetailPage } from "../src/features/library/ItemDetailPage";
import { LibraryFolderView } from "../src/features/library/LibraryFolderView";
import { LibraryHomeView } from "../src/features/library/LibraryHomeView";
import { LibraryLayout } from "../src/features/library/LibraryLayout";
// The app's REAL stylesheet — a geometry/visibility claim about an unstyled frame is worthless.
import "../src/styles/index.css";

const params = new URLSearchParams(location.search);
const ROUTE = params.get("route") ?? "/library/home";
//: `?detail=tv` serves the SERIES shape — his row is an EPISODE of "Sholay — Special Ops", so
//: "Details" opens the SERIES page (/library/item/s-shso), which is the surface his report is about.
const DETAIL_KIND = params.get("detail") === "tv" ? "tv" : "movie";

const PROFILE = {
  id: "uid-admin", name: "rkm", is_admin: true, has_password: true, disabled: false, last_login: "",
};

/** His library's own row for "sholay" — the episode that contains the string. */
const EPISODE_ROW = {
  id: "ep-shso-8", kind: "episode", title: "Sholay — Special Ops", year: 2025, played: false,
  playback_position: 120, runtime: 3600, play_count: 1, series_id: "s-shso",
  series_name: "Sholay — Special Ops", season: 1, episode: 8,
};

const MOVIE = {
  item_id: "m-sholay", title: "Sholay", year: 1975, media_type: "movie", played: false,
  playback_position: 0, runtime: 12240,
};

const ITEM_DETAIL = {
  type: DETAIL_KIND, item_id: "m-sholay",
  name: DETAIL_KIND === "tv" ? "Sholay — Special Ops" : "Sholay",
  year: DETAIL_KIND === "tv" ? 2025 : 1975,
  runtime: DETAIL_KIND === "tv" ? 0 : 12240,
  overview: "Two friends, their village, and a bandit — the film that made the Hindi blockbuster.",
  genres: ["Action", "Drama"], community_rating: 8.1, official_rating: "PG",
  studios: ["Sippy Films"], has_backdrop: false, primary_aspect: 0.667,
  people: {
    actors: [{ id: "p1", name: "Dharmendra", role: "Veeru", has_image: false },
             { id: "p2", name: "Amitabh Bachchan", role: "Jai", has_image: false }],
    directors: [{ id: "p3", name: "Ramesh Sippy", role: "Director", has_image: false }],
    writers: [],
  },
  play: { played: false, resume_ticks: 0, resume: 0, play_count: 0 },
};

const calls: { url: string; method: string }[] = [];

window.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const raw = typeof input === "string" ? input : String((input as Request).url ?? input);
  const path = raw.slice(raw.indexOf("/api"));
  calls.push({ url: path, method: String(init.method || "GET").toUpperCase() });
  const send = (payload: unknown) =>
    new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });

  if (path === "/api/auth/me") {
    return send({ user: { id: "uid-admin", name: "rkm" }, profile: { id: PROFILE.id, name: PROFILE.name },
                  profile_selected: true, on_own_profile: true, expires: "2026-10-12T00:00:00Z" });
  }
  if (path === "/api/auth/profiles") {
    return send({ profiles: [PROFILE], current: PROFILE, profile_selected: true, warning: "" });
  }
  if (path.startsWith("/api/search/global")) {
    return send({
      query: "sholay", provider: "jellyfin", tmdb_key: true, strong_match: true,
      items: [EPISODE_ROW], people: [], person_titles: [], genres: [], collections: [], discovery: [],
    });
  }
  if (path.startsWith("/api/jellyfin/detail")) {
    return send(ITEM_DETAIL);
  }
  if (path.startsWith("/api/jellyfin/similar")) {
    return send({ similar: [] });
  }
  if (path.match(/^\/api\/library\/series\/.+\/episodes$/)) {
    return send({ provider: "jellyfin", episodes: [], warnings: [] });
  }
  // The player's probe — without it the primary action (Play/Resume) throws in the frame, and a
  // harness that crashes where the app works is worse than no harness.
  if (path.startsWith("/api/jellyfin/playback-info")) {
    return send({
      media_source_id: "harness-ms", container: "mkv",
      video: { codec: "h264", profile: "High", width: 1920, height: 1080, bit_depth: 8, bit_rate: 5_000_000 },
      audio: [{ index: 1, name: "Hindi AAC 2.0", language: "hin", codec: "aac" }],
      subtitles: [], preferred_subtitle: null, mode: "direct",
    });
  }
  if (path.startsWith("/api/jellyfin/progress") || path.startsWith("/api/jellyfin/subtitle")) {
    return send({ ok: true });
  }
  if (path.startsWith("/api/library/folders/")) {
    return send({ provider: "jellyfin", items: [MOVIE], folder_id: "f1", warnings: [] });
  }
  if (path === "/api/library/folders") {
    return send({ libraries: [{ name: "Movies", path: "/data/Movies", folder_id: "f1",
                                collection_type: "movies", ok: true, warning: "" }], warnings: [] });
  }
  if (path === "/api/library/items") {
    return send({ provider: "jellyfin", items: [MOVIE], warnings: [] });
  }
  if (path === "/api/library/continue-watching" || path === "/api/library/recently-watched") {
    return send({ provider: "jellyfin", items: [], warnings: [] });
  }
  if (path === "/api/library") {
    return send({ provider: "jellyfin", available: true, counts: {}, recent: [MOVIE] });
  }
  return send({});
}) as typeof fetch;

/** Geometry of everything a modal claim depends on. */
const rect = (el: Element) => {
  const b = el.getBoundingClientRect();
  return { left: b.left, right: b.right, top: b.top, bottom: b.bottom,
           width: b.width, height: b.height };
};

(window as unknown as { __probe: () => unknown }).__probe = () => {
  const dialogs = [...document.querySelectorAll('[role="dialog"]')];
  // A scrim is any fixed, viewport-covering element that paints a dark translucent fill.
  const scrims = [...document.querySelectorAll("body *")].filter((el) => {
    const cs = getComputedStyle(el);
    if (cs.position !== "fixed" && cs.position !== "absolute") return false;
    const b = el.getBoundingClientRect();
    const covers = b.width >= innerWidth * 0.98 && b.height >= innerHeight * 0.98;
    const dark = /rgba?\(0,\s*0,\s*0/.test(cs.backgroundColor) ||
                 /rgba?\(\s*(?:[0-9]|[1-5][0-9]),\s*(?:[0-9]|[1-5][0-9]),\s*(?:[0-9]|[1-5][0-9])/.test(cs.backgroundColor);
    return covers && dark && cs.backgroundColor !== "rgba(0, 0, 0, 0)";
  });
  const back = document.querySelector('button[aria-label="Back"]') ||
               [...document.querySelectorAll("button")].find((b) => (b.textContent || "").trim() === "Back");
  const h1 = document.querySelector("h1");
  const main = document.querySelector("main");
  const header = document.querySelector("header");
  const mainEl = main?.firstElementChild ?? main;
  // The Dialog shell: its outer div is the scrim, its [role=dialog] child is the panel.
  const panel = document.querySelector('[role="dialog"]') as HTMLElement | null;
  const scrim = (panel?.parentElement ?? null) as HTMLElement | null;
  const css = (el: Element | null | undefined, prop: string) =>
    el ? getComputedStyle(el).getPropertyValue(prop) : null;
  const closeBtn = document.querySelector('[data-testid="item-detail-close"]') as HTMLElement | null;
  const inertWrap = document.querySelector('[aria-hidden="true"].pointer-events-none') as HTMLElement | null;
  // ⚠ Scoped to the PANEL: the background library view carries a hero of its own, and `main …` was
  // matching that one — so the "content is inset from the panel's edges" measurement was reading the
  // wrong element entirely (caught by the check's own inset assertion, 2026-09-13).
  const heroEl = panel?.querySelector("[class*='rounded-2xl'][class*='h-']") ?? null;
  return {
    route: location.search,
    pathname: window.location.pathname + window.location.search,
    calls: [...calls],
    searchCalls: calls.filter((c) => c.url.startsWith("/api/search/global")).length,
    dialogCount: dialogs.length,
    dialogText: dialogs.map((d) => (d.textContent || "").trim().slice(0, 80)),
    scrimCount: scrims.length,
    bodyOverflow: getComputedStyle(document.body).overflow,
    viewport: { w: innerWidth, h: innerHeight },
    panel: panel
      ? { ...rect(panel), radius: css(panel, "border-top-left-radius"), shadow: css(panel, "box-shadow"),
          overflowY: css(panel, "overflow-y"), maxHeight: css(panel, "max-height"),
          centredX: rect(panel).left + rect(panel).width / 2 - innerWidth / 2,
          centredY: rect(panel).top + rect(panel).height / 2 - innerHeight / 2 }
      : null,
    scrim: scrim
      ? { ...rect(scrim), bg: css(scrim, "background-color"), blur: css(scrim, "backdrop-filter"),
          position: css(scrim, "position") }
      : null,
    closeBtn: closeBtn ? rect(closeBtn) : null,
    behindInert: inertWrap ? { pointerEvents: css(inertWrap, "pointer-events"),
                               text: (inertWrap.textContent || "").trim().slice(0, 60) } : null,
    heroInset: heroEl && panel
      ? { left: rect(heroEl).left - rect(panel).left, top: rect(heroEl).top - rect(panel).top }
      : null,
    playerOpen: Boolean(document.querySelector("[class*=rkm-player]")),
    main: mainEl ? rect(mainEl) : null,
    header: header ? rect(header) : null,
    hero: (() => {
      const hero = document.querySelector("main .rounded-2xl.relative, main [class*='h-[300px]']");
      return hero ? rect(hero) : null;
    })(),
    title: h1 ? { text: (h1.textContent || "").trim(), ...rect(h1) } : null,
    back: back ? { ...rect(back), visible: !!back.offsetParent, label: back.getAttribute("aria-label") } : null,
    closeButtons: [...document.querySelectorAll("button")].filter((b) =>
      /close|dismiss/i.test((b.getAttribute("aria-label") || "") + (b.textContent || ""))).length,
    body: (document.body.textContent || "").slice(0, 600),
  };
};

const router = createMemoryRouter(
  [
    {
      path: "/",
      element: <AppShell />,
      children: [
        { index: true, element: <Navigate to="/library/home" replace /> },
        {
          path: "library",
          element: <LibraryLayout />,
          children: [
            { index: true, element: <Navigate to="/library/home" replace /> },
            { path: "home", element: <LibraryHomeView /> },
            { path: "folder/:folderId", element: <LibraryFolderView /> },
            { path: "item/:itemId", element: <ItemDetailPage /> },
          ],
        },
      ],
    },
  ],
  { initialEntries: [ROUTE] },
);

function Frame() {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false } } }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
