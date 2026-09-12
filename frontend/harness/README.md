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
| `?enforce=0&signedIn=0` | Phase 1's world: the app renders SIGNED OUT, the bar offers Sign in, a wrong password shows the generic error **without** signing the app out, a correct one lands signed in — and (Phase B) on **"Who's watching?"**, which must then be answered before the app appears |
| `?enforce=1&signedIn=0` | the server refuses app calls ⇒ the login view, and app content **never appears** (asserted with a MutationObserver, so enabling enforcement cannot flash the shell before bouncing you out) |
| `?enforce=1&signedIn=1` | a valid session is left alone by the guard |
| blank password (scenario D) | a Jellyfin account with **no password** can sign in — the form must not block an empty submit (a `required` field silently made such accounts unusable) |

The stub is SESSION-AWARE: enforcement refuses only an unsigned caller — and a BLANK password
authenticates, because a household account can legitimately have no password. A cruder stub that
refused everything (or one that refused blank passwords) made a correct app look broken during
development; if a scenario fails, check the stub before the app.

`window.__probe()` and `window.__authCalls` expose what rendered and every stubbed call.
⚠ **Restart the dev server after editing app source** (the same watcher trap as above): a
stale module gave a false FAIL here until the vite PID holding :5199 was killed.

## `household-frame.html` — the Household screen (Phase 1b)

`python3 tools/check_household_ui.py` mounts the REAL `HouseholdView` (plus the real query client
and auth provider) over a stubbed api and drives it in a browser:

| Query | What it asserts |
|---|---|
| `?admin=1` | the household lists; access resolves to library **names**; a password-less member says so; **Remove is disabled for your own account with the reason on screen**; the typed name arms the confirm button only on an exact match |
| `?admin=0` | a non-administrator session sees the requirement stated plainly — no accounts, no add form, and **no write is attempted** |
| `?admin=1` + add | adding a member posts the name, a **blank password**, and **only the ticked libraries** — the default is everything, and unticking one sticks |

The stub is deliberately generous but honest: it echoes the created member back the way the API does,
so a refresh is visible. `window.__calls` records every request (url, method, body) and
`window.__probe()` reports the rendered rows, whether the add form is open, whether the confirm
button is armed, and any `role="alert"` text.

## `profile-frame.html` — "Who's watching?" (Phase B)

`python3 tools/check_profile_picker.py` mounts the REAL `ProfilesView` (plus the real `AuthProvider`,
`RequireSession` and `Header`) over a stubbed api and drives six scenarios:

| Query | What it asserts |
|---|---|
| `?signedIn=1&profileSelected=0` | the picker IS shown and **app content never appears** (MutationObserver); a lock only where the server needs one — including an administrator with NO password of its own; the disabled row is inert (even to a programmatic click) and says why; no row claims "Watching now"; **zero `/api/admin/*` calls** |
| …then pick `uid-guest` | a password-LESS profile posts `{"user_id":"uid-guest","password":""}` and lands as `Watching as Guest` |
| …then pick `uid-locked` | the prompt appears with **0 requests sent**, a blank attempt and a wrong one both answer the generic message, the right one lands |
| …then pick `uid-owner-nopw` | the administrator's profile asks even with no password set (the server refuses a blank attempt on it) |
| `?signedIn=1&profileSelected=1` | straight into the app, picker NOT shown; the header's **Switch profile** (`/profiles?switch=1`) brings it back with the current profile marked |
| `uid-off` | a disabled profile is not selectable and clicking it makes no call |

⚠ The stub must mirror the SERVER's refusals: a blank attempt on the administrator's profile is
401, a disabled profile is 403, and a password-less profile accepts an empty one. A kinder stub makes
a correct picker look broken.

The stub's own `me()` must keep reporting `profile_selected` honestly — that flag IS the picker's
trigger, so a stub that always said `true` would prove nothing about this screen.
