# Native feel + offline downloads — plan

**Status: PLAN ONLY — nothing in this document has been built.** Written 2026-09-14 after his ask:
*"i want to implement something that would make the apps on ios and ipados very snappy… right now
every time i open the app the posters are being downloaded… can we implement some kind of caching so
that the user would feel like a native app experience… second off line downloads feature… come up
with a detailed idea to implement above… i just need idea and detailed plan for now"*.

Two workstreams, deliberately separated because they have different risk profiles:

| | Workstream | Risk | Payoff |
|---|---|---|---|
| **A** | Instant launch / native feel | **Low** — frontend + one nginx line, no app rebuild for most of it | Everything feels faster immediately |
| **B** | Offline downloads | **High** — new native code, new backend routes, an iOS media question that must be answered by an experiment before the design is fixed | The app works on a plane |

⚠ **Every measured claim below is marked with the file it was read from.** Items marked **[VERIFY]**
are NOT established and have an experiment in §5 with the exact steps — the plan does not assume them.

---

## 1. What "snappy" and "offline" have to mean, as numbers

Feelings do not survive a code review, so each goal gets a number and an instrument. The app already
has the instrument that makes this possible — the shell logs **every request with status, duration and
bytes** (`WebBridge.swift` → `RKMLog.request`, `apple/LOGGING.md` §9) — so these are checks against
existing output, not new machinery.

| Goal | Number | Measured by |
|---|---|---|
| **Cold launch → usable home** | ≤ 400 ms to a painted, populated home screen (rows + posters from disk) | One new log line per launch (§3.5) |
| **App shell bytes on a warm launch** | **0 bytes** for JS/CSS (not 304s — no request at all) | The request log |
| **API calls per cold launch** | ≤ 2 (today: 6–8) | The request log |
| **Poster bytes on a re-visit within a week** | 0 (0-byte 304 at worst) | The request log + `curl -I` |
| **Offline playback** | A downloaded title starts with the Wi-Fi **off**, in ≤ 1 s, and resume position is correct | Device test |
| **Offline watch state** | Progress recorded offline appears in Continue Watching once the server is reachable again | Device test |

---

## 2. Why it is slow today — read out of the code, not guessed

### 2.1 ⚠⚠ The biggest one: the SPA's own JS/CSS are served `no-store`

`nginx/default.conf:13-16`:

```nginx
location / {
    add_header Cache-Control "no-store, no-cache, must-revalidate, max-age=0";
    try_files $uri $uri/ /index.html;
}
```

`add_header` applies to **every** response this location produces — including the hashed, immutable
`/assets/index-<hash>.js` matched by `try_files`. So on **every cold launch the browser re-downloads
the whole app**: `index-*.js` **1,073.87 kB (327.86 kB gzip)** + `index-*.css` **55.85 kB (10.42 kB
gzip)** (my own `npm run build`, 2026-09-14). Vite hashes those filenames precisely so they can be
cached forever; the blanket `no-store` throws that away.

The same line makes **offline launch impossible**: `no-store` on `index.html` means no cached copy can
ever be reused, so with the server unreachable the shell has nothing to render.

### 2.2 Every API call is `no-store` by design, and nothing replaces it client-side

`nginx/default.conf:19-31` stamps `Cache-Control: no-store` on `/api/` — correct for *rows* (a stale
row is worse than a slow one), but the client then has **no cache at all**: `main.tsx:9-13` builds the
`QueryClient` in memory only (`staleTime: 30_000`, no persistence), so a cold launch starts with an
empty cache and refetches everything.

From his own device log (2026-09-14, quoted in `docs/PROGRESS.md`) — **six calls, one screen**:

| Call | ms |
|---|---|
| `GET /api/library/items` | 299 |
| `GET /api/library/recently-watched` | 380 |
| `GET /api/jellyfin/detail?id=…` | 395 |
| `GET /api/library` | 423 |
| `GET /api/library/continue-watching` | 446 |
| `GET /api/jellyfin/similar?id=…` | **1,330** |

Easily ~1 s of serialised network before the home screen is complete, on every launch, on a LAN.

### 2.3 Artwork is already handled — this is the part that works

`jellyfin_poster.py` (module docstring + `ARTWORK_CACHE_CONTROL`, line 24) and the nginx nested
location (`default.conf:43-49`) already give posters `public, max-age=604800,
stale-while-revalidate=604800` with `ETag`/`Last-Modified` → a bodiless 304 on re-validation. There is
even a gate: `tools/verify_nginx_artwork_cache.py`.

⚠ So "the posters are being downloaded every time" is **partly a symptom of §2.1**: with the bundle
and every API response uncached, the whole screen — posters included — starts from nothing each
launch. The poster policy itself is measured and correct. **Posters are also the expensive part in
bytes** (a 140-title folder = ~13 MB per visit, per that docstring), so they are the thing most worth
protecting from a cold start.

### 2.4 ✅ MEASURED against the LIVE server (2026-09-14) — not read from the config

`curl -sI http://rkm-hp.tail8d5e8.ts.net:8124/…` from the sandbox, which can reach the box:

```
/                                        → 200, 1623 B, ETag "6aa74580-657"
  Cache-Control: no-store, no-cache, must-revalidate, max-age=0
/assets/index-9K9pHiDW.js                → 200, 1,074,168 B   ← ⚠ UNCOMPRESSED
  Cache-Control: no-store, no-cache, must-revalidate, max-age=0
/api/jellyfin/poster?id=x                 → 405 (HEAD is not served; see 4.3)
```

**Both defects are therefore confirmed, and a third one was not in my reading of the config:**

* ⚠⚠ **The 1.07 MB bundle really is `no-store`** — §2.1 is a measurement now, and it is re-fetched on
  every single launch.
* ⚠ **It is served UNCOMPRESSED.** Vite reports `1,073.87 kB │ gzip: 327.86 kB`; nginx sends
  **1,074,168 bytes** because `nginx/default.conf` has no `gzip on` / `gzip_static on`. So the launch
  payload is **1.13 MB** where it could be **~340 kB** — a **3.3×** reduction available for two lines
  of config, before any caching at all.
* The deployed bundle is **byte-identical** (same SHA-256) to the one this sandbox builds from
  `frontend/`, which is a useful fact in its own right: the live UI is the repo's current source.

### 2.5 What is NOT the problem (recorded so it is not re-litigated)

* **WKWebView's cache is not being cleared.** The data store is deliberate and persistent
  (`WebShellView.swift:34` `websiteDataStore = .default()`); `WebsiteData.swift` only clears on an
  explicit, confirmed user action; the load uses the default cache policy
  (`WebShellModel.swift:68` `webView.load(URLRequest(url:))`).
* **The shell is not reloading on every launch** — one `load #N` line per launch, which is what a
  native app start should do.

---

## 3. Workstream A — make launch feel native

### 3.1 A1 · Correct cache headers (the single cheapest win)

> ✅ **BUILT 2026-09-14** on `perf/nginx-asset-caching` — `nginx/default.conf` only, plus the new
> `tools/verify_nginx_shell_cache.py` gate. **Measured against the live stack, before/after on the
> same bytes:** the shell's `index-9K9pHiDW.js` is served **1,074,168 B with `Cache-Control: no-store`
> and no `Content-Encoding`**, and the same bytes gzip to **326,111 B** (3.29×); the CSS is 55,854 B →
> **10,303 B** (5.4×). So **1,130,022 B re-fetched on every launch becomes 336,414 B fetched once.**
> **⚠ A CORRECTION TO THIS SECTION'S OWN PREMISE, verified before it was written down:** the snippet
> below says to serve "the .gz Vite/our build already emitted, **where one exists**" — **the build
> emits NONE.** `frontend/dist/assets/` holds only the `.js` and the `.css`; there is no compression
> plugin in `vite.config.ts` or `package.json`. So **`gzip_static on` was NOT added**: it would be
> inert today, and whether `nginx:alpine` is compiled with `--with-http_gzip_static_module` cannot be
> verified from the sandbox (no docker daemon) — an unknown directive makes nginx **refuse to start**,
> i.e. take the web container down for no gain. `gzip on` does the whole job; add `gzip_static` only
> in the same change as a build step that emits the `.gz` files, and test that build.
> **⚠ AND THE ONE THING THAT WOULD HAVE SHIPPED SILENTLY:** `gzip_types` is matched against the
> Content-Type **nginx assigned**, which for a static file comes from `mime.types`. The first version
> of the new gate omitted that include, so *every* static-file case failed while the proxied JSON
> still compressed — a harness bug wearing the costume of a config bug. `find_mime_types()` in the
> tool now loads the real one and prints the resolved path.

`nginx/default.conf`:

```nginx
    # ⚠ Compression FIRST — this is independent of caching and worth 3.3x on its own
    # (measured: 1,074,168 B uncompressed for a bundle Vite reports as 327.86 kB gzipped).
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;
    # …and serve the .gz Vite/our build already emitted, where one exists.
    gzip_static on;

    # index.html: revalidate every time, but MUST be storable — `no-store` is what makes an
    # offline launch impossible and forces a 1 MB re-download of the shell.
    location / {
        add_header Cache-Control "no-cache";
        try_files $uri $uri/ /index.html;
    }

    # Vite's hashed bundles: immutable by construction. Cache them forever.
    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files $uri =404;
    }
```

Notes that matter:
* `no-cache` still guarantees freshness (it forces revalidation) but lets the browser **store** the
  document — the prerequisite for booting with no network.
* Keep `/api/` `no-store` for JSON, keep the artwork nested location as is. The existing comment's
  warning applies: **nginx does not inherit `add_header` into a location that defines one**, so each
  block must state its own.
* ✅ `tools/verify_nginx_shell_cache.py` — **WRITTEN AND FALSIFIED 2026-09-14.** It runs a stand-in api
  behind the REAL repo config and asserts 13 cases (document storable-and-revalidated on `/` and on a
  deep link, hashed bundles immutable, a missing bundle a 404 rather than the shell, both bundles
  really gzipped and really smaller with `Vary`, **media through the proxy NOT gzipped**, `/api/` JSON
  still `no-store` **and** compressed, and the artwork policy undisturbed). **Falsified before it was
  trusted:** run with `--config <the pre-change file>` it reports **9 FAIL**; against the repo config
  **13/13 PASS**. That `--config` flag is deliberate — it is how the next session re-proves the check
  can fail.
  A header policy that is only in a config file rots the moment someone edits the file.
* **[VERIFY]** read from the config, not from a live response: confirm on the box with
  `curl -sI http://<host>:8124/assets/index-<hash>.js | grep -i cache-control` before and after.

**Cost:** one file, no app rebuild, no frontend rebuild. **Gate:** the second launch's request log
shows **no** request for the JS/CSS at all.

### 3.2 A2 · Persistent query cache — paint from disk, then revalidate

Add TanStack Query persistence so the home screen renders from the last session's data before any
network call:

* `@tanstack/query-persist-client-core` + a small IndexedDB storage adapter (or hand-rolled
  `idb`-free wrapper, ~40 lines, to keep dependencies at zero).
* `staleTime` and `gcTime` raised for read-mostly queries (`/library`, `/library/items`,
  `/library/folders`), while mutations invalidate as they do now.
* **A per-query policy, not a global one.** Cached-for-instant-paint: library rows, folders, item
  detail, artwork URLs. Never persisted: `/auth/me` (session truth), playback-info, progress.
* ⚠ **Sign-out must purge it** — the cache is per-profile data on a device that multiple household
  profiles share (`HOUSEHOLD_USERS_PLAN.md`). `queryClient.clear()` on sign-out/sign-in, asserted by
  a test that fails if the persister survives a profile switch.
* Data-version stamp: cache `{schemaVersion, serverId}`; a mismatch (new server address, contract
  bump) drops the cache instead of rendering another server's library.

**Effect:** §1's "usable home ≤ 400 ms" becomes reachable, because the first paint no longer waits for
Jellyfin at all.

### 3.3 A3 · One call instead of six: `/api/library/home`

A read-only aggregator returning exactly what the home screen needs:

```
GET /api/library/home
→ { schema, folders[], rows[{id,title,items[]}], continue_watching[], recently_watched[],
    counts{}, generated_at }
```

* Server-side fan-out with a short in-process memo (e.g. 20 s, keyed by profile) — the same Jellyfin
  calls, made once, in parallel, by the process that is already warm.
* ⚠ **Additive and opt-in**: the existing routes stay byte-identical so nothing else breaks
  (`docs/api/openapi.v1.json`, ADR-0001 — the contract is committed, so the new route must be added
  there with its session decision, or `tests/test_route_protection.py` fails the suite **by design**).
* `/jellyfin/similar` (the 1.33 s call) stays lazy — it is below-the-fold detail-page work, not home.

### 3.4 A4 · Artwork and prefetch

* Keep the 1-week + SWR policy; ensure every list requests the width it renders (the proxy takes
  `width`, and a 140-title grid at `width=500` is the case the policy was measured against).
* `loading="lazy"`, `decoding="async"`, `fetchpriority="high"` only for the first row, and a fixed
  aspect-ratio box per tile so nothing reflows as posters land.
* Prefetch the *next* screen's first row on idle (`requestIdleCallback`), gated on
  `navigator.connection.saveData === false && effectiveType` ≥ 3g — never on cellular.
* ⚠ Ignore `navigator.onLine`: it is famously optimistic. Offline decisions come from failed requests
  and the native bridge (§4), not from that flag.

### 3.5 A5 · Instrument it, then hold the line

One log line per launch, emitted through the existing bridge:

```
[cold] launch→LCP 612ms · bundle cached=yes · api 1 call 240ms · artwork 0 bytes · data from disk
```

Plus a battery-visible gate (`tools/check_launch_budget.py`, in the style of
`tools/check_nav_access.py`): drive the built app in the browser harness with a **cold** profile and
assert the request count and bytes for a first paint; then a warm profile and assert **zero** requests
for `/assets/`.

⚠ Without this, A1–A4 are unfalsifiable on the next regression — which is exactly the class of change
this repo pins elsewhere (`shell-contract.test.ts`).

---

## 4. Workstream B — offline downloads

### 4.1 The design decisions, and the alternatives that were rejected

| Question | Decision | Why |
|---|---|---|
| Where do downloaded films live? | **Native, in the app container** (`Application Support/Offline/`, `isExcludedFromBackup = true`) | `Caches/` is purgeable by iOS under pressure — a downloaded film that vanishes is worse than no feature. Backup exclusion keeps multi-GB files out of iCloud. |
| Who fetches them? | **`URLSession` background download tasks in the shell** | Continues while the app is suspended/backgrounded, survives app relaunch, gives resumable transfers with progress — none of which a page can do. A page-side download stops when the app is backgrounded. |
| Web-layer storage (Cache Storage / OPFS) instead? | **Rejected** | WebKit caps the Cache API at a **fixed ~50 MiB per partition** (WebKit blog, "Workers at Your Service"), and evicts caches idle for a few weeks. One film exceeds the whole budget. |
| How does the page play a local file? | **A loopback HTTP server inside the app** (`http://127.0.0.1:<port>/offline/<token>.mp4`), port handed to the page over the bridge | `WKURLSchemeHandler` is the elegant answer and is **not** safe here: WebKit's media stack is a separate process and does not route media through app scheme handlers, with current reports of media elements failing to load from local/custom sources on iOS 26 (**[VERIFY]** — experiment E1). loopback HTTP also gives real `Range` support for free, which seeking needs. |
| Does the loopback server weaken ATS? | **No change needed** | `Info.plist` already carries `NSAllowsArbitraryLoads` only, which covers `http://127.0.0.1`. ⚠ **The existing warning is now load-bearing:** adding `NSAllowsLocalNetworking` **disables** `NSAllowsArbitraryLoads` on iOS 10+, and the loopback server would break with it. |
| Serve from `file://` instead? | **Rejected** | The page's origin is `http://<server>`; `file://` subresources are cross-origin and blocked. |
| What about a service worker for the page shell? | **Not assumed** | WebKit's position has been that WKWebView gets Service Workers for **app-bound domains**, which is a **build-time** domain list — and this app's address is typed at runtime and can be any host (`APPLE_CLIENTS_PLAN.md` §2). **[VERIFY]** with E2. If unavailable, A1's cache headers are the offline-shell story. |

### 4.2 What gets downloaded: the *playable* rendition, not the file on disk

The library is MKV/whatever Jellyfin has; WebKit can decode H.264/HEVC but cannot demux MKV, and
audio (EAC3/DTS/TrueHD) is a second trap the HLS work already documented
(`backend/api/routes/jellyfin_hls.py` docstring). A downloaded film must therefore be **the rendition
the player would have streamed**:

| Source | Offline package |
|---|---|
| Direct-playable (H.264/AAC in a WebKit-readable container) | the file as-is — no server CPU |
| Needs a container change | **remux → single-file MP4, `-movflags +faststart`, streams copied** |
| Needs audio transcode (EAC3/DTS/TrueHD) | remux video + **AAC audio**, single-file MP4 |
| Needs video transcode | H.264 + AAC MP4 (last resort, CPU-heavy — surface the cost in the UI) |

**Packaged server-side into a staging file**, not streamed on the fly, because:
* `Content-Length` is then real → true progress, % complete, and "this is 2.3 GB, you have 41 GB
  free" *before* he taps Download;
* the transfer is **resumable** (byte ranges) and verifiable (size/ETag);
* Jellyfin's transcode pipe is tied to a playback session, which is the wrong lifetime for a download.

Staging rules: `RKM_OFFLINE_STAGING` dir, one file per (item, rendition), **TTL cleanup** (e.g. 48 h
after last access) so a cancelled download cannot eat the server's disk, and a size cap.

### 4.3 Backend contract (additive; ADR + `openapi.v1.json` + a route-protection decision)

```
POST   /api/offline/prepare      {item_id, mode}        → {job_id, state, needs_transcode}
GET    /api/offline/status/{id}                          → {state, bytes, duration_s, ready_at}
HEAD   /api/offline/file/{id}                            → Content-Length, Accept-Ranges, ETag
                                                          ⚠ must be an EXPLICIT @router.head:
                                                          measured 2026-09-14, a GET-only FastAPI
                                                          route answers HEAD with 405, so size
                                                          probing would fail silently
GET    /api/offline/file/{id}                            → 200 / 206 + Content-Range (Range honoured)
GET    /api/offline/bundle/{id}                          → metadata + poster/backdrop URLs + subtitle list
GET    /api/offline/subtitles/{id}?lang=                 → .vtt sidecar (existing subtitle service)
DELETE /api/offline/{id}                                 → drop the staging file
```

* **Auth:** the same session rules as every other route — the route-protection test forces the
  decision to be explicit rather than inheriting one silently (`api/session.py`: a route on the auth
  router is NOT session-scoped; a `_user_id()` fallback silently acts as the first account).
* **Authorization:** offline downloads are per-profile only in the UI; the media server has one
  credential, so the *file* is not per-profile. Record that as a decision, not an accident.
* **Idempotent `prepare`**: asking twice returns the same job/file.
* Direct play needs no prepare step at all (`mode=direct` → serve `Static=true` through the existing
  stream proxy, which already passes `Content-Range`/`Accept-Ranges` through).

### 4.4 Native side (the shell)

New: `apple/ios/RKMCinema/Offline/`

| File | Responsibility |
|---|---|
| `OfflineStore.swift` | The container layout + `manifest.json` (item id, title, rendition, bytes, downloaded-at, poster file, subtitle files), CRUD, atomic writes. |
| `OfflineDownloader.swift` | `URLSession` **background** configuration, one task per item, progress KVO/closures, resume via `Range` on failure, Wi-Fi-only option, retry with backoff. |
| `OfflineServer.swift` | Loopback HTTP/1.1 on `127.0.0.1` (`Network.framework` `NWListener`): `GET`/`HEAD` only, `Range`/206/416, correct `Content-Type`, opaque tokens instead of paths (**no path traversal by construction**), bound to loopback only. |
| `OfflineBridge.swift` | The page↔native contract (§4.5). |
| `AppDelegate` addition | `application(_:handleEventsForBackgroundURLSession:completionHandler:)` — background sessions are delivered through the app delegate, and this app is SwiftUI `@main` with no delegate today. |

⚠ **Auth for native fetches:** a native `URLSession` does **not** share the web view's cookie jar. Two
options, in order of preference:

1. **Cookie mirroring (no backend change):** copy cookies from
   `WKWebsiteDataStore.default().httpCookieStore` into `HTTPCookieStorage.shared` before starting
   downloads, and re-sync on `rkm_session` refresh/sign-in. Cheap, keeps today's auth model, and it is
   testable (a download that 401s is an immediate, visible failure rather than a silent empty file).
2. **A device token** — the bearer work already planned as **Phase 2** of `APPLE_CLIENTS_PLAN.md`
   ("non-browser auth"), stored in the Keychain. Cleaner, and it removes the session-expiry edge; but
   it is a backend change and a bigger dependency for this feature. **Recommendation: start with (1),
   move to (2) when Phase 2 lands.**

⚠ **Storage discipline:** `isExcludedFromBackup = true` on the offline directory; a **storage cap**
setting (e.g. 10/25/50 GB or "keep until I delete"), LRU eviction when the cap is hit, and a
"delete after watching" option. Never silently evict something he chose to keep — eviction candidates
are only items marked auto-managed.

### 4.5 The bridge contract (page ↔ native)

Today `WebBridge` is **one-way** (page → native) for instrumentation
(`Shell/WebBridge.swift`, `WebInstrumentation`). Offline needs both directions:

```
page → native   rkm-offline { c: "download" | "cancel" | "delete" | "list" | "play",
                              itemId, mode }        → reply via WKScriptMessageHandlerWithReply
native → page   window.__rkmOffline.emit({ e: "progress" | "state" | "ready",
                                           itemId, state, bytes, total, url })
```

* Versioned and additive (`{v:1}`), the same discipline as the HTTP contract.
* The **loopback URL never appears in a manifest on disk**, only in a live message: a stale port must
  not be cached anywhere.
* The page still works with no bridge (desktop browser): every offline affordance is hidden unless
  `window.__rkmOffline` exists — the same rule as the fullscreen button (never render a control that
  cannot work).

### 4.6 Page side (offline UX)

* **Detail page:** a Download button with the **ready size** and the rendition it will fetch
  ("1080p · 2.1 GB · remux"), a progress ring, pause/cancel, and Delete when present. It asks native
  first (`list`), so state survives relaunch and is right on every screen.
* **Downloads screen:** a new route listing downloaded titles with size, downloaded-at, disk usage vs
  cap, and per-item delete + "keep" (pin against eviction).
* **Playing offline:** the player asks native for the item before it asks `/api/jellyfin/playback-info`;
  with a local file it sets `<video src=loopback…>` and **skips playback-info entirely**, so playback
  needs no server. Offline it also stops reporting progress upstream (the calls would just fail).
* **Progress spool — the part that makes it feel finished:** positions recorded offline are written to
  a local queue and replayed to `POST /api/jellyfin/progress` on the next successful connection, with
  a monotonic rule (newest timestamp wins) so a stale replay cannot rewind what he watched later
  online. Without this, a film watched on a plane never appears in Continue Watching.
* **Artwork and subtitles offline:** both are captured into the item's bundle at download time
  (posters via the existing `width`-parameterised proxy; subtitles as `.vtt` sidecars, so the existing
  overlay renderer works unchanged).

### 4.7 Failure modes the design must state up front

| Situation | Behaviour |
|---|---|
| Server restarts / address changes while a download runs | Task fails → retryable row with the reason; the manifest keeps what was already fetched only if resumable (byte offset stored). |
| Session expires mid-download | Native sees 401/302 → surfaces "sign in again to continue" in the Downloads screen, rather than corrupting a file. |
| App force-quit mid-download | iOS stops background tasks on force-quit **by design** — downloads resume on next launch (`URLSession` background session reports the unfinished tasks). |
| Device storage full | Cap + eviction first; if still short, downloads pause with a clear message — never a half-file played as if complete (a size/ETag check gates `ready`). |
| Housekeeping: item deleted from the server | The file still plays (the whole point); the row is marked "no longer in the library" on the next sync. |

---

## 5. Experiments to run BEFORE any of Workstream B is designed in concrete

| # | Experiment | Decides | Cost |
|---|---|---|---|
| **E1** | Add a throwaway loopback server to the shell serving one file from the container; load `http://127.0.0.1:<port>/probe.mp4` in a `<video>` inside the page (a one-line `console.log` of `video.canPlayType` + `onerror` through the existing bridge) | **The single most important unknown**: does media play from loopback inside this WKWebView, with seeking (Range)? Also compare a `WKURLSchemeHandler` URL in the same build — one build answers both. | One Mac round (~1 h) |
| **E2** | Log `'serviceWorker' in navigator`, `navigator.storage.estimate()`, and `document.fullscreenEnabled` on launch (HUD console line) | Whether a service worker is even available for the offline shell — if not, A1's headers *are* the offline story and no SW work is planned | One `apply` + a screenshot of the HUD |
| **E3** | `curl -sI` the deployed `/assets/*.js`, `/`, `/api/jellyfin/poster`, `/api/library` | Confirms §2.1 and gives before/after numbers for A1 | ✅ **DONE 2026-09-14 — see §2.4.** `no-store` on the bundle confirmed; a third defect found (no gzip: 1.07 MB uncompressed on the wire) |
| **E4** | In the shell, cold launch twice with `log stream --device`, counting JS/CSS/API requests | The baseline the ≤400 ms and 0-byte gates are measured against | 10 minutes |
| **E5** | Time `ffmpeg -c copy` remux of one of his films → MP4 on the server | The real cost of `prepare` for a typical title, and whether 4K titles need a cap | 15 minutes |

⚠ E1 is the one that changes the design. Everything in §4.4–4.6 assumes loopback HTTP works.

---

## 6. Phases, with gates

Sandbox-side work is mine; **building and running on device is his** (this sandbox has no Xcode —
`APPLE_CLIENTS_PLAN.md` §7). Nothing below starts without his go-ahead, and each phase is separately
shippable.

| Phase | Work | Gate | Est. |
|---|---|---|---|
| **A0** | A1 cache headers + a `curl` assertion added to `tools/` | Second launch: **no** JS/CSS request in the log; `curl -I` shows `immutable` on `/assets/` and `no-cache` on `/` | 0.5 d |
| **A1** | A2 persistent query cache + sign-out purge + schema stamp | `vitest` green incl. a "persister cannot survive a profile switch" test; cold launch paints rows with the network blocked in the harness | 1 d |
| **A2** | A3 `/api/library/home` + memo, contract + route decision | `pytest` green; `check_deployed.py` sees the new route; launch request count ≤ 2 | 0.5 d |
| **A3** | A5 launch-budget instrument + gate | Baseline printed in the log; gate fails if a warm launch fetches `/assets/` | 0.5 d |
| **B0** | **E1 + E2 spike build** (throwaway, not merged) | A downloaded file plays from loopback, with seeking, inside the shell — or the design changes before anything else is written | 0.5 d |
| **B1** | Backend offline API + staging + packaging + TTL, tests, contract | pytest + a `curl` proof: `HEAD` gives the size, a `Range` request returns 206 + `Content-Range`, `prepare` is idempotent | 1 d |
| **B2** | Native: `OfflineStore` + `OfflineDownloader` + background-session delegate + cookie mirroring | Downloads complete with the app backgrounded, resume after a forced failure, and appear in the manifest after a relaunch | 2–3 d |
| **B3** | Native: `OfflineServer` + `OfflineBridge` (both directions) | Loopback server passes a Range test suite; page round-trips a command and a progress event | 1–2 d |
| **B4** | Page: download affordances, Downloads screen, offline player path, progress spool | A film downloads, plays offline with Wi-Fi off, and its position lands in Continue Watching after reconnect | 1–2 d |
| **B5** | Lifecycle: cap, eviction, keep/pin, delete-after-watch, disk meter, error states | Cap enforced; nothing pinned is ever evicted; storage-full path pauses cleanly | 1 d |

**Total: ~9–12 evenings.** A0–A3 alone (~2.5 days) deliver most of the perceived "native" win and carry
almost none of the risk.

---

## 7. Risks, ranked

1. **Local media playback inside WKWebView (E1).** If neither loopback HTTP nor a scheme handler plays
   media, the fallback is to hand offline playback to **AVPlayer natively** (a small SwiftUI player
   driven by the same manifest, outside the web UI) — a real but larger piece of work, and the reason
   E1 comes before any design is frozen.
2. **Background downloads vs iOS lifecycle.** `URLSession` background sessions are the right tool, but
   force-quit stops them and the completion path needs an app delegate that this SwiftUI app does not
   currently have. Well-trodden, still worth the spike.
3. **Storage arithmetic.** Multi-GB files on a phone: caps, eviction, and a UI that never silently
   deletes something he chose to keep.
4. **Auth drift for native fetches.** Cookie mirroring is simple but expires; a 401 mid-download must
   be loud. Resolved properly by the Phase-2 bearer work.
5. **Server CPU/disk for packaging.** Remux is cheap (I/O bound); video transcode is not. Per-title
   mode selection plus a staging TTL keeps it bounded — and E5 measures it before it is promised.
6. **Contract drift.** Every new route needs `openapi.v1.json` + a route-protection decision, or the
   suite fails — deliberately, so this is a checklist item rather than a surprise.

---

## 8. Recommendation

**Do A0 first — today, on its own.** One nginx block, no rebuild, and it takes the launch payload
from **1.13 MB re-downloaded every launch** to **~340 kB downloaded once** (§2.4: a 3.3× compression
win plus the caching win). It is also the prerequisite for any offline shell at all, and it is
measurable from the log he already has.

Then **A1 → A2 → A3** (a persistent cache, one home call, and a budget gate) — that is the whole
"feels like a native app" ask, on the frontend, with no native code and no device round trips.

Then **B0 (the E1/E2 spike)** — one Mac round that decides whether offline video is a
three-day job or a different design entirely. Nothing in Workstream B should be written before it.

⚠ Explicitly **not** planned here: a service worker (until E2 says whether WKWebView will even give us
one), bundling the web app inside the app (it would break the "live UI, no rebuild" property that makes
`apply` enough for a frontend change — `apple/README.md`), and any third-party download or web-server
dependency in the shell.
