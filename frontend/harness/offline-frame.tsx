/**
 * Harness: the REAL offline page (B4) against a SCRIPTABLE fake bridge.
 *
 * `tools/check_offline_page.py` drives this frame in a real browser, because the page half of offline
 * downloads has a property no unit test can reach: **every decision it makes is about a channel that
 * only exists inside the iOS shell.** The rules are pure and falsified in `src/features/offline/*.test.ts`;
 * what is proved HERE is the WIRING — that the real `DownloadButton`, `DownloadsView` and `Player` pass
 * those rules through to a bridge, and that the bridge is not spoken to at all when there is none.
 *
 * Why a fake bridge and not a mock of the app: `window.__rkmOffline` is the actual boundary the Swift
 * side owns (`OfflineBridge.swift`), so `?bridge=0` reproduces a DESKTOP browser exactly (no global),
 * and `?bridge=1` reproduces the shell. Everything on the page side of that line is the shipped code:
 * the only things stubbed are `fetch` (no backend in the sandbox) and the bridge object itself.
 *
 * ⚠ **The one deliberate substitution: the media element.** A fake `http://127.0.0.1:<port>/offline/…`
 * URL cannot deliver bytes, so the frame rewrites the SOURCE to `/harness-sample.mp4` the instant the
 * player sets it — after recording the URL it replaced (`__mediaSwaps`), which is the assertion that
 * matters. Everything else about playback (the report path, the queue, the dock chip) is untouched,
 * and the swap is what lets a real `<video>` tick so the progress spool has something to hold.
 *
 * Query params: `?bridge=0|1` · `?bundle=0|1` · `?route=/library/item/m-sholay` · `?api=down` ·
 * `?media=0|1`.
 */
import { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, Navigate, RouterProvider } from "react-router-dom";

import { AuthProvider } from "../src/features/auth/AuthProvider";
import { RequireSession } from "../src/features/auth/RequireSession";
import { AppShell } from "../src/app/layout/AppShell";
import { LibraryLayout } from "../src/features/library/LibraryLayout";
import { LibraryHomeView } from "../src/features/library/LibraryHomeView";
import { ItemDetailPage } from "../src/features/library/ItemDetailPage";
import { DownloadsView } from "../src/features/offline/DownloadsView";
import { useOffline, __setSpoolForTests } from "../src/features/offline/session";
// The app's REAL stylesheet — a visibility claim about an unstyled frame is worth nothing.
import "../src/styles/index.css";

const params = new URLSearchParams(location.search);
const WITH_BRIDGE = params.get("bridge") !== "0";
const WITH_BUNDLE = params.get("bundle") !== "0";
const API_DOWN = params.get("api") === "down";
const MEDIA = params.get("media") !== "0";
const ROUTE = params.get("route") ?? "/library/item/m-sholay";

const PROFILE = {
  id: "uid-admin", name: "rkm", is_admin: true, has_password: true, disabled: false, last_login: "",
};

const ITEM_ID = "m-sholay";
const TITLE = "Sholay";
const MOVIE = {
  item_id: ITEM_ID, title: TITLE, year: 1975, media_type: "movie",
  played: false, playback_position: 0, runtime: 12240,
};
const ITEM_DETAIL = {
  type: "movie", item_id: ITEM_ID, name: TITLE, year: 1975, runtime: 12240,
  overview: "Two friends, their village, and a bandit.",
  genres: ["Action", "Drama"], community_rating: 8.1, official_rating: "PG", studios: ["Sippy Films"],
  has_backdrop: false, primary_aspect: 0.667, people: { actors: [], directors: [], writers: [] },
  play: { played: false, resume_ticks: 0, resume: 0, play_count: 0 },
};
/** The server's own answer about a download: what it would cost, before anything is packaged. */
const BUNDLE = {
  v: 1, item_id: ITEM_ID, title: TITLE, year: 1975, type: "movie", series_id: null,
  mode: "remux", needs_transcode: false, container: "mkv", video_codec: "h264",
  audio_codecs: ["aac"], duration_s: 12240, estimate_bytes: 2_100_000_000,
  state: "missing", bytes: 0, size: 0, borrowed: false,
  subtitles: [], poster_url: "/api/jellyfin/poster?id=x&width=500",
  backdrop_url: "/api/jellyfin/backdrop?id=x&width=1600", file_url: `/api/offline/file/${ITEM_ID}`,
};
const PLAYBACK_INFO = {
  media_source_id: "harness-ms", container: "mp4",
  video: { codec: "h264", profile: "High", width: 960, height: 540 },
  audio: [{ index: 1, name: "English AAC", language: "eng", codec: "aac" }],
  subtitles: [],
};
const LOOPBACK_URL = "http://127.0.0.1:51234/offline/0123456789abcdef0123456789abcdef.mp4";

const calls: { url: string; method: string; body: string }[] = [];
const mediaSwaps: { from: string; to: string }[] = [];

// ---------------------------------------------------------------- the fake bridge

interface FakeBridge {
  items: unknown[];
  commands: unknown[];
  listeners: ((event: unknown) => void)[];
  refusal: { code: string; message: string } | null;
  playUrl: string;
  emit: (event: unknown) => void;
}

const bridge: FakeBridge = {
  items: [],
  commands: [],
  listeners: [],
  refusal: null,
  playUrl: LOOPBACK_URL,
  emit(event: unknown) {
    bridge.listeners.slice().forEach((listener) => {
      try {
        listener(event);
      } catch {
        /* the page's listeners are the page's problem */
      }
    });
  },
};

function reply(result: unknown) {
  if (bridge.refusal) return Promise.resolve({ v: 1, ok: false, error: bridge.refusal });
  return Promise.resolve({ v: 1, ok: true, result });
}

if (WITH_BRIDGE) {
  (window as unknown as { __rkmOffline: unknown }).__rkmOffline = {
    version: 1,
    available: true,
    on(listener: (event: unknown) => void) {
      bridge.listeners.push(listener);
      return this;
    },
    off(listener: (event: unknown) => void) {
      bridge.listeners = bridge.listeners.filter((each) => each !== listener);
      return this;
    },
    list() {
      bridge.commands.push({ c: "list" });
      const items = bridge.items as Array<{ bytes?: number }>;
      return reply({
        items: bridge.items,
        bytes: items.reduce((total, row) => total + (row.bytes ?? 0), 0),
        count: bridge.items.length,
      });
    },
    ping() {
      bridge.commands.push({ c: "ping" });
      return reply({ accepted: "ping" });
    },
    play(itemId: string) {
      bridge.commands.push({ c: "play", itemId });
      return reply({
        play: { itemId, url: bridge.playUrl, contentType: "video/mp4", size: 1_543_383_346 },
      });
    },
    cancel(itemId: string) {
      bridge.commands.push({ c: "cancel", itemId });
      return reply({ accepted: "cancel" });
    },
    remove(itemId: string) {
      bridge.commands.push({ c: "delete", itemId });
      return reply({ accepted: "delete" });
    },
    download(itemId: string, title: string, mode: string) {
      bridge.commands.push({ c: "download", itemId, title, mode });
      return reply({ accepted: "download" });
    },
  };
  (window as unknown as { __bridge: unknown }).__bridge = bridge;
}

// ---------------------------------------------------------------- the API stub

let apiDown = API_DOWN;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const realFetch = window.fetch.bind(window);
window.fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const raw = typeof input === "string" ? input : String((input as Request).url ?? input);
  const at = raw.indexOf("/api");
  const path = at >= 0 ? raw.slice(at) : raw;
  const method = String(init.method || "GET").toUpperCase();
  const body = typeof init.body === "string" ? init.body : "";
  calls.push({ url: path, method, body });

  // ⚠ A dropped connection, reproduced exactly: `fetch` REJECTS (nothing answered), which is the case
  // the auth guard used to read as "signed out".
  if (apiDown && path.startsWith("/api")) {
    throw new TypeError("Failed to fetch");
  }

  if (path === "/api/auth/me") {
    return json({
      user: { id: PROFILE.id, name: PROFILE.name },
      profile: { id: PROFILE.id, name: PROFILE.name },
      profile_selected: true, on_own_profile: true, expires: "2026-10-12T00:00:00Z",
    });
  }
  if (path === "/api/auth/profiles") {
    return json({ profiles: [PROFILE], current: PROFILE, profile_selected: true, warning: "" });
  }
  if (path.startsWith("/api/offline/bundle/")) {
    if (!WITH_BUNDLE) return new Response("", { status: 404 });
    return json({ ...BUNDLE, item_id: path.split("/").pop() });
  }
  if (path === "/api/jellyfin/progress") return json({ ok: true });
  if (path.startsWith("/api/jellyfin/playback-info")) return json(PLAYBACK_INFO);
  if (path.startsWith("/api/jellyfin/detail")) return json(ITEM_DETAIL);
  if (path.startsWith("/api/jellyfin/similar") || path.startsWith("/api/jellyfin/backdrop")) {
    return new Response("", { status: 404 });
  }
  // ⚠ The media routes answer immediately and emptily. A page that has gone to the SERVER for a film it
  // holds locally must fail FAST here, or the run measures a dead backend's timeouts rather than the
  // page's behaviour (measured: the HLS escalation ladder turns one wrong decision into minutes).
  if (path.startsWith("/api/jellyfin/stream") || path.startsWith("/api/jellyfin/hls")) {
    return new Response("", { status: 404 });
  }
  if (path.startsWith("/api/library/items")) {
    return json({ provider: "jellyfin", items: [MOVIE] });
  }
  if (path.startsWith("/api/library/folders")) {
    return json({
      provider: "jellyfin", folders: [], libraries: [],
      warnings: [],
    });
  }
  if (path.startsWith("/api/library")) return json({ provider: "jellyfin", items: [], recent: [] });
  if (path.startsWith("/api/config")) return json({ updated: "", heroMode: "", rotation: [], services: {} });
  if (path.startsWith("/api/health")) {
    return json({ ok: true, updated: "", titleCount: 0, services: {}, degraded: false, serviceDetail: {} });
  }
  return realFetch(input, init);
}) as typeof window.fetch;

/** The test flips the network mid-run (offline → reconnect) through this handle. */
(window as unknown as { __setApiDown: unknown }).__setApiDown = (down: boolean) => {
  apiDown = down;
};

// ---------------------------------------------------------------- the media swap

if (MEDIA) {
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      const el = record.target as HTMLVideoElement;
      if (record.attributeName !== "src" || !el || el.tagName !== "VIDEO") continue;
      const current = el.getAttribute("src") || "";
      // ⚠ Only a media URL the app owns is swapped, and the URL it replaced is RECORDED — that record
      // is the evidence that the player chose the loopback server over the API.
      if (current.startsWith("http://127.0.0.1:")) {
        mediaSwaps.push({ from: current, to: "/harness-sample.mp4" });
        observer.disconnect();
        el.setAttribute("src", "/harness-sample.mp4");
        el.load();
        observer.observe(document.documentElement, { subtree: true, attributes: true, attributeFilter: ["src"] });
      }
    }
  });
  observer.observe(document.documentElement, { subtree: true, attributes: true, attributeFilter: ["src"] });
}

// ---------------------------------------------------------------- the probe

function text(selector: string): string {
  const el = document.querySelector(selector);
  return el ? (el.textContent || "").trim() : "";
}

function buttonsIn(scope: Element | null): string[] {
  if (!scope) return [];
  return [...scope.querySelectorAll("button")]
    .map((button) => (button.textContent || "").trim())
    .filter(Boolean);
}

(window as unknown as { __probe: unknown }).__probe = () => {
  const state = useOffline.getState();
  const panel = document.querySelector('[role="dialog"][aria-modal="true"]');
  const video = document.querySelector("video");
  return {
    route: location.pathname,
    offlineAvailable: state.available,
    loaded: state.loaded,
    rows: state.items.map((row) => ({
      itemId: row.itemId, state: row.state, bytes: row.bytes, totalBytes: row.totalBytes, mode: row.mode,
    })),
    queued: state.queuedReports,
    notice: state.notice,
    nav: [...document.querySelectorAll("a")]
      .map((a) => a.getAttribute("href"))
      .filter((href) => href === "/downloads"),
    detail: {
      panelPresent: Boolean(panel),
      buttons: buttonsIn(panel),
      summary: panel ? [...panel.querySelectorAll("span")].map((s) => (s.textContent || "").trim()) : [],
      status: text("[data-testid^='download-status-'], [role='dialog'] p"),
    },
    downloads: {
      summary: text("[data-testid='downloads-summary']"),
      queued: text("[data-testid='downloads-queued']"),
      rows: [...document.querySelectorAll("[data-testid^='download-row-']")].map((row) => ({
        id: row.getAttribute("data-testid"),
        state: row.getAttribute("data-state"),
        text: (row.textContent || "").trim(),
        buttons: buttonsIn(row),
      })),
    },
    commands: bridge.commands,
    progressPosts: calls
      .filter((call) => call.url === "/api/jellyfin/progress" && call.method === "POST")
      .map((call) => call.body),
    playbackInfoCalls: calls.filter((call) => call.url.includes("/api/jellyfin/playback-info")).length,
    bundleCalls: calls.filter((call) => call.url.includes("/api/offline/bundle/")).length,
    mediaSrc: video ? video.getAttribute("src") : null,
    mediaSwaps,
    mediaCurrentTime: video ? video.currentTime : null,
    videoReadyState: video ? video.readyState : null,
    loginForm: Boolean(document.querySelector('input[type="password"]')),
    okBoard: Boolean(document.querySelector("main")),
    body: (document.body.textContent || "").slice(0, 700),
  };
};

/**
 * TEST ONLY: tell the page what the device holds, exactly as `OfflineBridge.pageDidLoad()` does —
 * set the rows AND emit one `state` event per row.
 *
 * ⚠ Both halves are needed, and that is a property of the real system rather than of the fake: `list`
 * answers a request that happens once, and the bridge RE-ANNOUNCES every title after each page load
 * (a reload is a new document that knows nothing). A test that only set `bridge.items` would reload
 * into an empty screen and conclude the app was broken.
 */
(window as unknown as { __announce: unknown }).__announce = (items: Record<string, unknown>[]) => {
  bridge.items = items;
  items.forEach((item) => {
    bridge.emit({
      v: 1, e: "state", itemId: item.itemId, title: item.title, state: item.state,
      bytes: item.bytes, totalBytes: item.totalBytes, mode: item.mode,
      error: item.error ?? null, url: item.url ?? null,
    });
  });
};

/** TEST ONLY: seed the on-disk queue (the tool asserts a replay, and a play is not scriptable). */
(window as unknown as { __seedSpool: unknown }).__seedSpool = (entries: Record<string, unknown>) => {
  __setSpoolForTests({ entries: entries as never });
};

// ---------------------------------------------------------------- the mount

const router = createMemoryRouter(
  [
    {
      path: "/",
      element: (
        <RequireSession>
          <AppShell />
        </RequireSession>
      ),
      children: [
        { index: true, element: <Navigate to="/library/home" replace /> },
        {
          path: "library",
          element: <LibraryLayout />,
          children: [
            { index: true, element: <Navigate to="/library/home" replace /> },
            { path: "home", element: <LibraryHomeView /> },
            { path: "item/:itemId", element: <ItemDetailPage /> },
          ],
        },
        { path: "downloads", element: <LibraryLayout />, children: [{ index: true, element: <DownloadsView /> }] },
      ],
    },
  ],
  { initialEntries: [ROUTE] },
);

function Frame() {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<Frame />);
