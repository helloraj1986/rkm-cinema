# Repo Structure Plan — segregate frontend/backend into a production-grade monorepo

> Plan doc for branch `refactor/production-repo-structure` (created 2026-09-08 from `main` @ `e71eaf0`).
> **Status: EXECUTED 2026-09-08 — Phases 0–5 committed (8939cb5 · 0e60ca5 · 5c8b85c · 517daff · 228cb29 + docs commit), gates green after every phase, contract zero-diff. Awaiting RKM-HP deploy (`.\\bootstrap.ps1`) + merge to main + push.**
> Target confirmed by user: `backend/` + `frontend/` (rename `web/` → `frontend/`) + deploy/infra stays at root; one-off tools and stale task/QA docs move to `tools/archive` + `docs/archive` (safe, reversible — git mv only, nothing deleted).

## Goal

Turn the flat, mixed repo root into a clean monorepo:

```
rkm-cinema/                          # deploy/infra + docs + config stay at root
├── .env.example  .gitignore  .dockerignore
├── README.md  ARCHITECTURE.md  PROGRESS.md  TAILSCALE_HOSTING.md
├── docker-compose.yml
├── rkm-cinema.ps1  bootstrap.ps1  bootstrap.sh
├── render_config.py                 # deploy tooling (reads repo .env) — stays at root
├── nginx/default.conf               # infra — stays at root (web image COPYs it)
├── docs/                            # plans, ADRs, api contract — stays at root
│   └── archive/                     # (new) stale task/spec docs moved here
├── backend/                         # FastAPI app + tests + its Dockerfile
│   ├── Dockerfile                   # moved from repo root (api image)
│   ├── requirements.txt  ruff.toml
│   ├── api/  services/  domain/  core/  config/  infrastructure/  application/  jobs/
│   ├── scripts/                     # backend ops: snapshot_openapi, probes, migrate
│   ├── tests/                       # pytest suite + conftest
│   └── provisioner/                 # jellyfin provisioner (own Dockerfile, compose builds ./provisioner)
├── frontend/                        # renamed from web/
│   ├── Dockerfile  package.json  package-lock.json  tsconfig*  vite.config.ts  tailwind.config.js  postcss.config.js
│   ├── index.html  src/
│   └── legacy/                      # old vanilla app served under /legacy
│       ├── index.html  app.js  app.css  api.js  dashboard.html
│       └── tests/                   # node harnesses phase11/18/25/26 (they load api.js/app.js)
└── tools/archive/                   # (new) one-off utility scripts
```

## Current state (audited 2026-09-08)

Repo root today mixes ALL of the following (git tracked unless noted):

- **Backend python tree at ROOT**: `api/ services/ domain/ core/ config/ infrastructure/ application/ jobs/ scripts/` + `requirements.txt` `ruff.toml` + root `Dockerfile` (api image). Import style is top-level (`import api.main`, `from services…`), so CWD/pythonpath matters everywhere.
- **Legacy vanilla frontend at ROOT**: `index.html` (tracked; un-ignored via `.gitignore`), `app.js`, `app.css`, `api.js`; `dashboard.html` + `dashboard-data.json` gitignored/generated. nginx serves `/legacy/` by aliasing the **repo-root mount** (`./:/legacy-source:ro` in compose).
- **React frontend**: `web/` (src, package.json, Dockerfile, .gitignore) + `nginx/default.conf` COPYed by `web/Dockerfile`.
- **Deploy/infra**: `docker-compose.yml`, `rkm-cinema.ps1`, `bootstrap.ps1/.sh`, `render_config.py`, `provisioner/`, `nginx/default.conf`, `.github/workflows/ci.yml` (git-ignored on disk — token lacks `workflow` scope; do NOT push it, but DO update it in place so it is ready).
- **One-off/stale at ROOT (tracked)**: `build_dashboard.py build_first_watchlist.py rebuild_verify.py tvdb_enrich.py verify_dashboard.py verify_html.py verify_trailers.py check_js.py`; markdown: `RKM_Watchlist_Production_Refactor_Task.md .hermes_report_data_model_tests.md progress_download_selection.md ARCHITECTURE_GUIDE.md`; `archive/` (tracked QA/monolith remnants).
- **Ignored junk on disk**: `.env .rkm.env .rkm_state.json data/ rkm.config.toml cinemagoer.db dashboard-data.json dashboard.html app.js.backup* app.js.bak* app.js.orig app.js.before* .pytest_cache/ .ruff_cache/ __pycache__/ .DS_Store` + a stray literal `D:\hermes_agent\hermes-workspace\projects\rkm-cinema\data` directory (created on disk by a bad path — **delete in Phase 0**, not tracked).

## The traps (why this must be phased and gated)

1. **Python top-level imports** — every `import api.* / services.* / config.*` and the Docker CMD `uvicorn api.main:app` assume the packages sit at the process root. After the move, local runs/tests need `cd backend` (or `PYTHONPATH=backend`); the container must keep the packages at `/app/<pkg>` top level.
2. **`scripts/` is imported at runtime by `jobs/add_watchlist.py`** (`from scripts.add_watchlist_cron import main`) and COPYed into the api image — `scripts/` moves WITH the backend, never to tools/archive.
3. **`config/recommendations.yaml`** is loaded via `Path("config/recommendations.yaml")` (CWD-relative) in `services/recommendation/criteria.py` → all local pytest/dev must run with `backend/` as CWD (or config on the path).
4. **Root `Dockerfile` + `web/Dockerfile` COPY paths are context-root-relative** in compose (`build: .` + `dockerfile:`), and `web/Dockerfile` also `COPY nginx/default.conf` from the context root. Decide the compose pattern FIRST (recommended: keep `context: .` at repo root, relocate the Dockerfiles into their dirs and set `dockerfile: backend/Dockerfile` / `frontend/Dockerfile`, updating internal COPY lines to `backend/…` / `frontend/…`). This keeps `.dockerignore` and `nginx/` reachable with minimal churn.
5. **nginx `/legacy/` alias** serves the *repo-root mount*. Once the legacy app moves to `frontend/legacy/`, the compose `web` volume must become `./frontend/legacy:/legacy-source:ro` (or nginx alias changed) — otherwise `/legacy` 404s. Legacy `dashboard-data.json` generation (`scripts/rebuild_dashboard.py`) must target the new legacy dir.
6. **Node harnesses** (`tests/phase*.test.mjs`) load `api.js/app.js` from repo root via `path.join(__dirname,'..')`. They must move beside the legacy app (`frontend/legacy/tests/`) so their `..` still points at the legacy files; pytest suite moves to `backend/tests/`.
7. **Docs/ops references to paths**: README, ARCHITECTURE, PROGRESS verify-command blocks, skill reference `jellyfin-web-playback → references/rkm-cinema.md`, `.github/workflows/ci.yml` (on disk), `scripts/snapshot_openapi.py` sys.path insert. All need path updates; PROGRESS gets a record at the end.

## Phases (each ends committed + gates green)

Gates (after EVERY phase): `cd backend && python -m pytest tests/ -q` (292 passing) · `ruff check api application config core domain infrastructure jobs services` (from backend) · `cd frontend && npm run typecheck && npx vitest run && npm run build` · legacy node harnesses (`node frontend/legacy/tests/phase*.test.mjs`) · `python scripts/snapshot_openapi.py` from repo root with backend on path → contract zero-diff. Live/container steps cannot run in the sandbox (no docker daemon) → after final deploy, RKM-HP eyeball (user) is the acceptance, exactly as established.

### Phase 0 — baseline + hygiene (no structure change)
- Verify gates green on `main`-equivalent state; record baselines.
- `git mv` NOTHING yet. Delete untracked junk: stray `D:\…\data` dir, `.DS_Store` (leave gitignored caches alone).
- Commit: `chore(cleanup): remove stray untracked artifacts` (working tree otherwise clean).

### Phase 1 — create `backend/` and move the python tree
- `mkdir backend frontend`
- `git mv` into `backend/`: `api services domain core config infrastructure application jobs scripts provisioner requirements.txt ruff.toml Dockerfile`
- `git mv tests backend/tests`
- Repo-root `Dockerfile` → now `backend/Dockerfile`; update compose `api.build.dockerfile: backend/Dockerfile` (keep `context: .`), and inside the Dockerfile change COPY lines to `COPY backend/api /app/api` … (context is repo root) OR switch compose api build to `context: ./backend` + plain COPYs. **Choose the second** (cleaner, matches "Dockerfile lives with its app"): `build: { context: ./backend, dockerfile: Dockerfile }`; Dockerfile keeps current COPY lines unchanged; `.dockerignore` moves to `backend/.dockerignore` (copy + extend for root-level excludes no longer needed).
- Update run/test commands everywhere: README, ARCHITECTURE, PROGRESS verify blocks, skill reference, CI (on-disk) to `cd backend && python -m pytest tests/` / `ruff check …` / `uvicorn api.main:app` (dev) etc. `render_config.py` and `bootstrap.*` stay at root unchanged (they don't import app packages).
- Fix `scripts/snapshot_openapi.py` sys.path insert (repo-root → backend) and any `config/settings.py` CWD assumptions (keep `/workspace/.env`+`/app/.env` lookup list; add backend-root fallback so it still works from repo root when needed — verify against real .env).
- Gates; commit `refactor(backend): move FastAPI app + tests under backend/`.

### Phase 2 — rename `web/` → `frontend/`
- `git mv web frontend`
- `web/Dockerfile` → `frontend/Dockerfile`. Compose `web` service: recommend keeping `context: .` and `dockerfile: frontend/Dockerfile` (it needs `nginx/default.conf` from root context) — update the Dockerfile's internal COPYs from `web/…` to `frontend/…` (COPY frontend/package.json…, COPY frontend/ ./, keep `COPY nginx/default.conf`). Update `.dockerignore` (root) patterns `web/dist`→`frontend/dist`, `web/node_modules`→`frontend/node_modules`; `frontend/.gitignore` moves with the dir (git mv keeps it).
- Update `package.json` scripts if they reference `../docs` (they don't — generate:types already points at `../docs/api/openapi.v1.json`, which is still correct from `frontend/`).
- Update CI (on-disk) working-directory `web` → `frontend`; README/ARCHITECTURE/PROGRESS/skill references.
- Gates; commit `refactor(frontend): rename web/ to frontend/`.

### Phase 3 — move the legacy app into `frontend/legacy/`
- `git mv` root `index.html app.js app.css api.js` → `frontend/legacy/`; move (track or copy) `dashboard.html`+`dashboard-data.json` handling: `dashboard.html` is gitignored and generated by `scripts/rebuild_dashboard.py` → update that script's output dir to `frontend/legacy/`; add `frontend/legacy/dashboard-data.json` + `dashboard.html` to `.gitignore` (keep root patterns cleaned).
- `git mv tests/phase11_frontend.test.mjs tests/phase18_frontend.test.mjs tests/phase25_suggest_frontend.test.mjs tests/phase26_jellyfin_play_frontend.test.mjs frontend/legacy/tests/`
- Compose `web` volume `./:/legacy-source:ro` → `./frontend/legacy:/legacy-source:ro` (nginx alias unchanged). nginx `default.conf` unchanged.
- Check legacy asset references are relative (`./app.css ./api.js ./app.js` — they are), so relocation is safe.
- Gates (incl. the 4 node harnesses from their new home); commit `refactor(legacy): move legacy app under frontend/legacy/`.

### Phase 4 — archive one-off tools + stale docs (safe, reversible)
- `mkdir -p tools/archive docs/archive`
- `git mv` into `tools/archive/`: `build_dashboard.py build_first_watchlist.py rebuild_verify.py tvdb_enrich.py verify_dashboard.py verify_html.py verify_trailers.py check_js.py`
- `git mv` into `docs/archive/`: `RKM_Watchlist_Production_Refactor_Task.md .hermes_report_data_model_tests.md progress_download_selection.md ARCHITECTURE_GUIDE.md`; also move current `archive/` contents: QA scripts → `tools/archive/qa/`, its README/md → `docs/archive/` (git mv; keep history).
- Confirm nothing imports them (`grep -rn "build_dashboard\|verify_dashboard\|tvdb_enrich\|rebuild_verify\|check_js" backend/ api web frontend 2>/dev/null` → only archive/README self-refs allowed).
- Gates; commit `chore(archive): park one-off tools and stale docs`.

### Phase 5 — docs, CI, skills, final sweep
- README project-layout section rewritten to the new tree; run/test/deploy command blocks updated; ARCHITECTURE.md pointers updated (root files that moved get new relative links).
- `.github/workflows/ci.yml` (still git-ignored on disk) paths updated (`backend`/`frontend` contexts + cache-dependency-path `frontend/package-lock.json`).
- Update skill reference `jellyfin-web-playback → references/rkm-cinema.md` (repo layout, verify commands, file pointers).
- Update PROGRESS.md header + add LATEST SESSION record (per repo convention).
- Full gates from repo root and from each subdir; contract snapshot zero-diff; `git status` clean of stray files.
- Commit `docs(structure): record repo restructure + final layout`.
- Push `refactor/production-repo-structure`; deploy note for RKM-HP (`.\bootstrap.ps1`) + user eyeball (dashboard, one Play path, /legacy) = acceptance.

## Open questions to confirm at execution time
- Compose api build: switch to `context: ./backend` (recommended) vs keep root context + prefixed COPYs. If RKM-HP rebuild behaves differently, fall back to root-context form.
- Whether `render_config.py` + bootstrap scripts should eventually move under `backend/` or a `deploy/` dir — user said deploy/infra stays at root for this pass; revisit later.
- Keep `requirements.txt` flat at `backend/` (recommended) vs introducing `pyproject.toml`/src-layout — out of scope this pass; structure only.

## Rollback
Every phase is a set of `git mv`s + config edits committed separately → `git revert <phase commit>` (or checkout) restores the app. Because moves preserve history, nothing is ever deleted.
