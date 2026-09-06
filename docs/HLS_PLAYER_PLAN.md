# HLS/MSE Player Plan — "make it play like Plex"

Status: **Phase 0 DONE (2026-09-06) — probes below; Phase 1 (backend HLS proxy)
NEXT.** Decision date 2026-09-06 (user, after confirming the
seek-bar fix `f74ceba` was redeployed and the bug **still reproduces on every
3 Body Problem episode**). The progressive-stream approach is being replaced with
a Plex-style HLS/MSE player. Do NOT continue patching
the progressive/restart-seek machinery.

---

## 1. Why the current design is being abandoned (evidence)

Symptom (user): clicking the seek bar moves the UI to the target but actual
playback position does not move — on resume AND from 0:00, on movies and now
confirmed on **all episodes** after redeploying `f74ceba`.

Root cause class (diagnosed across 2026-09-06 sessions, incl. headless-Chromium
harness against the live Jellyfin):

- Direct play (Static file): seeking relies on the browser byte-range-seeking an
  MP4. Fine for real MP4, but non-MP4 containers can't be indexed up-front
  (`duration = Infinity`) so seeks silently no-op.
- Remux/transcode (progressive chunked MP4 from Jellyfin): seeking requires
  restarting the stream at `StartTimeTicks`. Suspect: mid-file start offsets on
  copy/remux streams are unreliable; combined with a controlled `<input
  type=range>` that visually stays at the click point when state doesn't change,
  you get "bar moved, video didn't".
- Every fix so far addressed symptoms at the UI/event layer. The transport model
  itself is the problem: the browser is asked to seek a server-generated
  progressive stream.

**Plex / Jellyfin-web never have this problem because they use HLS + MSE**:
clicking a position asks the SERVER for a segment starting at that time; the
browser plays whatever segment arrives — a silent no-op is structurally
impossible. Direct-play is used only for files the browser can natively seek.

## 2. Target architecture

Decision function per title (reuse/extend `pickStreamMode` in
`web/src/features/playback/lib.ts`):

- **Native direct play** (keep today's code path) — container mp4-family +
  browser-safe codecs (H.264 8-bit, AAC/MP3/Opus). This already works and is
  what Plex does too.
- **HLS mode (everything else)** — MKV / remux-needed containers, HEVC/10-bit,
  EAC3/AC3/DTS/TrueHD, any quality ≠ Original:
  - Chrome/Firefox/Edge: **hls.js** (new npm dep) over a same-origin HLS proxy.
  - Safari/iOS: native HLS (`canPlayType('application/vnd.apple.mpegurl')`) —
    no hls.js needed; bonus: iPad playback works.

With HLS mode:
- **Delete** the offset model (`baseRef`/`startAt`/`start_time_ticks` restart
  logic), the restart-seek, scrub-commit special-casing. Position = plain
  `video.currentTime`; the media timeline IS the item timeline.
- Seek = `video.currentTime = x` (hls.js fetches the segment at x). Subtitle
  overlay (already item-time aligned) becomes trivially correct.
- Audio/quality changes = rebuild master URL at same position (clean segment
  switch, no manual reload dance).
- Error ladder stays (audio-aware, see §3b): browser-safe audio →
  `remux-HLS (copy-copy)` → fallback `transcode-HLS`; EAC3/AC3/DTS/TrueHD →
  start at `copy+aac` (copy-copy HLS keeps `ec-3`, which Chrome MSE can't
  decode) → fallback `h264+aac`; then friendly give-up.
- Chip (Direct play / Remux / Transcode) stays so mode is visible per title.

## 3. Phase 0 — Verify before building (½ day)

1. **Re-confirm deployed hash** on RKM-HP if anything still smells stale
   (bundle filename in the network tab vs `web/dist` after
   `docker compose -p rkm-bundled up -d --build web`).
2. **Probe one 3 Body Problem episode**: playback-info facts (container/video
   codec/audio codec) → confirms which mode episodes take today. Expect MKV
   + h264/AAC or similar; record it.
3. **Probe Jellyfin HLS output shapes live** (see §6 harness):
   - `GET /Videos/{id}/master.m3u8?api_key=…&MediaSourceId={id}`
     (+ `VideoCodec=copy&AudioCodec=copy` for remux-HLS; + h264/aac/bitrate for
     transcode-HLS; + `AudioStreamIndex` when relevant)
   - Capture: master playlist layout, media-playlist URIs, segment URI patterns,
     whether remux (copy) HLS is offered for the episode's codecs, MIME types.
   - This defines the URL-rewriting the proxy needs.

## 3b. Phase 0 — EXECUTED 2026-09-06 (live probes, all redacted)

Harness committed as `scripts/probe_jellyfin_hls.py` (auth + playback-info +
master/media/segment/StartTimeTicks probes; re-run any time). Probed against
the bundled Jellyfin **10.11.11** (`http://host.docker.internal:8098`), real
3 Body Problem S1E4 "Our Lord" (item `b87e1f71a103c2799a9141163ba14c28`).

**Episode facts (drives the routing decision today):**
- container **mkv** · video **h264 Main 1920×1080 8-bit** (~5.4 Mbps) ·
  audio[1] **eac3 5.1 + Atmos** (768 kbps, "Dolby Digital Plus")
- ⇒ `pickStreamMode` today: quality Original → video safe (h264/8-bit) →
  audio **eac3 unsafe → `transcode_audio`**. Episodes are NOT direct/remux —
  they ride the chunked-progressive transcode path whose restart-seek is the
  bug. This confirms HLS mode must carry **every** 3BP episode.

**HLS master shapes (all variants, MIME `application/vnd.apple.mpegurl`):**
- Master = a **3-line single-variant** playlist: `#EXTM3U` +
  `#EXT-X-STREAM-INF:BANDWIDTH=…,AVERAGE-BANDWIDTH=…,VIDEO-RANGE=SDR,CODECS="…",RESOLUTION=1920x1080,FRAME-RATE=23.976` + **one relative URI**.
  No ABR ladder (fixed rendition v1 as planned) even with `MaxStreamingBitrate`.
- The master's variant URI is **relative** (`main.m3u8?…`) and the media
  playlist's segments are relative too (`hls1/main/N.ts?…`) → URI rewriting is
  simple path + query work, no absolute-host mangling.
- CODECS per variant: default/no-params `avc1.4D4028` (video only — no audio
  codec listed, odd but harmless); `VideoCodec=copy&AudioCodec=copy` →
  `avc1.4D4028,ec-3` (**remux HLS keeps EAC3!** codec is `ec-3`, which Chrome
  MSE cannot decode — so for EAC3 titles the default HLS attempt must be
  audio-transcode or full-transcode, not copy-copy); `copy+aac` and
  `h264+aac` → `avc1.4D4028,mp4a.40.2` (browser-safe).
- **Resume is client-side**: a `StartTimeTicks=600000000` master probe returned
  the SAME full 442-segment VOD playlist (segment URIs echo `StartTimeTicks`
  but the playlist does not truncate). Plan stands: hls.js `startPosition`.

**Media playlist shape (VOD):** `#EXT-X-PLAYLIST-TYPE:VOD`, `#EXT-X-VERSION:3`,
`#EXT-X-TARGETDURATION:7`, `#EXT-X-MEDIA-SEQUENCE:0`, 442 × `#EXTINF:6.006000`
segments (last 1.772s), `#EXT-X-ENDLIST`; every URI
`hls1/main/N.ts?api_key=…&MediaSourceId=…[&codec params]&runtimeTicks=N×60060000&actualSegmentLengthTicks=60060000`.
MIME `application/vnd.apple.mpegurl`.

**Segment facts:** `.ts` container (`video/mp2t`, ~4.8 MB first segment), and
**Range works upstream** (206 + Accept-Ranges + Content-Range) — forward Range
like the stream route, though hls.js fetches whole segments.

**⇒ Proxy contract to build in Phase 1 (all confirmed necessary):**
1. `api_key` is embedded in EVERY playlist URI line → the proxy MUST strip it
   (token server-side only; no secret leak to the browser).
2. Rewrite relative URIs to the same-origin proxy path; keep MediaSourceId +
   codec params + runtimeTicks/actualSegmentLengthTicks (the segment server
   needs them — verified a bare segment path 404s/errors without the query).
3. Passthrough MIME (`application/vnd.apple.mpegurl`, `video/mp2t`) + Range.
4. Frontend picks the HLS codec pair by the same audio/video facts that drive
   `pickStreamMode` today: EAC3/AC3/DTS/TrueHD → `copy+aac` (NOT copy-copy);
   HEVC/10-bit/bitrate → `h264+aac`; browser-safe audio + odd container →
   `copy-copy`. The plan's "remux-HLS (copy)" must be audio-aware.

## 4. Phase 1 — Backend HLS proxy (½–1 day)

New `api/routes/jellyfin_hls.py` (same token-server-side pattern as
`jellyfin_stream.py`; additive contract paths only):

- `GET /api/jellyfin/hls/{item_id}/master.m3u8` → fetch Jellyfin master,
  **rewrite every URI** (media playlists + segments) to
  `/api/jellyfin/hls/{item_id}/…` same-origin (no Jellyfin host/api_key leaks).
- Media-playlist + segment passthrough routes; correct MIME
  (`application/vnd.apple.mpegurl`, `video/mp2t` or `video/mp4`); forward Range
  where upstream supports it; pass `X-Playback-Session-Id`-style params through.
- Query params mirrored from the stream route: `mode=remux|transcode`,
  `audio_stream_index`, `max_bitrate`; legacy `transcode_audio` mapping.
  **Codec-pair mapping (per §3b):** `remux`→copy-copy HLS (safe audio only),
  `transcode_audio`→`copy+aac` (EAC3 etc.), `transcode`→`h264+aac`
  (+bitrate/audio index). Proxy passes the right Jellyfin params through.
- Contract: snapshot regen (`python scripts/snapshot_openapi.py`) + `npm run
  generate:types`; full pytest + ruff gates (see §7).

## 5. Phase 2 — Frontend hls.js engine (1–2 days)

1. `npm i hls.js` in `web/`.
2. `lib.ts`: extend routing helpers: `usesHls(mode)`, HLS capability detection
   (native vs hls.js), master-URL builder params. Pure + unit-tested.
3. `Player.tsx`: branch playback engine on mode:
   - direct → existing <video> path (unchanged).
   - hls → `new Hls({ startPosition: resume })`, attach `video`, listen
     `Hls.Events.ERROR` → escalate along the audio-aware ladder (§3b) via URL
     rebuild; destroy on unmount/switch.
   - Native-HLS branch for Safari (`video.src = masterUrl`).
4. **Remove** the offset/restart machinery: `baseRef`, `startAt`,
   `pendingSeekRef`, transition-restart, custom scrub-commit stay ONLY for the
   direct path; for HLS, slider scrub can commit on release still (nice UX) but
   the seek is a plain `currentTime` set.
5. Subtitle overlay: unchanged mechanics; alignment is now trivial.
6. Quality picker: rebuild master with `max_bitrate` (fixed rendition v1; ABR
   ladder out of scope for v1).
7. Keep `streamModeLabel` chip.

Acceptance: on the harness (real browser), fresh episode → click 10:05 →
`currentTime` genuinely ≈ 605 s; resume 24:05 → click 30:00 → plays from 30:00.
All episodes of 3 Body Problem + the 2 movies.

## 6. Sandbox harness (recreate next session — scripts were /tmp, ephemeral)

Live Jellyfin reachable at `http://host.docker.internal:8098` (bundled Jellyfin
10.11.11). Admin creds in `/workspace/projects/rkm-cinema/.env`
(`RKM_JELLYFIN_ADMIN_USER/PASSWORD`); Jellyfin auth needs the
`X-Emby-Authorization: MediaBrowser Client="…"` header; token via
`POST /Users/AuthenticateByName`.

Gotchas learned (recorded so the next session doesn't re-derive them):
- `/workspace/.env` `JELLYFIN_URL=http://192.168.65.254:8096` points at the OLD
  EMBY (4.9.5) and `JELLYFIN_API_KEY` is EMPTY there — stale for the bundled
  stack. From the sandbox, run the API with real env overrides:
  `JELLYFIN_URL=http://host.docker.internal:8098`, `JELLYFIN_API_KEY=<token>`,
  `MEDIA_SERVER=jellyfin`, `WATCHLIST_SCHEDULER=false` (config.settings loads
  .env first, then real env vars override).
- React UI only serves when built with `VITE_ENABLE_REACT=1 npm run build`
  (legacy placeholder otherwise).
- Static+proxy server: python `http.server`-based; for chunked (no
  Content-Length) upstream responses you must NOT send `Content-Length: 0`
  (kills the stream); omit CL and close (HTTP/1.0 semantics).
- Headless Chromium: playwright python + browsers at
  `/root/.cache/ms-playwright/chromium-1234` (run
  `python3 -m playwright install-deps chromium` if libs missing). Launch with
  `--no-sandbox --autoplay-policy=no-user-gesture-required --mute-audio`.
- Sandbox Chromium could NOT decode progressive chunked streams (demux error →
  our error ladder → overlay blocked mouse) — HLS segments (standard H.264/AAC
  MP4/TS) are expected to decode; if not, verify seek via src/`start_time_ticks`
  changes + `aria-valuenow` as before.
- Probing/moving resume positions on the real library mutates the user's
  state — restore afterwards via `/Sessions/Playing` + `/Sessions/Playing/Stopped`
  with the original `PositionTicks`.

## 7. Gates before each commit

Backend: `python -m pytest tests/ -q` · `ruff check api application config core
domain infrastructure jobs services` · snapshot + types regen if contract
touched. Frontend: `npx vitest run` · `npm run typecheck` · `npm run build`
(with `VITE_ENABLE_REACT=1`). Push to `experiment/bundled-docker-stack` with
token from `/workspace/.env` (`GITHUB_TOKEN`), e.g.
`git push https://x-access-token:${TOKEN}@github.com/helloraj1986/rkm-cinema.git
experiment/bundled-docker-stack`.

## 8. Deploy to RKM-HP after each backend/frontend milestone

PowerShell (PS 5.1, separate lines — no `&&`):
```
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\bootstrap.ps1
```
(web image alone: `docker compose -p rkm-bundled up -d --build web`)

## 9. Out of scope (v1)

ABR/adaptive-bitrate ladder · casting · HDR/tonemapping · DASH · offline ·
Chromecast. Roadmap item 5 (full transcode-fallback engine) is effectively
satisfied by the HLS ladder.
