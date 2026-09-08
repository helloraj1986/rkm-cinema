# RKM Cinema

A self-hosted **media discovery + download dashboard**. Browse your Plex library, request movies/series (added to **Radarr**/**Sonarr** and downloaded via **qBittorrent**), track each title through a lifecycle, and discover new titles via a **Suggest** tab driven by TMDB.

> **Plex is the source of truth** for availability. Metadata comes from **TMDB**; official trailers are found by scraping **youtube.com** (no YouTube API key).

> ## ⚠ Status (2026-09-08) — production repo restructure done + legacy app removed
> Plan: [`docs/REPO_STRUCTURE_PLAN.md`](docs/REPO_STRUCTURE_PLAN.md) · ADRs: [`docs/adr/`](docs/adr/) · **Frozen API contract:** [`docs/api/openapi.v1.json`](docs/api/openapi.v1.json) (ADR-0001).
> Monorepo: **`backend/`** (FastAPI + tests) · **`frontend/`** (React/TS shell — the only UI; the legacy vanilla app + `/legacy` route were removed) · deploy/infra + `.env` stay at the repo root. Session history: `PROGRESS.md`.

---

## Features

- **Watchlist lifecycle** — `requested → downloading → downloaded → available → recommended` (status derived from Plex/*arr/qBittorrent facts via a single state machine in `backend/domain/status.py`).
- **Request movies/series** — movie → Radarr, series → Sonarr, with quality-profile selection and duplicate prevention.
- **In-app trailers** — YouTube embed (official channels), no API key.
- **Deep watch links** — "Watch on Plex / Emby" straight into the server's own web UI over Tailscale.
- **Suggest** — user filters (genre, year, min rating) → TMDB discover → add to watchlist.
- **Dashboard** — discover rows, watchlist grid, downloaded, library views. Status auto-polls and refreshes.

---

## Run the app (one command, Windows)

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\run-rkm-cinema.ps1
```

That one script builds and starts both Docker containers, waits for readiness, and checks the API health:
- `api` container — FastAPI backend on :8000 (internal, holds all secrets)
- `web` container — nginx on **:8123**, serves the UI + proxies `/api/*` to the API

Then open **http://rkm-hp.tail8d5e8.ts.net:8123** (or `http://localhost:8123` on that machine).

### Windows prerequisites

- **Windows 10/11 (64-bit)** with **WSL2** enabled.
- **Docker Desktop** installed, with the **WSL2 backend**, and running (the script's `docker compose` needs it; the script exits with a clear error if Docker isn't up).
- **PowerShell** — the script targets **Windows PowerShell 5.1**, which ships with Windows. (PowerShell 7 works too.)
- **Git** (to clone the repo; already present if you set up the workspace).
- **The media stack reachable on your LAN:** Plex, Radarr, Sonarr, and qBittorrent on `MEDIA_HOST` (default `192.168.65.254`). Optional: Emby, a **TMDB API key** for metadata/artwork.
- **A configured `.env`** at the repo root — copy `.env.example` → `.env` and fill in the secrets (see [Configuration](#configuration)).
- **Tailscale** (optional) — only needed for on-the-phone / remote access at the `rkm-hp.tail8d5e8.ts.net` URL. For phone access, also allow inbound TCP 8123 through Windows Firewall (the script prints the exact rule).

If you don't use Tailscale, the dashboard is still available locally at `http://localhost:8123`.

---

## Run it any other way

### Bundled self-contained stack (experiment branch: `experiment/bundled-docker-stack`)
The **bundled** build runs its **own** Jellyfin (media server) + the RKM app in one
isolated Compose project (`rkm-bundled`) — a "Jellyfin client" that needs no
pre-existing Plex/*arr. Fully isolated from your prod stack (own network
`rkm-exp`, own `./data`, non-colliding ports), fully reversible with
`docker compose -p rkm-bundled down`.

```powershell
# Windows (zero-edit: TMDB key auto-fills from your workspace .env, Jellyfin password auto-generates)
.\bootstrap.ps1
```
```bash
# Linux/macOS
./bootstrap.sh
```

Then open **http://localhost:8124/** (dashboard) and **http://localhost:8098/web**
(Jellyfin). Auto-add is **off** by default (Suggest-first); flip `[recommend]
auto_add_enabled = true` in the TOML to turn on the daily job. See
`docs/BUNDLED_DOCKER_STACK_PLAN.md` for the full design & weighing.

---

### Local dev (WSL / sandbox)
```bash
cd projects/rkm-cinema
cd backend
pip install -r requirements.txt
python3 -m uvicorn api.main:app --port 8000   # or: python3 -m api.main
```
Then in another shell: `cd frontend && npm run dev` (vite dev server proxies `/api` → :8000).

### Docker Compose (any host with Docker)
```bash
cd projects/rkm-cinema
docker compose up -d --build
```

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11 · **FastAPI** (`uvicorn api.main:app`) under `backend/` |
| Frontend | React 18 + TypeScript + Vite (`frontend/`) — the only UI (legacy vanilla SPA removed) |
| Persistence | **SQLite** (`WATCHLIST_STORE=sqlite`) — a JSON store is supported for backward compat |
| Infra | **Docker Compose** — `api` (FastAPI, holds secrets) + `web` (nginx, proxies `/api/*`) |
| External | Plex · Radarr · Sonarr · TMDB · YouTube · Emby · Jellyfin · qBittorrent |

---

## Project layout

```
rkm-cinema/                        # deploy/infra + docs + config stay at root
├── .env.example  .gitignore  .dockerignore
├── README.md  ARCHITECTURE.md  PROGRESS.md  TAILSCALE_HOSTING.md
├── docker-compose.yml
├── bootstrap.ps1  bootstrap.sh  run-rkm-cinema.ps1
├── render_config.py               # deploy tooling (reads the repo .env)
├── nginx/default.conf             # infra — COPYed by the frontend image
├── docs/                          # plans, ADRs, api contract
│   └── archive/                   # stale task/spec docs parked (git history kept)
├── backend/                       # FastAPI app + tests + its Dockerfile
│   ├── Dockerfile  requirements.txt  ruff.toml
│   ├── api/  services/  domain/  core/  config/  infrastructure/
│   │        application/  jobs/  scripts/  provisioner/
│   └── tests/                     # pytest suite (run from backend/: python -m pytest tests/)
├── frontend/                      # React 18 + TS + Vite shell (the only UI)
│   ├── Dockerfile  package.json  tsconfig*  vite.config.ts  src/
└── tools/archive/                 # one-off tools + archived scripts (git history kept)
```

Run/test/deploy: **backend** — `cd backend && python -m pytest tests/ -q`,
`ruff check api application config core domain infrastructure jobs services` ·
**frontend** — `cd frontend && npm run typecheck && npx vitest run && npm run build` ·
**deploy** — `.\\bootstrap.ps1` (bundled Jellyfin stack) or `.\\run-rkm-cinema.ps1` (prod Plex/Emby).
Contract snapshot (zero-diff gate): `python backend/scripts/snapshot_openapi.py` from the repo root.

---

## Configuration

Everything the stack needs lives in **one repo-level `.env`** — copy `.env.example`
→ `.env` (kept out of git) and fill it in. `bootstrap.ps1`/`.sh`,
`render_config.py` and `docker compose` all read that single file; there is no
`rkm.config.toml` any more. On the first run after the upgrade,
`render_config.py` auto-copies missing service keys (TMDB/*arr/Plex/Emby) from
the legacy workspace `.env` into the repo `.env` once, so you don't have to
re-type anything. Key variables (full list with comments in `.env.example`):

```bash
# compose / ports / storage
RKM_MEDIA_PATH=./data
RKM_DASHBOARD_PORT=8124
RKM_JELLYFIN_PORT=8098
RKM_TIMEZONE=Australia/Melbourne

# media backend + admin (bundled Jellyfin auto-provisions on first run)
MEDIA_SERVER=jellyfin            # jellyfin | plex | emby
RKM_JELLYFIN_ADMIN_USER=admin
RKM_JELLYFIN_ADMIN_PASSWORD=     # blank -> auto-generated & saved into .env
RKM_JELLYFIN_BROWSER=http://localhost:8098

# metadata
TMDB_API_KEY=...                 # required

# download automation (*arr you run, or blank for the bundled fullstack profile)
RADARR_URL=http://192.168.65.254:7878
RADARR_API_KEY=...
SONARR_URL=http://192.168.65.254:8989
SONARR_API_KEY=...
QBITTORRENT_URL=http://192.168.65.254:1701

# watch sources when backend = plex|emby (or watch links alongside jellyfin)
PLEX_URL=http://192.168.65.254:32400
PLEX_TOKEN=...
EMBY_URL=http://192.168.65.254:8096
EMBY_API_KEY=...

# app store + jobs
WATCHLIST_STORE=json             # json | sqlite (container path on the media volume)
WATCHLIST_DB_PATH=/data/rkm/watchlist.json
WATCHLIST_SCHEDULER=true
```

---

## Scheduled jobs

- **Daily auto-add** (recommended) — host cron runs `backend/scripts/add_watchlist_cron.py` (TMDB discover, Plex-gated, idempotent).
- **In-process scheduler** (optional) — set `WATCHLIST_SCHEDULER=true` to run reconcile (every 10 min) + daily watchlist job (default 18:00) inside the API container.

---

## Tests

```bash
cd backend
python -m pytest tests/ -q               # ~292 unit/API tests (all mocked, no live LAN)
cd ../frontend
npm run typecheck && npx vitest run && npm run build
```

---

## Key design principles

1. **Single source of truth** for status & media-type rules → `backend/domain/`.
2. **Plex is authoritative** for ownership; a watch-link failure never flips an available title to "not added".
3. **Canonical service seams** over legacy facades — extend `backend/services/library|acquisition|recommendation|reconciliation/`, not the old wrappers.
4. **Stable identity** — `media_id` (`type:tmdb:{id}` / `imdb` / `tvdb`), never bare `title`.
5. **Config over code** — recommendation quality gates live in `backend/config/recommendations.yaml`.

---

## License

Private project · RKM Media Stack