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

`tools/measure_player_layout.py` prints a PASS/FAIL table for 10 device sizes and
exits non-zero if any viewport fails. Add `--fullscreen` to also click the Fullscreen
button (needs a browser that has `Element.requestFullscreen`) and re-probe.

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
