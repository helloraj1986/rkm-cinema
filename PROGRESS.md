# RKM Watchlist — Session Handoff & Project Progress

> Last updated: 2026-09-06 (**Plex-style UI revamp Phases 1–3 DONE — `4831da9`+`f2dc060` — deployed & USER-CONFIRMED on RKM-HP. NEXT (parked for future): Plex-style views & navigation — plan `docs/PLEX_VIEWS_PLAN.md` (dedicated item pages + Movies/TV Shows sidebar folders); roadmap items 4–5 + legacy parity still open.) HLS player COMPLETE — USER-CONFIRMED FIXED on RKM-HP: "YES THE PROGRESS BAR BUG IS FIXED NOW". Plex-style HLS/MSE player live: same-origin HLS proxy + hls.js engine; seek = server-fetched segment, no-op structurally impossible. **Subtitles FIXED follow-up** (`82cb5f7`): VTT URL shape 404'd on Jellyfin 10.11 → live-verified `…/Subtitles/{n}/0/Stream.vtt` + cold-start timeout 12→45 s; end-to-end UI-verified (real dialogue overlay). **Subtitle index-0 fix** (`16c104e`): Off no longer collides with track 0. Redeploy `.\\bootstrap.ps1` to go live. **re-platform Phases 0,1a,2,3a,3b,item-2,4 DONE + `thumb` bug FIXED + **roadmap item 3 (player features) DONE** — backend 259 pytest + ruff; `web/` tsc+build+vitest 21/21; React shell validated live against real Jellyfin data.** `/api` frozen → **30 paths** (additive: playback-info, subtitle, backdrop; stream accepts audio_stream_index/max_bitrate); ABC capability surface; React shell + typed client; library+playback slices ported; item-2 watch-state; **item-3 player controls** (speed/audio/subtitle/quality pickers + autoplay-next + backdrop proxy); **Phase 4 cutover**: `web/` multi-stage Docker build serves React as the origin at :8124, legacy recoverable at /legacy/. **Jellyfin `thumb` leak fixed + regression test**. **All commits pushed to GitHub** (`experiment/bundled-docker-stack`); CI workflow left out of scope per user — workflow file untracked/git-ignored, pushes unaffected. **Audio-transcode follow-up**: player auto-transcodes browser-unsafe audio (EAC3/AC3/DTS/TrueHD → AAC, video copied) via new `transcode_audio` stream param; audio `codec` surfaced in playback-info; committed `1bc9940` + pushed. **Player seek-bar fix**: native `<video controls>` broke when direct-play reported `duration=Infinity` (no total shown, bar wrong seconds in) — replaced with custom controls whose total = API runtime (Jellyfin scan metadata) until the stream duration resolves; movie/episode/Up-Next all seed it; committed `d950c8a` + pushed. **Tier-1 honest routing**: `playback_info` now carries container + video codec facts; `/api/jellyfin/stream` takes `mode=direct|remux|transcode_audio|transcode` + `start_time_ticks` — Quality/Audio pickers are REAL now (Static=true ignores those params, verified live); player routes direct → remux (MKV) → transcode_audio (EAC3 etc.) → transcode (HEVC/10-bit/bitrate), restart-seeks non-direct streams at the exact position, escalates on media errors, shows a Direct play/Remux/Transcode chip; committed `208fc3d` + pushed. **Player bug-fix pass**: progress-bar scrubbing now previews during drag and commits ONE seek on release (was: every input event restarted remux/transcode streams) and respects pause state; subtitles no longer rely on native `<track>` (browser ignored dynamic swaps) — fetched VTT is parsed to item-time cues and rendered as an overlay aligned to the offset model, so subs survive restart-seeks; committed `ffb7905` + pushed. **Seek-bar root fix**: "bar moves but playback doesn't" traced to the native `<input type=range>` itself (verified headless: mouse events never reached it; a *controlled* range keeps the thumb at the click point when state doesn't change → permanent desync). Replaced with a custom div seek bar with pointer capture — preview on drag, ONE commit on release, fill driven by state so UI can't desync; committed `f74ceba` + pushed. **User re-deployed and CONFIRMED the seek bug still reproduces on every 3 Body Problem episode → architecture decision: replace progressive restart-seek with a Plex-style HLS/MSE player (hls.js) — full plan in `docs/HLS_PLAYER_PLAN.md`; NEXT: execute Phase 0 (episode facts + live Jellyfin HLS probe) → Phase 1 HLS proxy → Phase 2 hls.js engine.**)
> Live URL: **http://rkm-hp.tail8d5e8.ts.net:8123/** (Tailscale MagicDNS, tailnet-only — NEVER `tailscale funnel` it; page proxies /api → FastAPI which holds secrets server-side)
> Deploy path (Windows, RKM-HP): `cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema; .\run-rkm-cinema.ps1` (prod api+web nginx `:8123`; Plex/Emby backend) — or `.\bootstrap.ps1` for the **bundled api+web+Jellyfin** stack (`:8098`/`:8124`; this is where in-app Jellyfin playback lives). NOTE: there is **no `setup-watchlist.ps1` anymore — it was renamed.** The sandbox's `/workspace` maps to `D:\hermes_agent\hermes-workspace` (9p mount, confirmed via mountinfo 2026-08-18; NOT `D:\media`). The `web`+`api` containers are on RKM-HP (Docker daemon unreachable from sandbox).
> Repo: **private `rkm-cinema` on GitHub** (github.com/helloraj1986/rkm-cinema)
> **Status:** ✅ **Phases 1–18 committed. SQLite is now the AUTHORITATIVE watchlist store** (`WATCHLIST_STORE=sqlite`, DB on the shared `/workspace/media` volume so it survives every rebuild). `watchlist.json` is now a generated mirror/export, NOT authoritative. **DEPLOY PENDING on RKM-HP** to bake the 504/suggest API fixes + the SQLite store into the running image (`setup-watchlist.ps1`). Frontend-only (app.js synopsis fix) is already live via the volume mount.

## ▶ LATEST SESSION (2026-09-06) — user confirmed on RKM-HP + Plex-style views direction PARKED ✅ (plan: `docs/PLEX_VIEWS_PLAN.md`)
**User deployed `.\bootstrap.ps1`, confirmed the preplay overlay works ("yes it works"), then asked for the Plex navigation model as a future change.** Feedback: a title should open in **its own dedicated view/page** (URL-backed, Back works, deep-linkable) rather than an overlay, and the **left sidebar should browse Movies / TV Shows folders** like Plex. That is now a full plan, **PARKED for a future session** (`docs/PLEX_VIEWS_PLAN.md`): Phases 0–3 — `/library/home|movies|shows` + `/library/item/:id` routes, sidebar library group, `ItemDetail` overlay → routed `ItemDetailPage` (Back/Esc/scroll-top/player-on-top), card click navigates; expected to need **no backend/contract change** (client-side `isSeries` filter of the cached items) and **no new npm deps**. Everything else on the roadmap is parked/unchanged (list in the block above). No code shipped this session — this is the plan + tracking record only (commit below).

## ▶ LATEST SESSION (2026-09-06) — Plex-style UI revamp Phases 1–3 DONE ✅ (backend + frontend, headless-accepted; plan: `docs/PLEX_UI_PLAN.md`)
**Click any card → a Plex-style preplay overlay** (backdrop hero, poster, synopsis, ★ rating, genres, studio, cast headshots, big Resume/Play). One additive endpoint + a detail component + a card revamp; no new npm deps.
- **Phase 1 backend (`4831da9`):** `JellyfinLibraryProvider.item_detail(id)` normalises the single-item fetch (`/Users/{uid}/Items/{id}?Fields=Overview,Genres,People,CommunityRating,…` — live-verified 10.11.11) into `{type,name,year,runtime,overview,genres,community_rating,official_rating,studios,people{actors|directors|writers(id/name/role/has_image)},has_backdrop,primary_aspect,play{played,resume_ticks,resume,play_count}}`; Episode items carry series context. Additive `GET /api/jellyfin/detail?id=` (via `LibraryService.item_detail` aggregate; 404 soft-miss, 503 unconfigured) + `GET /api/jellyfin/person?id=` headshot proxy — person images sit at the same `/Items/{id}/Images/Primary` shape (HTTP 200 image/jpeg verified for imaged people; 404 for headshot-less → UI uses initials, and `has_image` skips doomed requests). Contract 32 → **34 paths**; `types.ts` regen. Probe harness `scripts/probe_jellyfin_detail.py` (redacted). **285 pytest** (+11) · ruff clean · vitest 40/40.
- **Phase 2/3 frontend (`f2dc060`):** whole-card click → **`ItemDetail.tsx`** preplay overlay (fetched ONLY on open, cached per item, 5 min staleTime); **`MediaCard` revamp** — hover ▶ (movie plays / series opens episodes), watched toggle + Jellyfin link on hover, ✓ badge + amber resume bar kept, metadata-clean footer; series detail auto-continues via **`nextPlayableEpisode`** (in-progress → first unwatched) and renders season-grouped episode rows with per-episode resume % + Play/Resume/Replay; **`EpisodePicker.tsx` deleted** (superseded — the detail owns episodes now). Pure helpers unit-tested (`fmtRuntime`/`ratingText`/detail-resume labels/person URL/continue-episode). **vitest 52/52** (+12) · tsc clean · `VITE_ENABLE_REACT=1` build ok.
- **Headless acceptance PASS** (built dist served like nginx → real bundled Jellyfin): movie detail Resume **(51%)** + ★7.3/10 + AU-M + synopsis + cast roles + initials fallback (those actors have no headshot in this library); series detail ★7.5/10 AU-MA 15+ Netflix + **Resume S1E1** + all **8 real episodes** w/ per-episode resume (16/62/43/44/12/6%) + 8 person-proxy headshots; Esc + ✕ close; **0 console errors**.
- ⚠ **Backend + frontend change → `.\\bootstrap.ps1` deploy on RKM-HP** (sandbox has no Docker daemon); then click cards → detail and eyeball it (DEPLOY PENDING block above has the check list).
- Deferred (kept light per plan): preplay footer media-facts line (needs a playback-info fetch per open; low value vs weight), trailers/more-like-this (server-side TMDB cost).

## ▶ LATEST SESSION (2026-09-06) — Phase 4: cutover — React served as origin, legacy recoverable at /legacy/ ✅ + live UI test

**Your one command now serves the React shell.** `bootstrap.ps1` unchanged — `docker compose up -d --build` builds the new multi-stage `web` image.

- **`web/Dockerfile`** — node:20-alpine build stage (`VITE_ENABLE_REACT=1`) → nginx serving `web/dist`; **no Node needed on the host**.
- **`nginx/default.conf`** — React SPA at `/` (try_files → `index.html`); `/api` proxy unchanged; repo root mounted at `/legacy-source` served under **`/legacy/`** so the old app + live `dashboard-data.json` stay reachable (discover/watchlist/search/suggest are there until ported).
- **`docker-compose.yml`** — `web` builds from `web/Dockerfile` (`rkm-bundled-web`), mounts `./:/legacy-source:ro`. `bootstrap.ps1`'s `up -d --build` picks it up automatically.
- **`.dockerignore`** — keeps `node_modules`/`web/dist`/pycache out of the build context.
- **Sidebar** — added a **Legacy app (/legacy)** link so the old UI is one click away.
- **Live UI validation (sandbox):** started the FastAPI backend against the **bundled Jellyfin** (freshly-authenticated admin token), served the **built `web/dist`** exactly as nginx would (static + `/api` proxy), and rendered it in headless Chromium: **Full Library + Continue Watching render, 5 cards, 5 posters, real titles/percentages/play-counts, `/legacy` link, 0 console errors.** Provably the same artifact the container serves.
- **⚠ Docker/nginx runtime not executed here** (daemon unreachable in sandbox) — the container config is authored; it was verified by the equivalent static+proxy server instead. Deploy step on RKM-HP: `.\bootstrap.ps1` (or `docker compose -p rkm-bundled up -d --build web`).

**To run it (RKM-HP):**
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\bootstrap.ps1
# React UI:  http://localhost:8124  |  Legacy:  http://localhost:8124/legacy/
```
Legacy `app.js`/`index.html` are **kept** (not retired) — full retirement waits for discover/watchlist/search/suggest parity (Phase 3 remainder).

### Known open
- ~~Thumb leak~~ ✅ FIXED (commit below) — no open thumb issue.
- ~~Seek-bar bug (UI moves, playback doesn't)~~ ✅ **FIXED + USER-CONFIRMED on RKM-HP** — the Plex-style HLS/MSE player (below) resolved it.
- ~~Subtitles: selectable but not applying~~ ✅ **FIXED** (commit `82cb5f7`) — VTT URL shape 404'd on Jellyfin 10.11 (`…/Subtitles/{n}/0/Stream.vtt` is the live-verified form) + cold-start timeout 12→45 s. **Redeploy `.\\bootstrap.ps1` to go live.**
- ~~Subtitle track at index 0 unselectable (50 First Dates external SUBRIP)~~ ✅ **FIXED** (commit `16c104e`) — Subs "Off" was value 0, colliding with track 0; Off is now `""`. Note: (500) Days genuinely has 0 subtitle streams in the file.
- ▶ **NEXT (approved): Plex-style UI revamp — DONE Phases 1–3 (commits `4831da9` + `f2dc060`), headless-accepted.** ⚠ **Deploy `.\\bootstrap.ps1` on RKM-HP**, then click a card → detail overlay and confirm metadata/Play/Resume/episodes feel right (see the LATEST SESSION record below; backend + frontend both changed → rebuild required). Parked: Bazarr subtitles-for-missing-subs (user: "lets park it for later").

## ▶ DONE + USER-CONFIRMED on RKM-HP — Plex-style UI revamp (backend `4831da9` + frontend `f2dc060`)
User deployed `.\bootstrap.ps1` and confirmed the preplay overlay works ("yes it works"), then gave direction for later: **wants Plex-style navigation — each title opening in its own dedicated view/page (not an overlay) + Movies / TV Shows folders in the left sidebar.** That direction is captured in a plan and **PARKED for a future session**: `docs/PLEX_VIEWS_PLAN.md` (Phases 0–3; expected to need no backend/contract change and no new npm deps).
- ▶ **Parked (future): Plex-style views & navigation** — dedicated item pages + sidebar Movies/TV Shows folders. Plan: `docs/PLEX_VIEWS_PLAN.md`.
- ▶ **Parked (future): Bazarr auto-subtitles** for files with no subs (needs OpenSubtitles account; user deferred).
- ▶ **Open roadmap (unchanged):** item 4 — library & discovery (in-library search, filters/sort, "Because you watched"); item 5 — transcode/playback robustness; React-parity ports for discover/watchlist/search/suggest (still `/legacy/`).

## ▶ LATEST SESSION (2026-09-06) — subtitle index-0 fix + user Q&A (audio transient; movie subs explained) ✅
**Follow-up after user confirmation.** (1) Audio on 3BP episodes: sandbox measured real audio energy on the `Transcode (audio)` HLS stream (RMS 617–1596, muted=false, vol=1) and the user re-tested: **sound works in Original quality too** — the earlier silence was a transient cold-start glitch, not a routing bug. (2) Movie subtitles: **(500) Days of Summer has ZERO subtitle tracks in the file** (`subs=[]` live) — nothing to select; external `.srt` beside the media would appear. **50 First Dates subtitle is index 0** (`Undefined - SUBRIP - External`) and the player's Subs dropdown used 0 as "Off" → the track was unselectable. Fixed: Off is now an empty-string option, track 0 selectable (committed `16c104e`); verified live (dialogue cues render).
- vitest 40/40 · tsc clean · build ok (frontend-only change).
## ▶ LATEST SESSION (2026-09-06) — subtitles FIXED: VTT URL shape + cold-start timeout ✅ (user-confirmed seek fix, follow-up)
**User reported subtitles still broken after the HLS deploy ("can select the subtitle but it's not being applied"). Root-caused live: the subtitle proxy fetched `/Videos/{id}/{src}/Subtitles/{index}/Stream?format=vtt` — which 404s on Jellyfin 10.11.11. The live-verified working shape is `/Videos/{id}/{src}/Subtitles/{index}/0/Stream.vtt` (extra `/0/` path segment; format as file extension).** Also raised the upstream timeout 12 s → 45 s (Jellyfin converts embedded tracks to VTT on first request — cold conversions took >12 s and 502'd; warm ≈0.05 s).

- **Verified end-to-end in the real UI** (headless Chromium → bundled Jellyfin): select Subtitle 3 (English SDH) → HTTP 200 → overlay renders real dialogue cues at the right timeline position ("Einstein went to the American Imperialists and helped them build the atomic bomb!"). Regression test pins the new URL shape.
- **274 pytest** · ruff clean · vitest 40/40 · tsc clean (frontend untouched).
- Committed `82cb5f7`; pushed to GitHub (below, after commit).
- ⚠ **Backend change → redeploy needed**: `.\\bootstrap.ps1` on RKM-HP, then pick a subtitle mid-play and confirm text overlays appear.

## ▶ LATEST SESSION (2026-09-06) — HLS player: **USER-CONFIRMED FIXED on RKM-HP** ✅ plan COMPLETE (plan: `docs/HLS_PLAYER_PLAN.md`)
**User deployed `.\\bootstrap.ps1` on RKM-HP and confirmed: "YES THE PROGRESS BAR BUG IS FIXED NOW".** The Plex-style HLS/MSE player (Phases 0–3, commits `0b330aa`→`714aaf7`) is fully live: every non-direct title now plays through same-origin HLS (hls.js on Chrome/Edge/Firefox, native on Apple mobile); seeking asks the server for the segment at the clicked time, so the silent no-op that plagued progressive restart-seek is structurally gone. No open player issues.

## ▶ NEXT SESSION — (open) HLS player: none — complete. Optional follow-ups: ABR ladder (out of scope v1), Safari/iOS native-HLS device check, revisit roadmap items 4/5.

## ▶ LATEST SESSION (2026-09-06) — HLS player Phase 2: hls.js engine in Player + Phase 3 headless acceptance PASS ✅ + latent mark-unwatched fix (plan: `docs/HLS_PLAYER_PLAN.md`)
**The Plex-style player is built and the original bug is structurally gone.** `npm i hls.js`; Player branches direct (unchanged native path) vs **HLS (hls.js on Chrome/Firefox/Edge; native on Apple mobile)**; the offset/restart-seek machinery (`baseRef`/`startAt`/`start_time_ticks`/transition-restart) is **deleted** — position = plain `video.currentTime`, seek = plain `currentTime` set, so hls.js asks the server for the segment at the clicked time (a silent no-op seek is impossible). Subs overlay aligns trivially. Audio-aware HLS ladder (`transcode_audio → transcode`); mode chip stays.

- **lib.ts** (+4 helpers, unit-tested): `usesHls`, `HLS_LADDER`, `nextHlsMode`, `hlsEngineFor`, `hlsModeLabel`; **client.ts** `hlsMasterUrl`.
- **Harness found two real bugs, both fixed:** (1) recent desktop Chromium advertises native HLS (`canPlayType` "maybe") but its TS demuxer fails on Jellyfin segments while hls.js transmuxes cleanly → `hlsEngineFor` now returns native ONLY on Apple-mobile UAs; (2) a leftover `v.removeAttribute("src")` after `hls.attachMedia` killed the MSE pipeline (no segments fetched) — removed.
- **Verification:** vitest **40/40** (+4) · tsc clean · vite build ok · pytest **274** + ruff clean (backend untouched this phase). **Headless acceptance on real bundled Jellyfin 10.11.11:** real 3BP episode via hls.js (mode=transcode_audio copy+aac — decodes, currentTime advances, sequential .ts fetches through the proxy); seek-bar click **10:05 → currentTime 605 (aria 605) PASS**, **30:00 → 1800 → continued 1804 PASS**, **40:00 → 2400 → continued 2404 PASS**. Harness-mutated library state restored afterwards.
- **Latent bug fixed live:** mark-unwatched POSTed `UnplayedItems/{id}` which 404s on Jellyfin 10.11 — now `DELETE PlayedItems/{id}` (both live-verified); regression test updated to pin the route.
- Committed `7ea25ff`; pushed to GitHub (below, after commit).

## ▶ NEXT SESSION — HLS player: user live check on RKM-HP (plan §8)
**Phases 0–2 DONE + headless Phase 3 acceptance PASSED.** Remaining: deploy + real-device check.
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\bootstrap.ps1
# or web image only after frontend-only changes:
docker compose -p rkm-bundled up -d --build web
```
Then on RKM-HP: play a 3 Body Problem episode and the 2 movies — click the seek bar mid-play and confirm the video genuinely jumps (the original bug). If anything smells stale, compare the bundle filename in the network tab vs `web/dist`.

## ▶ LATEST SESSION (2026-09-06) — HLS player Phase 1: backend same-origin HLS proxy ✅ live-verified (plan: `docs/HLS_PLAYER_PLAN.md`)
**Executed Phase 1 of the HLS/MSE plan. The progressive/restart-seek transport now has its replacement backend: a same-origin HLS proxy the browser hands to hls.js/native HLS. Seek-by-segment is now structurally possible — clicking a position asks the server for the segment at that time.**

- **`api/routes/jellyfin_hls.py`** (new, registered in `api/main.py`) — `GET /api/jellyfin/hls/{item_id}/master.m3u8` takes the stream-route vocabulary (`mode=remux|transcode_audio|transcode` + `audio_stream_index`/`max_bitrate`, legacy `transcode_audio=true`, `media_source_id` default = item id) and maps to the Jellyfin codec pair Phase 0 proved correct: remux→copy-copy, transcode_audio→**copy+aac** (EAC3 etc.), transcode→h264+aac. Default (no mode) = transcode; `direct` → 400 (not an HLS mode).
- **Playlist rewriting** — Jellyfin embeds `api_key` in EVERY URI line (master, media, segments; Phase-0 verified). The proxy strips it from every body and leaves URIs relative, so hls.js resolves them against the same-origin master URL and the passthrough route catches them. **No secret ever reaches the browser.**
- **Passthrough** `GET /api/jellyfin/hls/{item_id}/{rest}` — re-injects the server token server-side, drops any client-supplied `api_key` (defence in depth), forwards the query verbatim (MediaSourceId + codec params + `runtimeTicks`/segment ticks), streams `.ts` as `video/mp2t` with Range passthrough (206 verified).
- **Contract 30 → 32 paths** (additive) — snapshot + `types.ts` regenerated (141 lines added, frontend untouched).
- **Tests +10** — master URL mapping per mode (incl. legacy flag + default-transcode), api_key stripped from rewritten bodies, passthrough re-injection + client-key drop, segment Range 206 + MIME, media-playlist rewrite preserves runtimeTicks, 400 unknown/direct, 503 unconfigured. **274 pytest** · production ruff clean.
- **Live-verified end-to-end (sandbox uvicorn → real bundled Jellyfin 10.11.11):** `master.m3u8?mode=transcode_audio` → CODECS `avc1.4D4028,mp4a.40.2` (browser-safe) → media playlist (442-seg VOD) → first segment HTTP 200 `video/mp2t` 4,829,156 bytes (file(1): "MPEG transport stream") → Range request 206 + Content-Range. **Zero api_key leaks in any body** (grep-verified).
- **Frontend gates**: vitest 36/36 · `tsc` clean · `vite build` ok (types additive).
- Committed `2b0fdfc`; pushed to GitHub (below, after commit).

## ▶ NEXT SESSION — HLS player Phase 2: frontend hls.js engine (plan §5, §3b/§3c)
**Phases 0–1 DONE.** `npm i hls.js` in `web/`, then:
1. `lib.ts`: extend routing — `usesHls(mode)`, HLS capability detection (native Safari vs hls.js), master-URL builder (`/api/jellyfin/hls/{id}/master.m3u8?mode=…&audio_stream_index=…&max_bitrate=…`). Pure + unit-tested.
2. `Player.tsx`: branch playback engine on mode — direct → existing `<video>` (unchanged); hls → `new Hls({ startPosition: resume })`, attach video, `Hls.Events.ERROR` → escalate the **audio-aware ladder** (§3b/§3c: transcode_audio → transcode etc.), destroy on unmount/switch; Safari native (`video.src = masterUrl`).
3. **Delete** the offset/restart machinery (`baseRef`/`startAt`/`pendingSeekRef`, transition-restart, scrub-commit special-casing stays only for direct) — HLS position = plain `video.currentTime`; subs overlay trivially aligned; chip stays.
4. Phase 3 harness verify (click 10:05 → currentTime ≈ 605 s) + user live test on RKM-HP (deploy: `.\\bootstrap.ps1`).

## ▶ LATEST SESSION (2026-09-06) — HLS player Phase 0: live probes + durable harness ✅ (plan: `docs/HLS_PLAYER_PLAN.md`)
**Executed the plan's Phase 0 ("verify before building") against the real bundled Jellyfin (10.11.11) — one probe episode (3 Body Problem S1E4 'Our Lord', the actual reported title) + all HLS output shapes captured. No player code changed.**

- **Episode facts** — container **mkv** · video h264 Main 1080p 8-bit (~5.4 Mbps) · audio[1] **EAC3 5.1+Atmos** (768 kbps). So `pickStreamMode` sends every episode down the `transcode_audio` chunked-progressive path today — the exact path whose restart-seek is the bug. HLS must carry every 3BP episode (confirmed).
- **HLS shapes (all MIME `application/vnd.apple.mpegurl`)** — master is a 3-line single-variant playlist (`#EXT-X-STREAM-INF` + one **relative** `main.m3u8?…` URI; no ABR ladder even with `MaxStreamingBitrate`); media playlist is full VOD (442 × 6.006 s segments, `#EXT-X-ENDLIST`); segment URIs `hls1/main/N.ts?…` carry `api_key` + `MediaSourceId` + codec params + `runtimeTicks` + `actualSegmentLengthTicks` (relative too); segments are `video/mp2t` and **Range-capable upstream** (206). **`api_key` is embedded in EVERY playlist URI** → the Phase-1 proxy must strip it (server-side token only).
- **Critical routing discovery** — `VideoCodec=copy&AudioCodec=copy` (remux HLS) advertises `CODECS="avc1.4D4028,ec-3"` — **EAC3 survives copy HLS and Chrome MSE can't decode `ec-3`**. For EAC3/AC3/DTS/TrueHD titles HLS must start at **`copy+aac`** (advertises `mp4a.40.2`, browser-safe), not copy-copy; `h264+aac` is the full-transcode fallback. Plan §2/§4/§5 amended to an **audio-aware ladder**.
- **Resume is client-side** — `StartTimeTicks=600000000` master probe returns the same full VOD playlist (segments echo the param; no truncation) → hls.js `startPosition: resume` as planned.
- **Durable harness** — `scripts/probe_jellyfin_hls.py` committed (auth → playback-info → master/media/segment/StartTimeTicks probes; output fully redacted — verified 0 token leaks). Reusable for Phase 1 verification + future Jellyfin upgrades.
- Frontend/backend product code untouched; **no pytest/vitest change** (script is stdlib-only, not imported by tests).
- Committed `0b330aa`; pushed to GitHub (below, after commit).

## ▶ NEXT SESSION — HLS player Phase 1: backend same-origin HLS proxy (plan §4, §3b)
**Phase 0 DONE** (probes + durable harness above). Next: `api/routes/jellyfin_hls.py` — same token-server-side pattern as `jellyfin_stream.py`, **additive contract paths only**:
1. `GET /api/jellyfin/hls/{item_id}/master.m3u8` → fetch Jellyfin master, **strip every embedded `api_key`**, rewrite relative URIs (media playlist + segments) to `/api/jellyfin/hls/{item_id}/…` keeping `MediaSourceId` + codec params + `runtimeTicks`/`actualSegmentLengthTicks`; passthrough MIME (`application/vnd.apple.mpegurl`, `video/mp2t`) + Range.
2. Media-playlist + segment passthrough routes; query mirrors stream route (`mode=remux|transcode_audio|transcode`, `audio_stream_index`, `max_bitrate`) with the §3b codec-pair mapping.
3. Contract snapshot regen + `npm run generate:types`; full pytest + ruff gates (§7).
4. Phase 2 after that: hls.js engine in `Player.tsx` (delete offset/restart machinery; audio-aware HLS ladder; native HLS on Safari); Phase 3 harness verify.

Gates + deploy + out-of-scope: plan doc §7–9.

## ▶ NEXT SESSION — seek-bar ROOT fix follow-up (SUPERSEDED by the HLS plan above)
**Do NOT continue patching the progressive/restart-seek player.** After redeploying `f74ceba` the user confirmed the seek bug still affects every episode of 3 Body Problem (and movies). Root cause is the transport model — see the HLS plan (`docs/HLS_PLAYER_PLAN.md`), which replaces this effort.

## ▶ LATEST SESSION (2026-09-06) — seek-bar ROOT fix: custom div bar replaces the native range input ✅
**"The bar moves to where I click but the video keeps playing from the old position" — reproduced and root-caused in a headless Chromium harness against the live Jellyfin.** Two rounds of input-event fixes didn't cure it because the control itself was the problem:

- A native `<input type=range>` has a ~6 px hit area and its pointer events can be swallowed (recorded **zero** events reaching the input during real mouse drags while anything overlays the bottom strip).
- A *controlled* range input keeps its thumb visually wherever you clicked whenever React state doesn't change — so with a failed/silent seek the bar permanently shows the clicked point while playback continues from the old spot: exactly the reported symptom.

**Fix (`Player.tsx`):** custom `<div role="slider">` seek bar with pointer capture. Drag previews the fill/thumb; release commits exactly ONE seek (byte-range on direct, restart-at-`StartTimeTicks` on remux/transcode). Fill + thumb are rendered from player state only — the UI can never desync from real position again. Click target ~20 px + pointer capture (immune to overlays); arrows ±10 s, Home/End; click-vs-video-toggle isolated via stopPropagation.

**Verified in the harness:** real mouse drag on the bar previewed during the gesture and committed a single restart-seek at the released position (`start_time_ticks=34220000000` for a 60% click on a 5704 s title; `aria-valuenow` matched). The remaining headless limitation (this sandbox's Chrome can't decode the Jellyfin streams — demux error → error overlay) does not affect real browsers.
- **vitest 36/36** · `tsc` clean · `vite build` ok (frontend-only).
- Committed `f74ceba`; **pushed to GitHub** `experiment/bundled-docker-stack` (0 behind).

## ▶ LATEST SESSION (2026-09-06) — player bug-fix pass: one-commit scrubbing + subtitle overlay ✅
**Live-use bugs:** (1) clicking the seek bar on remux/transcode streams restarted the video — every `input` event during a drag fired a full stream RESTART at `StartTimeTicks` (how chunked streams seek), so a single gesture triggered many reloads; a paused seek also force-played. (2) Selecting a subtitle did nothing — dynamically swapping a native `<track>` after the media resource had loaded is unreliable in browsers, and native tracks align to the media element's *local* clock (wrong for restart-seek streams starting at an offset).

- **Scrub now commits once** — the slider previews while dragging (`scrub` state) and fires exactly ONE seek on pointer-up; plain clicks + keyboard arrows seek directly. The reload path honours the previous play/pause state (`autoPlayRef`), so seeking while paused stays paused, and `canplay` clears the "Preparing stream…" spinner when autoplay is blocked.
- **Subtitles render via overlay** — native `<track>` removed. Selecting a sub fetches the VTT proxy stream, parses it into item-time cues (`parseVtt`/`parseVttTime`; tags + STYLE/REGION/NOTE skipped), and the player draws the active cue aligned to the offset position model — correct across remux/transcode restarts and scrubs.
- **Tests** — +4 frontend (VTT timestamp parsing incl. comma decimals, multi-line cues + tag stripping + settings suffix, NOTE/STYLE/CRLF tolerance, active-cue lookup). **vitest 36/36** (+4) · `tsc` clean · `vite build` ok (no backend change).
- Committed `ffb7905`; **pushed to GitHub** `experiment/bundled-docker-stack` (0 behind).

## ▶ LATEST SESSION (2026-09-06) — Tier 1: honest stream routing — direct / remux / transcode_audio / transcode + REAL quality & audio pickers ✅
**The pickers were decoration.** Verified live: under `Static=true` Jellyfin **ignores** `AudioStreamIndex` + `MaxStreamingBitrate` (identical 206 responses with/without). So Quality and Audio did nothing unless the audio-transcode path happened to be on. Fixed with a full routing ladder + codec-aware auto-decisions; the player now plays the cheapest mode that actually works and says which one it's using.

- **Stream modes** (`/api/jellyfin/stream`, additive): `mode=direct` (Static file, range-seekable) · `remux` (copy/copy → mp4 — solves MKV-style containers the browser can't index up-front) · `transcode_audio` (video copy + AAC) · `transcode` (H.264 + AAC, honours `max_bitrate`). New `start_time_ticks` = restart-seek for chunked non-direct streams (probed live: remux/transcode return chunked `200` MP4 with `ftyp` first — duration resolves instantly but byte-range seeking doesn't exist). Legacy `transcode_audio=true` still maps. Unknown mode → 400.
- **Routing facts** — `playback_info` now returns `container` + first video stream (`codec/profile/width/height/bit_depth/bit_rate`, codecs lowercased). `pickStreamMode()` (frontend): quality ≠ Original → transcode; unsafe video codec (HEVC / 10-bit H.264) → transcode; unsafe audio (EAC3/AC3/DTS/TrueHD) → transcode_audio; non-mp4 container → remux; else direct. **Choosing an audio track forces non-direct** (Static can't honour it).
- **Player** — offset-position model: direct seeks by byte range; remux/transcode RESTART at `StartTimeTicks` mid-position so bar + resume stay seamless. Mode chip (Direct play / Remux / Transcode) in the header + control bar; media errors escalate the ladder (`direct → remux → transcode_audio → transcode`) before a friendly give-up; "Preparing stream…" spinner during mode/quality switches; progress reports now carry the true `PlayMethod` (DirectPlay/DirectStream/Transcode).
- **Tests** — +4 backend (remux URL, transcode URL + bitrate, legacy bool mapping, unknown mode 400, direct ignores params; provider video/container parse) + 6 frontend (routing decisions incl. 10-bit/HEVC/forceNonDirect, labels, play methods). **264 pytest** (+4) · ruff clean · **vitest 32/32** (+6) · `tsc` clean · `vite build` ok. Contract snapshot + `types.ts` regenerated (30 paths, additive).
- Committed `208fc3d`; **pushed to GitHub** `experiment/bundled-docker-stack` (0 behind).
- **Next tier options:** warm-start/prefetch + double-buffered episode switching; autohide controls/gestures/PiP/pref persistence; or HLS/hls.js adaptive (supersedes restart-seek for transcode).

## ▶ LATEST SESSION (2026-09-06) — player seek-bar fix: total from API runtime, custom controls ✅
**"When I start an episode the progress bar doesn't show the correct status — no length shown." Root cause: the player used the NATIVE `<video controls>` bar, and direct-play containers the browser can't index up-front report `duration = Infinity`. With no finite total the native bar broke: no end-length, position math wrong a few seconds in. Jellyfin's scan metadata (runtime on every movie/episode) was ALREADY correct end-to-end (probed live: `RunTimeTicks` + `UserData.PlaybackPositionTicks` present on items, episodes and Resume; the repo provider parses them right) — the player just never used it.**

- **`Player.tsx`** — native `controls` removed; custom bar whose total = `barTotal(stream duration once finite, else the API runtime hint)` → length + % correct from the first frame even while the stream duration is still unknown. Adds: play/pause, seek slider, `cur / total` time (mm:ss / h:mm:ss), volume + mute, fullscreen, click-video-to-toggle, keyboard (space, ←/→ ±10 s, m, f, Esc). Resume-seek + 5 s-throttled `/api/jellyfin/progress` reporting unchanged.
- **Length plumbing** — `QueueEntry` carries `runtime` (from `episodeQueue`), `LibraryView` threads it into the Player for movie / episode / Up-Next paths, so every play path seeds the correct total (e.g. *3 Body Problem* S1E4 shows 0:00 / 44:08, not `/ --:--`).
- **Helpers + tests** — pure `fmtTime` / `isFiniteDuration` / `barTotal` (stream-first, hint fallback) / `clampSeek`; queue test now asserts runtime travels with the entry. **vitest 26/26** (+4) · `tsc` clean · `vite build` ok.
- Committed `d950c8a`; **pushed to GitHub** `experiment/bundled-docker-stack` (0 behind).
- **Note:** seeking still depends on the browser being able to map time→bytes once buffered; for containers where even Jellyfin's own web player must transcode to seek, a future "force remux" option would be the lever (item 5 territory).

## ▶ LATEST SESSION (2026-09-06) — audio-transcode follow-up: EAC3/AC3/DTS/TrueHD → AAC (video copy) ✅
**In-app playback went silent on any Jellyfin title whose audio track the browser can't decode — direct play (`Static=true`) served EAC3/AC3/DTS/TrueHD untouched. Follow-up to item 3 lands automatic audio transcoding, fully additive (`/api` frozen → one new query param, no new path).**

- **Backend** (`api/routes/jellyfin_stream.py`): `GET /api/jellyfin/stream/{id}` accepts `transcode_audio=true` → swaps `Static=true` direct play for Jellyfin's on-the-fly stream with `VideoCodec=copy` (video untouched) + `AudioCodec=aac` + `MaxAudioChannels=2`. `audio_stream_index` / `max_bitrate` forward in both modes.
- **Codec surfacing** (`services/library/jellyfin.py`): `playback_info` audio tracks now carry `codec` (from the Jellyfin media-source `Codec` field) so the player decides without extra round-trips.
- **Frontend**: `audioCodecNeedsTranscode()` whitelists browser-safe codecs (`aac/mp3/opus/vorbis/flac/pcm_s16le/pcm_s24le/pcm_mulaw/alac`; unknown/missing → false — never over-transcode); `Player.tsx` derives `transcode` from the active track (first by default, re-evaluates on audio-track switch) and shows a subtle "⚠ audio transcoding (codec)" hint; `streamUrl` passes `transcode_audio`.
- **Contract**: OpenAPI snapshot + `types.ts` regenerated — additive, 30 paths unchanged, `transcode_audio` query param added.
- **Tests**: +2 backend (transcode URL asserts no `Static=true` + `VideoCodec=copy`/`AudioCodec=aac`/`MaxAudioChannels=2`/`AudioStreamIndex` forwarded; codec surfaced in track list), +1 frontend (codec whitelist: `eac3/ac3/dts/TRUEHD` → true, `aac/AAC/opus/flac` → false, case-insensitive, unknown/null → false). **260 pytest** (was 259) · production `ruff` clean · **vitest 22/22** · `tsc` clean · `vite build` ok.
- Committed `1bc9940`; **pushed to GitHub** `experiment/bundled-docker-stack` (0 behind).
- **Roadmap:** this lands the *audio-codec* slice of transcode robustness ahead of schedule; item 5 (full transcode-fallback engine — auto-open Jellyfin when direct play fails) remains its focus.

## ▶ LATEST SESSION (2026-09-06) — Roadmap item 3: player features — speed / audio / subtitle / quality pickers + autoplay-next + backdrop ✅
**Item 3 lands on the new modular structure.** The in-app player gains a full control surface, all same-origin (`/api` additive-only, no secret leaks).

- **Backend (additive):**
  - `JellyfinLibraryProvider.playback_info(item_id)` — probes `POST /Items/{id}/PlaybackInfo`, normalises the first media source into audio + **text-only** subtitle track lists (image/PGS subtitle streams are excluded — a browser `<track>` can't render them). ABC default + `LibraryService` aggregate added.
  - `GET /api/jellyfin/playback-info?id=` (via service) + `GET /api/jellyfin/subtitle?id=&ms=&index=` (WebVTT proxy, token server-side).
  - `GET /api/jellyfin/backdrop?id=` — `get_poster` gained a `kind` param (Primary/Backdrop/…) with a shared `_proxy_image` helper.
  - `GET /api/jellyfin/stream/{id}` now accepts `audio_stream_index` + `max_bitrate` (audio switching + the quality picker) — absent by default, forwarded when set.
  - **Contract 27 → 30 paths** (backdrop, playback-info, subtitle) + `types.ts` regenerated (additive, no drift).
- **Frontend:** `Player.tsx` adds **Speed** (0.5–2×), **Quality** (Original/1080p/720p/480p), **Audio** (track picker) and **Subs** (`<track>` VTT, default-on) controls; a 16:9 **backdrop** behind the player; **autoplay-next** — a cancellable 8s countdown auto-advances the series queue on `ended` (manual Play-next + Cancel kept).
- **Tests:** +2 provider (playback_info normalisation, excludes image subs; not-configured → None), +4 routes (stream params, backdrop kind, playback-info, subtitle VTT), +3 frontend (rates, quality mapping, autoplay delay). **259 pytest** (was 253) · production `ruff` clean · **vitest 21/21** · `tsc` clean · `vite build` 99 modules.
- **Deferred to item 5 (its focus):** the Jellyfin transcode-fallback *engine* (auto-open Jellyfin when direct-play fails). Item 3 shipped the quality picker UI; item 5 owns fallback robustness.
- **Roadmap status:** items 1–3 ✅. Items 4 (library & discovery) and 5 (transcode robustness) remain.

## ▶ LATEST SESSION (2026-09-06) — fix: Jellyfin `thumb` aspect-ratio leak ✅
**One-line fix + regression test. `thumb=it.get("Thumb","") or it.get("PrimaryImageAspectRatio","") or ""` emitted the *numeric aspect ratio* (e.g. `0.666`) as the item's thumb whenever Jellyfin returned no `Thumb` (banner) image — which is most titles. That float-string leaked into every `/api` `thumb` field. Now: `thumb=it.get("Thumb","") or ""` (matches the Emby provider); the React cards were unaffected (they build posters from `item.id` via the `/api/jellyfin/poster` id-proxy → `Primary`), so this was purely the API-shape/wrong-value fix.**

- `services/library/jellyfin.py` `_parse_item` — drop the `PrimaryImageAspectRatio` fallback (a ratio, not a path).
- `tests/test_jellyfin_provider.py` — new `test_parse_item_thumb_never_leaks_aspect_ratio`: thumb preserved when present; empty (never a numeric ratio) when absent.
- Verify: **253 pytest passed** (was 252) · production `ruff check` clean · no contract/`types.ts` regen needed (field stays a plain `string`; the bug was a *value*, not a type).
- Pushed to GitHub — `experiment/bundled-docker-stack` tip `8dc174a` (verified origin matches local, 0 behind). CI workflow file left out of scope per user.

## ▶ LATEST SESSION (2026-09-06) — Roadmap item 2: watch-state — mark watched/unwatched + Recently Watched + play count ✅

**Item 2 of the Plex roadmap lands** on the new modular structure (as planned — it lives in the library/playback feature area). Additive backend endpoint + contract regen + frontend.

- **Backend** (`services/library/jellyfin.py`): added `play_count` + `last_played` to `_item_public` (surfaced on every library serializer, additive contract fields); new `recently_watched(limit)` capability → played items sorted by `UserData.LastPlayedDate` desc; new `mark_state(item_id, watched)` → Jellyfin `Users/{uid}/PlayedItems|UnplayedItems`, invalidates the scan cache, returns fresh `{played, play_count}`.
- **ABC + service**: `LibraryProvider` gains `recently_watched`/`mark_state` (default `[]`/`None`); `LibraryService` aggregates to the first provider that supports it.
- **Routes** (additive): `GET /api/library/recently-watched` + `POST /api/library/{item_id}/state` `{watched}`. Snapshot **regen → 27 paths**; `types.ts` regenerated.
- **Frontend**: `client.ts` (`getRecentlyWatched`, `mutateItemState`); `useRecentlyWatched` + `useMutateItemState` (invalidates all library/episodes queries so the ticks move everywhere); **MediaCard** gets a **Mark-watched / ✓ Marked watched** toggle + **play-count**; **LibraryView** adds a **Recently Watched** row and wires toggles across grid / Continue Watching / Recently.
- **Tests**: +4 backend (`recently_watched` sort/filter, `mark_state` POST played+unplayed, both routes). **252 pytest** · ruff clean · frontend tsc/build/vitest 18/18.
- **Roadmap status:** item 2 ✅. Items 3–5 remain (player features, library/discovery, transcode robustness).

## ▶ LATEST SESSION (2026-09-06) — Phase 3b: `playback` slice — real in-app player + episode picker ✅

**Player core ported, frontend-only (no contract change — `reportProgress`/`streamUrl` hit the existing frozen `/api`).** Movies play in-app with resume + progress reporting; series get the episode picker with per-episode resume + Up Next.

- **`features/playback/Player.tsx`** — same-origin `/api/jellyfin/stream/{id}`; seeks saved resume on `loadedmetadata`; reports `/api/jellyfin/progress` (`start` / 5s-throttled `timeupdate` / pause·ended·error → `stopped`) via `postJson`, with the **resume-guard** that never POSTs 0 while a fresh stream sits at the start (mirrors legacy `_reportPos`); codec-failure fallback note; **Up Next** overlay from the series queue (Play next → switch).
- **`features/playback/EpisodePicker.tsx`** — season-grouped rows, per-episode thumb, ✓ watched tick, **Play/Resume/Replay** (start-position-aware), Escape/backdrop close.
- **`features/playback/lib.ts`** — pure `groupBySeason`/`nextEpisode`/`episodeQueue`/`playLabel`/`startPosition`/`episodeThumbUrl` exactly mirroring legacy; **+6 unit tests** (18 total).
- **`client.ts`** — added `postJson`, `ProgressPayload`, `reportProgress`, `streamUrl`. Endpoint already in the frozen contract → **no `types.ts` regen, no drift**.
- **`LibraryView`** — movie → Player; series → EpisodePicker → Player (Up-Next queue); Player keyed by item so an episode switch remounts cleanly.
- **Verify:** `tsc` clean · `vite build` 99 modules · `vitest` **18/18**.
- **Deferred (item 2 watch-state):** mark watched/unwatched, Recently Watched row, play count — needs an **additive backend endpoint** (`POST /api/library/{id}/state`) + contract regen; its own pass.

## ▶ LATEST SESSION (2026-09-06) — Phase 3a: `library` feature slice ported to React ✅

**`/library` now renders in the React shell at legacy parity** — poster wall + Continue Watching + scan wiring. Legacy `app.js` untouched.

- **`features/library/api.ts`** — `useLibraryItems`/`useContinueWatching` (TanStack Query) + `useScanLibrary` mutation that invalidates library queries on success (drive-the-backend).
- **`features/library/lib.ts`** — pure helpers mirroring legacy `app.js` exactly: `posterUrl` (Jellyfin poster proxy → Plex thumb proxy fallback), `playbackMarker` (watched tick vs amber resume % vs none — copied logic), `isContinueWatching` filter, `isSeries`. **10 unit tests** pins parity.
- **`MediaCard.tsx`** — poster, MOVIE/TV badge, watched/resume markers, primary **Play in RKM** (movie) / **Episodes** (series) + Jellyfin deeplink; **`ContinueWatchingRow.tsx`** + **`LibraryView.tsx`** (title counts, Scan button, series-play notice, poster grid).
- **`Player.tsx`** — minimal same-origin `/api/jellyfin/stream` video so movies actually play; **full playback slice (resume reporting, mark-watched, up-next, episode picker) = Phase 3b** (roadmap item 2 lands there).
- `client.ts` `MediaItem` aligned to the real item shape; `router.tsx` `/library → LibraryView`.
- **Verify:** `tsc` clean · `vite build` 96 modules · `vitest` **12/12**.

## ▶ LATEST SESSION (2026-09-06) — Phase 2: `web/` React/TS shell + typed client + flag ✅

**`web/` builds and serves a working shell showing `/api/config` health behind a flag.** Legacy `app.js` untouched, still the prod default.

- **Shell** (`web/`, React 18 + TS + Vite 5 + Tailwind 3): `main.tsx` → `RouterProvider` (react-router-dom) → `AppShell` (Sidebar/Header/Outlet) with routes `settings` (real) + `library`/`playback`/`discover`/`watchlist`/`search`/`suggest` (PortedPlaceholder stubs for Phase 3).
- **Typed client** — `src/lib/api/types.ts` **machine-generated from the frozen contract** (`npm run generate:types`, openapi-typescript over `docs/api/openapi.v1.json`, 1,817 lines = source of truth); `src/lib/api/client.ts` hand-tunes the narrow stable surface (config/health/library/episodes) keyed to the `@/` alias; same-origin `/api/*` (nginx→FastAPI, secrets stay server-side).
- **Feature flag** — `lib/flags.ts` (`VITE_ENABLE_REACT`): `npm run dev` shows the shell; a prod build without the env keeps the legacy app serving (LegacyPlaceholder) until Phase-4 cutover.
- **ConfigHealthView** — TanStack Query hooks (`features/settings/api.ts`) read `/api/config` + `/api/health`; per-service configured/ok badges + degraded banner. TanStack Query already the server-state layer.
- **CI** — added the **frontend job** to `.github/workflows/ci.yml`: `npm ci` → `typecheck` → `vitest` → `build` → **contract-drift guard** (`npm run generate:types && git diff --exit-code types.ts`).
- **Verify:** `tsc --noEmit` clean · `vite build` 90 modules, dist 0.44kB html + 252kB js / 9.5kB css · `vitest` **2/2** · `vite preview` serves `/`, js, css all **200**. (7 npm audit vulns = dev-deps; not force-fixed to avoid breakage.)

**Caveat (dev-proxy):** `vite.config.ts` proxies `/api → http://127.0.0.1:8000` for dev; point `VITE_API_PROXY` at a running backend (e.g. the bundled Jellyfin stack) to see live config health in `npm run dev`.

## ▶ LATEST SESSION (2026-09-06) — Phases 0 + 1a executed (CI + contract freeze + ABC capability surface) ✅

**Following `docs/modular-scalable-architecture.md`.** Not just documenting — executed Phase 0 fully and Phase 1's core (ABC capability surface). Both committed + verified green; **push to GitHub blocked on a token scope** (below).

### Phase 0 — CI + contract freeze + docs reset ✅ (`dc6c72a`)
- **`.github/workflows/ci.yml`** — backend job on every push: `ruff check` (F/pyflakes grade on production packages per `ruff.toml`) + `python -m pytest tests/ -q`. Frontend `tsc`+`vitest`+build job added in Phase 2 when `web/` exists.
- **Frozen contract** — `docs/api/openapi.v1.json` (25 paths) via new `scripts/snapshot_openapi.py` (idempotent, path-safe); `/api` = immutable v1, additive-only (ADR-0001).
- **ADRs** — `docs/adr/ADR-0001` (freeze /api) · `0002` (React/TS frontend) · `0003` (keep-Python, consolidate don't rewrite).
- **Docs reset** — README + ARCHITECTURE status pointers to the plan/contract/ADRs.
- **6 latent bugs fixed** (ruff F baseline) so the lint gate is genuinely green: `F823`/`UnboundLocalError` `urllib` used before the function-local import in `api/routes/search.py` + `services/plex.py` (real runtime bug); `F811` duplicate `has_jellyfin` in `config/settings.py`; `F402` dataclasses `field` shadowed by a loop var in `services/watchlist.py`; dead `entry`/`in_watchlist` vars in `api/routes/suggest.py`. Plus 55 safe ruff `--fix` cleanups (imports/vars) across prod packages.
- **Verify:** `ruff check` (prod) clean · **247 pytest passed**.

### Phase 1a — ABC capability surface + route cleanup ✅ (`ba32448`)
- `LibraryProvider` ABC now declares `all_items`/`continue_watching`/`episodes`/`refresh_library`/`get_poster` with harmless defaults (`[]`/`False`/`None`) — **uniform provider surface**.
- `LibraryService` gained **aggregate collapse** methods: each capability returns the first provider with a **meaningful** result, so a Plex defaulting to `[]` can't shadow a Jellyfin that implements it.
- Routes `/api/library/items`, `/library/continue-watching`, `/library/series/{id}/episodes`, and `/api/jellyfin/poster` now call the **service**, not `getattr`/`hasattr`; deleted `_first_provider_with` feature-detection.
- Tests re-targeted to the service seam (response shapes unchanged) + **1 new regression test** pinning the collapse behavior.
- **Verify:** ruff clean · **248 pytest passed** (+1).

### Phase 1b — facade "consolidation" finding ⚠ design refinement
The plan assumed parallel duplicate service modules to delete. **The audit shows they're NOT duplicates**:
- `services/plex.py` (`PlexService`), `services/radarr.py` (`RadarrService`), `services/sonarr.py` (`SonarrService`) are the **canonical low-level clients**; the canonical packages are thin adapters *over* them — e.g. `RadarrAcquisitionProvider` wraps `RadarrService` (`from services.radarr import RadarrService`); `services/library/plex.py` wraps `PlexService`. §43 "one implementation per rule" **already holds** — no parallel logic.
- `services/recommendations.py` (`RecommendationService`) + `services/media_status.py` (`MediaStatusService`) are already thin delegates to canonical `services/recommendation/` + `services/reconciliation/`.

**Recommendation:** Phase 1's "consolidation" is really **optional relocation** (move clients into their domain packages + re-export stubs), which buys organization but **not** dedup, and adds churn/risk. **Recommend low priority / defer** — it doesn't block the React port. The genuine Phase 1 value (uniform provider SPI + route-via-service) is DONE.

### ⚠ Push blocker (deployment-action needed)
Commits `dc6c72a`, `ba32448` are **local only**. `git push` to GitHub is refused because the new `.github/workflows/ci.yml` requires the token to hold the **`workflow`** scope, and the sandbox `GITHUB_TOKEN` (in `/workspace/.env`) lacks it.
```powershell
# GitHub → Settings → Developer settings → PAT (classic) → select the token used as
# GITHUB_TOKEN in /workspace/.env → add the "workflow" checkbox (keep "repo") → Update.
#   (or: gh auth refresh -s workflow)
# Then re-run the sandbox push; Phase 0+1a go up and CI actually runs on GitHub.
```

### NEXT (prioritized)
1. **Unblock the token** (`workflow` scope) → push Phase 0 + 1a → confirm CI green on GitHub.
2. Decide **Phase 1b** (defers relocation — recommend skip/defer).
3. **Phase 2** — `web/` React/TS shell + `openapi-typescript` typed client + feature flag.

## ▶ LATEST SESSION (2026-09-06) — Modular & Scalable re-platform: PLAN adopted (no code) ✅

**Decision:** keep the sound FastAPI/Python backend (consolidate facades + extend the ABC — no rewrite); rewrite the **frontend** to **React 18 + TypeScript + Vite + Tailwind** behind a **frozen `/api` contract**. The contract is the seam that de-risks the re-platform. Full plan committed at **`docs/modular-scalable-architecture.md`** (decisions table, risks, open questions, phases, validation).

**Why now (the constraint):** `app.js` is a **2,191-line single-file monolith** (+ `api.js` 124, `app.css` 967) — global render functions + delegated handlers, global state (`DATA`/`RES`/`LIBALL`/`LIBWATCH`) — not maintainable past a handful of screens. Backend is modular but carries **BC-facade debt** (`services/plex.py`, `emby.py`, `radarr.py`, `sonarr.py`, `recommendations.py`, `media_status.py` coexist with canonical `services/library|acquisition|recommendation|reconciliation/`) and the Jellyfin-only capability methods (`all_items`, `continue_watching`, `episodes`, `refresh_library`, `get_poster`) are **not declared in the `LibraryProvider` ABC** — routes call `getattr(provider, …)`. No CI, no typed API contract, stale root docs.

**Phases (each ends committed + a working demo):**
0. **CI + contract freeze + docs reset** — GH Actions (ruff/mypy + `pytest`; frontend `tsc`+`vitest`+build once `web/` exists); snapshot `openapi.json` → `docs/api/openapi.v1.json` (v1 immutable, additive-only); rewrite `README.md`/`ARCHITECTURE.md` + ADRs.
1. **Consolidate backend facades + ABC capability surface** — delete BC shims (re-export stubs w/ `DeprecationWarning` → remove); add `all_items`/`continue_watching`/`episodes`/`refresh_library`/`get_poster` to the ABC/mixin (Plex/Emby default `[]`/`False`); routes call the ABC. Target 250+ pytest.
2. **`web/` shell + typed client + flag** — Vite React/TS app, router, `AppShell`/`Sidebar`/`Header`, Tailwind; `types.ts` generated via `openapi-typescript`; `lib/api/client.ts`; TanStack Query (server state, tied to scan invalidation) + light Zustand; feature-flag routing behind a config toggle. Exit: shell builds + shows `/api/config` health.
3. **Port features to slices (parity each, behind the flag)** — `library` (poster wall, Continue Watching, scan wiring) → `playback` (player, resume, progress reporting, up-next, mark-watched — **roadmap item 2 lands here**) → `discover` (hero + rows) → `watchlist`/`search`/`suggest`/`settings`. Old app serves not-yet-ported views.
4. **Cut over + retire legacy** — flip default to React; delete `app.js`/`api.js`/legacy CSS.
5. **Items 2–5 on the new structure** — built once on the right foundation; multi-user (item 6) slots into `auth`/`playback` slices.

**Decisions (rationale + alternatives in the doc):** React 18+TS+Vite (matches your senior stack) · TanStack Query (cache + auto-invalidation tied to scan/job runs) + light Zustand · **keep Python/FastAPI** (already sound; rewriting is the classic trap) · **frozen `/api` + generated client** · **monorepo** (one repo, `web/` + backend dirs) · remove legacy **only at feature parity behind a flag**.

**Big-rewrite-smell risk + mitigations (highest risk):** (a) freeze `/api` first, (b) backend unchanged, (c) feature-flagged incremental port, (d) parity-check each view before retirement. Contract drift → closed by openapi-typescript + CI typecheck. Facade-deletion breakage → closed by one-release re-export stubs.

**Open questions (answer by Phase 2):** multi-user/auth? runtime = same nginx volume mount serving `web/dist/`? keep `dashboard.html`/`dashboard-data.json` legacy? testing bar (vitest + a few Playwright smoke)?

**Recommended next session: Phase 0 + 1** (CI + backend consolidation + contract freeze) — low-risk, immediately validates the modularity thesis, and makes the React port far safer.

## ▶ LATEST SESSION (2026-09-05, round 5) — TV shows: episodes + per-episode resume + Up Next ✅

**Item 1 of the Plex-like roadmap.** TV cards no longer "play" a non-playable Series id — they open an episode picker.

- **Backend (`services/library/jellyfin.py`):** `episodes(series_id)` lists every episode via `/Users/{uid}/Items?ParentId={seriesId}&IncludeItemTypes=Episode&SortBy=IndexNumber,ParentIndexNumber&Fields=…UserData…`, each with `{id,name,season,episode,thumb,played,playback_position,runtime}` (per-episode UserData → per-episode resume/watched). Route `GET /api/library/series/{id}/episodes` in `api/routes/library.py` (`_first_provider_with`).
- **Frontend (`app.js`/`app.css`/`api.js`):** `cardPrimaryPlay(itemId, position, isTv, title)` — movies → `data-act="play"` ("Play in RKM"), **TV → `data-act="series"` ("Episodes")**. Global handler `data-act="series"` + modal `data-role="episodes-jellyfin"` → `openEpisodes(seriesId,title)` modal: groups by season, each row has a thumb (`/api/jellyfin/poster`), watched/reume state, a per-episode **Play/Resume/Replay** button (`data-act="play"` + `data-resume`) → `openPlayer` reuses everything. `Up Next`: `_episodeQueue` (ordered episodes) + `nextEpisode(id)`; on `ended` the player shows an "Up Next" overlay with a Play-next button. Episode Stream proxy works per-episode-id (no new streaming code).
- **Note on TV testing:** the bundled library has **0 shows**, so this is unit-tested (grouping/sort/watched/resume/next) and the Jellyfin episodes endpoint was confirmed live (returns 200/400-shape, needs a real `ParentId`). Real TV can only be exercised once a show is added to the library.
- **Tests:** backend `test_episodes_lists_and_sorts_per_season` + `test_series_episodes_route`; frontend `cardPrimaryPlay` movie/TV, `playInRkmMarkup` TV role, `renderEpisodes` grouping/order/watched/resume, `nextEpisode` (phase26 now 25). **238 pytest + phase11/18/25/26 node green.**
- **To go live:** rebuild `.\bootstrap.ps1` (new backend route) + hard-refresh. Then a TV card's "Episodes" → pick a season/episode → plays in-app, resumes where you left it, and offers Up Next at the end.

## Automatic library scan (once/day) — small add-on

**Daily Jellyfin library scan inside RKM** so media dropped into the library folders gets scanned+indexed even when the app is idle.

- **Backend:** `JellyfinLibraryProvider.refresh_library()` → `POST {JELLYFIN_URL}/Library/Refresh` (verified 204 live). New `jobs/library_scan.py` (`LibraryScanJob.run` + `run_library_scan()`), records a `job_runs` audit row, returns `JobResult` (counts `{jellyfin, scanned}`). When Jellyfin isn't configured it reports cleanly (`{jellyfin:false, scanned:0}`) instead of erroring.
- **Scheduling:** added to the in-process scheduler (`jobs/scheduler.py`) as a **once/day** task at `DAILY_JOB_HOUR`, gated on `config.has_jellyfin()` (so Plex/Emby-only stacks skip it; independent of `AUTO_ADD_ENABLED`). Bundled stack already runs the scheduler (`WATCHLIST_SCHEDULER=true` in `render_config.py`). **On-demand** trigger too: `POST /api/jobs/library_scan/run` (registered in `api/routes/jobs.py`).
- **Tests:** provider refresh (204→True, not-configured→False), job not-configured/reconfigured, scheduler wiring, endpoint (6 new). **244 pytest + all node suites green.**
- **To go live:** rebuild `.\bootstrap.ps1`. After that it scans automatically every day; you can also hit `POST /api/jobs/library_scan/run` (or the refresh button wiring later) to force a scan. All job runs are visible on `GET /api/jobs`.
- **Cache bug that hid newly-added shows (FIXED, 247 pytest):** `JellyfinLibraryProvider` had a **single shared `_item_cache_expiry` for Movie AND Series**. Every fetch of Movies (e.g. any `/api/library` view) renewed that one deadline, so a Series cache populated **empty** at boot never refreshed — newly-added TV stayed invisible until a rebuild, despite Jellyfin having scanned it. Fix: **per-type expiry** (dict keyed by item type) + `refresh_library()` now calls `invalidate()` after a successful scan so results update immediately. Regression tests `test_per_type_cache_does_not_hide_series` + `test_refresh_library_invalidates_cache`. **This fix is backend — needs `.\bootstrap.ps1` to go live.**

## ▶ LATEST SESSION (2026-09-05, round 4) — Full library grid + Continue Watching ✅

**Poster-wall library + a Discover "Continue Watching" row**, completing the 1→3 roadmap. Branch **pushed to GitHub**.

- **Backend (`services/library/jellyfin.py`):** factored a shared serializer `_item_public(item)` (used by `recently_added`), a raw fetcher `_fetch_raw(url)`, and `_parse_item(it, type)` (dedupes the old inline item parsing). New **`all_items(limit=None)`** → every Movie+Series with playback facts (feeds the grid). New **`continue_watching(limit=12)`** → started-and-unfinished titles (**by filtering the already-fetched library scan for `position_ticks>0 and not played` — NOT Jellyfin's `/Items/Resume`, which returned 0 items despite a 21% position**; Jellyfin's resume endpoint is finicky about how it computes in-progress). Plex/Emby lack these methods → routes return `[]` gracefully.
- **Routes (`api/routes/library.py`):** `GET /api/library/items` and `GET /api/library/continue-watching`, thin — `_first_provider_with(service, attr)` picks the first provider exposing the method; failure-safe.
- **Frontend (`api.js`/`app.js`/`app.css`):** `API.getLibraryItems()` / `API.getContinueWatching()`; `loadLibrary()` caches `LIBALL` + `LIBWATCH`. `renderDiscover()` inserts a **Continue Watching** row right after the hero (from `LIBWATCH`, filtered, reusing `libraryCard` → resume bar + Play-in-RKM). `renderLibraryView()` adds a **Full Library poster-wall** `<div class="grid">` (from `LIBALL`) below the stats + recently-added strip.
- **Live-verified Jellyfin persistence:** a controlled `start`+`timeupdate(600s)` sequence stuck at **600s** in UserData and survived a `Stopped` call (the earlier "wiped back to 0" was a transient/library-scan artifact, not the reporting); the resume % bar reads this position.
- **Tests:** provider `test_all_items_lists_entire_library` + `test_continue_watching_filters_in_progress`; route `test_library_items_route_returns_all` + `test_library_continue_watching_route`; frontend `continueWatchingRowMarkup`×2 + `fullLibraryGridMarkup` (phase26 now 18 assertions). **236 pytest + phase11/18/25/26 node all green.**
- **To go live:** rebuild `.\bootstrap.ps1`, hard-refresh — Library tab becomes a poster wall; Discover shows a Continue Watching row for partially-watched titles.

## ▶ LATEST SESSION (2026-09-05, round 3) — Watched / progress (Jellyfin UserData) built + verified ✅

**Resume % bar + watched tick** driven by Jellyfin `UserData`, AND in-app playback now reports back so the markers actually move.

- **Backend data source:** `JellyfinItem` now captures `UserData.Played`, `UserData.PlaybackPositionTicks`, and item `RunTimeTicks`. `_match_from` → metadata gains `played` / `playback_position` / `runtime` (10ms ticks → seconds via `_ticks_to_sec()`); `recently_added()` emits the same three keys (so **`/api/library` recent** carries them → Library cards). `WatchLink` gains `played`/`playback_position`/`runtime` filled from `match.metadata` and emitted in `to_dict()` → `WatchEntryModel` (grid/modal via resource API).
- **Backend progress reporting:** `POST /api/jellyfin/progress` (in `jellyfin_stream.py`) takes `{item_id, position_ticks, is_paused, event}` and forwards to Jellyfin **Sessions** via the server-side key — `start`→`/Sessions/Playing`, `timeupdate`→`/Sessions/Playing/Progress`, `stopped`→`/Sessions/Playing/Stopped`. **Verified live:** these endpoints return `204` with `?api_key=…` + JSON body, and one progress call moved (500) Days to **1200s/5705s (21%)** in the server's UserData.
- **Critical finding:** a plain `<video>` (in-app playback) does NOT report to Jellyfin, so `UserData` stayed at 0 even after playing. Without this reporting the resume/watch markers would never move — that's why the player now reports.
- **Frontend (`app.js`/`app.css`):** `playbackMarkup(info)` renders a **watched tick** (green circle) when `played`, else an amber **resume % bar** (bottom of poster, `width:%`) when `position>0 && runtime>0`. Wired into `libraryCard` (Library view) + `cardMarkup` (grid, from `s.watch.jellyfin`). `openPlayer()` now sends `start` on play, throttled `timeupdate` every 5s, and `stopped` on pause/ended/error via `reportProgress()` → `/api/jellyfin/progress`.
- **Tests:** backend `test_resource_watch_carries_playback_facts`, `test_recently_added_carries_playback_facts`, `test_watch_link_emits_playback_facts`, `test_progress_forwards_to_jellyfin_sessions`, `test_progress_uses_playing_for_start_event` (5 new); frontend `playbackMarkup`×3, `libraryCard` resume+watched, `cardMarkup` resume, `reportProgress` capture (6 new). **232 pytest + phase11/18/25/26 node all green.**
- **To go live:** rebuild the bundled stack `.\bootstrap.ps1`, then hard-refresh — watch a movie a couple of minutes, close it, and its card shows a resume bar.

## ▶ LATEST SESSION (2026-09-05, round 2) — In-app Jellyfin playback built + verified ✅

**Plays the library INSIDE the RKM app** (native `<video>`, no jump to Jellyfin). Same branch `experiment/bundled-docker-stack`.

- **Backend:** new `api/routes/jellyfin_stream.py` → `GET /api/jellyfin/stream/{item_id}` proxies Jellyfin **direct play** (`/Videos/{id}/stream?api_key=…&Static=true`), forwards the client `Range` header upstream and passes through the upstream status (206/200) + `Content-Type`/`Accept-Ranges`/`Content-Range` chunked. 503 if not configured. Registered in `api/main.py`. **Verified live against the running bundled Jellyfin (10.11.11, tailnet `:8098`):** `Range: bytes=0-1023` → `206` + `Content-Range: bytes 0-1023/1882377499`, `video/mp4`, H.264/AAC direct-play.
- **`item_id` plumbing:** `WatchLink` (services/library/watch_links.py) gains `item_id` (filled from `match.metadata["item_id"]`); surfaced through `WatchEntryModel.item_id` + `StatusEntry.jellyfinItemId`; `/_snapshot_to_media` + `/status` emit it. Frontend `st()` exposes `jellyfinItemId`; `/api/watchlist` (→ `_snapshot_to_media`) is what feeds the live grid.
- **Frontend (`app.js`/`app.css`, volume-mounted → live on hard-refresh):** when Jellyfin is the available source with an `item_id`, the card's primary action becomes **"▶ Play in RKM"** (`data-act="play"` → `openPlayer(itemId)`), with the Jellyfin deep-link kept as a secondary button; the detail modal prepends a `data-role="play-jellyfin"` "Play in RKM" button. `openPlayer()` builds a `.player-overlay` with a native `<video controls autoplay>` hitting `/api/jellyfin/stream/{itemId}`; codec-failure shows a friendly in-overlay error instead of a dead video.
- **Tests:** `tests/test_jellyfin_stream.py` (4: Range→206 passthrough, 200 full, 503 unconfigured, resource `item_id`) + `tests/phase26_jellyfin_play_frontend.test.mjs` (6: st.jellyfinItemId, card Play-in-RKM, deep-link fallback, playInRkmMarkup, modal play-first). **227 pytest + phase11/18/25/26 node all green.**
- **To go live:** backend route + item_id need the API container rebuilt on RKM-HP via **`.\bootstrap.ps1`** (the bundled api+web+Jellyfin stack — that's where `MEDIA_SERVER=jellyfin` + the Jellyfin key are injected, so `item_id` flows and the Play-in-RKM buttons render). Prod `.\run-rkm-cinema.ps1` uses the Plex/Emby backend, so it won't show Jellyfin playback. Frontend-only files (app.js/app.css) are live immediately via the volume mount.

## ▶ LATEST SESSION (2026-09-05) — Bundled Jellyfin stack ("Jellyfin client") built + verified ✅

**Branch `experiment/bundled-docker-stack`.** Self-contained Compose project **`rkm-bundled`** that runs its OWN Jellyfin + the RKM app (api+web) — no pre-existing media stack needed. Fully **isolated from prod** (network `rkm-exp`, own `./data`, non-colliding ports: Jellyfin `:8098`, dashboard `:8124`). Verified live: `/api/config` → `jellyfin: true`, `/api/library` → provider `jellyfin`, counts `{movie:2}`, Watch links open Jellyfin & play.

**Run (Windows, one command):** `cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema; .\bootstrap.ps1` (zero-edit: TMDB auto-fills from canonical workspace `.env`; Jellyfin admin password auto-generates & persists to `rkm.config.toml`). Teardown: `docker compose -p rkm-bundled down` · full wipe: `down -v`.

**Files (on the branch):** `docker-compose.yml` (api+web+jellyfin, `fullstack` profile for radarr/sonarr/prowlarr/qbit), `render_config.py` (TOML→`.env`/`.rkm.env`), `rkm.config.example.toml`, `provisioner/provision.py` + Dockerfile, `bootstrap.ps1`/`.sh`, committed `index.html`. App changes: `JellyfinLibraryProvider` (`services/library/jellyfin.py`) + `build_library_service` factory (`services/library/factory.py`, `MEDIA_SERVER=jellyfin|emby|plex` — prod default Plex+Emby preserved, all call sites wired to the factory); settings `MEDIA_SERVER`/`JELLYFIN_BROWSER_URL` + runtime-config loader (`RKM_RUNTIME_PATH=/shared/runtime.json`); frontend `Watch on Jellyfin` (cards/modal/library) + tab re-order. Backend `api/routes/jellyfin_poster.py` proxies posters; deep links use Jellyfin-web `#/details` (NO `#!/` hashbang). **223 pytest + phase11/18/25 node green.**

**Jellyfin 10.11 provisioning gotchas (all banked in skill `media-server-stack` → `references/jellyfin-bundled-provisioning.md` — DO NOT re-derive):** wizard flag is `System/Info/Public.StartupWizardCompleted`; auth REQUIRES `X-Emby-Authorization` header (else `400 Error processing request`); `POST /Startup/User` sets-not-creates (needs `GET /Startup/User` first) + password is PLAINTEXT; `POST /Auth/Keys` flaky on 10.11 → fall back to **admin AccessToken as `?api_key=`**; libraries must use the `paths=` QUERY form (body PathInfos silently 204s w/o setting path) + verify `Locations`; after provisioning `up -d --force-recreate api` (Config is lru-cached per process). `x-media` compose anchor must be a scalar STRING.

### ▶ NEXT SESSION — prioritized next steps (recommended order, all incremental on current vanilla-JS UI)
1. ✅ **In-app Jellyfin playback** — DONE (round 2).
2. ✅ **Watched / progress** — DONE (round 3).
3. ✅ **Full library grid + Continue Watching** — DONE (round 4).
4. ✅ **TV shows (episodes + per-episode resume + Up Next)** — DONE (round 5, item 1 of Plex roadmap).
- **Plex-like roadmap (one item per session):** ⚠ **gated since 2026-09-06** — items 2–5 are now sequenced **after** the modular re-platform (Phase 5), so they get built once on the new structure. See top block; next session = Phase 0 + 1.
  - ✅ **item 1 TV shows** — DONE (round 5).
  - ▶ **item 2 Watch-state polish** — mark watched/unwatched buttons (cards + player), Recently Watched row, play count. **→ lands in the Phase 3 `playback` slice / Phase 5** (post-re-platform).
  - **item 3 Player features** — subtitle/audio-track/speed selectors, quality/transcode picker, player backdrops, autoplay-next.
  - **item 4 Library & discovery** — in-library search, filters/sort (unwatched/newest/type/genre), "Because you watched"/similar.
  - **item 5 Transcode/playback robustness** — Jellyfin transcode fallback + quality picker + auto-open Jellyfin player when direct-play fails.

## ▶ LATEST SESSION (2026-09-02, UI round) — lazy-load grids + smooth hover + in-Plex tick ✅

Frontend-only round (volume-mounted → **live on hard-refresh, no rebuild needed**). `app.js`/`app.css` only; backend + tests unchanged. 216 pytest + phase11/18/25 node green.

**1. Lazy loading (infinite scroll) for all big grids.** Movies, TV Shows, Watchlist and Downloaded now render the first **36** cards and append the next batch via an `IntersectionObserver` on a `#gridMore` sentinel (`rootMargin 900px`, i.e. prefetch just ahead of the viewport) until exhausted. DOM stays light for 296 titles. Genre filter in Movies/TV now **source-filters + re-renders** (was display-toggling, which couldn't work with lazy rendering). Sort/chips in Watchlist still full re-render. Keyboard arrow-nav delegated to `app` so it works on lazy-appended cards too.

**2. Smooth card hover/zoom.** `.card` + `.card img.poster` transitions switched from the snappy default ease to `cubic-bezier(0.22, 1, 0.36, 1)` (0.34s card, 0.55s poster zoom) + `will-change: transform` — lift and pinch now ease smoothly.

**3. In-Plex cards → bright-orange tick + hover actions.** Cards whose title is already in Plex (`state available|downloaded`) now show a **bright-orange circular tick** (top-right, glowing `#ff9500` radial) instead of the old translucent "✓ Available in Plex" text line. On hover the card-actions reveal **Watch on Plex** (gold) + **Trailer** stacked vertically, and the hover buttons got a solid dark blur backdrop + border + shadow so they read cleanly over bright posters. Emby-only cards get a purple Watch-on-Emby substitute. Reused the existing delegated click handling (`data-act=watch-plex|watch-emby|trailer`) — no new event wiring.

**Files:** `app.js` (`cardMarkup` in-Plex branch, `initLazyGrid/lazyAppend/lazyTeardown`, `renderGrid/renderWatchlist/renderDownloaded` lazy + genre re-render, delegated arrow-keynav), `app.css` (hover easings, `.plex-check`, `.card-actions.stacked`, button contrast, `.grid-more`), and regression tests in `tests/phase18_frontend.test.mjs` (in-Plex tick + Watch-on-Plex/Trailer/no-state-text, and not-added→Download).

**Deploy:** none needed for the UI round — `app.js`/`app.css` are volume-mounted. Hard-refresh (Ctrl+Shift+R). Ensure the backend image is current too if you've not run `run-rkm-cinema.ps1` (prod) / `bootstrap.ps1` (bundled) since the SQLite/504 work.

---

## ▶ LATEST SESSION (2026-09-02, follow-up) — Canonical store → SQLite + Suggest fresh-add card bug ✅

**User asked to move the watchlist off `watchlist.json` into a database, and to make it survive rebuilds.** The Phase 3 SQLite seam (spec §5) already existed but was idle; this session activated it and fixed a fresh-add card bug.

**1. Suggest fresh-add card showed no synopsis + no TMDB score (root-caused & fixed).**
`pushSuggestEntryToApp(entryFromWatchlistEntry(resp.entry))` maps the live-added card client-side, but `entryFromWatchlistEntry` read `w.overview` — which the persisted `WatchlistEntry` schema does NOT have (it stores the synopsis under `snippet`/`tmdb_overview`) and set `tmdb_score` (snake_case) while the modal reads `entry.tmdbScore`. So the fresh card's detail modal showed "No synopsis available yet." and no TMDB score. Existing dashboard cards were fine because `rebuild_dashboard.py` normalizes `overview = tmdb_overview || snippet` + camelCase `tmdbScore`.
**Fix (`app.js`, eslint-ok):** `entryFromWatchlistEntry` maps `overview = w.overview || w.snippet || w.tmdb_overview` and sets BOTH `tmdbScore` + `tmdb_score`. **Trailer:** the fresh card carries `trailerId` through (enrich persisted it); the modal `trailerButton` plays in-app if present, else "Search YouTube" fallback. Added regression test `tests/phase25_suggest_frontend.test.mjs`. Frontend is volume-mounted → **goes live on hard-refresh, no rebuild**.

**2. JSON → SQLite migration (activating the existing Phase 3 seam).**
- `.env` (canonical) now sets `WATCHLIST_STORE=sqlite` + `WATCHLIST_DB_PATH=/workspace/media/watchlist.db` — the DB lives on the **shared media volume** (/workspace/media, bind-mounted `:rw`), so `docker compose down`/rebuild no longer loses it (the old risk was the default `/app/watchlist.db`, which sits in the container's throwaway writable layer).
- **`scripts/migrate_json_to_sqlite.py`** (new, idempotent): JSON → SQLite, carries the recommendation seen-set (385 rows) across, round-trip verifies counts, re-exports watchlist.json as a one-time mirror, rebuilds the dashboard. **Ran successfully: 296 pending → SQLite, dashboard rebuilt (296 cards, 274 with trailers).**
- The whole app routes persistence through `build_repository()` (API, `rebuild_dashboard`, `add_watchlist_cron`, jobs, recommendation manager) — a flip requires no code changes; verified the API boots on the SQLite repo (`/api/health` + `/api/config` 200, "Using SQLite watchlist repository").
- **One test made deployment-immune:** `test_repository.test_build_repository_defaults_to_json` now forces an empty `WATCHLIST_STORE` env override (the checked-in `.env` previously carried it to sqlite). No test writes to the real DB — every other suite passes an explicit path.
- **216 pytest + phase11/18/25 node green.**

**⚠️ DEPLOY REQUIRED on RKM-HP** to bake the SQLite store + 504/suggest fixes into the running image:
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\setup-watchlist.ps1
```
The container reads `/workspace/.env` (env_file `../../.env`) and the shared `/workspace/media` volume, so the already-migrated `/workspace/media/watchlist.db` is picked up automatically. Verify `/api/health` 200 + entries still served after deploy.
**Note:** after the flip, `/workspace/media/watchlist.json` is a **frozen mirror** (last exported at migration). External media-stack scripts that read it directly still see pre-flip data until the next export — point them at the repository (or a fresh rebuild) if they must be live.

---

## ⭐ LATEST SESSION (2026-09-02) — 504 root-caused & fixed + Suggest UX round ✅
(previous latest session: 2026-08-28 below)

**Symptom:** `/api/status` + `/api/watchlist` returned **504 Gateway Timeout**; Suggest-search 404'd; the frontend hammered `/api/watchlist` every 15s.
**RCA (measured in-sandbox):** both endpoints ran a full `Reconciler().compute()` (all 292 entries) per request — fresh services each time ⇒ empty TTL caches ⇒ Plex re-scan + *arr lookups. All **155 TV entries are tmdb-only**, and each fired a **live Sonarr `/series/lookup?term=tmdb:<id>`** that TIMED OUT (12s × 3 retries) while indexers were down (AU s115a) ⇒ **58–84s per reconcile** against a 120s nginx window; the 15s poll then saturated the uvicorn threadpool ⇒ 504 everywhere. Suggest 404 = `api/routes/suggest.py` was **untracked** → not baked into the API image.

**Fixes — commit `e69e9f7`:**
- `Reconciler.compute_cached()` — process-level result cache (TTL **300s > 60s poll**, mtime-keyed, cleared on write & on `/media/{id}/request`) now backs `/api/status` + `/api/watchlist`. **Cold 58–84s → ~18s; warm poll 0.02s.**
- Sonarr tmdb→tvdb now via **TMDB `/tv/{id}/external_ids`** (lightweight, cached on disk at `/workspace/media/tmdb_to_tvdb.json`, 140 pre-resolved) instead of the live Sonarr lookup (the timeout source). Unresolved ids match by title+year against the cached Sonarr series list.
- Frontend status poll **15s → 60s** (`app.js`).
- Shipped Suggest (route + app): registered `suggest.router` in `api/main.py`, `POST /api/suggest`, `/api/suggest/add/{tmdb_id}`, `/api/suggest/detail/{tmdb_id}`.

**Suggest UX round — commits `1c8d9b1` (+last 3).** All next-session tasks were taken up this session:
1. ✅ **Search history — retain last 10.** `app.js` persists the last 10 filter sets to localStorage (`rkm_suggest_history`), rendered as clickable "Recent" chips in the Suggest tab (dedupe, most-recent-first).
2. ✅ **Add-to-Watchlist now lands TV as a TV Series.** Adds (Add **and** Download buttons) call `pushSuggestEntryToApp()`, which upserts the title into `DATA.entries` with `type:'tv'`/`isSeries:true` so it appears in the **TV Shows** tab (and Movies/Watchlist) immediately — no longer hidden until a dashboard rebuild. **Full card (not a stub):** `/api/suggest/add` now returns the enriched `entry` (poster, backdrop, genres, trailer, director, cast, imdb, tmdb_score, runtime) which the frontend maps via `entryFromWatchlistEntry()` — so a freshly-added title renders with poster + Trailer button + scores like every other card. From the Suggest UI now **216 pytest + phase11/18/25 node tests green**.

Three changes landed to get the watchlist unstuck (was frozen at 33 pending) and surface richer data:

### 1. Multi-strategy TMDB discover (un-stuck the 33-title plateau)
- **Symptom:** cron kept returning "0 added — all candidates already in Plex" because the generator ONLY ever queried `discover/movie` + `discover/tv` with `sort_by=popularity.desc` → always the same trending titles, which you already own.
- **Fix** (`services/recommendation/generator.py`): new `_DISCOVER_STRATEGIES` rotation — **popular** → **top-rated** → **hidden-gems** → **recent** — picked time-based (`int(time.time()) % 4`), so consecutive runs pull from different slices of the catalog. `_discover_tmdb` applies each strategy's `sort_by` + vote filters; strategy is logged.
- **Thresholds lowered** (`config/recommendations.yaml`): movies TMDB 7.5→**7.0**, IMDb 7.5→**7.0**, RT 80→**75**; series TMDB 7.5→**7.0**, IMDb 8.0→**7.5**, RT 85→**80**.
- **Result:** 33 → 47 pending (14 added in first run, tv-heavy because of rotation + ownership overlap; NOT a movies-are-blocked bug). **212 tests green.**

### 2. IMDb score for every title (was TMDB-only)
- Live entries had `imdb: 0.0` because TMDB discover carries no IMDb rating.
- **Fix:**
  - `services/tmdb.py` — detail calls now `append_to_response="...,external_ids"`, so `get_movie_details`/`get_show_details` return the IMDb id. New **`get_imdb_rating(imdb_id)`** (cached, OMDb free tier via `www.omdbapi.com`).
  - `services/recommendations.py` `enrich_metadata` — when TMDB yields an IMDb id, fetch + set `entry.imdb` (optional enrichment; gracefully skips failures/Mocks).
- **Result:** batch-enriched all 47 pending → **46 have IMDb scores** (1 missing: 2026 Avatar, no IMDb page yet). **212 tests green (incl. a Mock-guard update in `test_e2e_recommendation.py`).**

### 3. Plex dedup gap — owned titles could still be auto-added (fixed)
- **Symptom:** user flagged "The Dark Knight is already in my movies" after an auto-add — it (and 2 others) slipped through the Plex gate.
- **Root cause, two bugs in the matcher:**
  1. `services/library/plex.py` — the fuzzy subtitle fallback was **gated to title-only candidates** (`if not (identity.imdb_id or identity.tmdb_id)`). An id-bearing candidate whose Plex item exposes **no provider ids** AND has a title variant (`Batman: The Dark Knight` vs `The Dark Knight`) was treated as absent.
  2. `services/plex.py` `matches()` — strict year check (`if year is not None and self.year != year`) rejected a title match when the Plex item's year is **unknown (`0`)** (Dark Knight's Plex record has year=0 → failed vs candidate 2008).
- **Fix:** fuzzy substring fallback now runs for **any** candidate still having a title after the O(1) id + exact-title lookups miss (genuine last resort); `matches()` only rejects on year when the Plex item's year is actually **known** (`self.year != 0`). Applied to both `PlexMovie` and `PlexShow`.
- **Result:** The Dark Knight now correctly resolves to Plex `Batman: The Dark Knight`. Removed the 3 wrongly-added owned titles (**The Dark Knight, Avatar Aang 2026, Disclosure Day 2026**). Swept all pending — remaining 52 are legitimately new. **212 tests green.**

### Note — cron wrapper count
The auto-add job `1965aeb4af2e` is **`no_agent`** → it runs the shell wrapper `~/.hermes/scripts/rkm_watchlist_auto_add.sh` (NOT the Hermes prompt). The wrapper hardcodes `--count 20`; the strategy/threshold/dedup changes take effect there automatically (they're in the .py/.yaml it imports), but **`--count 30` would need a wrapper edit**. Cron schedule shown as `0 6 * * *` (daily 06:00 AEST).

## ▶ AUTO-ADD WATCHLIST CRON (2026-08-25) ✅ live

**Goal (user):** a scheduled job that picks movies/shows by criteria and adds them to the watchlist, using **Plex as source of truth** so owned titles are never re-added. Only **pending** watchlist entries are created — *no downloads* (user still approves Radarr/Sonarr in the UI).

**Mechanism:** reuses the Phase 12/13 refactor — `RecommendationManager` (TMDB discover → criteria → Plex gate → watchlist gate → history gate → rank) + `DailyWatchlistJob`. New **`scripts/add_watchlist_cron.py`** wires the manager with the Plex-backed `LibraryService` explicitly (the job's default manager has no library gate), runs the job, rebuilds the dashboard, prints a before/after summary. Backed by cron job **`1965aeb4af2e`** (Hermes, `no_agent`, weekly **Mon 09:00 AEST**, deliver=origin) → wrapper `~/.hermes/scripts/rkm_watchlist_auto_add.sh`.

- Usage: `python3 scripts/add_watchlist_cron.py [--count N] [--dry-run]`.
- Plex-gated: runs from sandbox against `PLEX_URL=192.168.65.254:32400` + `PLEX_TOKEN`; aborts if Plex unconfigured. TV dedup relies on title+year fallback (Plex show `provider_ids()` are `{}` — no external tmdb in the raw scan).
- **4 defects fixed** to make TMDB-discover actually work (commit `2f32130`, 210 green):
  1. `services/recommendation/generator.py` — `self._tmdb` **attr shadowed the `_tmdb()` method**, so the default (no injected tmdb) crashed "NoneType not callable". Renamed `_tmdb_injected`.
  2. `generator._discover_tmdb` — maps TMDB numeric `genre_ids` → **names** (new cached `TMDBService.genre_names()`) so name-based criteria (`exclude: ["horror"]`) fire on the TMDB path.
  3. `services/recommendation/criteria.py` — IMDb/RT anchor is now **skipped when both scores are unknown (0)**, the TMDB-discover case; TMDB rating gates alone. Keeps the curated IMDb/RT bar when scores are present (config unchanged).
  4. tmdb-only acceptance: `RecommendationService._validate_entry` requires a canonical id (**imdb OR tmdb**, not both); `check_watchlist_duplicate` + `WatchlistService.add_pending` dedup by either canonical id; `Candidate` + `verify_quality_gate` + `jobs/daily_watchlist._to_legacy_candidate` now carry `tmdb_score`/`vote_count`.
- **Manual live run occurred 2026-08-25** (during wrapper testing — NOT a pre-approved live run): added **15 titles** to the real watchlist as pending (7 films incl. recent 2026 release like Avatar Aang/Toy Story 5/Odyssey; 8 series incl. Rick & Morty, Grey's Anatomy, Simpsons, NCIS, CSI). Watchlist now **32 pending** (17 prior + 15 new). Plex gate skipped 10 owned. **Reversible** — remove pending tmdb ids if unwanted.

### Operations
- **Dry-run preview (no writes):** `cd /workspace/projects/rkm-cinema && python3 scripts/add_watchlist_cron.py --dry-run`
- **Live write:** `python3 scripts/add_watchlist_cron.py --count 20` (adds pending + rebuilds dashboard; runs against `/workspace/media/watchlist.json`)
- **Cron:** Hermes job `1965aeb4af2e` (weekly Mon 09:00 AEST). Pause/remove via cron. Wrapper at `~/.hermes/scripts/rkm_watchlist_auto_add.sh`.

---

## ▶ LATEST SESSION (2026-08-25) — Phase 17 API-test/§31 consolidation ✅

**Driving spec:** `RKM_Watchlist_Production_Refactor_Task.md` §31 (Phase 17) — API tests. **Before: 205 backend + 16 frontend green. After: 208 backend + 16 frontend green** (+3 in `tests/test_resource_api.py`). Test-only change; **no redeploy needed** (frontend volume-mounted, backend image unchanged — test files aren't shipped).

### §31 audit result
The §31 endpoint matrix was almost fully covered already by `test_resource_api.py` + `test_api.py`: `GET/POST /api/media/{id}`, `/api/watchlist`, `/api/reconcile`, `/api/jobs`, `/api/quality`, `/api/health` + the behavior asserts (AVAILABLE→can_download false, NOT_REQUESTED→can_download true, watch links exposed). The **one endpoint with zero coverage was `GET /api/library`**. Added 3 tests driving its Plex→Emby→partial fallback chain:

1. `test_library_plex_primary_success` — Plex healthy → full §18 Plex view (counts/recents/urls).
2. `test_library_plex_fail_falls_back_to_emby` — Plex down → Emby fallback, **200** with Emby counts.
3. `test_library_both_providers_fail_is_partial_not_error` — the §31 **"provider failure → partial response"** assert at API level: both providers down → **200 `provider=None available=False`**, never a 5xx (spec §28).

Fakes mock the provider boundary exactly (`PlexLibraryProvider` reaches `service.providers()` — a **method** returning a copy of `_providers`, not a bare attribute — and `provider._plex.get_library_counts()`/`runner._browser_base()`). No LAN, no keys.

### Next
**Phase 18 — Frontend tests/manual verification (spec §32)**: audit the Node suite against the §32 card-state matrix (NOT_REQUESTED/REQUESTED/DOWNLOADING/DOWNLOADED/AVAILABLE renders, can_download-gated Download button, plex/emby-gated buttons, **double-click Download → no duplicate request**). Then Phase 19 observability (§33), Phase 20 config cleanup (§34), Phase 21 frontend API boundary (§35), Phase 22 remove legacy duplication (§36).

---

## ▶ LATEST SESSION (2026-08-25) — Phase 16 testing/§30 consolidation ✅

**Driving spec:** `RKM_Watchlist_Production_Refactor_Task.md` §30 (Phase 16) — test requirements. **Before: 201 backend + 16 frontend green. After: 205 backend + 16 frontend green** (+4 in `tests/test_status.py` + `tests/test_recommendation_engine.py`). Test-only change; **no redeploy needed** (frontend volume-mounted, backend image unchanged — test files aren't shipped).

### §30 audit result
The spec's domain/identity/request/recommendation/watch-link test matrix was **already ~90% covered** by suites added across Phases 4–15 (a deliberate Phase 16 design: the tests came *with* the code). Audited each required case and found **3 genuine gaps**, all closed:

1. **Domain combos** (§30 "library available + downloading/requested → AVAILABLE"): `resolve_status` short-circuits on `in_plex` for every case, but no test pinned the two explicit combos. Added `test_library_wins_over_downloading` (in_plex + qbit_active → AVAILABLE, not DOWNLOADING) and `test_library_wins_over_requested` (in_plex + arr record → AVAILABLE, not REQUESTED).
2. **Watch link, Emby-only** (§30 "Plex link failure + Emby success → Emby button only"): only "Plex failure still AVAILABLE" was tested. Added `test_emby_button_only_when_plex_link_fails` — asserts AVAILABLE is preserved (spec §10: capability problem, never a state downgrade) with `plexUrl=""` and `embyUrl` intact.
3. **Recommendation watchlist exclusion** (§30 "already in watchlist → excluded"): the manager has a `watchlist_duplicates` counter but no test exercised it. Added `test_watchlist_exclusion` (candidate with `imdb_id` already pending → `watchlist_duplicates == 1`, `new_recommendations == 0`).

### Notes
- **Naming:** §30 writes the "nothing" state as `NOT_REQUESTED`; the codebase enum is `NOT_ADDED` (consistent since Phase 4, consumed by the resource API + frontend). Same state, different label — **no rename** to avoid churn across API/frontend. Documented in PROGRESS.
- Existing §30 cases confirmed present: domain available/downloading/requested/nothing + watch-link-availability (`test_status.py`); all identity forms (`test_identity.py`); request suite (`test_request_media.py`); rec pass/fail-rating/fail-genre/in-library/in-history/dup (`test_recommendation_engine.py`); Plex-match + Emby-match links (`test_watch_links.py`).

### Next
_Led into Phase 17 (now done). See the top-of-file Phase 17 block for the current next step._

---

## ▶ LATEST SESSION (2026-08-22) — refactor Phase 9 ✅ (idempotent request command)

**Driving spec: `RKM_Watchlist_Production_Refactor_Task.md`** §15 (Phase 9). THE checklist / §42 order / audit at `docs/ARCHITECTURE_AUDIT.md`. **Baseline before: 117 green. After Phase 9: 128 green** (+11 in `tests/test_request_media.py`, all earlier suites untouched).

### What was built
- **`application/`** — new application (use-case) layer.
- **`application/commands/request_media.py`** — the idempotent request command (spec §15):
  - `RequestMediaCommand.run(media_id, *, title, year)` orchestrates the full §15 flow through the canonical services: parse identity → **re-check library (AVAILABLE, §1.2 library-always-wins)** → **check existing acquistion (ALREADY_REQUESTED)** → **route via `AcquisitionService` + request** → map outcome. No caller knows Radarr vs Sonarr.
  - `RequestMediaResult` dataclass with the exact spec §15 vocabulary: `state` ∈ {AVAILABLE, ALREADY_REQUESTED, REQUESTED, AMBIGUOUS, NOT_CONFIGURED, PROVIDER_UNAVAILABLE} + `success` property + `candidates`/`item` for disambiguation.
  - **Idempotent** — repeated requests hit the ALREADY_REQUESTED guard (or AVAILABLE) and never double-write.
  - `persist=` hook (callable(media_id, provider, state)) for acquisition-state persistence — decoupled so DB wiring lands in Phase 10/13 without changing the command; failures don't break the request.
  - Legacy `plex=`/`radarr=`/`sonarr=` DI args wrapped in providers (§43); new canonical `library=`/`acquisition=` params. Module-level `request_media()` convenience.
- **`domain/enums.RequestMediaState`** — the canonical §15 outcome enum.

### Tests (11 new)
- AVAILABLE when in library; ALREADY_REQUESTED when *arr already holds it; REQUESTED on success (movie→radarr, series→sonarr); AMBIGUOUS; PROVIDER_UNAVAILABLE; NOT_CONFIGURED (no provider / unparseable id); idempotency (no double write); persist hook invoked on REQUESTED; module convenience fn.

### Remaining
- **Phase 18 next — Frontend tests/manual verification** (spec §32): verify each card state (NOT_REQUESTED/REQUESTED/DOWNLOADING/DOWNLOADED/AVAILABLE) renders; Download button only when can_download; Plex button only when Plex link available; Emby button only when Emby link available; **double-click Download creates no duplicate request**. The Node-based frontend suite (`tests/phase11_frontend.test.mjs`, 16 green) already asserts the capability-driven branching + legacy fallback — audit the remaining §32 card-state renders and idempotent-download asserts against it, add what's missing. Then Phase 19 observability (§33 structured logging), Phase 20 config cleanup (§34), Phase 21 frontend API boundary (§35), Phase 22 remove legacy duplication (§36).
- The **scheduler is built + wired** (Phase 14) but **off by default** — to enable the container job loop set `WATCHLIST_SCHEDULER=true` in `.env` (plus `RECONCILE_INTERVAL_MIN`, `DAILY_JOB_HOUR`). The existing host cron (`scripts/daily_recommendations.py`) still runs; it now coexists until you flip to the in-container loop (spec §40 prefers container jobs).

---

## ▶ POST-DEPLOY USER-TESTING (2026-08-22) — 2 bugs found & fixed ✅

Phases 10+11 deployed → user tested adding titles live. Two backend bugs surfaced and fixed (both reproduced against the real stack from the sandbox before the fixes were committed).

### Bug 1 — API down after first Phase 10/11 redeploy (502 on every `/api/*`)
- **Symptom:** after `.\setup-watchlist.ps1`, "API not reachable — check 'docker compose logs api'"; all `/api/*` returned 502; UI showed "Download failed — Retry" for **any** title (not Ex Machina specifically). Frontend loaded (200) because it's volume-mounted; only the API was down.
- **Root cause:** the **`Dockerfile` did not `COPY application` or `COPY infrastructure`** — it only copied `api/ services/ domain/ core/ config/`. Phase 10/11 routes import `application.commands.request_media` (`api/routes/media.py`) and `infrastructure.database.repository` (`api/routes/jobs.py`) **at module load**, so uvicorn died at import (`ModuleNotFoundError: No module named 'application'`) → never bound :8000 → nginx 502. Old image predated these routes, so it only broke on the first build that included them.
- **Fix (commit `2c3cbed`):** added `COPY infrastructure /app/infrastructure` + `COPY application /app/application`. Verified by simulating the container build context (import + boot + `/api/health` `/api/jobs` `/api/reconcile` all 200).
- **Pitfall recorded** in the rkm-watchlist skill: **whenever a route imports a new top-level package, add the matching Dockerfile COPY line.** Sandbox tests pass (dirs exist locally) while the deployed image 502s — reproduce by copying only the Dockerfile's dirs to a temp dir and importing `api.main`.

### Bug 2 — "No Radarr match for imdb:" on There Will Be Blood
- **Symptom:** specific title failed to add; message "no radarr match for imdb".
- **Root cause:** canonical `media_id` is **tmdb-preferred** (`movie:tmdb:7345`), so `request_media` builds an identity with **`imdb_id=None`**. But `RadarrAcquisitionProvider.request` / `add_movie` only ever looked up **by IMDb id** (`identity.imdb_id or ""` → empty string) → empty `imdb:` lookup → no result; title-search fallback also had no title → "No Radarr match". Radarr itself resolved fine by both `imdb:tt0469494` and `tmdb:7345` (verified live) — the bug was the lookup call, not Radarr.
- **Fix (commit `072f46a`):** added `lookup_movie_by_tmdb()` / `lookup_series_by_tvdb()`; `add_movie()`/`add_series()` now accept `tmdb_id`/`tvdb_id` and resolve by TMDB/TVDB when there's no IMDb id (the canonical case), before the title fallback. Closes a quiet §43 inconsistency too (`find()` already used tmdb/tvdb; `request()` only used imdb).
- **Regression tests (2)** in `tests/test_acquisition.py` (tmdb-only movie, tvdb-only series) → **145 green**. **Live-verified** against real Radarr: `movie:tmdb:7345` → *"There Will Be Blood added to Radarr — download starting"*.
- **Outcome:** user re-deployed, tested, and confirmed **working as intended**. No further reports.

---

## ⚡ NEXT SESSION — RESUME EXACTLY HERE (Phase 17 done, next Phase 18)

**Do NOT skip ahead (§42; §43.3 no parallel implementations; §43.7 keep `pytest` green after every phase).**

1. ✅ **Phase 5 — Watch links** (**DONE**, commit `5eb55c9`). 92 green.
2. ✅ **Phase 6 — Canonical status resolver** (**DONE**, commit `bdd4c07`). 103 green.
3. ✅ **Phase 7 — Reconciler** (**DONE**). `services/reconciliation/reconciler.py` → `MediaSnapshot`; `api/routes/status.py` consumes snapshots. 109 green.
4. ✅ **Phase 8 — Acquisition abstraction** (**DONE**). `AcquisitionService` single router; Reconciler + DownloadService rewired. 117 green.
5. ✅ **Phase 9 — Idempotent request command** (**DONE**, commit `f438be3`). `request_media` → `RequestMediaResult`; idempotent guards. 128 green.
6. ✅ **Phase 10 — Resource API** (**DONE**, commit `478278f`). `GET /api/media/{id}` + `POST /api/media/{id}/request` + `/api/watchlist` + `/api/reconcile` + `/api/jobs`; §18 resources; `config`/`health`/`quality` off direct Radarr/Sonarr → `AcquisitionService`; `list_job_runs()`/`record_job_run()`. 143 green.
7. ✅ **Phase 11 — Frontend capability-driven** (**DONE**, this session) — `app.js`/`api.js` render off the §18 resource's `status` + `capabilities{can_download,can_watch}` + `watch.{plex,emby}.available`, **never** `if movie.radarr/plex` (spec §19/§20); NEVER shows Download when AVAILABLE. Primary data path = `/api/watchlist`; request path = `POST /api/media/{id}/request`; `_applyRequestResult` optimistic RES patch. `api.js` added `mediaIdOf()`/`legacyStatusToResource()` + resource methods. **Graceful legacy fallback** to `/api/status`+`/api/download` when new endpoints 404 (old image). `MediaResponse` gained `speed/eta/qbitState/qbitName` so §20 progress detail survives the resource path. Node-based frontend test `tests/phase11_frontend.test.mjs` (16 assertions: AVAILABLE→Watch never Download, capability/watch branching, legacy fallback). **Backend 143 green + frontend 16 green**.
8. ✅ **Phase 12 — Recommendation engine** (**DONE**, this session, commit `a70fb57`) — `services/recommendation/{criteria,generator,ranker,manager}.py`; criteria in `config/recommendations.yaml` (spec §22, config not Python); `CriteriaEngine.evaluate() -> CriteriaResult{passed, score, reasons}`; `CandidateGenerator` (TMDB discover + DI source_fn); `rank()` by score; `RecommendationManager` pipeline (normalize → criteria → dedupe → library → watchlist → history → rank → persist) → §25-shape result, idempotent. Repository `record_recommendation()`/`list_recommendation_history()` on the SQLite `recommendations` table (spec §23, idempotent UPSERT). Legacy `RecommendationService` gates now delegate to the CriteriaEngine (BC shim §43). PyYAML added to requirements. **160 green** (+15 in `tests/test_recommendation_engine.py`).
9. ✅ **Phase 13 — Scheduled jobs** (**DONE**, this session, commit `ec2537a`) — `jobs/base.py` (`JobRunner` records every run to the `job_runs` table, success AND error visible — spec "job execution is recorded"/"failures visible"), `jobs/daily_watchlist.py` (`DailyWatchlistJob` feeds the Phase 12 `RecommendationManager` then adds survivors to the watchlist, idempotent, §25-shaped counts), `jobs/reconcile.py` (`ReconcileJob` → `Reconciler.compute()` tallies statuses, NO new recs — spec §26). `POST /api/jobs/{name}/run` stable command route (thin Route → job, 404 unknown; spec §40 host cron calls a stable command). Dockerfile `COPY jobs`. **168 green** (+8 in `tests/test_jobs.py`).
10. ✅ **Phase 14 — Health / partial failure + scheduling** (**DONE**, this session, commit `11d8484`) — typed per-service errors in `core/exceptions.py` (Plex/Emby/Radarr/Sonarr/QBittorrent/TMDB Unavailable + AmbiguousMedia + MediaNotFound; one failed service never destroys the response — spec §28). `core/http_client.py` real retry + exponential backoff (GET: network+5xx, POST: network only). `services/health.py` `HealthChecker` — canonical per-service structured health (`configured/ok/detail/error`) + `degraded` flag, DI-injectable; `/api/health` thin route keeps BC `services` bool map AND adds `serviceDetail` + `degraded`. `jobs/scheduler.py` opt-in in-container job loop (frequent reconcile at `RECONCILE_INTERVAL_MIN` + daily job at `DAILY_JOB_HOUR`) wired from app startup under `WATCHLIST_SCHEDULER=true` (default off), each run via JobRunner → job_runs. **183 green** (+15 in `tests/test_health_and_scheduler.py`).
| 11. ✅ **Phase 15 — Caching** (**DONE**, commit `54b9d53`). `core/cache.py` `TTLCache` (monotonic TTL, invalidate/clear, thread-safe) — the ONE cache primitive (§43). `TMDBService` metadata long-TTL cache (`config.TMDB_CACHE_TTL`, default 6h; movie/show details + searches). Emby scan TTL corrected 300s→**60s** (`EmbyLibraryProvider.EMBY_SCAN_TTL`). *arr write-path invalidation fixed: `add_movie`/`add_series` now clear the URL-keyed `_http_cache` too (was left stale up to 45s) via `_invalidate_after_write()`; new `clear_cache()`. `invalidate()` hoisted: `LibraryProvider`/`AcquisitionProvider` ABCs (no-op default → fake-safe) + concrete Plex/Emby/Radarr/Sonarr providers + `LibraryService.invalidate()` + `AcquisitionService.invalidate()` + `Reconciler.invalidate()`; `request_media` invalidates acquisition after a successful write. **201 green** (+18 in `tests/test_caching.py`).
| 12. ✅ **Phase 16 — Testing/e2e consolidation** (**DONE**, commit `17d4acf`). **205 green** (201 backend + 4 new in `test_status.py` + `test_recommendation_engine.py`, frontend 16 green). Spec §30 audit: most cases already existed from Phases 4–15; closed 3 real gaps — (a) domain: **in-library + active qBittorrent → AVAILABLE** (`test_library_wins_over_downloading`) and **in-library + *arr record → AVAILABLE** (`test_library_wins_over_requested`), the explicit §30 "library available + downloading/requested" combos; (b) watch-link: **Plex link failure + Emby success → AVAILABLE carries ONLY the Emby button** (`test_emby_button_only_when_plex_link_fails`, spec §10 capability-not-state); (c) recommendation: **already-on-watchlist → excluded** (`test_watchlist_exclusion`, exercises the `watchlist_duplicates` counter). §30 domain/identity/request/rec/watch-link matrix now fully covered (NOT: the codebase enum is `NOT_ADDED`, which §30's wording calls "nothing → NOT_REQUESTED" — same state, different label; no rename so resource API/frontend stay stable).
| 13. ✅ **Phase 17 — API tests** (**DONE**, commit `14ba4b2`). **208 green** (205 + 3 new in `test_resource_api.py`, frontend 16 green). Spec §31 audit: media/request/watchlist/reconcile/health endpoints + the AVAILABLE→can_download false, NOT_REQUESTED→can_download true, watch-links-exposed asserts were already covered by `test_resource_api.py` + `test_api.py`. The one endpoint gap was **`GET /api/library`** — added 3 tests driving its Plex→Emby→partial fallback chain: `test_library_plex_primary_success` (Plex healthy → full Plex §18 view, counts/recents/urls), `test_library_plex_fail_falls_back_to_emby` (Plex down → Emby fallback, still 200 with Emby counts), `test_library_both_providers_fail_is_partial_not_error` — the §31 "provider failure → partial response" assert at API level (both providers down → **200** `provider=None available=False`, never a 5xx; spec §28). Fakes mock the provider boundary (no LAN); exercised `service.providers()` (note: a method returning a copy of `_providers`, not an attribute).
14. ✅ **Phase 18 — Frontend tests/manual verification** (**DONE**, this session) — **16 green**.

---

## ⚡ HOW TO PICK UP WORK HERE (pre-refactor context, superseded for the refactor task)

- **Current refactor source of truth = `RKM_Watchlist_Production_Refactor_Task.md` + `docs/ARCHITECTURE_AUDIT.md`** (this). For the *current live modular backend*, `ARCHITECTURE.md` is the up-to-date map. The **old two-API-layer split is GONE**: the monolithic `api.py` is archived (`archive/api_legacy_monolith.py`) and the live backend is **`uvicorn api.main:app`**. Edit the modular tree — `api/routes/*` (thin), `services/*` (business logic), `domain/*` (state machine + media-type resolver), `infrastructure/database/*` (persistence).
- **Adding a feature** → follow ARCHITECTURE.md §12 ("Adding a feature").
- **Quick checklist:** backend change → edit `api/routes/*` + `services/*` (+ `domain/*` for rules, `infrastructure/database/*` for persistence), then `python -m pytest tests/ -q` (must stay green), then `scripts/rebuild_dashboard.py`, then deploy `.\setup-watchlist.ps1`. Frontend (`api.js`/`app.js`/`app.css`) is volume-mounted — no rebuild needed for UI-only changes.
- **Secrets** live in `/workspace/.env` (canonical). `.env` is git-ignored; use `.env.example` as the template. **Never commit real keys.**

## Latest session (2026-08-21) — curated batch of 8 added ✅

- **Scope:** solid curated batch (movies + series), verified live, added to pending + dashboard rebuilt. User picked this.
- **Ownership gate:** pulled Plex ground truth — **774 movies (incl. 132 kids) + 100 shows** (section keys: Movies 13, Kids 19, TV Shows 15). Candidates were deduped against this BEFORE selection. Many popular titles (Interstellar, Dune Pt2, Parasite, Whiplash, Chernobyl, Severance, Beef already-in-pending, etc.) rejected as owned.
- **Batch added (8):** Knives Out(tt8946378), Blade Runner 2049(tt1856101), Ex Machina(tt0470752), There Will Be Blood(tt0469494) [4 films] + The Expanse(tt3230854), Shōgun(tt2788316), Ozark(tt5071412), Scam 1992(tt12392504) [4 series, Hindi]. → **17 pending total (10 movies / 7 series).**
- **Scores live-verified** via r.jina.ai (IMDb) + RT direct/aggregate (BR2049=88, Shōgun=94, Expanse=85, Ozark=86, Knives=92, ExMachina=86, TWBB=86; Scam 1992 IMDb 9.2, not on RT → rt:0). All pass gates (OR).
- **All 8 TMDB↔IMDb IDs cross-verified OK** (Radarr/Sonarr lookups will resolve). Posters + trailerIds live-validated (HTTP 200 image/*).
- **Wrote via atomic tmp+os.replace, deduped by imdbId, validated pending[].** Rebuilt dashboard → live `:8123` already serves 17 (volume-mounted, no redeploy needed).
- Remaining entry-level gap: **The Night Agent (rt 74 / imdb 7.0) still in pending** — breaks the series gate (needs RT≥85 OR IMDb≥8.0); pre-existing, flag to user if they act on it.

## Latest session (2026-08-21) — Watch-Now links fix (2 backend bugs) ✅ verified live

**Symptom:** page showed "Download" on titles already in the Plex library instead of Watch links.
**Root cause:** `/api/status` **timed out at 30s+**, so the frontend never received `available` state → fell back to Download. The UI already renders Watch Now/Plex/Emby for `available`; it was the backend that never answered.

Two compounding backend bugs (modular API, both deployed):
1. **No Plex library caching** — `PlexService.get_all_movies()/get_all_shows()` did a FULL Plex scan (774→790 movies + 100 shows) on **every entry**. `/api/status` calls `has_media` on all 17 pending → 17 full rescans → blew the window. `_library_cache` was declared but never used. **Fix:** wired it up with a 60s TTL (first scan ~1.3s, cached ~0.2s; full status pass 4.8s). Committed `820f772`.
2. **Sonarr None crash** — for unmatched TV entries, `stats = rec.statistics` ran even when `rec is None` → `AttributeError`. **Fix:** `getattr(rec, "statistics", None) or {}`. Committed `3d50b4b`.

**Verified against LIVE services from sandbox:** 17 entries resolved in 4.8s → 2 downloading / 8 available / 7 not_added. Available titles carry correct deep links (`app.plex.tv/.../7780f377...` + Emby `#!/item?id=…`). Tests: 39 pass (ignoring fastapi-only modules).

**⚠️ DEPLOY REQUIRED on RKM-HP** to ship both fixes into the running image:
```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\setup-watchlist.ps1
```
Then hard-refresh the page (Ctrl+Shift+R). Verify `/api/status` returns <5s and owned titles show Watch Now instead of Download.

## Latest session (2026-08-21) — Watch deep-links fixed to point at server web UI ✅

**Symptom:** Plex/Emby Watch links "don't open anything."
**Root cause:** Plex deep-links pointed at **`app.plex.tv`** (Plex's cloud app) which requires account login + remote relay and rarely auto-opens the item. Also `plexKey` was set to the full URL instead of the numeric ratingKey. Emby already deep-linked into the local server's web UI correctly.
**Fix (commit `ecf4b58`):**
- **Plex links now point at the server's OWN web UI** on the browser-reachable Tailscale HTTPS host: `https://rkm-hp.tail8d5e8.ts.net:32400/web/index.html#!/server/{machineId}/details?key=/library/metadata/{ratingKey}` — **raw path, not `%2F`-encoded** (encoding broke Plex's hash router). Same idea Emby already uses. No cloud relay.
- **plexKey** now carries the numeric ratingKey (`320819`), not a URL.
- **Config-driven browser endpoints:** new optional `PLEX_BROWSER_URL` / `EMBY_BROWSER_URL` in `.env`; default safely to the Tailscale host (browser-reachable) even unset. LAN `PLEX_URL`/`EMBY_URL` (backend/API) are NOT used for deep links.
- `api/routes/library.py` hardcoded `app.plex.tv` + Emby URL cleaned up to the same config-driven builder.
- **New regression tests `tests/test_watch_links.py`** (7) + 2 library-cache tests in `test_plex_ownership.py` → **46 pure-logic tests pass**. Asserts: no app.plex.tv, raw `/library/metadata/`, numeric plexKey, Tailscale default fallback, search fallback, cached-scan reuse.
- **Live-verified:** available titles now emit `https://rkm-hp.tail8d5e8.ts.net:32400/web/index.html#!/server/7780f…/details?key=/library/metadata/320819` (web UI HTTP 200) + Emby item links.

**⚠️ DEPLOY REQUIRED on RKM-HP** (same as above): `cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema; .\setup-watchlist.ps1`, then hard-refresh.
**Optional .env addition (not required — defaults work):** `PLEX_BROWSER_URL=https://rkm-hp.tail8d5e8.ts.net:32400` and `EMBY_BROWSER_URL=https://rkm-hp.tail8d5e8.ts.net:8096` if you want them explicit.

## ⚡ HOW TO PICK UP WORK HERE

- **Start with `ARCHITECTURE.md`** — it's the up-to-date map. The **old two-API-layer split is GONE**: the monolithic `api.py` is archived (`archive/api_legacy_monolith.py`) and the live backend is now the **modular FastAPI app** (`uvicorn api.main:app`). Edit the modular tree — `api/routes/*` (thin), `services/*` (business logic), `domain/*` (state machine + media-type resolver). There is exactly ONE implementation of each rule.
- **Adding a feature** → follow ARCHITECTURE.md §12 ("Adding a feature").
- **Quick checklist:** backend change → edit `api/routes/*` + `services/*` (+ `domain/*` for rules), then `python -m pytest tests/ -q` (must stay green), then `scripts/rebuild_dashboard.py`, then deploy `.\setup-watchlist.ps1`. Frontend (`api.js`/`app.js`/`app.css`) is volume-mounted — no rebuild needed for UI-only changes.
- **Secrets** live in `/workspace/.env` (canonical). `.env` is git-ignored; use `.env.example` as the template. **Never commit real keys.**

## Latest session (2026-08-21) — production-grade refactor ✅

**Goal:** eliminate the two-backend problem and make the modular architecture the single source of truth.

- **Domain layer added (`domain/`):** `enums.py` (`MediaType`, `MediaStatus`, `DownloadResultState`), `models.py` (`DownloadResult`), `state_machine.py` (`resolve_status()` — the ONLY availability resolution: Plex→available, *arr hasFile→downloaded, qBittorrent→downloading, *arr record→requested, else not_added), `resolver.py` (`resolve_media_type()` — single movie/tv resolver).
- **Services stabilized (DI):** all services now accept injectable `config`/`http` (testable, no real LAN). Extracted **`QBittorrentService`** and **`MediaStatusService`** from the fat status route.
- **Routes thinned:** `status.py` delegates to `MediaStatusService`; `download.py` delegates to new **`DownloadService`** (routing + add + title-fallback + cross-service fallback + "pick one" ambiguity → typed `DownloadResult`). Added **`/api/plex/thumb`** route (via `PlexService.get_thumb`) so modular cutover doesn't break thumbnails.
- **Fixed latent bugs found by tests:** `UnboundLocalError` in both `RadarrService.add_movie` & `SonarrService.add_series` when no quality-profile override set; silent-guess ambiguity now returns **`ambiguous`** instead of picking a wrong title; `WatchlistService.update_status` to `recommended` now moves the entry out of pending into history.
- **Docker migration (Phase 5):** `Dockerfile` now copies `api/ services/ domain/ core/ config/` + `requirements.txt` and runs **`uvicorn api.main:app`**. `WatchlistService` auto-resolves `/app/watchlist.json` (container) vs `/workspace/media/watchlist.json` (sandbox). Verified the copied Docker tree imports and exposes all 8 endpoints.
- **Frontend (Phase 7):** new **`api.js`** centralized API client (`API.getJSON/getStatus/download/...`); `app.js` delegates all `/api/*`+`/dashboard-data.json` calls to it. `api.js` wired into `index.html` + `dashboard.html`. No rendering/behavior change.
- **Legacy removed (Phase 6):** `api.py` → `archive/api_legacy_monolith.py` (+ `archive/README.md`).
- **Tests: 47 passing, all mockable (no live LAN):** domain state machine, media-type resolver, Radarr/Sonarr routing + title fallback + ambiguity, download status, error handling, Plex ownership, duplicate prevention, trailer validation, recommendation pipeline, and API endpoints (`tests/test_api.py`).

**⚠️ DEPLOY REQUIRED:** all of the above is committed but the running site is still the OLD monolithic image. Run `.\setup-watchlist.ps1` on RKM-HP to build & start the modular backend (`uvicorn api.main:app`). Then verify `/api/health`, `/api/config`, `/api/status`, `/api/library`, `/api/plex/thumb`, download flow, and Plex/Emby watch buttons per ARCHITECTURE.md §11.

---

## Previous sessions

## Latest session (2026-08-20) — 9 fixes

### 8f. Emby links — HTTPS scheme fix ✅
- **Bug:** Emby deep links were built with `http://`, but the Tailscale Emby server is **HTTPS-only** — so clicking returned "Client sent an HTTP request to an HTTPS server" (400). Confirmed: `http://rkm-hp.tail8d5e8.ts.net:8096` → 400, `https://...` → 200.
- **Fix:** all Emby URL builders (legacy `api.py` `_emby_url_for`, library `urls.emby`, modular `services/plex.py` `emby_url_for`, `api/routes/library.py`) now use `https://rkm-hp.tail8d5e8.ts.net:8096/web/index.html`. Verified: Banshees → `https://.../#!/item?id=67719&serverId=b54476...`.

### 8e. Emby Watch buttons — fixed deep-link format ✅
- **Bug:** Emby watch buttons used the search path `#!/search/<title>`, which doesn't deep-link to the item. The correct format is `#!/item?id=<itemId>&serverId=<serverId>`.
- **Fix:** backend now resolves the Emby **item id** for a title (via `/Users/<id>/Items?searchTerm=...`) and the **server id** (`/System/Info/Public` → `b54476cfb9054f389fcc0ce450f17c60`), then builds `#!/item?id=<id>&serverId=<sid>`.
- **Verified** for The Banshees of Inisherin → `#!/item?id=67719&serverId=b54476...`, exactly matching the URL Plex/Emby generates when you click the movie. Applies to legacy `api.py` (`_emby_url_for`, library `recent[]`), modular `services/plex.py` (`emby_url_for`/`_emby_item_id`/`_emby_server_id`), and frontend `libraryCard()` (uses backend-provided `embyUrl`).
- Note: Plex-library recents that are *seasons* resolve to the parent series item id in Emby (e.g. id 38373) — acceptable; movie/series top-level items resolve correctly.

### 8d. Plex is the source of truth for status ✅
- **Bug:** a title in Plex but with a stale/missing *arr record (e.g. `not_added` in Radarr yet present in Plex) showed `not_added`/`requested` because the status logic only reached `available`/`downloaded` when *arr reported `hasFile` — it never checked Plex first.
- **Fix (`api.py` + modular `api/routes/status.py`):** at the top of each entry evaluation, if the title exists in Plex it is immediately `available` with correct `plexUrl`/`embyUrl`, regardless of what Radarr/Sonarr report. Only titles *not* in Plex fall through to the *arr/qBittorrent pipeline.
- Added a ~45s-cached Plex library lookup (`_plex_library`) so repeated per-title checks don't re-scan 787 movies on every request (first status call ~2.4s, subsequent ~0.4s).
- **Verified:** Spider-Man, The Bear, Banshees, Mandalorian all now show `available` with working Plex links (they were `not_added` before).

### 8c. Plex Watch buttons — fixed deep-link format ✅
- **Two bugs in the generated Plex URLs:** (1) used the LAN host `192.168.65.254:32400` as the server id instead of the Plex **`machineIdentifier`** (`7780f37754c6ff144dd28c42b052e0187301dba1`); (2) passed a bare `key=320126` instead of the **URL-encoded `/library/metadata/320126`** (`%2Flibrary%2Fmetadata%2F320126`).
- **Fix:** backend now fetches and caches the machineIdentifier (`/identity`), builds `key=%2Flibrary%2Fmetadata%2F<ratingKey>`, and serves the correct `plexUrl` per item from `/api/library`. Verified the generated URL for The Mandalorian (key 320126) **exactly equals** the URL Plex itself produces when you click the show.
- Applies to: legacy `api.py` (`_plex_emby_urls`, library `recent[]`), modular `api/routes/status.py` + `services/plex.py` (new `server_id()`/`find_item()`/`plex_url_for()` helpers), and frontend `libraryCard()` (now uses the backend-provided `plexUrl` instead of building it client-side).

### 8b. Emby integration ✅
- Added `EMBY_URL=http://192.168.65.254:8096` + `EMBY_API_KEY` to `/workspace/.env` (user-provided key). The server at :8096 is **Emby** v4.9.5 (not Jellyfin).
- **Verified Emby API:** `Items/Counts` → **824 movies / 103 series / 5078 episodes** (shares the same library as Plex).
- Legacy `api.py`: added `EMBY_URL`/`EMBY_API_KEY` loading; `/api/library` now tries **Plex first** (richer view: recents + thumbnails + ratingKey deep links), then falls back to **Emby** for counts. Health/config report `emby: true`.
- Frontend: library cards show **both "▶ Plex" and "▶ Emby"** deep links; empty-state text updated. Since Plex and Emby share the library, Plex-primary gives the full view and Emby is a fully-working fallback.

### 8. Library fetch from Plex + click-to-watch buttons ✅
- **Root cause:** legacy `/api/library` called Plex **without** the `Accept: application/json` header, so Plex returned XML and JSON-parse failed → endpoint always returned `provider:null` (no library). 
- **Fix (`api.py`):** added the JSON header to all Plex library calls. Verified live: `/api/library` now returns real Plex data — **787 movies / 98 shows / 8 recent** with `ratingKey`.
- **Frontend (`app.js`):** library cards are now **clickable** — each recent item shows **"▶ Plex"** and **"▶ Emby"** buttons that deep-link to the item: Plex `app.plex.tv/desktop/#!/server/<host>/details?key=<ratingKey>` and Emby search via Tailscale MagicDNS. Thumbnails render through a new server-side proxy `/api/plex/thumb` (keeps the token secret; verified 200).
- **Emby note:** the server at `:8096` is **Emby** (v4.9.5) and now has a working API key (`EMBY_API_KEY` in `.env`), so both the Plex-primary library view **and** Emby fallback counts work — and every library card carries "▶ Plex" and "▶ Emby" watch buttons.

### 7. Watch Now buttons live-fix + Sonarr TV fallback ✅
- **`api.py` (legacy) status was returning HTTP 500** → that's exactly why no Plex/Emby buttons appeared: a `NameError` (`plexUrl` used as an unquoted dict key instead of `"plexUrl"`) broke `/api/status` for every request, so the frontend never got status data and never rendered the buttons. Fixed to string keys; verified `/api/status` now returns `available` with real `plexUrl`/`embyUrl` for in-Plex titles (Banshees, Mandalorian).
- **The Bear → "No Sonarr match for imdb"** — same root cause as the Radarr title: Sonarr's `imdb:tt10157119` lookup returns **0 results**, but a title search finds it (**tvdb 403294**). Added the same **title/year fallback** to `SonarrService.add_series` (+ `search_series`) and legacy `sonarr_add`. Verified: `The Bear` → added to Sonarr via title fallback (tvdb 403294).
- Card, hero, and modal buttons all render Watch-on-Plex/Emby for `available` state (frontend was already correct and volume-mounted).

### 5. Missing posters — TMDB artwork backfill ✅
- **Root cause:** many watchlist entries carried **fabricated/stale poster URLs** (e.g. `...9x9x9x9xX.jpg`, `...U9g3g7.jpg`) that 404 — the artwork was never validated against TMDB.
- **Fix:** new `scripts/backfill_tmdb_artwork.py` re-fetches the authoritative **poster + backdrop** from TMDB by each entry's `tmdbId` (movie or tv), updates `/workspace/media/watchlist.json` (the real API data source at the workspace root, per docker-compose mount), and rebuilds the dashboard.
- **Verified:** all 9 entries now have valid 200-returning TMDB posters. Also fixed a crash bug: `TMDBService` was raising `ServiceUnavailableError` with the wrong signature.

### 5b. Add-time self-healing posters ✅
- **Root cause:** `RecommendationService.enrich_metadata` copied `candidate.poster` verbatim and never overwrote it with TMDB — so any candidate carrying an empty/fabricated poster leaked straight into the watchlist at add-time.
- **Fix (`services/recommendations.py`):** enrichment now always sets `entry.poster` from the authoritative TMDB `poster` (movie or show), guarded by a new `_is_valid_poster()` — a real HEAD request requiring HTTP 200 + `image/*` content type. Fabricated/dead URLs are rejected.
- **Verified:** a candidate with `poster=...FAKE...9x9x9x9xX.jpg` is healed at enrich time → real `w500/6izwz...` TMDB poster. `_is_valid_poster`: valid→True, fabricated→False, empty→False.


### 4. "No Radarr match" — stale IMDb ID fallback (title search) ✅
- **Root cause:** the watchlist entry for *The Zone of Interest* had stale/wrong IDs — Radarr's `imdb:tt2197033` and `tmdb:457780` both returned **0 results**, while a **title search** found the correct movie (The Zone of Interest, 2023, **tmdb 467244**, imdb tt7160372).
- **Fix (`services/radarr.py`, `api.py`, `api/routes/download.py`, `api/models.py`, `app.js`):** when the stored IMDb lookup resolves nothing (or ambiguously), the backend now falls back to a **title (+year) search** in Radarr. Exact title/year match is preferred; multiple matches return a numbered "pick one" list with title · year · tmdbId for disambiguation (HTTP 404) instead of silently guessing or failing.
- `DownloadRequest` now carries optional `title`/`year`; the frontend sends them.
- Verified live: `tt2197033` + title/year → resolved to tmdb 467244 and added to Radarr.

### 1. YouTube trailer — NO API key required ✅
- **`services/youtube.py` rewritten** to scrape `youtube.com/results` directly (no YouTube Data API key).
- Parses `ytInitialData` JSON + fallback regexes; scores candidates for "official trailer" indicators, studio/distributor channel names, and verified badges; penalizes fan/noise videos.
- `has_youtube()` always True; `get_embed_url()` builds `youtube.com/embed/<id>` for **in-app playback**.
- Verified live: `Arrival` → `oGI9hSl0q-w` (Paramount official trailer); `Dune: Part Two` → `Way9Dexny3w` (official trailer).
- Frontend trailer button now **plays in-app** (opens the modal iframe) instead of opening a new YouTube tab.

### 2. Download routing — movies → Radarr, TV → Sonarr ✅
- Root cause: routing trusted the frontend `type` field; a missing/wrong type could send a movie to Sonarr.
- **`api.py` (legacy)**: added `_resolve_download_type()` — explicit type → watchlist `isSeries` → Radarr lookup (movie) then Sonarr lookup (series), defaulting to movie. A movie can no longer reach Sonarr.
- **`api/routes/download.py` (modular)**: same authoritative resolver + Radarr/Sonarr cross-fallback ("No Sonarr match" → retry as Radarr; "No Radarr match" → retry as Sonarr).
- Also fixed a latent bug: `RadarrService._get` / `SonarrService._get` now accept `timeout` (was raising `unexpected keyword argument` in modular download).
- Verified: `tt2543164` (Arrival, movie) → Radarr; `tt10157119` (The Bear, tv) → Sonarr; unknown → defaults to movie.

### 3. Plex/Emby "Watch" buttons for available content ✅
- **Legacy `api.py` status** now computes an `available` state (Radarr `hasFile`/Sonarr episodes downloaded AND present in Plex) and includes `plexUrl` + `embyUrl` deep links (Plex search/detail + Emby via Tailscale MagicDNS `rkm-hp.tail8d5e8.ts.net:8096`).
- **`app.js`**: hero + modal download buttons now render "Watch on Plex" / "Watch on Emby" / both for `available` state (cards already did).
- `services/emby.py` added as a service; config supports `EMBY_URL`/`EMBY_API_KEY` (`has_emby()`).

**Remaining before deploy:** run `setup-watchlist.ps1` on RKM-HP to ship backend changes; frontend files (app.js) go live via volume mount immediately.

## Status (2026-08-19)

- **NEW MODULAR ARCHITECTURE DEPLOYED**: Complete service layer with clean separation of concerns
  - `config/settings.py` - Centralized Config class (single source of truth for all env vars)
  - `core/http_client.py` - Shared HTTP client with caching, retry, structured errors
  - `core/logging.py` - Structured JSON logging
  - `core/exceptions.py` - Custom exception hierarchy
  - `services/plex.py` - Plex ownership verification (ground truth)
  - `services/radarr.py` - Movie management + quality profiles
  - `services/sonarr.py` - TV series management
  - `services/trailers.py` - TVDB v4 + TMDB trailer enrichment
  - `services/watchlist.py` - CRUD + state machine (atomic writes)
  - `services/recommendations.py` - Pipeline: category → gates → Plex → dedupe → enrich → add
  - `api/main.py` - FastAPI app factory with modular routes
  - `api/routes/` - Health, config, status, download, search, library, quality endpoints
  - `scripts/daily_recommendations.py` - Single orchestration entry point for daily cron
  - `scripts/auto_complete.py` - pending → recommended transition (hasFile + Plex)
  - `scripts/enrich_trailers.py` - Standalone trailer enrichment
  - `scripts/rebuild_dashboard.py` - Refactored build pipeline using services
  - Comprehensive test suite in `tests/`

- **Previous v2 stack still live** (needs redeploy to pick up new architecture):
  - `api` (FastAPI, :8000, secrets server-side) + `web` (nginx :8123)
  - qBittorrent status integration — DONE (code, needs redeploy)
  - PLEX_TOKEN in .env (user provided 2026-08-18)
  - .env consolidated: canonical `/workspace/.env` (= `D:\.env`); `/workspace/media/.env` is symlink
  - ⚠ Radarr indexers ALL down — The Father + 5 others at "requested"

- **7 pending titles** (same as before):
  | # | Title | Year | State |
  |---|---|---|---|
  | 0 | Arrival | 2016 | requested (waiting on indexers) |
  | 1 | The Grand Budapest Hotel | 2014 | requested (waiting on indexers) |
  | 2 | Mad Max: Fury Road | 2015 | requested (waiting on indexers) |
  | 3 | Prisoners | 2013 | requested (waiting on indexers) |
  | 4 | Nightcrawler | 2014 | requested (waiting on indexers) |
  | 5 | Whiplash | 2014 | not_added (user hasn't approved) |
  | 6 | The Father | 2020 | requested (waiting on indexers) |

- **Plex is ground truth for ownership** (user-ratified): all services now use Plex FIRST via PLEX_TOKEN

## New Architecture (modular service layer)

```
┌─────────────────────────────────────────────────────────────────┐
│                        DAILY CRON ORCHESTRATOR                   │
│  (scripts/daily_recommendations.py - single entry point)        │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         SERVICE LAYER                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   PlexSvc   │  │  RadarrSvc  │  │  SonarrSvc  │             │
│  │ (ownership) │  │  (movies)   │  │   (tv)      │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  RecoSvc    │  │ TrailerSvc  │  │ WatchlistSvc│             │
│  │ (recs+gates)│  │ (TVDB/TMDB) │  │  (CRUD+FSM) │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CORE / INFRASTRUCTURE                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Config    │  │    HTTP     │  │  Logging    │             │
│  │  (central)  │  │  (client)   │  │  (struct)   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EXTERNAL SERVICES                           │
│  Plex · Radarr · Sonarr · Prowlarr · TVDB · TMDB · qBittorrent  │
└─────────────────────────────────────────────────────────────────┘
```

## File inventory (`/workspace/projects/rkm-cinema/`)

| File | Purpose |
|---|---|
| `config/settings.py` | **Centralized Config class** - all env vars, validation, defaults |
| `core/http_client.py` | Shared HTTP client with caching, retry, structured errors |
| `core/logging.py` | Structured JSON logging setup |
| `core/exceptions.py` | Custom exception hierarchy (ServiceUnavailableError, DuplicateError, etc.) |
| `services/base.py` | BaseService with common patterns |
| `services/plex.py` | Plex ownership verification (has_movie, has_show, has_media) |
| `services/radarr.py` | Radarr movie management, quality profiles, queue, indexer health |
| `services/sonarr.py` | Sonarr series management, quality profiles, queue |
| `services/trailers.py` | TVDB v4 + TMDB trailer enrichment, validation |
| `services/watchlist.py` | Watchlist CRUD, state machine, atomic persistence |
| `services/recommendations.py` | Recommendation pipeline (category, gates, Plex check, enrich) |
| `services/__init__.py` | Unified exports |
| `api/main.py` | FastAPI app factory |
| `api/models.py` | Pydantic request/response models |
| `api/routes/health.py` | GET /api/health |
| `api/routes/config.py` | GET /api/config |
| `api/routes/status.py` | GET /api/status (per-title state + qBit progress) |
| `api/routes/download.py` | POST /api/download (Radarr/Sonarr + qualityProfileId) |
| `api/routes/search.py` | GET /api/search (watchlist + TMDB) |
| `api/routes/library.py` | GET /api/library (Plex/Jellyfin) |
| `api/routes/quality.py` | GET /api/quality (quality profiles for download chooser) |
| `scripts/daily_recommendations.py` | **Daily cron orchestration** - single entry point |
| `scripts/auto_complete.py` | **Auto-complete** - pending → recommended when hasFile + Plex |
| `scripts/enrich_trailers.py` | Trailer enrichment (probe, dry-run, enrich) |
| `scripts/rebuild_dashboard.py` | Dashboard build using WatchlistService |
| `tests/test_*.py` | 7 test modules covering critical workflows |
| `app.js` / `app.css` | Frontend (volume-mounted, live immediately) |
| `index.html` / `dashboard.html` | Slim shell loading app.js |
| `Dockerfile` / `docker-compose.yml` | api image + nginx web |
| `setup-watchlist.ps1` | Windows deploy (rebuild + up) |
| `nginx/default.conf` | no-store headers; `/api/` → api:8000 |
| `watchlist.json` | **Data** — at `/workspace/media/watchlist.json` |
| `ARCHITECTURE.md` | Detailed architecture documentation |
| `README.md` | Project overview, setup, usage |
| `PROGRESS.md` | This file |

## Config — `.env`

Canonical: **`/workspace/.env`** (= `D:\.env`). `/workspace/media/.env` is a symlink. Variable names only:

`MEDIA_HOST, RADARR_URL, RADARR_API_KEY, SONARR_URL, SONARR_API_KEY, PROWLARR_URL, PROWLARR_API_KEY, PLEX_URL, PLEX_TOKEN, JELLYFIN_URL, JELLYFIN_API_KEY, BROWSER_RADARR_URL, BROWSER_SONARR_URL, QBITTORRENT_URL, GITHUB_TOKEN, RADARR_QUALITY_PROFILE_ID, SONARR_QUALITY_PROFILE_ID, TMDB_API_KEY, TVDB_API_KEY`

**MISSING (next session):**
- `TVDB_API_KEY` — **user has this key**; paste into `.env` → `python3 scripts/enrich_trailers.py --probe` → enrich → rebuild.
- `TMDB_API_KEY` — optional; second trailer source + poster fallback.

---

## FEATURE 1: Auto-complete (pending → available when downloaded + in Plex) ✅ COMPLETE

**Goal:** when a pending title's file lands (qBittorrent 100% → Radarr import → Plex scan), auto-move it from `pending[]` to `recommended[]` with a completion date, and notify Rajeev in chat. No manual "drop N" needed.

**Implementation Completed:**

1. ✅ **API status endpoint** - Detects `available` state when both *arr hasFile AND Plex has title
   - Movies: `rec.hasFile and in_plex` → `state: "available"` with Plex/Emby deep links
   - TV Series: `downloaded and in_plex` → `state: "available"` with deep links
   - Keeps `downloaded` for content in *arr but not yet scanned into Plex

2. ✅ **Frontend rendering** - Updated `app.js`:
   - `STATE_LABEL` includes `available: 'Available'`
   - `dlStateMarkup()` shows "Available in Plex" for available state
   - `downloadButton()`, `heroDownloadButton()`, `downloadButton()` all handle `available` state
   - `rerenderDownloadButtons()` updated for available state styling
   - Watch Now dropdown functionality added for Plex/Emby links

3. ✅ **Auto-complete integration** - Updated `scripts/daily_recommendations.py`:
   - Runs `auto_complete.py` FIRST before processing new recommendations
   - Reports auto-completed entries in results
   - Returns completion count for cron logging

**Next Steps:**
1. Deploy new architecture - Run `setup-watchlist.ps1` on RKM-HP
2. Verify PlexService integration against live Plex
3. Test `/api/status` against known-owned titles
4. Verification pass - Rebuild dashboard and confirm no regressions## NEXT SESSION — FEATURE 6: Download quality choice (1080p vs 4K before adding)

**Goal:** when clicking Download on a card, let Rajeev pick the quality profile (e.g. 1080p vs 2160p/4K) instead of silently using the default.

**IMPLEMENTATION STATUS: Backend COMPLETE in new architecture**

The following are **already implemented**:

1. ✅ **RadarrService.get_quality_profiles()** - Returns profiles with id, name, items
2. ✅ **SonarrService.get_quality_profiles()** - Returns profiles with id, name, items
3. ✅ **RadarrService.add_movie(imdb_id, quality_profile_id)** - Accepts optional qualityProfileId
4. ✅ **SonarrService.add_series(imdb_id, quality_profile_id)** - Accepts optional qualityProfileId
5. ✅ **API endpoint GET /api/quality** - Returns Radarr + Sonarr profiles (no secrets)
6. ✅ **API endpoint POST /api/download** - Accepts `qualityProfileId` in request body
7. ✅ **DownloadRequest model** - Includes `qualityProfileId: int | None`

**Remaining tasks (do in order):**

1. **Deploy new architecture** - Run `setup-watchlist.ps1` on RKM-HP
2. **Frontend — quality chooser on Download** - In `app.js`:
   - Fetch `/api/quality` once (cache in `QUALITY`)
   - On `doDownload`, if entry not yet added and profiles > 1 → show chooser (modal/dropdown): "1080p (HD-720p profile)" / "4K" / "Default"
   - Remember last pick in `localStorage` (`rkm_qp`) as default
   - Pass `qualityProfileId` in `postDownload` body
   - Keep single-click path when only one profile exists
3. **Quality profile hygiene** - Check Radarr has sensible 1080p and 2160p profiles (see `progress_download_selection.md` — profile 3 = "HD-720p", 720p/1080p capped 2GB; 4K profile may not exist yet)
4. **Verification pass** - Add test title with each profile choice → confirm `/api/v3/movie` reflects chosen `qualityProfileId`; rebuild dashboard; live-curl

---

## FEATURE 7: Watch Now - Plex/Emby deep links ✅ COMPLETE

**Goal:** When a movie/series reaches `available` state (downloaded + in Plex), replace the "Download" button with a **"Watch Now"** action that offers both **Plex** and **Emby** deep links using Tailscale MagicDNS URLs.

**Implementation Completed:**

1. ✅ **API Model Update** (`api/models.py`):
   - Added `plexUrl: Optional[str]` and `embyUrl: Optional[str]` to `StatusEntry` model

2. ✅ **API Endpoint Enhanced** (`api/routes/status.py`):
   - Extended `/api/status` to compute Plex deep links when `rec.hasFile and in_plex` is true
   - Generate Plex deep link via ratingKey if available, otherwise search link
   - Generate Emby deep link via Tailscale MagicDNS
   - Returns `plexUrl` and `embyUrl` fields in status response

3. ✅ **Frontend Handler** (`app.js`):
   - Enhanced `downloadButton()` to show "Watch Now ▼" dropdown for available state
   - Handles both Plex and Emby URLs with data attributes
   - Click handler processes `watch-plex`, `watch-emby`, and `watchnow` actions
   - Opens links in new tab

4. ✅ **Build Script Fixed** (`scripts/rebuild_dashboard.py`):
   - Fixed to work with current `WatchlistEntry` model
   - Added safe defaults for missing fields

**Priority:** High — completes the lifecycle UX (Recommended → Download → Available → Watch)## TVDB v4 integration plan (resume here)

Endpoint shapes NOT yet live-verified from the sandbox (oEmbed blocked; use `scripts/enrich_trailers.py --probe` first):

1. `POST https://api4.thetvdb.com/v4/login` body `{"apikey":"<TVDB_API_KEY>"}` → `data.token` (JWT ~30 days). Cache to `/workspace/media/.tvdb_token`; re-login on expiry.
2. `GET /v4/search?query=<title>&type=movie|series&year=<year>` → match `remoteids[]` to known `imdbId` → TVDB `id`.
3. `GET /v4/movies/{id}/extended` or `/v4/series/{id}/extended` → `artworks`, `trailers`, `genres`, `runtime`, `overview`.
4. Extract YouTube ID from `watch?v=ID` / `youtu.be/ID` / `/embed/ID`. Only YouTube embeds; else search-link fallback.
5. Fallback: TMDB `/movie/{tmdbId}/videos` (site=YouTube, type=Trailer).
6. Rule: NEVER write an unverified `trailerId` — empty → search link.

**Implemented in `services/trailers.py`** - Complete with token caching, search, extended, trailer extraction, validation.

---

## Operations

- **Rebuild dashboard:** `cd /workspace/projects/rkm-cinema && python3 scripts/rebuild_dashboard.py`
- **Rebuild + verify:** `python3 rebuild_verify.py` (legacy, still works)
- **Repair if corrupted:** `python3 fix_all.py` (legacy)
- **TVDB enrich:** `python3 scripts/enrich_trailers.py` (probe first: `--probe`)
- **Auto-complete:** `python3 scripts/auto_complete.py [--dry-run]`
- **Daily recommendations:** `python3 scripts/daily_recommendations.py [--candidates file.json] [--dry-run]`
- **Deploy (Windows PowerShell):** `cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema; .\setup-watchlist.ps1` — REQUIRED to ship api.py changes (image rebuild); frontend files go live via volume mount immediately.
- **Run tests:** `cd /workspace/projects/rkm-cinema && pytest tests/ -v`
- **Cron:** job `0cd1d3c2c872` "RKM Watchlist daily rec", `0 18 * * *` AEST, LLM-driven, loads `weekly-media-recommendations` skill. Prompt updated 2026-08-18: Plex-first library check, r.jina.ai score verification, qBittorrent-aware. Approval always the user's — cron never POSTs to *arr.

---

## Known issues / next-session checklist

1. **DEPLOY PENDING (urgent — unblocks 504 fix + Suggest):** run `cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema; .\setup-watchlist.ps1` on RKM-HP. Bakes the API-side 504 fixes (`compute_cached`, Sonarr-tmdb→tvdb) **and** the Suggest route (`api/routes/suggest.py` is committed now). Until deployed the running container still has the old slow reconciler + a 404 on `/api/suggest`. Web-side (app.js/app.css: 60s poll, hover buttons, search history, add-to-app) go live via the volume mount without a rebuild.
2. **Radarr/Sonarr indexers may still be down** — requested titles sit "requested"/"Waiting — search indexers down" until indexers recover (AU s115a). Not an app bug. The 504/status slowness is now decoupled from this, but a still-down indexer means downloads won't start.
3. **TVDB_API_KEY not in .env** — user has it; optional for TMDB-first tvdb resolution (fallback only).
4. **Verify post-deploy:** confirm `/api/watchlist` + `/api/status` return fast (<1s on a warm poll, ~18s after a write/expiry), `/api/suggest` returns 200, and TV suggestion-adds appear under **TV Shows**.
5. **Test Suggest search history persistence** across reloads (localStorage `rkm_suggest_history`) + hover-only card buttons on desktop vs always-visible on touch.
6. **Monitor the reconcile-cache invalidation on acquisition writes** — after a download request, next poll should reflect it quickly (mtime + route-clear).
7. **Host path mapping:** sandbox `/workspace` = `D:\hermes_agent\hermes-workspace` (9p mount, NOT `D:\media`). Any doc/skill mentioning `D:\media\...` is stale.
8. **Order of next-session work:** (a) push commits to GitHub, (b) deploy, (c) verify the 3 UX items above, (d) legacy-cleanup of old scripts now that suggest + resource API are the path.

---

## Lessons log

- **2026-08-28 (auto-add + dedup):**
  - **A single-source TMDB discover plateaus fast.** `discover/*` with only `popularity.desc` always returns your owned trending titles — the op looks "broken" (0 added) when it's really converging. Rotate strategies (popular/top-rated/hidden-gems/recent) so fresh candidates keep flowing.
  - **Never gate a title-matching fallback on the candidate carrying an id.** `PlexLibraryProvider.find()` skipped its fuzzy-substring fallback for id-bearing candidates, assuming id absence was authoritative — but Plex items often expose **no provider ids** (`provider_ids()={}`), so an owned title with a title variant (`Batman: The Dark Knight` vs `The Dark Knight`) was treated as unowned and re-added. Run the substring fallback as a genuine last resort for ANY candidate still lacking a match.
  - **Treat Plex `year=0` as "unknown", not a hard mismatch.** `matches()` rejected a title match whenever `self.year != candidate_year` — including year=0 (unknown). Only reject when the Plex year is actually known. Explicitly: `if year is not None and self.year and self.year != year`.
  - **TMDB discover yields no IMDb rating** — need `external_ids` on the detail call + a lookup (OMDb free tier) to show IMDb scores. Keep it optional/manually-guarded so Mocks/failures don't crash the enrich pipeline.
  - **`no_agent` cron runs the shell wrapper, not the Hermes prompt** — editing the job prompt changes nothing. To change `--count`, edit `~/.hermes/scripts/rkm_watchlist_auto_add.sh`.
- **2026-08-17:** `esc()` must `String(s ?? '')` (silent blank-page crash); posters center via `object-position`; atomic writes + publish guard against corruption; sandbox has NO Docker access (PS deploys) + inline mega-commands get blocklisted → write `.py` scripts.
- **2026-08-18:**
  - **PS 5.1 parse errors = encoding, not syntax.** UTF-8-no-BOM `.ps1` with em-dashes breaks: byte 0x94 reads as a smart quote, terminating strings mid-line ("missing terminator"). Scripts for Windows must be pure ASCII + CRLF.
  - **Docker Desktop cannot follow WSL symlinks.** After consolidating `.env`, compose `env_file: ../.env` hit `media\.env` (a WSL symlink) → "file cannot be accessed". Fix: `env_file: ../../.env` → the real canonical file at the workspace root. Sandbox-side scripts can use the symlink; Windows-side tooling must use the real path.
  - **Radarr ≠ ownership.** Plex had Spirited Away + Andhadhun that Radarr never tracked — Plex is ground truth; Radarr check alone created duplicate pending entries.
  - **qBittorrent is the real download truth.** Radarr queue can be empty while a torrent is active (or vice-versa) — status must read qBittorrent directly.
  - **urllib gotcha:** `timeout=` is a `urlopen()` kwarg, NOT `Request()` — qbit fetch failed silently (returned []) until fixed.
  - **Indexer outage = silent stall.** Requested titles sat static with no explanation; health-check awareness ("Waiting — search indexers down") is essential UX, not decoration.
  - **.env split was cruft** — consolidated to `D:\hermes_agent\hermes-workspace\.env` with `media/.env` symlink; compose env_file + hardcoded script paths keep working.
  - **Plex API shapes:** sections via `/library/sections`; movies = `<Video>` nodes, shows = `<Directory>` nodes in section dumps.
- **2026-08-19 (Architecture Refactor):**
  - **Service layer pattern works** - Clean separation makes testing, debugging, and maintenance vastly easier
  - **Centralized Config** - Single source of truth eliminates env loading bugs across scripts
  - **Atomic watchlist writes** - tmp + os.replace prevents corruption; validation before publish prevents empty dashboards
  - **State machine in WatchlistService** - Valid transitions enforced, prevents invalid states
  - **Structured logging** - JSON logs enable log aggregation and debugging
  - **Pydantic models for API** - Type safety, auto-documentation, validation
  - **Tests first** - Writing tests for plex ownership, radarr/sonarr routing, duplicates, trailers, status, e2e, errors caught design issues early
