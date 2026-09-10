# RKM Cinema

A self-hosted **media library + acquisition dashboard**. Browse your media server's
libraries, request movies and series, watch them in the browser, and track every
title from "requested" to "available".

Runs against **Jellyfin** (bundled), **Plex** or **Emby**, and hands new titles to
**Radarr**/**Sonarr** → **qBittorrent**. Metadata and discovery come from **TMDB**.

---

## How it works

```
        your browser
             |
             v
   +---------------------+        web container (nginx)
   |   web  :8124        |  serves the React UI, proxies /api/* to the backend,
   +----------+----------+  and caches artwork (7 days) so posters don't re-download
              |
              v
   +---------------------+        api container (FastAPI, secrets never reach the browser)
   |   api  :8000        |  library browsing, watchlist state machine, search,
   +--+------+-------+---+  player streaming (HLS), posters, *arr hand-off
      |      |       |
      |      |       +--> TMDB ................ metadata, discovery, similar titles
      |      +----------> Radarr / Sonarr ..... new requests (quality profiles, no dupes)
      |                     |
      |                     +--> qBittorrent .. downloads
      v
   media server  ---  Jellyfin (bundled, :8098) | Plex | Emby   <- what you can watch
      |
      v
   your media drives .... D:\RKM_MEDIA (movies) + B:\RKM_MEDIA (TV)
```

**One `.env` file at the repo root is the single source of truth.** `bootstrap.ps1`
renders it into `.rkm.env` for the containers — including which folders become
libraries and which drives are mounted. Nothing else needs editing.

**Status is derived, never stored by hand.** `backend/domain/status.py` is a pure
resolver: library availability always wins, then download progress, then the
acquisition request.

```
in library  -> AVAILABLE      downloading -> DOWNLOADING     requested -> REQUESTED
downloaded  -> DOWNLOADED     otherwise   -> NOT_REQUESTED
```

---

## Features

| Feature | What it does |
|---|---|
| **Libraries** | Every folder you declare (`MEDIA_LIBRARY_N_*`) appears in the sidebar, wired into the media server automatically at startup |
| **Library browsing** | Poster grids and list rows per folder, with detail pages (cast, runtime, ratings) |
| **Continue watching** | Resume row built from the media server's own playback state |
| **Recently added / played** | Rows for what's new and what you were watching |
| **In-app playback** | Streams through the backend with HLS — no separate player app, no media URLs exposed |
| **Trailers** | Official YouTube trailers, embedded, no API key required |
| **Global search** | One search across everything you have and everything you could request |
| **Watchlist** | Add titles, watch status move through the lifecycle, with toasts and optimistic UI |
| **Requests** | Movie → Radarr, series → Sonarr, with quality-profile choice and duplicate prevention |
| **Suggest** | Filter by genre/year/rating, pull ideas from TMDB, add straight to the watchlist |
| **Deep watch links** | "Watch on Plex/Jellyfin" opens the server's own web UI (works over Tailscale) |
| **Settings / config health** | Shows which integrations are configured and reachable, and what's missing |
| **Artwork caching** | Posters cached 7 days with `304` revalidation; dynamic JSON stays `no-store` |

---

## Quick start (bundled, self-contained stack)

Ships its own Jellyfin, so nothing else needs to be installed first.

**Windows prerequisites:** Windows 10/11 with **WSL2**, **Docker Desktop** running,
**PowerShell 5.1** (built in), and **Python 3** for the diagnostics. Docker Desktop
must be allowed to share every drive you mount (Settings → Resources → File sharing).

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema

# 1. Configure (once)
copy .env.example .env
notepad .env                      # set RKM_MEDIA_PATH + your media folders/keys

# 2. Run it
.\rkm.ps1 deploy

# 3. Check it
.\rkm.ps1 status
```

Then open **http://localhost:8124/** — and Jellyfin itself at
**http://localhost:8098/web** (user `admin`, password from `RKM_JELLYFIN_ADMIN_PASSWORD`).

First run does a full library scan: **2–4 h** for a large collection. Leave it alone
while it runs — see the rules below.

Linux/macOS: `./bootstrap.sh` instead of `.\rkm.ps1 deploy`.

**Optional extras** (`fullstack` profile — only if you have no *arr stack already):

```powershell
docker compose -p rkm-bundled --profile fullstack up -d
```

---

## Important commands

Everything is behind one entry point. `.\rkm.ps1 help` prints this list too.

| Command | What it does |
|---|---|
| `.\rkm.ps1 status` | Containers, state volumes, app + media-server health, library counts, scan state — **start here when anything looks off** |
| `.\rkm.ps1 deploy` | Build + start the stack, wire libraries, trigger a scan |
| `.\rkm.ps1 backup` | Archive media-server state (users, watch history, libraries) to `D:\RKM_BACKUPS` |
| `.\rkm.ps1 restore -Archive <file>` | Restore that state (defaults to the newest archive) |
| `.\rkm.ps1 schedule` | Install the nightly 04:00 backup task |
| `.\rkm.ps1 diagnose` | Classify every series: watched vs episodes present; find why a show looks wrong |
| `.\rkm.ps1 logs` | Tail api + web + jellyfin |
| `.\rkm.ps1 help` | The command list |

Underlying scripts, if you prefer them directly:

```powershell
.\bootstrap.ps1                 # same as .\rkm.ps1 deploy
.\bootstrap.ps1 -NoBackup       # skip the automatic pre-rebuild backup
.\run-rkm-cinema.ps1            # PROD profile: :8123, points at your existing Plex/Emby/*arr
docker compose -p rkm-bundled ps
docker compose -p rkm-bundled down          # stop (keeps state)
```

### The three rules

1. **Never `docker compose ... down -v`** — it deletes the state volumes (watch history, libraries). `down` alone is safe.
2. **Don't restart the stack while a library scan runs.** A cancelled scan can leave shows present with no episodes attached, which reads as "everything watched". `.\rkm.ps1 status` shows scan state.
3. **Always use `-p rkm-bundled`** (the scripts do). A different project name creates *fresh empty* volumes and orphans your real ones.

---

## Configuration

`.env` (git-ignored) — see `.env.example` for the full annotated list. The ones that matter most:

| Key | Purpose |
|---|---|
| `RKM_MEDIA_PATH` | Primary media root, mounted at `/data` (e.g. `D:/RKM_MEDIA`) |
| `RKM_MEDIA_PATH_2`, `_3` | Extra physical drives, mounted at `/media2`, `/media3` — **two drives need two entries** |
| `MEDIA_LIBRARY_N_NAME/_PATH/_TYPE` | Sidebar libraries. `PATH` is a host path (`D:/RKM_MEDIA/Movies`) or container path (`/data/Movies`); `TYPE` = `movie`/`tv`/`mixed`. Leave all empty to auto-discover every folder |
| `MEDIA_SERVER` | `jellyfin` (bundled), `plex` or `emby` |
| `RKM_DASHBOARD_PORT`, `RKM_JELLYFIN_PORT` | Host ports (bundled defaults `8124` / `8098`; prod uses `8123` / `8096`) |
| `WATCHLIST_DB_PATH` | Where the app's own watchlist JSON lives |
| `RKM_PRUNE_LIBRARIES` | `true` (default) removes libraries the stack no longer declares — **files on disk are never touched** |
| `RADARR_URL` / `SONARR_URL` / `PROWLARR_URL` + API keys | Your acquisition stack (bundled or existing on the LAN) |
| `TMDB_API_KEY` | Metadata, artwork, discovery, similar titles |
| `RKM_JELLYFIN_ADMIN_PASSWORD` | The bundled media server's admin password |

**A container can only read what is bind-mounted.** Declaring a *library* on a drive
is not enough — the *drive* must also be declared as a media root, or nothing can
see it.

---

## Ports

| Service | Bundled | Prod |
|---|---|---|
| Dashboard / API (web) | **8124** | 8123 |
| Media server | **8098** → 8096 | 8096 |
| Radarr / Sonarr / Prowlarr | 7879 / 8988 / 9697 (profile `fullstack`) | your own |
| qBittorrent | 8080 (profile `fullstack`) | your own |

---

## Troubleshooting

| Symptom | Try | Likely cause |
|---|---|---|
| Library rows greyed out | `.\rkm.ps1 status` | The app can't authenticate to the media server, or a library path doesn't resolve — `status` prints the exact warning |
| Every show shows as watched | `.\rkm.ps1 diagnose` | Series with no episodes attached read as "all played". Healthy series report `played=false` |
| Episodes missing under a show | `.\rkm.ps1 status`, then `diagnose` | Scan still running, or a scan was cancelled mid-way |
| Posters reload on every visit | — | Usually a stale `web` image: `.\rkm.ps1 deploy` |
| A drive's content never appears | `.\rkm.ps1 status` | The drive isn't declared as a media root, or Docker Desktop can't share that drive |
| `.\rkm.ps1 deploy` stopped at the provisioner | `.\rkm.ps1 logs` | The `[jellyfin]` line it stopped on names the cause |

Full runbook, failure modes and recovery: **[`docs/OPERATIONS.md`](docs/OPERATIONS.md)**.

---

## Project layout

```
backend/          FastAPI app (layered: api · application · domain · services · infrastructure)
  api/routes/     HTTP surface (library, watchlist, search, player, posters, health …)
  domain/         pure logic — status resolver, enums, state machine (no HTTP)
  services/       integrations: media servers, *arr, qBittorrent, TMDB, YouTube
  provisioner/    one-shot container: creates the admin user, wires libraries, scans
  tests/          41 files
frontend/         React + TypeScript UI (features: library, playback, watchlist, search,
                  suggest, discover, settings)
nginx/            web container config (routing + artwork cache policy)
scripts/          backup / restore / scheduled-task PowerShell
tools/            status + diagnostics (Python, work on Windows and in containers)
docs/             architecture, plans, ADRs, frozen API contract (docs/api/openapi.v1.json),
                  OPERATIONS.md, PROGRESS.md (session history)
rkm.ps1           single entry point for running and operating the stack
```

---

## Development

```powershell
# Backend (from backend/)
python -m pytest -q          # 499 tests
ruff check .                 # lint

# Frontend (from frontend/)
npm ci
npm run dev                  # Vite dev server
npm test                     # 160 Vitest tests
npm run typecheck            # tsc --noEmit
npm run build                # production build
npm run generate:types       # regenerate TS types from the frozen OpenAPI contract
```

The API contract (`docs/api/openapi.v1.json`) is **frozen** per ADR-0001 — regenerate
types from it rather than hand-writing request/response shapes.

---

## Documentation

| Doc | Contents |
|---|---|
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Runbook: commands, rules, fresh install, recovery, what survives what |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System and module architecture |
| [`docs/api/openapi.v1.json`](docs/api/openapi.v1.json) | Frozen API contract |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | What changed, session by session |
| [`docs/TAILSCALE_HOSTING.md`](docs/TAILSCALE_HOSTING.md) | Remote/phone access over Tailscale |
| [`docs/adr/`](docs/adr/) | Architecture decision records |
