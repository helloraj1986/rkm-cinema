# RKM Cinema

A self-hosted **media discovery + download dashboard**. Browse your Plex library, request movies/series (added to **Radarr**/**Sonarr** and downloaded via **qBittorrent**), track each title through a lifecycle, and discover new titles via a **Suggest** tab driven by TMDB.

> **Plex is the source of truth** for availability. Metadata comes from **TMDB**; official trailers are found by scraping **youtube.com** (no YouTube API key).

---

## Features

- **Watchlist lifecycle** — `requested → downloading → downloaded → available → recommended` (status derived from Plex/*arr/qBittorrent facts via a single state machine in `domain/status.py`).
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
pip install -r requirements.txt
python3 scripts/rebuild_dashboard.py   # build dashboard-data.json + index.html
python3 -m api.main                    # FastAPI on :8000
```
Then serve `index.html` (or open it), pointing the UI at the API.

### Docker Compose (any host with Docker)
```bash
cd projects/rkm-cinema
docker compose up -d --build
```

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11 · **FastAPI** (`uvicorn api.main:app`) |
| Frontend | Vanilla JS SPA (no framework, no build step) — `api.js` + `app.js` |
| Persistence | **SQLite** (`WATCHLIST_STORE=sqlite`) — a JSON store is supported for backward compat |
| Infra | **Docker Compose** — `api` (FastAPI, holds secrets) + `web` (nginx :8123, proxies `/api/*`) |
| External | Plex · Radarr · Sonarr · TMDB · YouTube · Emby · qBittorrent |

---

## Project layout

```
├── api/             FastAPI app + routes (health, config, status, suggest, media, jobs, ...)
├── domain/          Business layer: state machine, media identity, status rules (single source of truth)
├── services/        External integrations + canonical seams: library/ acquisition/ recommendation/ reconciliation/
├── infrastructure/  Persistence: WatchlistRepository (SQLite/JSON)
├── jobs/            Scheduler + reconcile / daily-watchlist jobs
├── application/     Use-case commands (request_media)
├── scripts/         Host-side cron + dashboard builder (rebuild_dashboard.py)
├── config/          settings.py + recommendations.yaml (quality gates)
├── tests/           pytest (unit/API, all mocked) + frontend .mjs harnesses
└── index.html · api.js · app.js · app.css   SPA (volume-mounted)
```

See **`ARCHITECTURE_GUIDE.md`** for the definitive architecture & agent reference.

---

## Configuration

All config lives in `.env` (canonical: `/workspace/.env`). Key variables:

```bash
MEDIA_HOST=192.168.65.254
RADARR_URL=http://192.168.65.254:7878
RADARR_API_KEY=...
SONARR_URL=http://192.168.65.254:8989
SONARR_API_KEY=...
PLEX_URL=http://192.168.65.254:32400
PLEX_TOKEN=...
TMDB_API_KEY=...        # required for metadata/artwork
EMBY_URL=...            # optional (shares the Plex library)
EMBY_API_KEY=...
QBITTORRENT_URL=http://192.168.65.254:1701

WATCHLIST_STORE=sqlite                 # json | sqlite
WATCHLIST_DB_PATH=/workspace/media/watchlist.db
```

> `MEDIA_HOST` in the live `.env` carries an `http://` prefix — harmless because every service URL is explicit.

---

## Scheduled jobs

- **Daily auto-add** (recommended) — host cron runs `scripts/add_watchlist_cron.py` (TMDB discover, Plex-gated, idempotent).
- **In-process scheduler** (optional) — set `WATCHLIST_SCHEDULER=true` to run reconcile (every 10 min) + daily watchlist job (default 18:00) inside the API container.

---

## Tests

```bash
python -m pytest tests/ -q               # ~216 unit/API tests (all mocked, no live LAN)
node tests/phase25_suggest_frontend.test.mjs   # frontend harnesses
```

---

## Key design principles

1. **Single source of truth** for status & media-type rules → `domain/`.
2. **Plex is authoritative** for ownership; a watch-link failure never flips an available title to "not added".
3. **Canonical service seams** over legacy facades — extend `services/library|acquisition|recommendation|reconciliation/`, not the old wrappers.
4. **Stable identity** — `media_id` (`type:tmdb:{id}` / `imdb` / `tvdb`), never bare `title`.
5. **Config over code** — recommendation quality gates live in `config/recommendations.yaml`.

---

## License

Private project · RKM Media Stack