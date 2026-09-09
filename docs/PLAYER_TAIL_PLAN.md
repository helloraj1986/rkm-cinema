# Player Roadmap Tail — Execution Plan (`feat/player-tail`)

Scope: the queued player roadmap tail (PROGRESS 2026-09-09 record):
**warm-start / next-episode prefetch · auto-hiding controls · PiP (+ preference
persistence) · hls.js ABR ladder.** All frontend-only, additive, no `/api`
contract change. Branch from `main` @ `67bb9fd`.

Target files:
- `frontend/src/features/playback/Player.tsx` (908 lines — the whole in-app player)
- `frontend/src/features/playback/lib.ts` (pure helpers — unit-tested in `lib.test.ts`)
- `frontend/src/features/playback/api.ts` (only if a client helper is needed)
- callers that mount `<Player>` (item page / episode rows) unchanged unless a phase needs a prop

Player facts the phases build on (verified in code):
- One `<video>` element; modes `direct` (native MP4) vs `remux / transcode_audio /
  transcode` (HLS). hls.js on Chrome/Firefox/Edge, native HLS on Safari/iOS;
  `hlsEngineFor` decides once per item; `engineTypeRef` cached for the mount.
- Engine (re)build effect keyed on `engineKey` (src URL); `engineStartRef` =
  position where the next engine begins; hls.js gets `{ startPosition, maxBufferLength: 30 }`.
- `switchModeTo()` / `escalateHls()` rebuild via the same effect; fatal errors walk
  `HLS_LADDER` (`remux → transcode_audio → transcode`).
- Up Next: `onEnded` → `nextEpisode(queueRef, item_id)` → `setUpNext` +
  `startAuto(next)` (8 s `AUTOPLAY_DELAY_MS`, countdown → `onSwitchRef(next)`).
- Custom chrome: gradient top bar, center play button, subtitle overlay, div seek
  bar + transport row; settings strip (Speed/Quality/Audio/Subs) BELOW the video.
- Progress reporting: `reportNow(event)` throttled 5 s via `timeupdate`.
- `info` (`PlaybackInfo` from `api.playbackInfo(id)`) drives routing facts
  (`desiredMode`), audio/subtitle pickers.
- Runtime/position model is item-timeline; seeks are plain `currentTime`.

Design tokens/gates: same conventions as every frontend phase — vitest (pure
helpers), `tsc --noEmit`, `npm run build` green after EVERY phase, then RKM-HP
web-only redeploy (`docker compose -p rkm-bundled up -d --build web`) + Brave
eyeball = acceptance. No backend change anywhere → no api rebuild/provisioner.

---

## Phase 1 — hls.js ABR ladder + buffer policy (pure config + live level badge)

Why: the hls.js default ABR starts conservatively (default estimate ~500 kbps /
`abrEwmaDefaultEstimate`) so the first seconds of a transcode can look soft, and
`maxBufferLength: 30` is short for LAN streaming. We do NOT disable ABR — the
server ladder (capped by the Quality select's `max_bitrate`, absent = source cap)
is chosen by hls.js by bandwidth; we make that adaptation start sane and smooth.

1. `lib.ts`: add `hlsConfigFor(facts?: { startPosition?: number; estimateBps?: number })`
   (pure, exported): returns an `Hls.Config` —
   - `startPosition` when > 0 (today passed inline),
   - `maxBufferLength: 60`, `maxMaxBufferLength: 180`,
   - `abrEwmaDefaultEstimate`: 5_000_000 (LAN) — makes level 0 picks sensible,
   - `abrBandWidthUpFactor: 1.5` (default), `abrBandWidthDownFactor: 0.5` (default-ish) —
     keep defaults explicit so the policy is documented in one place,
   - `backBufferLength: 60`? — NO: keep default (back-buffer pruning off) unless a
     live-probe shows memory pressure; note in a comment.
   - `capLevelToPlayerSize: false` (default) — never downscale to element size.
2. `Player.tsx`: build hls.js with `hlsConfigFor({ startPosition: start })`.
3. Live level feedback (honest, cheap): subscribe `Hls.Events.LEVEL_SWITCHED` +
   `LEVEL_LOADED`; keep `levelRef`; show a tiny passive badge in the settings strip
   only while `mode !== "direct"`: e.g. `Auto · 1080p` (resolution from
   `level.height`) next to the Quality select, cleared on engine rebuild. This is
   information only — Quality remains a cap, never a lie about forcing.
4. Tests (`lib.test.ts`): `hlsConfigFor` returns the tuned defaults, honours
   `startPosition`, never sets `capLevelToPlayerSize` true.

Acceptance: LAN playback starts crisp within a second or two, buffering is
smoother on long files, and the badge tracks ladder switches during a transcode.

## Phase 2 — auto-hiding chrome

Cinema behaviour: while PLAYING and idle ~2.8 s, hide the top bar, control bar +
subtitle overlay? (NO — subs stay; hiding them would lose dialogue) and hide the
cursor. Movement/key/touch/pause bring everything back instantly.

1. `lib.ts`: pure `shouldAutoHide({ playing, switching, error, paused, chromeVisible, idleMs })`
   and `CHROME_HIDE_MS = 2800`; testable (playing+idle → true; paused/switching/
   error → false; activity → reset).
2. `Player.tsx`: `const [chromeHidden, setChromeHidden]` + refs (`lastActivityRef`,
   hide timer). Rules:
   - Activity (pointermove/pointerdown/keydown/touchstart on the ROOT, throttled
     ~200 ms) → reveal + restart timer.
   - Pointer resting inside the control bar / settings strip → never auto-hide
     (`pointerenter` on bar/strip sets `hoveringChrome`).
   - Pause/switching/error/upNext visible → force reveal, no timer.
   - Timer only arms while `playing` is true.
   - Apply: top bar + bottom control bar get opacity/translate-y transition classes
     (`transition-opacity duration-300`); root gets `cursor-none` when hidden.
     Reduced motion: still hide (opacity snap, no translate animation).
   - Keyboard (space/arrows/m/f) counts as activity (reveal first).
3. A11y: chrome must be reachable when hidden — hiding only affects visuals +
   cursor; elements remain in the a11y tree and tabbing reveals (focus → reveal).

Acceptance: let an episode play fullscreen; chrome + cursor vanish after ~3 s;
nudge the mouse → instant return; pausing keeps chrome; subs never disappear.

## Phase 3 — warm-start / next-episode prefetch

Goal: clicking "Play next" (or auto-play) should feel instant, and remounting the
player for the next episode should skip the "Preparing stream…" stall.

1. `lib.ts` + small module in `Player.tsx` (or `playback/warm.ts` if it grows):
   `warmCache` — `Map<itemId, { info: Promise<PlaybackInfo|null>, master?: Promise<string|null>, at: number }>`
   with `WARM_TTL_MS = 10 min`; functions `warmNext(id)`, `consumeWarmInfo(id)`,
   `pruneWarm()`. (Pure-ish; unit-test TTL/cap/prune + dedupe.)
2. Trigger points in `Player.tsx`:
   - `onEnded` when `upNext` resolves → `warmNext(upNext.id)` (playback-info fetch).
   - `timeupdate` throttle (existing 5 s report cadence): within 45 s of the end
     and a next queue entry exists → `warmNext(next.id)`.
   - `warmNext` fetches `api.playbackInfo(id)`; when the returned facts point at an
     HLS mode (reuse `pickStreamMode` w/ default audio), ALSO prefetch the master
     manifest URL (`api.hlsMasterUrl(id, {mode, max_bitrate: qualityFor("Original")})`)
     via a no-store `fetch` (just warms the Jellyfin transcode pipe + proxy cache).
   - No preload of a second `<video>`; no background decode — keeps it cheap.
3. Mount-time consume in the existing item effect: if `consumeWarmInfo(id)`
   resolves before the live fetch, `setInfo` immediately (no spinner); engine
   build is already driven by `info → desiredMode → switchModeTo`, so the first
   HLS master load also benefits from the warm manifest.
4. Safety: cache is best-effort — all failures swallowed (same as today); stale
   cache pruned on `ended`/`close` events; never warms beyond queue.length.

Acceptance: finish an episode → Up Next appears → Play next starts near-instantly
(spinner skipped) vs today's cold start; auto-play at 8 s also lands faster.

## Phase 4 — PiP + preference persistence

1. Persistence (`lib.ts`): `PLAYER_PREFS_KEY = "rkm.playerPrefs.v1"`;
   `loadPlayerPrefs()/savePlayerPrefs()` (try/catch localStorage — never throws);
   shape `{ volume: number (0–1), muted: bool, rate: number, quality: string }`
   (audio/sub index are per-item — not persisted). Tests: round-trip, corrupt
   JSON → defaults, storage unavailable → defaults.
2. `Player.tsx`: on mount apply saved volume/muted/rate/quality (volume AFTER
   metadata? volume is settable immediately — apply in the item effect before
   play); save on change (volume slider, mute, rate, quality select). Reset per
   item: quality/rate/volume persist ACROSS items; `resume` stays server-side.
3. PiP: button in the transport row, shown only when
   `document.pictureInPictureEnabled && video.disablePictureInPicture !== true`:
   `requestPictureInPicture()` / `document.exitPictureInPicture()`, sync `isPip`
   via `enterpictureinpicture`/`leavepictureinpicture`. The video element must be
   visible for PiP to engage — our full-bleed layout qualifies.
4. Media Session (makes PiP + OS media keys usable — video has no DOM controls in
   the PiP window): set `navigator.mediaSession.metadata` (title/episode art),
   handlers for play/pause/seek/`previoustrack`/`nexttrack` (next = the queue
   entry → `onSwitch`) + `setPositionState` on timeupdate. Guard for unsupported
   browsers; clear handlers on unmount.
5. Escape/backdrop unchanged; PiP exit returns to the player as-is.

Acceptance: volume/speed/quality remembered across episodes AND browser sessions;
PiP button floats the video while browsing the library; OS media keys + PiP
window controls play/pause/seek/next.

---

## Order + gates

Phase 1 → 2 → 3 → 4 (each independent, each committed separately with vitest /
tsc / build green). Phases 1+4 touch lib.ts first (pure helpers + tests), then
Player.tsx. No `/api` contract change, no backend edit, no new deps.

## RKM-HP acceptance checklist (after all phases)

- `docker compose -p rkm-bundled up -d --build web` (web-only), hard refresh.
- Start a transcode (HEVC/AV1 title): starts crisp, badge shows live ladder level.
- Fullscreen an episode, hands off: chrome + cursor hide ~3 s; mouse nudge
  returns them; pausing keeps them; subs stay visible.
- Finish an episode: Up Next → Play next starts with no spinner; same for auto.
- Set volume 40% + 1.5× + a quality cap → next episode AND a new browser session
  remember them. PiP button floats the video; media keys work; PiP ▶ / next works.
- Merge `feat/player-tail` → main + push + fast-forward `experiment/bundled-docker-stack`.
