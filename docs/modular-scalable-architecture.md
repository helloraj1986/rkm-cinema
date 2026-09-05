# RKM Cinema — Modular & Scalable Architecture Plan

> Status: **PLAN** (no code changed). Gate before continuing the feature roadmap (item 2+).
> Branch: `experiment/bundled-docker-stack`

## Why this plan exists

The app works and has proven the core loop (in-app playback, resume/progress, library grid,
Continue Watching, TV episodes, daily scan). But it was built as a **working prototype first**,
and that is now the constraint:

- **Frontend is a single 2,191-line `app.js` monolith** (plus `api.js`, `app.css`). Every feature
  appends global render functions + delegated handlers. This is not maintainable past a handful
  of screens and is exactly what the roadmap already flagged as the "Appendix A" re-platform.
- **Backend is modular but carries consolidation debt**: canonical subpackages
  (`services/library/`, `services/acquisition/`, `services/recommendation/`,
  `services/reconciliation/`) coexist with legacy facades/shims (`services/plex.py`,
  `services/emby.py`, `services/radarr.py`, `services/sonarr.py`, `services/recommendations.py`,
  `services/media_status.py`). Root `README.md`/`ARCHITECTURE.md` are stale.
- **No CI**, no typed API contract the frontend consumes, no per-feature boundaries.

> Decision: keep the **FastAPI/Python backend** (already sound; only consolidate + formalize it).
> Rewrite only the **frontend** to React + TypeScript behind a **frozen `/api` contract**. The
> backend contract is the seam that de-risks the re-platform.

---

## 1. Current architecture (ground truth)

### Backend (`api/`, `services/`, `domain/`, `core/`, `infrastructure/`, `application/`, `jobs/`, `config/`)

```
api/routes/*                  Thin HTTP routes; no business rules.
  config health download search quality status library media
  watchlist reconcile suggest jobs jellyfin_poster jellyfin_stream
domain/                       Pure rules (enums, MediaStatus, identity, resolver) — no infra/HTTP.
services/
  library/      LibraryProvider ABC + Plex/Emby/Jellyfin + WatchLinkResolver + factory(MEDIA_SERVER)
  acquisition/   AcquisitionService (movie→Radarr, series→Sonarr) + ABC
  recommendation/ CandidateGenerator / RecommendationManager / criteria / ranker
  reconciliation/ Reconciler (canonical fact-gatherer → MediaSnapshot)
  plus facades:  plex.py emby.py radarr.py sonarr.py recommendations.py media_status.py
core/                          cache (TTLCache), http_client, logging, exceptions
infrastructure/database/       repository seam (SQLite) + job_runs
application/commands/          use-case layer (RequestMediaCommand)
jobs/                          reconcile, daily_watchlist, add_watchlist, library_scan, scheduler
config/settings.py             single typed settings source
```

**Strengths to preserve:** thin routes; DI-ready services (`config`/`http` injectable); central
`domain/status` resolver; provider ABC + `build_library_service` factory; repository seam; one
cache primitive; scheduler + `JobRunner` audit.

**Debt to remove:** BC facades (parallel implementations) → §43 rule; stale docs; no
capability interface for the newer provider methods (`all_items`, `continue_watching`,
`episodes`, `refresh_library`) — they exist only on the Jellyfin provider, not declared in the ABC.

### Frontend (`app.js`, `api.js`, `app.css`, `index.html`, `dashboard.html`)

```
app.js     2,191 lines — hero, Discover rows, carouse, grid, modal, trailer, player +
            resume reporting, up-next, episode picker, library view, suggest, search,
            watchlist, lazy-loading, toasts, keynav. All global scope.
api.js       124 lines — fetch wrappers (API.*).
app.css      967 lines — global stylesheet.
```

**Problem:** no module boundaries, no componentization, no typed data, global state
(`DATA`, `RES`, `LIBALL`, `LIBWATCH`, `modalEntry`), imperative DOM rendering + delegated
events. Works, but every feature adds joins to one file.

---

## 2. Target architecture

### 2.1 High-level

```
┌──────────────────────────── Browser ────────────────────────────────┐
│  web/  (React 18 + TypeScript + Vite + Tailwind)                     │
│  ┌────────────┐  router / layout    ┌────────────────────────────┐  │
│  │ app shell  │───────────────▶    │ features/  (one per domain) │  │
│  └────────────┘                     │   library / playback /      │  │
│        ▲                           │   search / watchlist / recs │  │
│        │ typed client (openapi-    │   suggest / settings        │  │
│   ┌────┴─────────────┐             └────────────┬───────────────┘  │
│   │ lib/api * client │ ◀── generated types ────┘                   │
│   └──────────────────┘  (frozen /api contract)                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP only /api/*
┌──────────────────────────────▼──────────────────────────────────────┐
│  api/ (FastAPI) — thin, ROUTES ONLY. One OpenAPI schema is truth.   │
│  application/commands → services/* (canonical) → jellyfin/radarr …  │
│  domain/  core/  infrastructure/  jobs/  config/                     │
│  NOTE: keep Plex/Emby/Jellyfin behind ONE media-gateway SPI.         │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Backend consolidation targets

1. **One consolidated `services/library/` = "media gateway"** (keep the dir, extend the ABC).
   - Promote the Jellyfin-only capabilities into the **`LibraryProvider` ABC / a capability
     mixin**: `all_items()`, `continue_watching(limit)`, `episodes(series_id)`,
     `refresh_library()`, `get_poster()`. Every provider returns the same surface (Plex/Emby
     implement what they can; others default to `[]`/`False`). Routes call the ABC, not
     `getattr(provider, "episodes", …)`.
2. **Delete the BC facades** and point their imports at canonical modules:
   - `services/plex.py`, `services/emby.py` → `services/library/plex.py`, `services/library/emby.py`
   - `services/radarr.py`, `services/sonarr.py` → `services/acquisition/radarr.py|sonarr.py`
   - `services/recommendations.py` → `services/recommendation/`
   - `services/media_status.py` → `services/reconciliation/` (already a shim)
   - `services/trailers.py` → keep (thin) or move under `services/metadata/`
   - Keep as **re-export stubs with a `DeprecationWarning` for one release**, then delete, so
     nothing breaks mid-flight.
3. **Freeze the `/api` contract**: export `openapi.json` and treat v1 as immutable for the
   frontend. New fields are additive. Versioning (if ever needed): `/api/v1/*`.
4. **Generate the typed client** from OpenAPI (`openapi-typescript`) so the frontend and backend
   can never drift.

### 2.3 Frontend target (`web/`, new dir; old `index.html` untouched until parity)

```
web/
  package.json  vite.config.ts  tsconfig.json  tailwind.config.js
  index.html
  src/
    main.tsx  app/
      router.tsx            # TanStack Router or React Router
      layout/  (AppShell, Sidebar, Header, Toasts)
    features/               # one dir per bounded context — owns its API + store slice
      library/   api.ts · components/ · hooks/ · store.ts        # poster wall, Continue Watching
      playback/  api.ts · Player.tsx · EpisodePicker · usePlayback · upNext · markWatched
      watchlist/ api.ts · components/ · store.ts
      search/    api.ts · SearchBox · results
      discover/  api.ts · rows · ContinueWatchingRow · hero
      suggest/   api.ts · filters · grid
      settings/  api.ts · (backend config, scan button wiring)
    components/
      ui/         Button, Modal, Skeleton, Toast, Badge, ProgressBar …   # primitives
      media/      MediaCard, ResumeBar, WatchedTick, Player, EpisodeRow  # composed
    lib/
      api/        client.ts · types.ts (generated) · endpoints/
      storage/    resume/watched persistence if we take ownership from Jellyfin
    hooks/
    styles/
  tests/   (vitest + @testing-library/react; Playwright e2e)
```

- **State:** server state via **TanStack Query** (cache + invalidation; the library-scan job
  invalidates library/playback queries) + a light **Zustand** store for UI/auth state. No
  hand-rolled global `DATA`/`RES` maps.
- **Capabilities/status** stay backend-derived (`MediaResponse` §18) — the UI renders, never
  reconstructs.
- **Feature flag** each ported view (`?v=react` / config) so the old `app.js` app keeps working
  while we migrate.

### 2.4 Cross-cutting

- **CI** (GitHub Actions): ruff/mypy + `pytest` for backend; `tsc` + `vitest` + Vite build for
  frontend; run on every push to the branch.
- **Docs**: rewrite `ARCHITECTURE.md` + `README.md` to match reality; add `docs/adr/` for the
  big choices; this plan + the API contract live in `docs/`.
- **Config**: keep single `config/settings.py`; frontend config via `/api/config` only.

---

## 3. Decisions (with rationale + alternatives)

| Decision | Choice | Why / alternative |
|---|---|---|
| Frontend framework | **React 18 + TS + Vite** | Matches user's senior stack (React/TS/Next/Tailwind); huge ecosystem; Vite = fast dev + easy deploy alongside nginx. Alternative: Vue/Svelte — same modularity, less REPL fit. |
| Server state | **TanStack Query** | Cache + auto-invalidation tied to scan/job runs; avoids hand-rolled polling maps. |
| Client state | **Zustand** (light) | Tiny, scalable slice pattern. Alternative: Redux Toolkit (heavier). |
| Backend language | **Keep Python/FastAPI** | Already sound; rewriting is the classic trap. Only consolidate facades + extend the ABC. |
| API contract | **Frozen `/api` + generated client** | De-risks the rewrite; the seam between tiers. |
| Monorepo | Yes — one repo, `web/` + backend dirs | Simpler deploy/CI than a multi-repo split. |
| Legacy app removal | Remove only at **feature parity** behind a flag | Avoids losing a working demo during migration. |
| Multi-user/auth (roadmap item 6) | Architecture has an `auth` feature slice + per-user watch map seam | Don't build it yet (YAGNI) but don't make it impossible. |

---

## 4. Migration phases (non-breaking)

> Order matters: **freeze the contract first**, then build the shell, then port features, then
> formalize backend, then cut over and delete legacy. Each phase ends green + committed.

### Phase 0 — CI + contract freeze + docs reset (fastest win)
- Add GitHub Actions: backend lint+`pytest`, frontend `tsc`+`vitest`+build (once `web/` exists).
- Snapshot `openapi.json` into `docs/api/openapi.v1.json`; treat `/api` as frozen.
- Rewrite `README.md`/`ARCHITECTURE.md`; add this plan + an ADR for "freeze /api, React/TS frontend".
- **Exit:** CI green on push; contract snapshotted.

### Phase 1 — Consolidate the backend facades + extend the LibraryProvider ABC
- Delete BC shims (point imports to canonical; re-export stubs → remove).
- Add capability methods to the ABC/mixin (`all_items`, `continue_watching`, `episodes`,
  `refresh_library`, `get_poster`); update routes to call the ABC instead of `getattr`.
- Add `ADRs`; run full `pytest` (target: 250+ green).
- **Exit:** no duplicate service modules; provider surface is uniform.

### Phase 2 — Stand up the `web/` shell + typed client
- Vite React/TS app, router, `AppShell`/`Sidebar`/`Header`, Tailwind theme.
- Generate `types.ts` from `openapi.json`; `lib/api/client.ts`.
- Feature-flag routing so the shell can render behind a config toggle.
- **Exit:** `web/` builds + a blank shell showing backend `/api/config` health.

### Phase 3 — Port features to feature slices (one per sub-commit, parity each)
Order by current value + lowest risk:
1. `library` (poster wall, Continue Watching, library scan wiring)
2. `playback` (player, resume, progress reporting, up-next, mark-watched — roadmap item 2 lands here)
3. `discover` (hero + rows + continue-watching row)
4. `watchlist`, `search`, `suggest`, `settings`
Each turns on behind the flag; old app still serves the not-yet-ported views.
- **Exit:** each ported view matches the legacy UI 1:1.

### Phase 4 — Cut over + retire legacy
- Flip default to the React app; remove `app.js` legacy paths; delete `index.html` legacy or
  keep as `.legacy` for history.
- **Exit:** `app.js`/`api.js`/legacy CSS deleted; only `web/` remains.

### Phase 5 — Post-restructure roadmap
Resume **item 2 (watch-state)** … then items 3–5 on the new modular structure. Multi-user
(item 6) now slots into the `auth`/`playback` slices cleanly.

---

## 5. Higher-order architecture rules (use-principally)

- **Layering:** `route → command → service → provider(db/api)`. Routes never embed business
  rules; services never talk HTTP; `domain/` is pure.
- **One way to do a thing (§43):** one identity, one status resolver, one acquisition service,
  one library SPI, one cache primitive, one repository. Search + consolidate before adding.
- **Contract-first:** any frontend need = an additive field/endpoint on the frozen `/api`;
  regenerate the client.
- **Provider SPI:** all media-server providers (Plex/Emby/Jellyfin) implement the same
  capability surface; frontend never branches on provider name.
- **Additive, flag-gated:** no breaking cut-overs; keep a recoverable demo at every commit.

---

## 6. Risks, tradeoffs, open questions

**Risks**
- **"Big rewrite" smell (highest):** mitigated by (a) freezing `/api`, (b) backend unchanged,
  (c) feature-flagged incremental port, (d) parity-check each view before retirement.
- **Contract drift:** closed by generating the client from OpenAPI + CI typecheck.
- **Facade-deletion breakage:** close with re-export stubs + deprecation warning for one release.
- **Time:** the re-platform is the largest effort on the roadmap; it's the price of scalability
  and matches the original "Appendix A" intent. Sequencing it before items 2–5 means items
  2–5 get built once, on the right foundation (avoids the re-platform-after-items-2-5 trap).

**Tradeoffs**
- Keep the demo (first) vs. rewrite-fast (fastest clean code). → Choose **keep the demo, migrate
  incrementally** — acceptable given it's a personal/proof tool.
- Python backend vs. all-TypeScript (NestJS). → Keep Python; it's working and test-covered.

**Open questions (answer before/at Phase 2)**
1. Do we ever need **multi-user / auth**? Gating the `auth` slice + per-user watch state.
2. Target runtime for `web/`: same nginx volume mount as today (`web` container serves `dist/`)?
   (Recommend yes — nearly free.)
3. Do we keep `dashboard.html`/`dashboard-data.json` legacy or fold into Discover?
4. Testing bar: unit (vitest) + a few Playwright e2e (play/resume/scan) — enough, or heavier?

---

## 7. Suggested task queue (next sessions)

1. **Phase 0:** CI + `openapi.json` snapshot + docs reset. (~half day)
2. **Phase 1:** backend facades consolidation + ABC capability surface. (~1 day)
3. **Phase 2:** `web/` shell + typed client + flag. (~1 day)
4. **Phase 3:** port `library` → `playback` (incl. **item 2 watch-state**) → `discover` → rest. (~2–4 days)
5. **Phase 4:** cut over, delete legacy. (~half day)
6. Then items 3–5 on the new structure.

> Recommended next session: **Phase 0 + Phase 1** (CI + backend consolidation + contract freeze).
> It's low-risk, immediately tests the "modular" thesis, and makes the React port far safer.

---

## 8. Validation

- Backend: `python -m pytest tests/ -q` stays green (target >250), no duplicate module imports.
- Frontend: `npm run typecheck`, `npm run test` (vitest), `npm run build` all pass on `web/`.
- Parity: each ported view visually matches legacy (manual + a Playwright smoke: library loads,
  play at poster, resume bar, Continue Watching, manual scan, TV episodes).
- Contract: `curl /api/openapi.json` matches `docs/api/openapi.v1.json` (or is pure additive).