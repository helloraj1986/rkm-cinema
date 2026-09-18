# Cold-Launch Offline Shell — Implementation Plan

> **Status:** ⚠ **RE-SCOPED, and its core BUILT, 2026-09-19** — phases **A**, **B** and **E** were
> replaced by **ADR-0012** on branch `feat/offline-cold-launch` (a launch ladder in the shell, **not** a
> scheme handler + a synced `ShellCache/`), and **C**, **D's first tier** and **§5a were already built
> before this plan was written** — re-read **§0a** before building anything from this file. Implements
> design-improvement **#9** from `ARCHITECTURE.md` §18 ("An offline SHELL for cold launch"), previously
> "only if he wants cold-launch offline."
> Last written: 2026-09-19, against `ARCHITECTURE.md` verified 2026-09-18.

## 0. The problem, precisely

Two different things currently get conflated under "offline doesn't work":

| Already works today (§17.4) | Does NOT work today (§17.6, §18 #9) |
|---|---|
| A **downloaded title plays** with no network — native filesystem + loopback `NWListener` server + real `Range` support | **Cold launch with no network paints nothing** — there is no service worker, no bundled UI, and the WKWebView has nowhere to load from if nginx is unreachable |
| The offline video path never calls `/api/jellyfin/playback-info` | **Posters/library UI** depend on the live SPA + live `/api/*` responses, which need nginx reachable |

So "just like Plex" has two separable pieces:
1. **The shell** (React app itself — HTML/JS/CSS) must be able to paint with zero network.
2. **The data** it paints (library list, posters, "already downloaded" state) must come from a local cache, not a live fetch.

Neither touches Seam 1 (`page → api`) or Seam 2 (`page ↔ native` bridge) contracts. This is entirely about **what the app does *before* those seams are reachable.**

---

## 0a. ⚠ Re-read against the repo before building — do NOT rebuild any of this

The plan was re-read on 2026-09-19, the day its phase started. **Two of its four phases and the whole of
its "separate track" were already done**, and the scheme handler it proposed had already been measured out
for the kind of load it was meant for:

| This plan asked for | State found in the repo |
|---|---|
| **Phase C** — a persisted query cache, so a cold launch has rows to paint | ✅ **BUILT 2026-09-14** as A1: `frontend/src/lib/query/persist.ts` (localStorage, profile-gated, 24 h max age, 1.5 MB cap, never throws), wired in `main.tsx`, ~30 vitest cases + `tools/check_query_cache.py` |
| **Phase D, first tier** — posters visible with no network | ✅ **Already the artwork policy**: `max-age=604800, stale-while-revalidate=604800` with an ETag (nginx's nested artwork location + the api's own `ARTWORK_POLICY`), so a poster wall browsed within the week paints from the device |
| **Phase A** — a `WKURLSchemeHandler` serving the document and its assets | ⚠ **Not built, and not needed as written** — see §0b. A0 made the shell *storable*; the WebView's own HTTP cache is the cache this phase proposed to build by hand |
| **Phase B** — diff-and-sync on every successful live load | ⚠ **Not built, and obsoleted**: content-hashed `immutable` assets plus a revalidating document **is** sync-on-load. A second cache would store the same bytes under a second staleness rule |
| **§5a** — audit whether compatible MKV is being transcoded | ✅ **Done, and it was worse than this plan guessed** — the live B1 gate found ordinary MP4s arriving as `"mov,mp4,m4a,3gp,3g2,mj2"` and **13 of 13** of them being fully re-copied. Fixed 2026-09-16; `choose_mode()` now matches the container by FAMILY (ADR-0007 D3) |
| **§5b** — pipeline packaging + transfer | ⚠ **NOT built, and deliberately not built here.** It breaks ADR-0008 D4's atomic-publish invariant (the artefact becomes servable while `ffmpeg` is still writing it), so it needs its own decision *and* the measurement this plan asks for. ⚠ No packaging-vs-transfer split has ever been recorded, so "measure first" is still step one |

## 0b. Why the DOCUMENT does not need a scheme handler

E1 (B0 spike, 2026-09-16) measured `WKURLSchemeHandler` out **for media** — `mediaError=code=4` *with* the
bytes served. A document is a different risk profile, which was this plan's own caveat — but the question
turned out not to need answering, because the premise underneath it was out of date:

* `nginx/default.conf` serves `/` with `Cache-Control: no-cache` — revalidated on every load, but **stored**.
  It used to be `no-store`, which forbids keeping the document at all, and *that* is what made an offline
  launch impossible by construction.
* `/assets/*` is `immutable` for a year, keyed by Vite's content hash.

Those are exactly the two properties a hand-built shell cache would have to reproduce. So what was missing
was never the cache — it was that **nothing ever asked for it**: the app asked the network, was refused, and
went straight to *"Can't reach this server"*. ADR-0012 is that question, asked in the right order.

---

## 1. Decisions to make first (write these as an ADR before coding)

Per your own convention (§20): a load-bearing, expensive-to-reverse choice gets an ADR. This one qualifies — it changes the "one live SPA, no bundled UI, every deploy reaches the phone instantly" invariant in §17.1.

| Decision | Options | Recommendation |
|---|---|---|
| **When does the app load local vs. live?** | (a) Always try live first, fall back to local on failure. (b) Always load local shell, let the page's own `TanStack Query` layer fetch live data over it. | **(a)** — simplest, matches "the app can be older than the page" tolerance already built into the bridge (ADR-0009 D6). Local is a fallback, not the default. |
| **What decides "unreachable"?** | A short-timeout `GET /api/health` probe before deciding which URL to load. | Native-side, in Swift (`Server/` or `App/AppDelegate.swift`) — the page cannot know the network is down before it tries and hangs. |
| **How stale can the local shell get?** | Bundle at build time (ships with the binary, goes stale between App Store releases) vs. sync-on-every-successful-live-load (always as fresh as the last time you had network). | **Sync-on-successful-live-load.** A store-shipped bundle would drift for months between releases and reintroduces the exact "app older than page" problem the bridge already has to tolerate — except now for the WHOLE UI, not just the bridge contract. |
| **Where do cached assets live?** | Same `Application Support/Offline/` used for downloads, or a sibling directory. | **Sibling directory** (e.g. `Application Support/ShellCache/`) — keeps "offline video" and "offline shell" as separate concerns with separate eviction rules; a full downloads wipe shouldn't force a re-download of the UI shell. |
| **Poster storage** | Cache posters as part of the shell-cache sync, or only for downloaded/browsed titles. | **Both, tiered**: sync a small poster set (recently added + watchlist) with every successful shell sync; save full-res posters permanently alongside any title that's actually downloaded (already the natural time to spend the bytes). |

---

## 2. Phased plan

### Phase A — ⚠ SUPERSEDED by ADR-0012: the launch ladder loads the cached document without a scheme handler

**Goal:** cold launch with no network paints *something* instead of a blank WebView / spinner-forever.

- [ ] Add a fast, short-timeout probe of `GET /api/health` on launch (reuse whatever HTTP client `Server/` already has for address validation).
- [ ] Register a `WKURLSchemeHandler` (e.g. custom scheme `rkm-local://` or intercepting the app's own recorded origin) that serves a synced copy of the built SPA (`index.html`, hashed JS/CSS from `frontend/assets/*`) from `Application Support/ShellCache/`.
  - ⚠ Re-read §17.6 before touching scheme handlers: custom schemes were **measured out for media** (B0/E1, `mediaError=code=4`). A *document/JS/CSS* load is a different risk profile than streaming a video byte-range, but confirm this holds before assuming it's safe — don't just take the doc's word for it, re-run whatever check ruled media out and see if it says anything about document loads.
- [ ] On launch: probe → reachable ⇒ load the live URL as today; unreachable ⇒ load the local scheme URL.
- [ ] Falsification test (per house rule #5): kill network mid-session, force-quit, relaunch — confirm the shell paints. Then restore network and confirm it goes back to loading live (no permanent stickiness to local mode).

**Files likely touched:** `apple/ios/RKMCinema/Server/*`, `apple/ios/RKMCinema/App/AppDelegate.swift`, a new `apple/ios/RKMCinema/Offline/ShellCache.swift`.

### Phase B — ⚠ NOT BUILT, and obsoleted: hashed `immutable` assets + a revalidating document IS sync-on-load

**Goal:** the local shell copy never gets meaningfully stale, and stays additive to the existing "app can be older than the page" tolerance.

- [ ] After each successful live page load (`didFinish` navigation delegate callback), diff the served asset manifest (Vite's build already content-hashes `frontend/assets/*` — §2 nginx table) against what's cached locally.
- [ ] Download only changed/new hashed assets; write atomically (temp file + rename, same pattern as `.part` files in the downloader per ADR-0008) so a killed sync never leaves a half-written shell.
- [ ] Cap total shell-cache size and evict oldest-unused assets past the cap — this is UI code, not media, so the cap can be small (tens of MB, not GB).

**Files likely touched:** `apple/ios/RKMCinema/Offline/ShellCache.swift` (extends Phase A), possibly a tiny additive endpoint or reuse of the existing `/assets/*` immutable-cache headers (§2) to make diffing cheap.

### Phase C — ✅ ALREADY BUILT 2026-09-14 as A1 — see §0a. Nothing to do here.

**Goal:** once the shell paints, it has *something* to show — not just chrome around empty lists.

- [ ] Confirm what the frontend's `TanStack Query` persister currently targets (per §19 it's already in use for cache/invalidation — check if it's persisted to `localStorage`/IndexedDB or memory-only).
- [ ] If memory-only: add a persister (TanStack Query ships one) so library lists, titles, metadata, and "what's downloaded" state survive a cold, offline launch.
- [ ] Make sure the persisted cache degrades the same way the bridge does: **no cache → no shell data**, never a crash or an infinite spinner. Same discipline as `bridgeAvailable()` (§17.1).
- [ ] Falsification: cold launch fully offline on a device that has *never* synced anything — confirm graceful empty state, not a crash.

**Files likely touched:** `frontend/src/lib/api/client.ts` or a new `frontend/src/lib/queryPersist.ts`, wherever `QueryClientProvider` is set up in `frontend/src/app/`.

### Phase D — ⚠ Tier 1 already ships (artwork policy, §0a). Tier 2 — posters and subtitles captured INTO a downloaded title's bundle — is still open: `ADR-0010` limit 1.

**Goal:** the "Plex-like" browsing experience — posters visible with zero network.

- [ ] Tiered as decided in §1: recently-added + watchlist posters synced alongside Phase B's shell sync; full-res posters for any downloaded title saved permanently at download time (extend `Offline/OfflineDownloads.swift`'s existing package step to also pull the poster it already knows the URL for).
- [ ] Serve cached posters through the **same loopback server** already used for offline video (`Offline/OfflineServer.swift`) rather than inventing a second local-serving path — keeps "how does the app serve local bytes to the page" as ONE mechanism, in the spirit of your "one way to do a thing" rule (§19).
- [ ] Page-side: the poster `<img src>` should already be relative to the API origin — when running against the local scheme, this needs to resolve to the loopback poster server instead. Small, explicit switch in `frontend/src/features/library` (or wherever poster URLs are built), not a global rewrite.

**Files likely touched:** `Offline/OfflineDownloads.swift`, `Offline/OfflineServer.swift`, `frontend/src/features/library/*` (poster URL construction).

### Phase E — ✅ DONE as `adr/ADR-0012-cold-launch-offline-shell.md` — and read it, because the decisions taken differ from §1 (no scheme handler, no shell cache, no sync)

- [ ] `docs/adr/ADR-00XX-cold-launch-offline-shell.md` — capture the five decisions in §1 above, the reachability-first rule, and explicitly note this is **additive to §17.1's "one live SPA" model**, not a replacement of it (there is still exactly one UI; this just lets a synced copy of it stand in when the original is unreachable).
- [ ] Update `ARCHITECTURE.md` §18 item #9's status from "not started" to point at the new ADR, per your own documentation convention (§21.2 — mark what supersedes what).

---

## 3. What this plan deliberately does NOT change

- Seam 1 and Seam 2 contracts — untouched.
- The identity/session model (§11) — the local shell still defers to the live api for anything requiring auth; it doesn't invent an offline identity.
- "One implementation of every business rule" — poster/shell caching is pure infrastructure (what bytes are available where), not a new business rule about what's *offered*, which stays owned by `frontend/` per §2's ownership table.

## 4. Suggested order

**A → C → B → D → E.** Reachability-gated load with a hand-bundled or one-shot-synced shell (skip the diffing sophistication of Phase B at first) gets you a working demo fastest, and proves out the riskiest unknown (whether the scheme-handler approach is actually safe for documents, not just ruled out for media) before you invest in the sync machinery. Do the transcode-mode audit in §5 first — it's unrelated to this plan and cheaper to fix first.

> ⚠ **What actually happened (2026-09-19):** A, B and C were moot before the order could matter — C was already built (A1), A and B were replaced by ADR-0012, and §5a was already fixed. The only thing this order got right was the *instinct*: build the cheap part first and prove the risky unknown before investing in machinery. See §0a/§0b.

---

## 5. Separate track: fast download & play

Independent of the offline-shell work above — this is about making an individual download/playback fast, not about working with no network. Two distinct levers.

### 5a. Fast play — skip transcode when you can (cheapest fix, do this first) — ✅ ALREADY DONE, see §0a

Per §17.4, packaging is always `remux OR transcode` via `ffmpeg` — never a raw copy, because most of the library is `.mkv` and AVFoundation (what plays the `<video>` tag under WKWebView) can't demux MKV at all, compatible codecs or not.

- **Remux is basically free**: `ffmpeg -c copy` (stream copy, no decode/encode) just repackages existing H.264/AAC streams into `.mp4`. I/O-bound, should take seconds to low-minutes even for a feature-length file.
- **Transcode is expensive**: a real re-encode, CPU-bound, can take as long as the film's runtime or longer depending on hardware.

- [ ] Audit what `plan()` in `offline.py` / ADR-0007 actually checks before choosing `mode`. If it's transcoding files that are already H.264+AAC just because the container is MKV, that's a bug — those should remux.
- [ ] If transcode is correctly reserved for genuinely incompatible codecs (DTS/TrueHD audio, unsupported HEVC profiles/bit-depth on older devices), attack it with hardware-accelerated `ffmpeg` (Quick Sync/NVENC on the Windows host) instead of software x264 — can cut transcode time 5–10x.

### 5b. Fast download — pipeline packaging and transfer instead of doing them sequentially

§17.4 already names the rough edge: *"the packaging phase is why a row can sit at zero bytes for minutes: the number is honest ('nothing has arrived')."*

Today's flow is sequential: **finish packaging → then start transfer.** Wall-clock = packaging time + transfer time.

- [ ] Have the api start serving `Range` bytes off the output file **while `ffmpeg` is still writing it** (tail-following a growing file — `ffmpeg -movflags +faststart+frag_keyframe` or similar so the MP4 is valid to serve incrementally).
- [ ] The background `URLSession` can then start pulling bytes as soon as the first chunk exists. Wall-clock becomes **max(packaging time, transfer time)** instead of the sum.
- [ ] Needs care: track how much ffmpeg has actually flushed vs. what's been requested, so the api never serves past what's been written yet (extends the existing `.part`-file discipline in ADR-0008 to the *server* side, not just the device side).
- [ ] Bigger change than 5a — touches `offline.py`'s serving logic — but fixes the exact UX edge the doc already calls out, not just a performance nice-to-have.

### 5c. Smaller wins, in order of effort

| Lever | Effort | When it helps |
|---|---|---|
| Fix remux-vs-transcode selection (5a) | Small — one function's logic | Every download where source is already compatible-codec MKV |
| Hardware-accelerated `ffmpeg` for real transcodes | Small–medium — flag + host needs HW encoder | Only the genuinely-incompatible subset |
| Pipeline packaging + transfer (5b) | Medium — touches `offline.py` serving + verify logic in ADR-0008 | Every download; biggest single win for perceived speed |
| Speculative pre-packaging (package on watchlist-add, not on download-tap) | Medium, plus disk/CPU cost for titles never downloaded | Only if downloads are predictable (e.g. always the newest episode) |
| Parallel-range chunked transfer | Small, but only matters if network is the bottleneck | Only if a single TCP stream isn't saturating the Tailscale link — measure before building |

**Recommended order:** fix 5a first (cheap, likely resolves most "why is this transcoding" cases outright), then **measure** how much of total download time is packaging vs. transfer on a real download before investing in 5b — if remux is already fast relative to transfer time, pipelining buys less than it costs to build.
