# RKM Cinema — Architecture

> ⚠ **Integrating with the phone/tablet app? Read §17 first** — the three parts (backend · web · the
> iOS shell) and the two seams between them, in one place. §2 is the same picture with the shell in it.

> **Identity: read §11 and [`adr/ADR-0006`](adr/ADR-0006-delegated-identity-and-sessions.md) before
> touching anything that calls the media server.** Since 2026-09-12 the app has a session per browser
> and a *profile* per person, and the credential a call is made with is decided in ONE place
> (`api/session.py`). A route that skips that seam serves one household member another's library —
> silently, and with no error anywhere.

> ⚠ **2026-09-08:** repo restructured into a monorepo (`REPO_STRUCTURE_PLAN.md`)
> and the legacy vanilla app removed (branch `chore/remove-legacy-app`):
> **`backend/`** holds the FastAPI app + tests, **`frontend/`** the React/TS shell
> (renamed from `web/`) — now the only UI; the `/legacy` route, `frontend/legacy/`
> and the `rebuild_dashboard.py` static dashboard generator are gone (archived in
> `tools/archive/`). Deploy/infra + docs stay at the root. The authoritative
> project tree + commands live in `../README.md`.

> **Single codebase.** The monolithic `api.py` has been archived
> (`tools/archive/api_legacy_monolith.py`) and the production backend is now the
> modular FastAPI app: **`uvicorn api.main:app`** (see `backend/Dockerfile`). There is
> exactly ONE implementation of each business rule. Add features to the modular
> tree, not a parallel monolith.

---

## 1. What this is

A self-hosted **media library, player and acquisition dashboard** for one household. It:

- Shows what's in your **Jellyfin** library (source of truth for availability) and recently added.
- **Plays it in the browser** — same-origin HLS/MSE through the api, so no media URL or server
  credential is ever exposed to the client.
- Lets you **request** movies/series, which are added to **Radarr** (movies) or **Sonarr** (TV) and downloaded via **qBittorrent**.
- Tracks each title through a lifecycle: requested → downloading → downloaded → available → recommended (history).
- Deep-links each available title straight into **Jellyfin**'s own web UI.
- Fetches **posters/backdrops/genres** from **TMDB**, **trailers** by scraping `youtube.com` (no YouTube API key), and **subtitles** from OpenSubtitles.com (optional, ADR-0005).
- **Signs people in and keeps them apart.** One administrator holds the server session; everyone else
  picks a *profile* on the who's-watching screen, and each profile gets its own Continue Watching,
  history and subtitle choices. The watchlist (the acquisition queue) and the subtitle download
  quota stay deliberately **shared** — see §11.

Access is private over **Tailscale**, and — since `RKM_AUTH_REQUIRED` was armed — the app itself is
closed: the browser talks to nginx on :8124, nginx proxies `/api/*` to the FastAPI container (which
holds all secrets), and every route but `/api/health` and the sign-in routes needs a session.

---

## 2. High-level layout

**Three parts, two seams.** There is ONE UI (the React app), ONE implementation of every business rule
(the api), and ONE native app whose job is *only* the things a web page cannot do. Nothing below is a
second implementation of anything else (see §17 for the long form).

```
                    ┌──────── the ONE UI: frontend/ (React 18 + Vite) ────────┐
                    │  built INTO the web image — not volume-mounted (§13)    │
                    └───────┬────────────────────────────────────┬────────────┘
                            │  served over http(s)               │
        ┌───────────────────┴──────────┐              ┌──────────┴───────────────────────────┐
        │ BROWSER  (Tailnet or LAN)    │              │ iPhone/iPad — apple/ios (WKWebView)  │
        │  the SPA, loaded from nginx  │              │  loads the SAME live SPA, and adds    │
        │                              │              │  what a page cannot do:              │
        │  · full UI, no install       │              │   · background URLSession downloads  │
        │  · nothing offline           │              │   · the app's own filesystem         │
        └───────────────┬──────────────┘              │   · a LOOPBACK HTTP server (127.0.0.1)│
                        │                             │   · window.__rkmOffline (the bridge)  │
                        │                             └───────┬──────────────────┬────────────┘
                        │  same-origin /api/*  ─────── SEAM 1 │                  │ SEAM 2:
                        │  (the same one the page uses)      │                  │ page ↔ native bridge
                        ▼                                    ▼                  ▼
     ┌──────────────────────────────────────────────────────────────────────────┐
     │ nginx — web container, host port RKM_DASHBOARD_PORT (:8124)               │
     │   /            → the built SPA        Cache-Control: no-cache             │
     │   /assets/*    → year-long immutable  (content-hashed by the build)       │
     │   /api/*       → api:8000             no-store JSON · artwork 7 days      │
     │   /openapi.json→ api:8000             (so tools/check_deployed.py works)  │
     └───────────────────────────────────┬───────────────────────────────────────┘
                                         ▼
     ┌──────────────────────────────────────────────────────────────────────────┐
     │ FastAPI — api container:  uvicorn api.main:app                           │
     │  holds EVERY secret · sessions + identity (§11) · the only route surface  │
     │   /api/library* ·status ·search ·download   the library + acquisition     │
     │   /api/jellyfin/stream|hls|progress|poster  in-browser playback proxy     │
     │   /api/offline/*                            package + serve a download    │
     └───┬──────────────┬───────────────┬──────────────────┬────────────────────┘
         ▼              ▼               ▼                  ▼
   Jellyfin        Radarr/Sonarr    TMDB · OpenSubtitles   state on disk (§10)
   THE media       Prowlarr/qBit     YouTube (scraper)      watchlist.json ·
   truth     ──►  (acquisition)     (metadata/subtitles)   sessions.json ·
   (files on D:\RKM_MEDIA · B:\RKM_MEDIA)                  subtitles.json
```

⚠ **The seams, named — these are the only two places integration happens:**

| Seam | Protocol | Who owns the contract |
|---|---|---|
| **1. Page → api** | plain HTTP, same origin, `HttpOnly` session cookie | `docs/api/openapi.v1.json` + `frontend/src/lib/api/client.ts` (ADR-0001, additive-only) |
| **2. Page ↔ native** | `postMessage` / injected JS global, both directions | `OfflineBridgeContract.swift` (pure, executed on Linux) + `docs/adr/ADR-0009` (versioned `{v:1}`) |

⚠ **Nothing else is a seam.** The shell has no API client of its own for the app's data (it does not
need one — the page talks to nginx directly), and the page never touches the app's filesystem (it cannot
— different process, different sandbox). **Anything that looks like a third integration path is a
design smell**; §18.2 is the one exception worth having (bearer tokens for native fetches).

**Who owns which truth — the rule that explains most of the code:**

| Fact | Owner | Why not the other side |
|---|---|---|
| is this title in the library · resume position · watched | **Jellyfin** | it holds the files; the app is a client of it (§6) |
| the session, who is watching, which credential a call acts as | **the api** (`sessions.json` + §11) | one place decides identity, or a call silently acts as the admin |
| the acquisition queue, subtitle choices, staged downloads | **the api** (`watchlist.json`, `subtitles.json`, `/shared/offline`) | durable, shared, and safe from the OS purging a browser cache |
| the UI, and every rule about what is *offered* | **frontend/** | one UI, so it cannot disagree with itself across clients |
| **what is on THIS device** · whether a film can play with no network | **the native app** | only the app can see its own container and its own socket |

⚠ **A fact has exactly one owner, and a screen that needs two facts must ask two owners** — that is why
the detail page asks the app *and* the server before it offers a download (§17.4).

---

## 3. Repository layout

```
rkm-cinema/                       (full annotated tree in ../README.md)
├── backend/                      FastAPI app + pytest suite + Dockerfile
│   ├── api/                      main.py app factory + routes/ (thin routers)
│   ├── services/                 external integrations + app services
│   │   ├── library/ acquisition/ recommendation/ reconciliation/  (canonical)
│   │   ├── radarr.py sonarr.py tmdb.py youtube.py
│   │   ├── qbittorrent.py watchlist.py media_status.py recommendations.py
│   ├── domain/                   business layer: state machine + resolver
│   ├── core/  config/  infrastructure/  application/  jobs/
│   ├── scripts/                  daily pipeline + probes
│   ├── provisioner/              bundled-stack Jellyfin provisioner
│   └── tests/                    unit + API tests (mockable, no live LAN)
├── frontend/                     React 18 + TS + Vite shell (the only UI)
├── docs/                         architecture, plans, ADRs, API contract,
│                                 OPERATIONS.md, PROGRESS.md, ARCHITECTURE.md
├── nginx/  scripts/  tools/      web config; backup/restore; diagnostics
├── docker-compose.yml  bootstrap.ps1  bootstrap.sh  render_config.py  rkm-cinema.ps1
└── README.md  .env (single config)  .env.example (committed template)
```

Run everything from the subdirs: `cd backend && python -m pytest tests/ -q`,
`cd frontend && npm run typecheck && npx vitest run && npm run build`.
Deploy stays at the root (`.\\bootstrap.ps1`, wrapped by `.\\rkm-cinema.ps1 deploy`).

---

## 4. Dependency direction (the contract)

```
 React shell (frontend/src)
      ↓  /api/*            one client: frontend/src/lib/api/client.ts
 API routes (api/routes/*)         thin: validate → call service → map response
      ↓                           every app router publishes the identity (§11)
 Domain + app services (services/)  business rules once, in one place
      ↓
 External service clients (services/*, core/http_client)  isolated URL/auth/HTTP
      ↓
 Jellyfin · Radarr · Sonarr · TMDB · qBittorrent · YouTube
```

Rules:
- Routes **never** call external APIs directly or build raw `urllib` calls.
- Services **never** leak secrets; the browser never sees keys/URLs (nginx fronts `/api`).
- The `domain/` state machine + resolver are the **single owners** of status and movie/tv rules.
- **The credential a call is made with comes from `api/session.py` only** (`acting_media_token` /
  `owner_media_token`). Build a URL with a token from anywhere else and that call silently acts as the
  administrator — §11.

---

## 5. Endpoints — and what each one requires

**The frozen contract is the list** (`api/openapi.v1.json`, ADR-0001: additive-only). What matters
architecturally is the LEVEL of each route, and that is declared and enforced in
`tests/test_route_protection.py::ROUTE_LEVELS` — *the* inventory: it fails if a route ships without a
decision, and a second test fails if a session route is not on the Phase-5 dependency.

| Level | Count | Meaning |
|---|---|---|
| **PUBLIC** | 1 | `GET /api/health` — the Docker HEALTHCHECK calls it; a 401 here marks the api unhealthy and cascades |
| **auth-route** | 6 | `/api/auth/*` — reachable signed out (sign-in cannot require a session) and deliberately **not** behind the credential probe: they are the FIX for a refused credential |
| **session** | 36 | everything else in the app — the identity is published for the request (§11) |
| **ADMIN** | 11 | `require_admin_session`: a Jellyfin **administrator**, strictly, *even while* `RKM_AUTH_REQUIRED` is false. The 6 `/api/admin/*` household routes plus the four operational ones Phase E gated (`POST /api/download`, `POST /api/jobs/{name}/run`, `GET /api/library/scan`, `POST /api/reconcile`) |

Grouped by what they are for:

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service up/down flags (radarr, sonarr, tmdb, qbit, jellyfin) + `degraded`. **Public** |
| `POST /api/auth/login\|logout` · `GET /api/auth/me` | The session: sign in (administrator only), revoke server-side, who am I |
| `GET /api/auth/profiles` · `POST /api/auth/profile` | "Who's watching?" — the picker's list and the switch (which re-authenticates as that profile) |
| `POST /api/auth/profile/password` | Change **your own** password (proves the current one). The administrator's reset of somebody else is a different route, by design |
| `GET /api/config` | Public-safe booleans + dashboard freshness (never keys/URLs) |
| `GET /api/status` | Per-title state via the `Reconciler` → `domain.status.resolve_status()`; includes the watch url + item id |
| `POST /api/download` | Add movie→Radarr / series→Sonarr (title fallback, "pick one" ambiguity). **Admin** |
| `GET /api/search` · `/api/search/global` | Watchlist + live TMDB search; owned media + discovery |
| `GET /api/library*` | Counts, folders, per-folder items, continue watching, recently watched, episodes |
| `GET /api/jellyfin/poster\|person\|backdrop` | Same-origin artwork proxy — the api key stays server-side |
| `GET /api/jellyfin/stream\|hls` · `POST /api/jellyfin/progress` | In-browser playback + watch-state reporting |
| `GET·POST /api/jellyfin/subtitle-*` | Subtitle search/select/disable (ADR-0005) |
| `GET /api/quality` | Radarr/Sonarr quality profiles for the download dialog |
| `GET /api/admin/*` | Household: list accounts, grant libraries, create/rename/policy/password/delete. **Admin**, and refused while somebody else's profile is selected |
| `POST /api/jobs/{name}/run` · `GET /api/library/scan` · `POST /api/reconcile` | Operational verbs (a full scan, a generic job, a reconcile pass). **Admin** |

---

## 6. Media status state machine

The canonical resolution lives in `domain/state_machine.py::resolve_status`:

```
 the server has it → AVAILABLE        (with the watch link + item id)
 else *arr has file → DOWNLOADED
 else qBittorrent active → DOWNLOADING (progress/speed/eta)
 else *arr queue  → DOWNLOADING
 else *arr record exists → REQUESTED ("waiting — indexers down" if health says so)
 else             → NOT_ADDED
```

**The media server (Jellyfin) is the source of truth** for availability. A title
it holds is `available` even if its *arr record is stale/missing. The `Reconciler`
gathers the external facts and feeds them to `resolve_status`; the domain module
decides. The `WatchLinks` value object carries `library_available`, `watch_url`
and `server_item_id` (the server's own item id, not a URL) for
`available`/`downloaded` titles.

> **Performance guard:** the Jellyfin provider caches its full item listing (60 s
> window) and the reconciler caches its whole result on the watchlist file's
> mtime. The status pass asks for every watchlist entry; without those caches one
> `/api/status` request re-scanned the library per entry and blew the request
> window.

---

## 7. Download flow

1. Frontend `POST /api/download` → `DownloadService.download(...)`.
2. Media type resolved by **`domain/resolver.py`** (single authoritative rule):
   explicit `type` → watchlist `isSeries` → Radarr/Sonarr lookup → default movie.
3. `RadarrService.add_movie` / `SonarrService.add_series`:
   - Lookup by `imdb` first; if it resolves nothing, **fall back to title (+year) search**.
   - Unique match → used. Multiple matches, none exact → **`ambiguous`** ("pick one" list), never a silent guess.
4. Cross-service fallback: a "No Radarr match" on a real series retries Sonarr (and vice-versa).
5. `DownloadResult` (typed domain object) maps to `DownloadResponse` with predictable HTTP codes (404 ambiguous, 502 unavailable, 503 not configured).

---

## 8. Watch links (Jellyfin only)

There is exactly ONE media server (Jellyfin, bundled) and it is the only source of
watch links — the Plex/Emby providers were removed on 2026-09-11
(`adr/ADR-0004-remove-plex-emby-support.md`).

Two ways to watch an available title, both same-origin:

- **In-app playback** (`jellyfinItemId`): the recorded item id drives
  `/api/jellyfin/stream|hls` through the same proxy the browser already talks to,
  so no token or cross-origin request is involved.
- **Deep link** (`jellyfinUrl`): `{browser base}/web/index.html#!/details?id={itemId}`
  on the browser-reachable host. The base is config-driven — `JELLYFIN_BROWSER_URL`
  (defaults to the Tailscale MagicDNS HTTPS host, see `TAILSCALE_HOSTING.md`). The
  container-internal `JELLYFIN_URL` is the api's own address and is **never** used
  to build a user link.

The `/api/status` payload therefore carries `jellyfinUrl` + `jellyfinItemId`; the
reconciler's snapshot keeps a `watch` map keyed by provider name, holding the
`jellyfin` entry's `available` / `url` / `item_id`.


## 9. External integrations

| Service | Responsibility |
|---|---|
| `RadarrService` | Movies, `lookup_movie`, `search_movies` (title fallback), `add_movie`, profiles/queue, indexer health |
| `SonarrService` | Series, `lookup_series`, `search_series` (title fallback), `add_series`, tvdb resolve, profiles/queue |
| `TMDBService` | Movie/show details, posters/backdrops/genres, search |
| `YouTubeService` | Scrape youtube.com for the official trailer (no API key) |
| `QBittorrentService` | Torrent list + download-state (used by status) |
| `TrailerService` | Legacy trailer fallback |
| `OpenSubtitlesClient` | Subtitle search/download/quota from OpenSubtitles.com (`services/opensubtitles.py`) — isolated: no Jellyfin imports, no app state. **The app's only credential besides the media server and TMDB**; its key reaches the api only (see ADR-0005) |
| `WatchlistService` | Atomic watchlist persistence + state validation |
| `MediaStatusService` | Per-entry status via the domain state machine |
| `DownloadService` | Movie/tv routing + add + fallback orchestration |
| `RecommendationService` | Quality gates, library/duplicate checks, enrichment, add |

All services accept injectable `config`/`http` (constructor DI) and are unit-tested
with fakes — **no test touches the live LAN**.

---

## 10. Config & data

- **`config/settings.py`** — single `Config` singleton from the repo `.env` (+ env overrides). Provides `has_jellyfin()`, `has_tmdb()`, `validate_required()`, etc. **Never returns secrets via `/api/config`.** Exposes the browser-reachable `JELLYFIN_BROWSER_URL` used only for deep-links (falls back to the Tailscale host when unset), and the ONE media-server rule `resolve_media_server()` — jellyfin is the default AND the fallback for a blank/unknown value, so a missing key can never select a retired backend. `validate_required()` deliberately does **not** demand a media-server credential (a fresh install has none until the provisioner writes it; `/api/health` reports that state).
- **`watchlist.json`** — the household acquisition queue; volume-mounted into the container at `/app/watchlist.json`. `WatchlistService` auto-resolves the correct path (container vs sandbox). Deliberately **shared** by every profile (§11).
- **Sessions** — `<media root>/rkm/sessions.json` beside the watchlist, so an api rebuild does not sign
  the household out. Written `0600`, atomically, and holding the **sha256** of each session id, never
  the id and never a Jellyfin token. Corrupt-tolerant: an unreadable file starts empty (everyone signs
  in again; nobody is stuck).
- **`.env`** — canonical at `/workspace/.env`, never committed; see `.env.example`. 

---

## 11. Identity: sessions, profiles, and the one place a credential comes from

Read [`adr/ADR-0006`](adr/ADR-0006-delegated-identity-and-sessions.md) first: this section is the same
model as built. The app owns **sessions**, Jellyfin owns **accounts**.

```
 browser ── rkm_session cookie (HttpOnly, opaque) ─┐
                                                   ▼
                                      api/session.py::require_live_credential     (per app router)
                                                   │  resolves the cookie → SessionContext
                                                   │  asks the media server: is this credential accepted?
                                                   ▼
                                       contextvar  ──►  acting_media_token()  ──►  provider / raw URLs
```

**The two identities in one session.** `user_*` is the account that signed in to the server (always an
administrator); `profile_*` is who is WATCHING. With no profile chosen the profile IS the owner, so an
old session behaves exactly as it did. `acting_media_token()` answers with the profile's token,
`owner_media_token()` with the account's — and the difference is the whole feature: media and watch
state use the first, account administration uses the second.

**The rail.** `session_context_from_request` RECORDS that a request arrived as somebody.
`_published_identity` then refuses (`UnpublishedIdentityError`) if a route resolved a session and
published nothing, instead of falling back to the app's own key — that fallback once wrote a password
to the wrong account while reporting success. Three states, three answers: no request context
(provisioner, scheduler, tools, tests) ⇒ the app's own key, unchanged; a request as nobody ⇒ the same;
a request as SOMEBODY with nothing published ⇒ an error. `owner_media_token` is the ONE deliberate
exception (its fallback *is* the administrator by definition).

**One dependency, per router.** `api/main.py::SESSION_SCOPED = [Depends(require_live_credential)]` —
not a `Depends` on ~40 endpoints, because a site that forgot it would silently serve one person's
library to another. It must be `async def`: a sync dependency runs in a worker thread whose context is
a COPY, so the contextvar would be discarded and every user would share one identity with no error
anywhere.

**Two 401s, two answers.** The dependency asks the media server whether the credential it is about to
act as is still accepted (`credential_is_accepted`, `/Users/<id>?api_key=…`, cached 20 s). A definite
refusal becomes `401` + `X-RKM-Auth-Problem`:

| Marker | What is wrong | What the app does |
|---|---|---|
| `session` (or no marker — an older api) | the cookie is gone or stale | the login view; the sign-out rule is unchanged |
| `profile-token` | the cookie is fine, the credential the PROFILE acts as is refused | keeps the session, drops the fetched rows, sends the person to "Who's watching?" with the server's sentence (`guardDecision({profileStale})`) |

Without this, a refused profile credential was **silent**: media calls came back empty and the app said
"you have no library". `/api/auth/*` is deliberately NOT behind the probe — it is the fix.

**One device per session.** Jellyfin invalidates the previous token of a `(device, user)` pair on every
login, so `new_session_device_id()` mints `rkm-cinema-web-<hex>` per sign-in and a profile switch
re-authenticates on it. A caller that NAMES a device keeps it — that is why the operation tools sign in
on `rkm-tools` (a diagnostic must not rotate the browser's token away).

**What stays shared (deliberate — do not "fix" these).** The watchlist (the household acquisition
queue), subtitle **usage** counts (they rank one download quota), and the server itself.

---

## 12. Frontend (React + TypeScript shell)

`frontend/` is a Vite + React 18 + TypeScript SPA — **the only UI** (the legacy `app.js`/`api.js` and
`frontend/legacy/` were deleted on 2026-09-08). It is **baked into the web image** by
`frontend/Dockerfile` (`npm run build` → `nginx:alpine`), so a UI change needs `.\\rkm-cinema.ps1 apply`
— it is not volume-mounted any more.

- **`src/lib/api/client.ts`** — the ONE HTTP client (`api.*`), `credentials: "same-origin"`, and the
  app's single auth rule: a 401 fires the sign-out handler **once per burst** (`noteUnauthorized`).
  Since Phase 5 that rule reads `X-RKM-Auth-Problem` and fires a *different* handler for
  `profile-token` — signing out there would throw a live session away. Auth-route calls pass
  `{ skipAuthRedirect: true }`: a wrong password is the form's business, and `me()` saying 401 is the
  ordinary signed-out answer.
- **`src/features/auth/`** — `AuthProvider` (session + profile state; purges the React Query cache on
  every identity change, so one person's rows can never flash for the next), `RequireSession` +
  `guardDecision` (**pure, unit-tested**: skeleton / login / picker / app), `LoginView`,
  `AccountMenu` (one menu off the avatar: Household for administrators · Account & password ·
  Switch profile · Settings · Sign out).
- **`/login` and `/profiles` sit OUTSIDE the app shell** for the same reason: they must render when
  nothing else can — including the day enforcement is armed and every other route is refusing.
- ⚠ **This is the whole UI for EVERY client** — the browser and the iOS shell alike (§17). There is no
  second UI to keep in sync, which is the point.
- **Browser checks.** `frontend/harness/*.html` are frames that mount real views over a stubbed api;
  `tools/check_*.py` drive them headless (login flow, picker, nav access, household, password,
  library scan, subtitle panel). Run them against `npx vite --port 5199`.

**One app, two layout shells (ADR-0011, 2026-09-16).** The shell above presents **one of two
arrangements** chosen by the viewport alone: `mobile` below 1024px (**phone AND tablet**) and
`desktop` at 1024px and above — the layout described in this section, untouched. `layouts/LayoutMode.tsx`
holds the switch (`MOBILE_MAX_PX = 1023`, one `useSyncExternalStore` on a shared `MediaQueryList`, and the
one hook `useLayoutMode()`), mounted once in `main.tsx` **above the router and below the query/auth
providers** so crossing the boundary re-renders the routed element without remounting the cache or the
session; the provider publishes `document.documentElement.dataset.layout`, which is how the scoped CSS in
`styles/index.css` reaches the `html`/`body` rules a shell needs but does not own. Inside the mobile mode
the phone/tablet difference is **CSS only** (`--m-grid-cols` 3 → 4 → 5 at 600px and 834px) — there is no
`isTablet` anywhere, and `LayoutMode.test.tsx` reads Tailwind's own resolved `lg` so the JS boundary and
the CSS boundary cannot drift apart. ⚠ **`layouts/mobile/**` may hold layout, markup, styling,
interaction and local UI state — nothing else**: no `fetch`, no second formatter, no second viewport
source, no re-derived rule. `layouts/importRule.ts` + `imports.test.ts` enforce exactly that, because a
mobile view is the easiest place in the app to quietly create the second copy of a rule this whole
architecture exists to prevent. ⚠ `layouts/desktop/index.ts` is a **thin re-export** — no view moved.

---

## 13. Deployment

- ⚠ **Branch strategy (2026-09-16): `dev`-first.** Every new branch is cut from **`dev`**; **`dev` is what
  he deploys and tests**; and **`main` advances only for work that is BOTH unit tested (the repo gates)
  AND accepted by him on the UI** — `dev` first, then `main` fast-forwards to `dev`. ⚠ The invariant that
  keeps that always possible: **`main` only ever moves by fast-forwarding to `dev`** (`git merge-base
  --is-ancestor main dev` — silence means yes). ⚠ `experiment/bundled-docker-stack` and `spike/*` are out
  of the flow. The full rule + the commands live at the top of `PROGRESS.md`.
- Deploy (RKM-HP / Windows): **`.\\rkm-cinema.ps1`** — one script, every verb. `apply` (make the running stack match this folder: re-render `.env`, rebuild + restart `api`/`web`), `deploy` (`apply` + the Jellyfin provisioner), `auth on|off`, `status`, `logs`, `backup`/`restore`, `schedule`, `diagnose`, `reset-admin-password`. `bootstrap.ps1` and `rkm.ps1` are one-line forwarders to it, kept so older notes still work.
- Three containers: `api` (FastAPI modular, holds secrets) + `web` (nginx :8124, the built React shell + `/api` proxy, **including `location = /openapi.json`** so `tools/check_deployed.py` can compare the running api's contract), plus the bundled `jellyfin` media server.
- ⚠ **Editing `.env` alone changes nothing** — a container reads its environment when it STARTS. `apply` (or `auth on|off`) is what applies it.
- **The media server is reached over Tailscale** (HTTPS via the MagicDNS host); deep-links must target the browser-reachable `JELLYFIN_BROWSER_URL` host, not the container-internal `JELLYFIN_URL` (see §8).

---

## 14. Adding a feature (recommended path)

0. ⚠ **Branch from `dev`** (`git checkout dev && git pull --ff-only && git checkout -b feat/<name>`), and
   land it back on **`dev`** first — `main` only receives work that is unit tested *and* tested by him on
   the UI (§13).
1. **Business rule (status/movie-tv)?** → put it in `backend/domain/` (state machine or resolver). Wire service gatherers in `backend/services/`.
2. **External integration?** → add a method on the relevant `backend/services/*` client; never in a route.
3. **Route?** → add a thin handler in `backend/api/routes/`, reuse a service, return a typed Pydantic model.
4. **UI?** → update the React shell (`frontend/src/`).
5. **Test it** → add a mockable pytest under `backend/tests/`; run `cd backend && python -m pytest tests/ -q`.
6. No static dashboard rebuild exists any more — the React shell reads the live `/api` (the old `rebuild_dashboard.py` static generator was removed with the legacy app).
7. Deploy with `.\\rkm-cinema.ps1 apply` (rebuilds `api` + `web` from this folder) and confirm with
   `.\\rkm-cinema.ps1 status` — the "Is the running api the code in THIS folder?" section answers MATCH
   or names the difference. A **new route** also needs a line in
   `tests/test_route_protection.py::ROUTE_LEVELS` (the test fails without one) and, if it touches the
   media server, to ride the session dependency (§11) — never its own token.

---

## 15. Testing

- `backend/tests/` cover: the status resolver + state machine, media-type resolver, Radarr/Sonarr routing + title fallback + ambiguity, duplicate prevention, error handling, trailer validation, the library provider + factory (one backend: Jellyfin), the `LibraryService` collapse and watch-link failure containment, the reconciler, recommendation pipeline, and API endpoints.
- All tests use **injected fakes** — no real LAN, no real API keys required.
- Run: `cd backend && python -m pytest tests/ -q` (all green; count moves with the suite — see `PROGRESS.md` for the current number).

---

## 16. Subtitles (OpenSubtitles) — additive, optional, never blocking

Read `adr/ADR-0005-opensubtitles-integration.md` before changing any of this. The shape:

```
  player picker  ──►  /api/jellyfin/subtitle-search   ──►  OpenSubtitles.com  (search: unmetered)
        │                    │                                  │
        │                    └──►  the item's OWN tracks  (always listed, never altered)
        │
        └── click a result ──►  /api/jellyfin/subtitle-select
                                     │  download (METERED — never retried)
                                     ├─► write  <video stem>.<lang>.srt  beside the media (atomic,
                                     │     UTF-8; reused if a same-language sidecar already exists)
                                     ├─► POST /Items/{id}/Refresh        (the ITEM — never a scan)
                                     └─► store the CHOICE (an identity, not an index) + count the use
                                                   │
  playback-info.preferred_subtitle  ◄──────────────┘   (ONE additive field: the player applies it on load)
```

The three rules that are easy to get wrong:

1. **Preferences store an IDENTITY, never a stream index.** Jellyfin's indices are
   positional and our own download shifts them; `resolveActiveSubtitle()` resolves the
   identity to the current index at load time and applies NOTHING when it no longer
   matches — never a different subtitle.
2. **The tick belongs on the row the user CLICKED.** A delivered subtitle arrives as a
   local track the server names generically ("English - SUBRIP - External"), so ticking the
   resolved index ticks a row the user never chose. `activeSubtitleRowKey()` (frontend,
   unit-tested) marks exactly one row: the chosen result, else the local track applying.
3. **A subtitle failure degrades the feature, never the app.** Every vendor failure is
   reported as a `warning` on a 200 listing (never a 500), the item's own subtitles are
   always returned, and only an action the user explicitly asked for (select) can fail the
   request — with an honest status: 503 not configured, 502 credentials/transport, 429
   quota/rate limit, 400 bad format. `tools/check_subtitle_panel.py --fail-search` proves
   the panel still lists and can still apply the local tracks with the vendor dead.

State: `<media root>/rkm/subtitles.json` — `prefs` (per item: provider, `subtitle_id`,
language, display title, `disabled`) and `usage` (per subtitle: count, last used). Atomic
writes, corrupt-tolerant, JSON by design. The quota is read from the API at runtime — never
hardcoded — and the UI shows a number only when the API has actually reported one.

---

## 17. The phone/tablet app, and how the three parts are integrated

**Read this before touching `apple/`, or before changing anything the app loads.** The one-sentence
version: **the iOS app is a shell around the LIVE web UI, and the only code in it is the work a web page
physically cannot do.**

### 17.1 The shape — and why it is not a second client

```
apple/
├── Shared/Sources/RKMServerKit/   the ONE thing both apps need: a typed server address
│                                  (parse · normalise · persist) + logging (LOGGING.md)
├── ios/RKMCinema/  (29 Swift files)  WKWebView shell — App/ · Shell/ · Offline/ · Server/ · Debug/
└── tvos/                            ⚠ EMPTY TODAY (0 Swift files). Planned, not built.
```

The iOS app has **no bundled UI and no API client of its own**. It:

1. takes a server address a human typed (normalised; `https://` assumed when no scheme is given);
2. loads that address in a `WKWebView` — **the same React app nginx serves**;
3. injects two scripts at document-start (instrumentation, and the `window.__rkmOffline` bridge global);
4. answers bridge commands from the page, and adds the native-only capabilities in §17.2.

**Consequences, both of them load-bearing:**

- ✅ **Every `apply` reaches the phone with no app rebuild and no store release.** A UI change is a web
  change, full stop. (This is why B4 — the whole offline UI — shipped as a web phase.)
- ⚠ **The app can be OLDER than the page.** A page deployed today may be viewed by a build from last
  month. That is exactly why the bridge is **versioned and refuses by version** (ADR-0009 D6), and why
  every page-side feature must degrade rather than assume: **no bridge → no offline affordance at all**
  (`frontend/src/features/offline/bridge.ts::bridgeAvailable()`).
- ⚠ **tvOS cannot use this seam at all** — tvOS has no WebKit. `tvos/` will be a *real* client: its own
  SwiftUI views plus an API client generated from `docs/api/openapi.v1.json`, and it additionally needs
  the bearer-token work (no browser session exists there). Nothing is built yet; do not assume it.

### 17.2 What the shell adds — the capability table

| Capability | Where | Why the web page cannot do it |
|---|---|---|
| **Background downloads** | `Offline/OfflineDownloads.swift` + `App/AppDelegate.swift` | a page-side download stops when the app is backgrounded, and WebKit's Cache API is capped (~50 MiB per partition) and evictable — one film exceeds the whole budget (plan §4.1) |
| **The app's own filesystem** | `Offline/OfflineStore.swift` → `Application Support/Offline/` | the page's origin has no access to the app's container. `Caches/` is purgeable, so it is not used; the directory is backup-excluded so multi-GB films stay out of iCloud |
| **A loopback HTTP server** | `Offline/OfflineServer.swift` (`NWListener`, `127.0.0.1`, ephemeral port) | a `file://` URL is cross-origin to the page's origin, and a custom scheme handler was **measured out for media** (B0/E1: `mediaError=code=4` with bytes served). Loopback HTTP also gives real `Range` seeking for free |
| **The bridge global** | `Shell/WebShellView.swift` + `Offline/OfflineBridge.swift` | a page cannot call Swift. `WKScriptMessageHandlerWithReply` makes `postMessage` return a Promise — ⚠ the plain `add(_:name:)` form must NOT be used, it is a promise that never settles |
| **Cookie mirroring for native fetches** | `Offline/CookieMirror.swift` | a native `URLSession` has no jar of the page's. ⚠ A hard prerequisite since `RKM_AUTH_REQUIRED=true`: a background session's own cookie handling loses cookies on redirects (Apple r.16,852,027), so the cookie is sent as an explicit `Cookie:` header |
| **The offline UI's trigger** | `Shell/WebBridge.swift` (a new `offline` report case) | the native→page direction needs a witness outside the native code: the page reports what it received back through the EXISTING instrumentation channel (ADR-0009 D9) |

### 17.3 Seam 2, in short — the bridge contract

```
page → native   { v:1, c:"list"|"download"|"cancel"|"delete"|"play"|"ping", itemId?, title?, mode? }
                  → { v:1, ok:true,  result:{ items[], bytes, count, play?, accepted? } }
                  → { v:1, ok:false, error:{ code, message } }
native → page   window.__rkmOffline.emit({ v:1, e:"state"|"progress"|"ready"|"removed", … })
page            window.__rkmOffline.request({c:…}) → a Promise (`.list()/.play()/.download()/…`)
```

Four rules that are easy to get wrong, all enforced in code that is *executed* on Linux
(`OfflineBridgeContract.swift`, 445+ checks):

1. **`v` is required and exact** — a missing version and a *newer* page are both refused with a sentence
   ("update the app"), never guessed at;
2. **every refusal is a REPLY**, with a stable `code` the page switches on and a `message` a human can
   act on. An unanswered `postMessage` is a button that does nothing and an error nowhere;
3. **the event stream is throttled by a PURE planner** — state changes are never throttled, progress is
   whole-percent steps, a rewind is a state change that resets the throttle, an unknown total is never a
   percentage;
4. ⚠ **the loopback URL is a capability**: never in the manifest, never in a log, handed only to the
   live page. The port changes every launch, so a cached URL is a stale URL.

### 17.4 The offline path end to end — the one flow that crosses all three parts

**(a) A download — the page asks two owners, then the app does the work.**

```
 page                     native (iOS)                         api                    Jellyfin
  │  GET /api/offline/bundle/{id} ─────────────────────────────►│  plan(): mode · estimate ·
  │  ◄── rendition · "about 2.1 GB" · needs_transcode ──────────│  container · subtitles   [no packaging]
  │  list  ───────────────►│  what is ALREADY on this device     │
  │  ◄── items[] (state · bytes · totalBytes · url) ────────────│
  │  download{itemId,title,mode} ───►│  prepare ─────────────────►│  package (remux/transcode)
  │                        │  status ──────────────────────────►│  into /shared/offline  ──► ffmpeg
  │                        │  (⚠ "packaging": NOTHING on the device yet)
  │  ◄── state/progress events ─────│  file (Range) ◄───────────│  borrowed = the library file
  │                        │  verify size + ETag → `ready` → mint a loopback handle
  │  ◄── ready{url} ────────────────│
```

⚠ **Two owners, two answers**: the SERVER says what a download would cost; the APP says what is already
on the phone. A page that conflated them would offer to download a film it holds, or claim a film is on
the device when it is not. ⚠ And the **packaging** phase is why a row can sit at zero bytes for minutes:
the number is honest ("nothing has arrived"), the *label* was not — it now says
**"Preparing on the server…"**.

**(b) Playing it with the network off.**

```
 page                                native                        network
  │  play{itemId} ───────────────────►│  start the loopback server (if not up)
  │  ◄── play{url: http://127.0.0.1:<port>/offline/<handle>.mp4} ──│
  │  <video src=loopback>  ⚠ and NO /api/jellyfin/playback-info call at all
  │  ◄══ bytes over loopback, real Range/206 ══│                   │   ← nothing here
```

⚠ The player asks the **device first** and then does not ask the server: `playback-info` is pointless
online and impossible offline. The resume point comes from the device's OWN queue (the server's position
is the fact that stopped updating), and the engine key stays empty until the device has answered — so no
stream is started for a film that turns out to be local.

**(c) A position reached with no server — the queue that makes it feel finished.**

```
 offline play ──► progress reports ──► QUEUE on the device (localStorage, stamped with owner+server origin)
                                          │  replayed when the server is reachable
                                          ▼
                                    POST /api/jellyfin/progress ──► Jellyfin user-data write ──► Continue Watching
```

⚠ **The queue keeps the FURTHEST position per title, never the latest** (a reopened film reports `start`
at the resume point, and last-write-wins would rewind a viewer by a whole act), a successful **live** post
supersedes everything at or below it, and a replay is dropped by its own timestamp so a newer position
survives the race. It is identity-bearing state: another profile's queue — or another server's — is
dropped on read. ⚠ The page is the owner here, not the app: the position is the PLAYER's fact, and the
app never sees it.

### 17.5 What a change costs — decide with this table

| You changed… | Deploy | Round needed |
|---|---|---|
| `frontend/` (UI, offline page, player) | `docker compose -p rkm-bundled up -d --build web` | none — visible on the phone immediately |
| `backend/` (routes, services) | `… up -d --build api` (add `web` if both) | none |
| `apple/ios/` (native) | nothing to deploy | ⚠ a Mac build + the app's own gate (`mac-round.sh`, then the log-reading checker) |
| **the BRIDGE contract** (seam 2) | both of the above | ✅ **both sides** — and additive-within-`v1` only; a breaking change is a `v2` plus a page+app pair (ADR-0009 D6) |
| `.env` / `render_config.py` / compose / provisioner | the full `bootstrap.ps1` | ⚠ full bootstrap re-provisions and can cancel a library scan |

### 17.6 ⚠ Integration traps, each of which has already cost a round

- ⚠ **ATS is `NSAllowsArbitraryLoads` ONLY.** Adding `NSAllowsLocalNetworking` (or a `…InWebContent` /
  `…ForMedia` variant) makes iOS **ignore** it on iOS 10+, which breaks plain `http://` to the tailnet
  **and** the loopback server outright. Read `Config/Info.plist`'s comment before touching it.
- ⚠ **There is no service worker** (E2: `navigator.serviceWorker` is absent on this WebView, on a secure
  origin as well as the app's). The offline-SHELL story is therefore the HTTP cache headers in
  `nginx/default.conf` + the persisted query cache (A1) — not a SW.
- ⚠ **A web view with a socket is not a page.** Between `attach` and the first `didFinish` there is no
  document, and `evaluateJavaScript` against it THROWS. The bridge tracks `pageIsReady`; skipping events
  there loses nothing because a page load re-announces every title (ADR-0009 D7a).
- ⚠ **A 204 is a SUCCESS WITH NO BODY**, and a browser gives it a null body whatever the server writes.
  `POST /api/jellyfin/progress` answers 204 — so any client that parses every success as JSON turns an
  accepted report into a failure. Found on a phone, not by a test (ADR-0010 D9a).
- ⚠ **A silent identity fallback is worse than an error**: `_user_id()` falls back to the FIRST account in
  the store, so a write made without a published identity acts as somebody else (ADR-0006, §11).
- ⚠ **`LogRedactor` rewrites the words the security grep searches for, inside ANY message** — so never
  name a logged thing with one of them (`LOGGING.md` §9).
- ⚠ **A fake more permissive than the real route is a gate that cannot fail.** The offline gate's stub
  answered `200 {ok:true}` for a route that answers 204, and passed six scenarios on a live bug.

---

## 18. Design improvements this architecture suggests, ranked

Ordered by (value × certainty) ÷ cost. **Nothing here is required for the app to work today**; each item
is an argument about what the CURRENT design makes easy to get wrong.

| # | Improvement | Why (and what it would have caught) | Cost | Verdict |
|---|---|---|---|---|
| **1** | **Contract-shape tests shared by the api and the frontend stubs.** One table of `(method, route, status, body)` that the backend asserts AND the harness stubs are generated from | ⚠ The 204 bug: the api was right, the client was wrong, and every gate was green because each side was tested against its own assumption. This is the highest-value change on the list — it removes a whole class of "works everywhere but in the app" | 1–2 evenings | **Do first** |
| **2** | **A machine-readable bridge schema** (one JSON file that both `OfflineBridgeContract.swift`'s Linux checks and the TS `lib.ts` parse) | The two halves of seam 2 are written twice, in two languages, and drift is silent until a Mac round. A single schema turns "the page reads a field the app stopped sending" into a red test | ~1 evening | With B5 |
| **3** | **`preparing` as a real state in the native `OfflineState`** | The page currently infers "the server is still packaging" from `bytes == 0 && totalBytes == 0` and says "Preparing on the server…". That is honest but coarse: a stalled transfer with no bytes yet reads the same. A real state (and the server's own packaging progress in it) makes the row exact | small, but needs a Mac round | With B5 |
| **4** | **Persist the last profile id** so a COLD offline launch can stamp the queue | Today a launch with no network runs the session with no owner, so positions reached then are memory-only and lost on a reload. The query cache already writes an owner to disk — the same fact, for the same reason | small | With B5 |
| **5** | **Bearer/device tokens instead of cookie mirroring** (`APPLE_CLIENTS_PLAN` Phase 2) | Removes the session-expiry edge on native fetches and deletes `CookieMirror` + the explicit `Cookie:` header. ⚠ It is also a PREREQUISITE for tvOS, which has no browser session to mirror | medium (backend + native) | Before tvOS |
| **6** | **Decide what "my downloads" means on a SHARED device** | The file is the household's, not the profile's (ADR-0007 D6): on the family iPad, one person's downloads are visible to the next. Today the row shows the title only, so it is not a leak of *content* — but it is a product decision that is currently implicit | product call + medium work | His call |
| **7** | **One shared `tools/harness.py`** (frame loading · dev-server freshness · **a fresh page per scenario**) | Every browser tool re-implements this, and each re-implementation has had the same two failures: a stale module served by a non-watching dev server, and a frame that never mounts because a previous scenario left a `<video>` playing. Both cost real time today | half an evening | **Do first** |
| **8** | **Generate `ROUTE_LEVELS`** from the router declarations (a `level=` argument on each `@router.get`) | The inventory is hand-maintained, and it exists (correctly) to make a missing protection decision a test failure. Generating it removes the one way it can be wrong | small | Next api phase |
| **9** | **An offline SHELL for cold launch** (a `WKURLSchemeHandler` serving the DOCUMENT and assets from the app's container) | E1 measured custom schemes out for **media** — but a document is not media. Today, a cold launch with no network depends on WebKit's HTTP cache and may not paint at all, which is the last gap in "it works offline" | medium-high, needs a Mac round | Only if he wants cold-launch offline |
| **10** | **Split `PROGRESS.md`** into a short current-state page + a history archive | It is ~5,100 lines and the file the next session reads first. The rationale already lives in ADRs; the status file can be a page, not a book | small | Housekeeping |

**⚠ What I would NOT change:** the single React UI, the "one implementation per business rule" layering,
the api as the only secret-holder, the pure-core/executable-rules pattern for native code, or the ADR +
plan + PROGRESS convention. Those are why a phase like B4 could be verified on Linux and shipped to a
phone the same evening — and why the ONE bug that got through (the 204) was found by a person in minutes
rather than by a code review in weeks.

⚠ `ARCHITECTURE_AUDIT.md` is a PHASE-1 audit of the LEGACY app — read it as history (several of its
"gaps" have shipped); this §18 is about the architecture as it stands today.

**In one line:** do **1** and **7** next (both are test-infrastructure, both pay back immediately), take
**2 · 3 · 4** with B5, put **5** on the critical path to tvOS, and treat **6** and **9** as your product
decisions rather than engineering ones.
