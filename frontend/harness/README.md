# Player layout harness (sandbox, not shipped)

The in-app player's job is to fit a *viewport*, and the sandbox has no Docker /
Jellyfin to play a real movie against. This harness mounts the **real** `<Player>`
component with a stubbed API so the layout can be measured in a real browser.

Nothing here ships: `vite build` only builds `/index.html`, so these files are inert
in the web image. They exist so that "the controls fit the screen" is a number, not
an opinion — see `docs/PLAYER_LAYOUT_PLAN.md` §1.

## Run it

```bash
cd frontend
npx vite --port 5199 --strictPort &          # dev server (harness is served from /harness/)

# optional: a real 16:9 file so the <video> reports genuine intrinsic dimensions
curl -sSL -o public/harness-sample.mp4 \
  https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4

cd .. && python3 tools/measure_player_layout.py --shots /tmp/shots
```

⚠ **Restart the dev server after editing app source.** Vite's watcher does not fire on
this mount (WSL2/Docker), and an orphaned `vite` holding port 5199 keeps serving the
pre-edit module — the measurement then reports the OLD layout and looks like your fix
did nothing. Check before trusting a run:

```bash
pkill -f "vite --port 5199"          # then start it again
curl -s http://localhost:5199/src/features/playback/Player.tsx | grep -c rkm-player__dock
```

`tools/measure_player_layout.py` prints a PASS/FAIL table for 10 device sizes and
exits non-zero if any viewport fails. It asserts: the shell == the viewport, the dock
is fully inside it, nothing pokes outside, the transport row never clips its own
content, every rendered control is ≥32px and on-screen, the header policy matches the
viewport height, and (with `--fullscreen`) that real element fullscreen still leaves
the shell == the screen.

## What it stubs

| App call | Harness answer |
|---|---|
| `GET /api/jellyfin/playback-info` | mp4 / h264 / 960×540 + 1 audio + 1 subtitle track → `direct` mode |
| `GET /api/jellyfin/progress` | `{ ok: true }` |
| `GET /api/jellyfin/subtitle` | a 20 s WebVTT cue (exercises the subtitle overlay) |
| `GET /api/jellyfin/backdrop` | 404 (seeded-art / no-image path) |
| media URL (`/api/jellyfin/stream/...`) | rewritten to `/harness-sample.mp4` when present |

Query params: `?kind=series|movie` (movie = no episode queue), `?src=<url>` to point
the media element somewhere else.

`window.__probe()` (defined in `player-frame.html`) returns the measurements the tool
asserts on: shell / video / dock / row rects, `100dvh`, document scroll size, and every
element that pokes outside the viewport.

## Sign-in flow harness (`login-frame.html`)

`tools/check_login_flow.py` drives the SESSION rules in a real browser, mounting the real
`AuthProvider`, `RequireSession`, `LoginView` and `Header` over a stubbed api (the app's own
pages are not involved — a fake Home stands in, because Phase 1 changes none of them):

| Scenario | What it proves |
|---|---|
| `?enforce=0&signedIn=0` | Phase 1's world: the app renders SIGNED OUT, the bar offers Sign in, a wrong password shows the generic error **without** signing the app out, a correct one lands signed in with the name in the chip, and Sign out flips back — the app still usable |
| `?enforce=1&signedIn=0` | the server refuses app calls ⇒ the login view, and app content **never appears** (asserted with a MutationObserver, so enabling enforcement cannot flash the shell before bouncing you out) |
| `?enforce=1&signedIn=1` | a valid session is left alone by the guard |

The stub is SESSION-AWARE: enforcement refuses only an unsigned caller. A cruder stub that
refused everything made a correct app look broken during development — if a scenario fails,
check the stub before the app.

`window.__probe()` and `window.__authCalls` expose what rendered and every stubbed call.
⚠ **Restart the dev server after editing app source** (the same watcher trap as above): a
stale module gave a false FAIL here until the vite PID holding :5199 was killed.
