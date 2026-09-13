# RKM Cinema

A self-hosted **media library, player and acquisition dashboard** for one household.

It runs against **Jellyfin** (the stack ships its own), hands new titles to **Radarr**/**Sonarr** →
**qBittorrent**, and pulls metadata from **TMDB**. You browse your libraries, request what's missing,
watch in the browser, and track every title from *requested* to *available* — with a **sign-in and a
profile per person**, so each member of the house has their own Continue Watching and subtitle
choices while the download queue stays shared.

Private by design: the app is meant to live on a **Tailscale** tailnet, and supports requiring a
session on every route (`RKM_AUTH_REQUIRED`) — one command, proved, with a one-command way back.

---

## What you get

| | |
|---|---|
| **Sign-in + household profiles** | One administrator account signs in; everyone else picks a *profile* on the who's-watching screen. Per-person Continue Watching, history and subtitle choices; one shared library and download queue |
| **Libraries** | Every folder you declare appears in the sidebar and is wired into the media server at deploy time |
| **In-app playback** | Streams through the backend (HLS) — no separate player, no media URLs or keys exposed to the browser |
| **Subtitles** | Search OpenSubtitles inside the player and apply with one click; the choice is remembered per title (optional, needs a free API key) |
| **Requests** | Movie → Radarr, series → Sonarr, with quality-profile choice and duplicate prevention |
| **Discovery** | Global search across what you own *and* what you could request; a suggest screen filtered by genre/year/rating; trailers |
| **Watchlist** | The household acquisition queue, with live status through the whole lifecycle |
| **Diagnostics** | One script that shows containers, volumes, health, library counts, scan state — and answers *"is the running api this folder's code?"* |

---

## Requirements

* **Windows 10/11** with **WSL2** + **Docker Desktop** running (the tested setup), or Linux/macOS with Docker.
* **PowerShell 5.1** (built into Windows) for the scripts; **Python 3** for the diagnostic tools.
* A media drive (or three) that Docker Desktop is allowed to share: *Settings → Resources → File sharing*.
* Optional: a **TMDB API key** (metadata/artwork) and an **OpenSubtitles API key** (subtitles).

---

## Quick start

```powershell
git clone https://github.com/helloraj1986/rkm-cinema.git
cd rkm-cinema

# 1. Configure (once)
copy .env.example .env
notepad .env                        # set RKM_MEDIA_PATH and your media folders

# 2. Bring the stack up (first run provisions Jellyfin: admin user, libraries, scan)
.\rkm-cinema.ps1 deploy

# 3. Check it
.\rkm-cinema.ps1 status
```

Linux/macOS: `./bootstrap.sh` instead of step 2.

Then open **http://localhost:8124/** and sign in. The first `deploy` **prints the administrator
password once** — write it down; there is no default password and nothing in `.env` stores it.
Jellyfin's own web UI is at **http://localhost:8098/web**.

> ⚠ **The first library scan takes 2–4 hours** on a large collection. Don't restart the stack while it
> runs: a cancelled scan can leave shows present with no episodes attached, which reads as
> "everything watched". `.\rkm-cinema.ps1 status` shows scan state.

**First 5 minutes after signing in**

1. Sign in as the administrator → the **Who's watching?** screen appears → pick your own profile.
2. **Optional but recommended** — make the app private: `.\rkm-cinema.ps1 auth on`.
3. **Optional** — add household members: avatar → **Household** → create the account → that person
   picks their profile on *Who's watching?* with the password you set.

---

## Ports

| Service | Host port |
|---|---|
| Dashboard / API | **8124** |
| Jellyfin (bundled) | **8098** → 8096 |
| Radarr / Sonarr / Prowlarr (`fullstack` profile) | 7879 / 8988 / 9697 |
| qBittorrent (`fullstack` profile) | 8080 |

The `fullstack` profile is only for hosts with **no** *arr stack of their own:

```powershell
docker compose -p rkm-bundled --profile fullstack up -d
```

---

## Commands — one script

`.\rkm-cinema.ps1` is the only entry point (`help` explains each verb; `bootstrap.ps1` and `rkm.ps1`
are one-line forwarders kept for older notes).

| Command | What it does |
|---|---|
| `.\rkm-cinema.ps1 status` | Containers, volumes, health, libraries, **and whether sign-in is required** — start here when anything looks off |
| `.\rkm-cinema.ps1 apply` | Make the running stack match this folder (re-render `.env`, rebuild + restart `api`/`web`). **Use after editing `.env` or pulling code** |
| `.\rkm-cinema.ps1 deploy` | `apply` **plus** the Jellyfin provisioner — first run, new libraries or keys |
| `.\rkm-cinema.ps1 auth` | Is sign-in required right now? (answered by the api, not by `.env`) |
| `.\rkm-cinema.ps1 auth on\|off` | Require a session everywhere / open it again (**the recovery if you lock yourself out**) |
| `.\rkm-cinema.ps1 logs [service]` · `backup` · `restore` · `schedule` | Tail the containers; archive and restore server state; install the nightly backup |
| `.\rkm-cinema.ps1 diagnose` · `reset-admin-password` | Why a show looks watched/episodes look missing; the break-glass for a forgotten admin password |

> ⚠ **Editing `.env` alone changes nothing.** A container reads its environment when it *starts*;
> `apply` (or `auth on|off`, which applies for you) is what makes it take effect.

### The three rules

1. **Never `docker compose … down -v`** — it deletes the state volumes (accounts, watch history,
   libraries). Plain `down` is safe.
2. **Don't restart the stack during a library scan** (see above).
3. **Always use `-p rkm-bundled`** (the scripts do). A different project name creates *fresh empty*
   volumes and orphans your real ones.

---

## Configuration

One `.env` at the repo root is the single source of truth — see **[`.env.example`](.env.example)** for
the full annotated list. The keys that matter most:

| Key | Purpose |
|---|---|
| `RKM_MEDIA_PATH` | Primary media root, mounted at `/data` (e.g. `D:/RKM_MEDIA`) |
| `RKM_MEDIA_PATH_2`, `_3` | Extra physical drives, mounted at `/media2`, `/media3` — **two drives need two entries** |
| `MEDIA_LIBRARY_N_NAME/_PATH/_TYPE` | Sidebar libraries. `PATH` is a host path or container path; `TYPE` = `movie`/`tv`/`mixed`. Leave all empty to auto-discover every folder |
| `RKM_DASHBOARD_PORT`, `RKM_JELLYFIN_PORT` | Host ports (defaults `8124` / `8098`) |
| `RKM_AUTH_REQUIRED` | `false` (default) = the app answers anyone who can reach it; `true` = every route needs a session. Prefer `.\rkm-cinema.ps1 auth on\|off` over editing it |
| `TMDB_API_KEY` | Metadata, artwork, discovery, similar titles |
| `RADARR_URL` / `SONARR_URL` + keys | Your acquisition stack (this machine's or one on the LAN) |
| `OPENSUBTITLES_API_KEY` | Online subtitle search/download (free key; searching is unmetered, downloads are metered) |
| `WATCHLIST_DB_PATH` | The app's own watchlist + session store live here (on the media root, so a rebuild doesn't sign you out) |

**A container can only read what is bind-mounted.** Declaring a *library* on a drive is not enough —
the *drive* must also be declared as a media root.

---

## Troubleshooting

| Symptom | First step |
|---|---|
| Anything looks off | `.\rkm-cinema.ps1 status` |
| Library rows greyed out | `.\rkm-cinema.ps1 status` — usually a missing credential or a library path that doesn't resolve; it prints the warning |
| Every show shows as watched / episodes missing | `.\rkm-cinema.ps1 diagnose` |
| *"Your profile's sign-in has expired"* | Pick the profile again on *Who's watching?* — your session is fine, this is not a sign-out |
| Locked out of the administrator account | `.\rkm-cinema.ps1 reset-admin-password` (no old password needed) |
| Locked out of the app entirely | `.\rkm-cinema.ps1 auth off` |

Full runbook — failure modes, recovery ladders, where state lives: **[`docs/OPERATIONS.md`](docs/OPERATIONS.md)**.

---

## Development

```powershell
# Backend (from backend/)
python -m pytest tests/ -q        # 1107 tests, no live LAN required
ruff check api application config core domain infrastructure jobs services

# Frontend (from frontend/)
npm ci
npm run dev                       # Vite dev server (proxies /api to 127.0.0.1:8000)
npm test                          # 294 Vitest tests
npm run typecheck                 # tsc --noEmit
npm run build                     # production build (baked into the web image)
npm run generate:types            # regenerate TS types from the frozen contract
```

The `/api` contract is **frozen** per [ADR-0001](docs/adr/ADR-0001-freeze-api-contract.md) — additive
only; regenerate types from `docs/api/openapi.v1.json` rather than hand-writing shapes. A **new route**
needs a line in `backend/tests/test_route_protection.py::ROUTE_LEVELS` (the suite fails without one).

**Layout**

```
backend/     FastAPI app + pytest suite (api · domain · services · infrastructure · jobs · config)
frontend/    React 18 + TypeScript + Vite — the only UI (built into the web image)
nginx/       web container: the shell, the /api proxy, artwork cache policy
tools/       diagnostics and probes (Python; work inside the container and on Windows)
scripts/     backup / restore / scheduled-task PowerShell
docs/        architecture, runbook, ADRs, plans, frozen contract, session history
rkm-cinema.ps1   the one script you run
```

---

## Documentation

| Doc | Contents |
|---|---|
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | **The runbook**: commands, rules, fresh install, recovery, the auth switch, where state lives |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | How the system is built, including the identity model (§11) |
| [`docs/adr/`](docs/adr/) | Architecture decision records — start with [ADR-0006](docs/adr/ADR-0006-delegated-identity-and-sessions.md) (identity) and [ADR-0001](docs/adr/ADR-0001-freeze-api-contract.md) (the frozen contract) |
| [`docs/api/openapi.v1.json`](docs/api/openapi.v1.json) | The frozen API contract |
| [`docs/TAILSCALE_HOSTING.md`](docs/TAILSCALE_HOSTING.md) | Remote/phone access over Tailscale |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | What changed, session by session — the project's working memory |

Plans for the workstreams that built this (identity, household accounts, subtitles, the bundled
stack) live beside them in `docs/` as `*_PLAN.md`.
